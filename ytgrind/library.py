"""Meme-/Soundeffekt-Bibliothek: feste Ordnerstruktur + Index (index.csv) mit Tags.

* Der Ordner ist die Hauptkategorie (z. B. memes/shock) – in DaVinci Resolve einfach den
  ganzen Ordner in den Media Pool ziehen, dann entstehen die Bins automatisch.
* Feine Tags (z. B. "minecraft,creeper,jumpscare") stehen in index.csv. Die Datei ist mit Excel
  bearbeitbar (Trennzeichen ';', passend fuer deutsche Excel-Einstellungen).
* Pro Datei werden Quelle + Lizenz notiert, damit du bei Copyright-Fragen nachweisen kannst, woher es kommt.
"""

from __future__ import annotations

import csv
import fnmatch
from datetime import date
from pathlib import Path

from .common import ToolError, probe

LAYOUT: dict[str, list[str]] = {
    "memes": ["reaction", "shock", "win", "fail", "cringe", "hype", "sad", "sus"],
    "sfx": ["impact", "whoosh", "win", "fail", "ui", "crowd", "ambience"],
    "overlays": ["stickers", "text-pop", "tier-graphics", "transitions"],
}

MEDIA_EXTS = {
    ".mp4", ".mov", ".webm", ".mkv", ".gif",  # Video
    ".png", ".jpg", ".jpeg", ".webp",  # Bild
    ".wav", ".mp3", ".ogg", ".m4a", ".flac",  # Audio
}
AUDIO_ONLY = {".wav", ".mp3", ".ogg", ".m4a", ".flac"}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}

FIELDS = ["file", "kind", "category", "tags", "duration", "has_audio", "source", "license", "added", "notes"]
DELIM = ";"

NAMING_README = """\
Bibliothek – Regeln
===================
Dateinamen:  kleinbuchstaben-mit-bindestrich.ext   z. B.  shocked-pikachu.mp4, bruh-sound.wav
Ordner:      memes/<emotion>   sfx/<typ>   overlays/<typ>
Meme-Clips:  maximal 3 Sekunden, vorher zuschneiden (ffmpeg / Resolve).
Neue Dateien:  python -m ytgrind lib scan      -> traegt sie in index.csv ein
Taggen:        python -m ytgrind lib tag shocked-pikachu +shock +pokemon
Suchen:        python -m ytgrind lib find shock --max-dur 2
Pruefen:       python -m ytgrind lib check     -> fehlende Tags / Quelle / Lizenz, zu lange Clips
Pro Datei in index.csv eintragen: source (URL/Herkunft) und license (z. B. 'pixabay', 'yt-audio-library',
'self-made'). Keine Musik, keine Film-/Serien-Clips mit Musik.
"""


def init(root: Path) -> list[Path]:
    created = []
    for kind, cats in LAYOUT.items():
        for cat in cats:
            d = root / kind / cat
            d.mkdir(parents=True, exist_ok=True)
            created.append(d)
    (root / "README.txt").write_text(NAMING_README, encoding="utf-8")
    idx = root / "index.csv"
    if not idx.exists():
        _write_index(idx, [])
    return created


# --------------------------------------------------------------------------- index


def _read_index(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return [{k: (row.get(k) or "") for k in FIELDS} for row in csv.DictReader(fh, delimiter=DELIM)]


def _write_index(path: Path, rows: list[dict]) -> None:
    rows = sorted(rows, key=lambda r: r["file"])
    with path.open("w", encoding="utf-8-sig", newline="") as fh:  # BOM: Excel zeigt Umlaute richtig an
        w = csv.DictWriter(fh, fieldnames=FIELDS, delimiter=DELIM)
        w.writeheader()
        w.writerows(rows)


def _split_tags(text: str) -> list[str]:
    return [t.strip().lower() for t in text.replace(";", ",").split(",") if t.strip()]


def _require_root(root: Path) -> Path:
    if not (root / "index.csv").exists():
        raise ToolError(f"Keine Bibliothek in {root}. Zuerst: python -m ytgrind lib init")
    return root / "index.csv"


def scan(root: Path) -> dict:
    idx = _require_root(root)
    rows = {r["file"]: r for r in _read_index(idx)}
    added, missing = [], []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in MEDIA_EXTS:
            continue
        rel = path.relative_to(root).as_posix()
        if rel in rows:
            continue
        parts = rel.split("/")
        info = None
        try:
            if path.suffix.lower() not in IMAGE_EXTS:
                info = probe(path)
        except ToolError:
            pass
        rows[rel] = {
            "file": rel,
            "kind": parts[0] if len(parts) > 1 else "",
            "category": parts[1] if len(parts) > 2 else "",
            "tags": parts[1] if len(parts) > 2 else "",
            "duration": f"{info.duration:.2f}" if info else "",
            "has_audio": ("yes" if info.has_audio else "no") if info else "",
            "source": "",
            "license": "",
            "added": date.today().isoformat(),
            "notes": "",
        }
        added.append(rel)
    for rel in rows:
        if not (root / rel).exists():
            missing.append(rel)
    _write_index(idx, list(rows.values()))
    return {"added": added, "missing": missing, "total": len(rows)}


def tag(root: Path, pattern: str, changes: list[str]) -> list[str]:
    """changes: '+tag' hinzufuegen, '-tag' entfernen. pattern: Teilstring oder Glob auf den Dateipfad."""
    idx = _require_root(root)
    rows = _read_index(idx)
    hits = [r for r in rows if _matches(r["file"], pattern)]
    if not hits:
        raise ToolError(f"Keine Datei passt auf {pattern!r}.")
    for r in hits:
        tags = _split_tags(r["tags"])
        for ch in changes:
            name = ch.lstrip("+-").lower()
            if ch.startswith("-"):
                tags = [t for t in tags if t != name]
            elif name not in tags:
                tags.append(name)
        r["tags"] = ",".join(tags)
    _write_index(idx, rows)
    return [r["file"] for r in hits]


def _matches(path: str, pattern: str) -> bool:
    p = pattern.lower()
    return p in path.lower() or fnmatch.fnmatch(path.lower(), p)


def find(root: Path, tags: list[str], *, any_tag: bool = False, kind: str | None = None,
         max_dur: float | None = None) -> list[dict]:
    rows = _read_index(_require_root(root))
    wanted = [t.lower() for t in tags]
    out = []
    for r in rows:
        have = set(_split_tags(r["tags"])) | {r["category"].lower(), Path(r["file"]).stem.lower()}
        if wanted:
            ok = any(w in have for w in wanted) if any_tag else all(w in have for w in wanted)
            if not ok:
                continue
        if kind and r["kind"] != kind:
            continue
        if max_dur is not None and r["duration"] and float(r["duration"]) > max_dur:
            continue
        out.append(r)
    return out


def check(root: Path, *, max_meme_seconds: float = 3.0) -> list[str]:
    rows = _read_index(_require_root(root))
    problems: list[str] = []
    for r in rows:
        f = r["file"]
        if not (root / f).exists():
            problems.append(f"FEHLT       {f}")
            continue
        if r["kind"] == "memes" and r["duration"]:
            try:
                if float(r["duration"]) > max_meme_seconds:
                    problems.append(f"ZU LANG     {f} ({r['duration']} s, Limit {max_meme_seconds:g} s)")
            except ValueError:
                pass
        if not r["license"] or not r["source"]:
            problems.append(f"QUELLE?     {f} (source/license leer)")
        if len(_split_tags(r["tags"])) < 2:
            problems.append(f"WENIG TAGS  {f}")
    return problems
