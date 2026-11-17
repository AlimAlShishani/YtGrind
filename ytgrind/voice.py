"""Stimme per KI (Text-to-Speech).

Anbieter:
  elevenlabs  bezahlter Dienst; API-Schluessel in der Umgebungsvariable ELEVENLABS_API_KEY
  mock        stille Platzhalter-Audiodatei (zum Testen von Schnitt/Untertiteln ohne Kosten)

Jede Szene wird nur EINMAL bezahlt: Das Ergebnis wird nach Text + Stimme + Einstellungen gecacht.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

from .common import ToolError, run_ffmpeg

ELEVEN_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}?output_format=mp3_44100_128"
DEFAULT_MODEL = "eleven_multilingual_v2"
KEY_ENV = "ELEVENLABS_API_KEY"


def cache_key(text: str, cfg: dict, provider: str) -> str:
    payload = json.dumps({"p": provider, "t": text, "v": cfg.get("voice_id"), "m": cfg.get("model_id", DEFAULT_MODEL),
                          "s": cfg.get("stability"), "sim": cfg.get("similarity_boost"), "st": cfg.get("style")},
                         sort_keys=True, ensure_ascii=False)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]


def build_elevenlabs_request(text: str, cfg: dict, api_key: str) -> urllib.request.Request:
    voice_id = cfg.get("voice_id")
    if not voice_id:
        raise ToolError("In story.json fehlt voice.voice_id (Voice-ID aus deinem ElevenLabs-Konto).")
    settings = {"stability": cfg.get("stability", 0.5), "similarity_boost": cfg.get("similarity_boost", 0.75)}
    if "style" in cfg:
        settings["style"] = cfg["style"]
    body = json.dumps({"text": text, "model_id": cfg.get("model_id", DEFAULT_MODEL), "voice_settings": settings}).encode("utf-8")
    return urllib.request.Request(
        ELEVEN_URL.format(voice_id=voice_id),
        data=body,
        method="POST",
        headers={"xi-api-key": api_key, "Content-Type": "application/json", "Accept": "audio/mpeg"},
    )


def _elevenlabs(text: str, out: Path, cfg: dict) -> None:
    api_key = os.environ.get(KEY_ENV, "").strip()
    if not api_key:
        raise ToolError(
            f"Umgebungsvariable {KEY_ENV} fehlt. PowerShell (einmalig, danach neues Terminal oeffnen):\n"
            f'    setx {KEY_ENV} "dein-schluessel"\n'
            "Den Schluessel nirgends einfuegen/teilen (auch nicht im Chat)."
        )
    req = build_elevenlabs_request(text, cfg, api_key)
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                out.write_bytes(resp.read())
            return
        except urllib.error.HTTPError as err:
            detail = err.read().decode("utf-8", "replace")[:300]
            if err.code == 429 and attempt < 3:  # Rate-Limit: kurz warten, nochmal
                time.sleep(2 * (attempt + 1))
                continue
            hint = " (Schluessel falsch/abgelaufen?)" if err.code == 401 else ""
            raise ToolError(f"ElevenLabs HTTP {err.code}{hint}: {detail}") from err
        except urllib.error.URLError as err:
            raise ToolError(f"ElevenLabs nicht erreichbar: {err.reason}") from err


def _mock(text: str, out: Path, cfg: dict) -> None:
    words = max(1, len(text.split()))
    run_ffmpeg(["-f", "lavfi", "-i", f"anullsrc=r=44100:cl=mono", "-t", f"{max(1.0, words * 0.38):.2f}",
                "-c:a", "libmp3lame", "-b:a", "64k", str(out)], quiet=True)


PROVIDERS = {"elevenlabs": _elevenlabs, "mock": _mock}


def synthesize(text: str, cache_dir: Path, cfg: dict, provider: str) -> tuple[Path, bool]:
    """Liefert (mp3-Pfad, aus_cache)."""
    if provider not in PROVIDERS:
        raise ToolError(f"Unbekannter Stimm-Anbieter {provider!r} (erlaubt: {', '.join(PROVIDERS)})")
    cache_dir.mkdir(parents=True, exist_ok=True)
    out = cache_dir / f"{cache_key(text, cfg, provider)}.mp3"
    if out.exists() and out.stat().st_size > 0:
        return out, True
    tmp = out.with_name(out.stem + ".part.mp3")  # echte Endung, damit ffmpeg das Format erkennt
    PROVIDERS[provider](text, tmp, cfg)
    tmp.replace(out)
    return out, False
