"""Automatische Untertitel im Shorts-Stil (grosse Woerter, aktuelles Wort gelb).

Transkription: faster-whisper (CPU, int8) – laeuft auch auf PCs mit AMD-Grafikkarte.
Das Ergebnis wird als <video>.words.json neben dem Video gecacht, damit jeder Short
nur noch die passenden Woerter ausschneidet statt neu zu transkribieren.
"""

from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path

from .common import ToolError, run_ffmpeg

HIGHLIGHT = "&H00FFFF&"  # ASS: BGR -> Gelb
BASE = "&HFFFFFF&"  # Weiss

Word = dict  # {"w": str, "s": float, "e": float}


# --------------------------------------------------------------------------- transkription


def words_cache_path(video: Path) -> Path:
    return video.with_suffix(video.suffix + ".words.json")


def load_cached_words(video: Path, model: str) -> list[Word] | None:
    cache = words_cache_path(video)
    if not cache.exists():
        return None
    try:
        data = json.loads(cache.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    st = video.stat()
    if data.get("size") != st.st_size or data.get("model") != model:
        return None  # Video oder Modell hat sich geaendert
    return data["words"]


def transcribe(video: Path, *, model: str = "small.en", language: str = "en", track: int = 0,
               use_cache: bool = True) -> list[Word]:
    if use_cache and (cached := load_cached_words(video, model)) is not None:
        print(f"Untertitel-Cache gefunden: {words_cache_path(video).name}")
        return cached
    try:
        from faster_whisper import WhisperModel
    except ImportError as err:
        raise ToolError("faster-whisper fehlt. Installieren: pip install -r requirements.txt") from err

    with tempfile.TemporaryDirectory() as tmp:
        wav = Path(tmp) / "voice.wav"
        # Whisper will 16 kHz mono; eine bestimmte Spur waehlen, damit Game-Sound nicht stoert
        run_ffmpeg(["-i", str(video), "-map", f"0:a:{track}", "-ac", "1", "-ar", "16000", str(wav)], quiet=True)
        print(f"Transkribiere mit Whisper '{model}' (CPU) – das dauert bei langen Videos einige Minuten ...")
        wm = WhisperModel(model, device="cpu", compute_type="int8")
        segments, _ = wm.transcribe(str(wav), language=language, word_timestamps=True, vad_filter=True, beam_size=5)
        words: list[Word] = []
        for seg in segments:
            for w in seg.words or []:
                text = w.word.strip()
                if text:
                    words.append({"w": text, "s": round(w.start, 3), "e": round(w.end, 3)})

    words_cache_path(video).write_text(
        json.dumps({"size": video.stat().st_size, "model": model, "words": words}, ensure_ascii=False),
        encoding="utf-8",
    )
    return words


# --------------------------------------------------------------------------- ASS


def slice_words(words: list[Word], start: float, end: float) -> list[Word]:
    """Woerter eines Zeitfensters, Zeiten auf 0 verschoben."""
    out = []
    for w in words:
        mid = (w["s"] + w["e"]) / 2
        if start <= mid < end:
            out.append({"w": w["w"], "s": max(0.0, w["s"] - start), "e": min(end - start, w["e"] - start)})
    return out


def _clean(text: str, uppercase: bool) -> str:
    text = re.sub(r"[{}\\]", "", text)
    text = re.sub(r"[,.;:\"“”]+$", "", text)  # Satzzeichen am Ende weg, ? und ! bleiben
    return text.upper() if uppercase else text


def chunk_words(words: list[Word], per_chunk: int = 3, max_chars: int = 20, max_gap: float = 0.6) -> list[list[Word]]:
    chunks: list[list[Word]] = []
    cur: list[Word] = []
    for w in words:
        if cur:
            too_long = sum(len(x["w"]) + 1 for x in cur) + len(w["w"]) > max_chars
            gap = w["s"] - cur[-1]["e"] > max_gap
            ended = re.search(r"[.?!]$", cur[-1]["w"]) is not None
            if len(cur) >= per_chunk or too_long or gap or ended:
                chunks.append(cur)
                cur = []
        cur.append(w)
    if cur:
        chunks.append(cur)
    return chunks


def _ts(t: float) -> str:
    cs = int(round(t * 100))
    h, rest = divmod(cs, 360000)
    m, rest = divmod(rest, 6000)
    s, c = divmod(rest, 100)
    return f"{h}:{m:02d}:{s:02d}.{c:02d}"


def build_ass(
    words: list[Word],
    *,
    hook_text: str | None = None,
    hook_seconds: float = 2.5,
    width: int = 1080,
    height: int = 1920,
    font: str = "Arial Black",
    size: int = 88,
    per_chunk: int = 3,
    uppercase: bool = True,
    margin_v: int = 560,
) -> str:
    """ASS-Datei: Untertitel unten-mittig (ueber der Plattform-UI), optional Hook-Text oben."""
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font},{size},&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,0,0,0,0,100,100,0,0,1,9,3,2,60,60,{margin_v},1
Style: Hook,{font},{int(size * 0.8)},&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,3,14,0,8,70,70,260,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events: list[str] = []
    if hook_text:
        txt = re.sub(r"[{}\\]", "", hook_text).replace("\n", "\\N")
        events.append(f"Dialogue: 1,{_ts(0)},{_ts(hook_seconds)},Hook,,0,0,0,,{txt.upper() if uppercase else txt}")

    chunks = chunk_words(words, per_chunk=per_chunk)
    for ci, chunk in enumerate(chunks):
        texts = [_clean(w["w"], uppercase) for w in chunk]
        next_start = chunks[ci + 1][0]["s"] if ci + 1 < len(chunks) else None
        for wi, w in enumerate(chunk):
            start = w["s"]
            if wi + 1 < len(chunk):
                end = chunk[wi + 1]["s"]
            else:
                end = max(w["e"], start + 0.15)
                if next_start is not None:
                    end = min(end, next_start)
            if end <= start:
                continue
            parts = [f"{{\\c{HIGHLIGHT if i == wi else BASE}}}{t}" for i, t in enumerate(texts)]
            events.append(f"Dialogue: 0,{_ts(start)},{_ts(end)},Default,,0,0,0,,{' '.join(parts)}")
    return head + "\n".join(events) + "\n"
