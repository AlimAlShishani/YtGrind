"""Gemeinsame Helfer: ffmpeg/ffprobe finden, Medien analysieren, Encoder waehlen."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


class ToolError(RuntimeError):
    """Fehler, der dem Nutzer ohne Traceback angezeigt wird."""


INSTALL_HINT = (
    "ffmpeg wurde nicht gefunden. Installation unter Windows:\n"
    "    winget install Gyan.FFmpeg\n"
    "Danach das Terminal neu oeffnen."
)


def tool(name: str) -> str:
    path = shutil.which(name)
    if not path:
        raise ToolError(INSTALL_HINT)
    return path


# --------------------------------------------------------------------------- zeit


_TC_RE = re.compile(r"^\s*(?:(?:(\d+):)?(\d+):)?(\d+(?:[.,]\d+)?)\s*$")


def parse_timecode(text: str) -> float:
    """'90', '1:30', '01:02:03', '1:30.5' -> Sekunden."""
    m = _TC_RE.match(text)
    if not m:
        raise ValueError(f"Ungueltiger Zeitcode: {text!r} (erlaubt: 90, 1:30, 01:02:03, 1:30.5)")
    h, mnt, sec = m.groups()
    return int(h or 0) * 3600 + int(mnt or 0) * 60 + float(sec.replace(",", "."))


def fmt_time(seconds: float) -> str:
    seconds = max(0.0, seconds)
    h, rest = divmod(int(round(seconds)), 3600)
    m, s = divmod(rest, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def slugify(text: str, max_len: int = 48) -> str:
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return (text[:max_len].strip("-")) or "untitled"


# --------------------------------------------------------------------------- probe


@dataclass
class MediaInfo:
    duration: float
    has_video: bool
    has_audio: bool
    audio_streams: int
    width: int = 0
    height: int = 0
    fps: float = 0.0


def _parse_rate(rate: str) -> float:
    if not rate or rate == "0/0":
        return 0.0
    if "/" in rate:
        a, b = rate.split("/")
        return float(a) / float(b) if float(b) else 0.0
    return float(rate)


def probe(path: Path) -> MediaInfo:
    out = subprocess.run(
        [tool("ffprobe"), "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)],
        capture_output=True,
        text=True,
    )
    if out.returncode != 0:
        raise ToolError(f"ffprobe konnte {path} nicht lesen:\n{out.stderr.strip()}")
    data = json.loads(out.stdout)
    streams = data.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video" and not s.get("disposition", {}).get("attached_pic")), None)
    audio = [s for s in streams if s.get("codec_type") == "audio"]
    duration = float(data.get("format", {}).get("duration") or (video or {}).get("duration") or 0)
    return MediaInfo(
        duration=duration,
        has_video=video is not None,
        has_audio=bool(audio),
        audio_streams=len(audio),
        width=int(video["width"]) if video else 0,
        height=int(video["height"]) if video else 0,
        fps=_parse_rate(video.get("avg_frame_rate") or video.get("r_frame_rate", "")) if video else 0.0,
    )


# --------------------------------------------------------------------------- ffmpeg


def run_ffmpeg(args: list[str], *, cwd: Path | None = None, quiet: bool = False) -> subprocess.CompletedProcess:
    cmd = [tool("ffmpeg"), "-hide_banner", "-y", "-loglevel", "error"]
    if not quiet:
        cmd.append("-stats")
    cmd += args
    res = subprocess.run(cmd, cwd=cwd, capture_output=quiet, text=True)
    if res.returncode != 0:
        detail = (res.stderr or "").strip()
        raise ToolError(f"ffmpeg ist fehlgeschlagen (Exit {res.returncode}).{(chr(10) + detail) if detail else ''}")
    return res


@lru_cache(maxsize=1)
def ffmpeg_major() -> int:
    """Hauptversion von ffmpeg; Git-Builds ('N-12345-...') gelten als neu."""
    out = subprocess.run([tool("ffmpeg"), "-version"], capture_output=True, text=True).stdout
    m = re.search(r"ffmpeg version n?(\d+)\.", out)
    return int(m.group(1)) if m else 99


@lru_cache(maxsize=1)
def amf_works() -> bool:
    """AMD-Hardware-Encoder (h264_amf) wirklich benutzbar? Kurzer Testlauf statt nur Encoder-Liste."""
    try:
        res = subprocess.run(
            [tool("ffmpeg"), "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
             "color=black:s=1280x720:r=30:d=0.3", "-c:v", "h264_amf", "-f", "null", "-"],
            capture_output=True,
        )
        return res.returncode == 0
    except ToolError:
        return False


def video_encode_args(encoder: str = "auto") -> list[str]:
    """encoder: auto | amf | x264. 'auto' nimmt die AMD-GPU, wenn sie funktioniert, sonst CPU (x264)."""
    use_amf = encoder == "amf" or (encoder == "auto" and amf_works())
    if use_amf:
        return ["-c:v", "h264_amf", "-quality", "quality", "-rc", "vbr_peak", "-b:v", "16M", "-maxrate", "24M",
                "-pix_fmt", "yuv420p"]
    return ["-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p"]


def encoder_label(encoder: str = "auto") -> str:
    return "AMD AMF (GPU)" if (encoder == "amf" or (encoder == "auto" and amf_works())) else "x264 (CPU)"
