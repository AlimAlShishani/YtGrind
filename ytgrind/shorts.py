"""Lange Videos -> vertikale Shorts (1080x1920) per Zeitliste.

Zeitliste (shorts.txt), eine Zeile pro Short:

    # Start - Ende | Titel (wird als Hook-Text oben eingeblendet) | Optionen
    00:01:23 - 00:01:58 | The Warden is overrated | mode=crop x=0.35
    00:04:10 - 00:04:52 | Creepers ruined my build

Optionen: mode=blur|crop   x=0..1 (Bildausschnitt links..rechts, nur crop)   subs=on|off   hook=on|off
"""

from __future__ import annotations

import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from .common import (ToolError, encoder_label, fmt_time, parse_timecode, probe, run_ffmpeg, slugify,
                     video_encode_args)
from . import subtitles

W, H = 1080, 1920

_RANGE = re.compile(r"^\s*([\d:.,]+)\s*(?:-|–|—|->|to)\s*([\d:.,]+)\s*$")


@dataclass
class ShortSpec:
    start: float
    end: float
    title: str = ""
    options: dict[str, str] = field(default_factory=dict)

    @property
    def duration(self) -> float:
        return self.end - self.start


def parse_spec_file(path: Path) -> list[ShortSpec]:
    specs: list[ShortSpec] = []
    for no, raw in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split("|")]
        m = _RANGE.match(parts[0])
        if not m:
            raise ToolError(f"{path.name}, Zeile {no}: Zeitbereich nicht lesbar: {parts[0]!r} (Beispiel: 01:23 - 01:58)")
        try:
            start, end = parse_timecode(m.group(1)), parse_timecode(m.group(2))
        except ValueError as err:
            raise ToolError(f"{path.name}, Zeile {no}: {err}") from err
        if end <= start:
            raise ToolError(f"{path.name}, Zeile {no}: Ende liegt vor dem Start.")
        opts: dict[str, str] = {}
        if len(parts) > 2:
            for tok in parts[2].split():
                if "=" not in tok:
                    raise ToolError(f"{path.name}, Zeile {no}: Option {tok!r} muss key=value sein.")
                k, v = tok.split("=", 1)
                opts[k.lower()] = v.lower()
        specs.append(ShortSpec(start, end, parts[1] if len(parts) > 1 else "", opts))
    if not specs:
        raise ToolError(f"{path.name} enthaelt keine Shorts.")
    return specs


def video_filter(mode: str, focus_x: float) -> str:
    """Filtergraph von [0:v] nach [v] (1080x1920)."""
    focus_x = min(1.0, max(0.0, focus_x))
    if mode == "crop":
        # Hochkant-Ausschnitt aus dem Querformat; focus_x bestimmt, wo der Ausschnitt sitzt.
        return f"[0:v]scale=-2:{H},crop={W}:{H}:(in_w-{W})*{focus_x:.3f}:0,setsar=1[v]"
    if mode == "blur":
        # Originalbild in voller Breite, Hintergrund = unscharfe, abgedunkelte Vergroesserung.
        return (
            f"[0:v]split=2[a][b];"
            f"[a]scale={W // 4}:{H // 4}:force_original_aspect_ratio=increase,crop={W // 4}:{H // 4},"
            f"gblur=sigma=6,scale={W}:{H},eq=brightness=-0.12[bg];"
            f"[b]scale={W}:-2,setsar=1[fg];"
            f"[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1[v]"
        )
    raise ToolError(f"Unbekannter Modus {mode!r} (erlaubt: blur, crop)")


def _flag(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value in {"on", "true", "1", "yes", "ja"}


def make_short(
    src: Path,
    out: Path,
    spec: ShortSpec,
    *,
    words: list | None,
    default_mode: str = "blur",
    encoder: str = "auto",
    hook: bool = True,
    font: str = "Arial Black",
) -> None:
    opts = spec.options
    mode = opts.get("mode", default_mode)
    focus_x = float(opts.get("x", "0.5"))
    graph = video_filter(mode, focus_x)

    show_subs = _flag(opts.get("subs"), words is not None) and words is not None
    show_hook = _flag(opts.get("hook"), hook) and bool(spec.title)

    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        if show_subs or show_hook:
            ass = subtitles.build_ass(
                subtitles.slice_words(words or [], spec.start, spec.end) if show_subs else [],
                hook_text=spec.title if show_hook else None,
                font=font,
            )
            (tmpdir / "sub.ass").write_text(ass, encoding="utf-8")
            # Relativer Dateiname + cwd=tmpdir: umgeht das Windows-Problem mit "C:\..."-Pfaden im ass-Filter
            graph = graph[: -len("[v]")] + "[vs];[vs]ass=sub.ass[v]"

        args = [
            "-ss", f"{spec.start:.3f}", "-t", f"{spec.duration:.3f}", "-i", str(src.resolve()),
            "-filter_complex", graph,
            "-map", "[v]", "-map", "0:a:0",
            "-af", "loudnorm=I=-14:TP=-1.5:LRA=11",
            *video_encode_args(encoder),
            "-r", "30",
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
            "-movflags", "+faststart",
            str(out.resolve()),
        ]
        run_ffmpeg(args, cwd=tmpdir)


def run(
    src: Path,
    spec_file: Path,
    out_dir: Path,
    *,
    mode: str = "blur",
    subs: bool = True,
    hook: bool = True,
    encoder: str = "auto",
    whisper_model: str = "small.en",
    track: int = 0,
    font: str = "Arial Black",
) -> list[Path]:
    info = probe(src)
    if not info.has_video:
        raise ToolError("Die Quelle hat kein Video.")
    specs = parse_spec_file(spec_file)
    for i, s in enumerate(specs, 1):
        if s.end > info.duration + 0.5:
            raise ToolError(f"Short {i}: Ende {fmt_time(s.end)} liegt hinter dem Videoende ({fmt_time(info.duration)}).")
        if not 15 <= s.duration <= 60:
            print(f"  Hinweis Short {i}: {s.duration:.0f} s (Ziel: 30-60 s)")

    words = None
    if subs and any(_flag(s.options.get("subs"), True) for s in specs):
        words = subtitles.transcribe(src, model=whisper_model, track=track)

    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"Encoder: {encoder_label(encoder)}  |  {len(specs)} Shorts -> {out_dir}")
    made: list[Path] = []
    for i, spec in enumerate(specs, 1):
        out = out_dir / f"{i:02d}_{slugify(spec.title or 'short')}.mp4"
        print(f"[{i}/{len(specs)}] {fmt_time(spec.start)}-{fmt_time(spec.end)}  {spec.title}")
        make_short(src, out, spec, words=words, default_mode=mode, encoder=encoder, hook=hook, font=font)
        made.append(out)
    return made
