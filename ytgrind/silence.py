"""Stille Pausen aus Voice-Aufnahmen (oder Videos) entfernen.

Ablauf: ffmpeg `silencedetect` findet Pausen -> wir behalten alles andere (mit etwas Luft
an den Raendern, damit es natuerlich klingt) -> ein einziger ffmpeg-Lauf schneidet und fuegt zusammen.
"""

from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path

from .common import (ToolError, encoder_label, ffmpeg_major, fmt_time, probe, run_ffmpeg, tool,
                     video_encode_args)

AUDIO_EXTS = {".wav", ".mp3", ".m4a", ".flac", ".ogg", ".aac"}

_START = re.compile(r"silence_start:\s*(-?\d+(?:\.\d+)?)")
_END = re.compile(r"silence_end:\s*(-?\d+(?:\.\d+)?)")


def detect_silence(path: Path, *, db: float, min_silence: float, track: int = 0) -> list[tuple[float, float]]:
    """Liefert [(start, ende), ...] aller Pausen >= min_silence auf Audiospur `track` (0-basiert)."""
    cmd = [tool("ffmpeg"), "-hide_banner", "-nostats", "-i", str(path), "-map", f"0:a:{track}",
           "-af", f"silencedetect=noise={db}dB:d={min_silence}", "-f", "null", "-"]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise ToolError(f"Stille-Erkennung fehlgeschlagen (existiert Audiospur {track}?):\n{res.stderr.strip()[-600:]}")
    silences: list[tuple[float, float]] = []
    start: float | None = None
    for line in res.stderr.splitlines():
        if (m := _START.search(line)):
            start = max(0.0, float(m.group(1)))
        elif (m := _END.search(line)) and start is not None:
            silences.append((start, float(m.group(1))))
            start = None
    if start is not None:  # Datei endet in Stille
        silences.append((start, float("inf")))
    return silences


def keep_segments(
    silences: list[tuple[float, float]],
    total: float,
    *,
    pad: float = 0.12,
    min_keep: float = 0.10,
    fps: float = 0.0,
) -> list[tuple[float, float]]:
    """Komplement der (um `pad` verkleinerten) Pausen. Mit fps: Schnittpunkte aufs Bildraster."""
    removed: list[tuple[float, float]] = []
    for s, e in silences:
        e = min(e, total)
        rs, re_ = s + pad, e - pad
        if re_ - rs > 0.02:
            removed.append((rs, re_))

    keeps: list[tuple[float, float]] = []
    cursor = 0.0
    for rs, re_ in removed:
        if rs > cursor:
            keeps.append((cursor, rs))
        cursor = max(cursor, re_)
    if cursor < total:
        keeps.append((cursor, total))

    if fps > 0:
        snapped = []
        for a, b in keeps:
            a2, b2 = round(a * fps) / fps, round(b * fps) / fps
            if b >= total - 1e-6:
                b2 = total
            snapped.append((a2, b2))
        keeps = snapped

    keeps = [(a, b) for a, b in keeps if b - a >= min_keep]
    # direkt aneinander liegende Stuecke wieder verbinden (z. B. nach dem Snappen)
    merged: list[tuple[float, float]] = []
    for a, b in keeps:
        if merged and a - merged[-1][1] < 1e-6:
            merged[-1] = (merged[-1][0], b)
        else:
            merged.append((a, b))
    return merged


