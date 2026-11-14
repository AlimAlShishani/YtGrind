"""Neues Video-Projekt mit fester Ordnerstruktur + Vorlagen anlegen."""

from __future__ import annotations

import shutil
from datetime import date
from pathlib import Path

from .common import ToolError, slugify

SUBDIRS = [
    "01_script",
    "02_raw/gameplay",
    "02_raw/voice",
    "03_resolve",
    "04_export",
    "05_shorts",
]

TEMPLATES = Path(__file__).resolve().parent.parent / "templates"


def create(root: Path, title: str, publish_date: date | None = None) -> Path:
    publish_date = publish_date or date.today()
    folder = root / f"{publish_date.isoformat()}_{slugify(title)}"
    if folder.exists():
        raise ToolError(f"{folder} existiert schon.")
    for sub in SUBDIRS:
        (folder / sub).mkdir(parents=True)
    script = TEMPLATES / "ranking_script_template.md"
    if script.exists():
        text = script.read_text(encoding="utf-8").replace("{{TITLE}}", title)
        (folder / "01_script" / "script.md").write_text(text, encoding="utf-8")
    shorts = TEMPLATES / "shorts.example.txt"
    if shorts.exists():
        shutil.copy(shorts, folder / "05_shorts" / "shorts.txt")
    return folder