def build_filter_script(segments: list[tuple[float, float]], *, has_video: bool, audio_tracks: list[int]) -> str:
    """filtergraph: trim je Segment + concat. Datei statt CLI, weil Windows ~32k Zeichen Limit hat."""
    n = len(segments)
    lines: list[str] = []

    def branches(src: str, kind: str, tag: str) -> list[str]:
        """Eine Quelle in n Kopien aufteilen (jedes Label darf nur einmal benutzt werden)."""
        if n == 1:
            return [src]
        outs = [f"[{tag}s{i}]" for i in range(n)]
        lines.append(f"{src}{'split' if kind == 'v' else 'asplit'}={n}{''.join(outs)};")
        return outs

    concat_inputs = [[] for _ in range(n)]
    if has_video:
        outs = branches("[0:v]", "v", "v")
        for i, (a, b) in enumerate(segments):
            src = outs[i] if n > 1 else "[0:v]"
            lines.append(f"{src}trim=start={a:.6f}:end={b:.6f},setpts=PTS-STARTPTS[v{i}];")
            concat_inputs[i].append(f"[v{i}]")
    for t, src_idx in enumerate(audio_tracks):
        outs = branches(f"[0:a:{src_idx}]", "a", f"a{t}")
        for i, (a, b) in enumerate(segments):
            src = outs[i] if n > 1 else f"[0:a:{src_idx}]"
            lines.append(f"{src}atrim=start={a:.6f}:end={b:.6f},asetpts=PTS-STARTPTS[a{t}_{i}];")
            concat_inputs[i].append(f"[a{t}_{i}]")

    outputs = (["[vout]"] if has_video else []) + [f"[aout{t}]" for t in range(len(audio_tracks))]
    lines.append("".join("".join(c) for c in concat_inputs)
                 + f"concat=n={n}:v={1 if has_video else 0}:a={len(audio_tracks)}{''.join(outputs)}")
    return "\n".join(lines)


def _run_with_graph(graph: str, inputs: list[str], tail: list[str]) -> None:
    """Filter-Datei statt CLI-Argument (Windows-Limit ~32k Zeichen). Optionsname aenderte sich in ffmpeg 7."""
    with tempfile.TemporaryDirectory() as tmp:
        script = Path(tmp) / "graph.txt"
        script.write_text(graph, encoding="utf-8")
        flag = "-/filter_complex" if ffmpeg_major() >= 7 else "-filter_complex_script"
        run_ffmpeg(inputs + [flag, str(script)] + tail)


def remove_silence(
    src: Path,
    dst: Path,
    *,
    db: float = -35.0,
    min_silence: float = 0.40,
    pad: float = 0.12,
    track: int = 0,
    all_tracks: bool = True,
    audio_only: bool = False,
    encoder: str = "auto",
    dry_run: bool = False,
) -> dict:
    info = probe(src)
    if not info.has_audio:
        raise ToolError("Die Datei hat keine Audiospur.")
    if track >= info.audio_streams:
        raise ToolError(f"Audiospur {track} existiert nicht (Datei hat {info.audio_streams}).")
    has_video = info.has_video and not audio_only and src.suffix.lower() not in AUDIO_EXTS

    silences = detect_silence(src, db=db, min_silence=min_silence, track=track)
    segs = keep_segments(silences, info.duration, pad=pad, fps=info.fps if has_video else 0.0)
    if not segs:
        raise ToolError("Alles wurde als Stille erkannt – `--db` hoeher (z. B. -45) oder Spur pruefen.")
    kept = sum(b - a for a, b in segs)
    stats = {"original": info.duration, "kept": kept, "cuts": len(segs) - 1, "segments": segs}
    if dry_run:
        return stats

    audio_tracks = list(range(info.audio_streams)) if all_tracks else [track]
    graph = build_filter_script(segs, has_video=has_video, audio_tracks=audio_tracks)

    maps: list[str] = []
    if has_video:
        maps += ["-map", "[vout]"]
    for t in range(len(audio_tracks)):
        maps += ["-map", f"[aout{t}]"]

    if has_video:
        codec = video_encode_args(encoder) + ["-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart"]
        print(f"Encoder: {encoder_label(encoder)}")
    else:
        codec = ["-c:a", "pcm_s16le"] if dst.suffix.lower() == ".wav" else ["-b:a", "256k"]
    dst.parent.mkdir(parents=True, exist_ok=True)
    _run_with_graph(graph, ["-i", str(src)], maps + codec + [str(dst)])
    return stats


def report(stats: dict) -> str:
    saved = stats["original"] - stats["kept"]
    pct = 100 * saved / stats["original"] if stats["original"] else 0
    return (f"{fmt_time(stats['original'])} -> {fmt_time(stats['kept'])}  "
            f"({stats['cuts']} Schnitte, {fmt_time(saved)} gespart = {pct:.0f} %)")
