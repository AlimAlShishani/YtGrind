"""KI-Story-Pipeline: story.json -> fertiges Video (KI-Stimme + KI-Bilder mit Kamerabewegung + Untertitel).

Du lieferst die Idee, Claude schreibt story.json (Szenen mit Sprechtext + Bild-Prompt).
Dieses Modul macht daraus: Stimme (gecacht) -> Szenen-Clips (Zoom/Pan + Untertitel) -> ein Video.
Nach einer Aenderung werden nur die geaenderten Szenen neu gerendert (und nur neue Texte neu vertont).
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import statistics
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from . import subtitles, voice
from .common import (ToolError, encoder_label, fmt_time, probe, run_ffmpeg, slugify, tool, video_encode_args)

FPS = 30
DEFAULT_PAUSE = 0.35  # Sekunden Luft nach jeder Szene
WORDS_PER_SECOND = 2.5  # grobe TTS-Geschwindigkeit fuer Laengenschaetzung
MOTIONS = ["zoom_in", "pan_right", "zoom_out", "pan_left"]
IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp")
ASPECTS = {"16:9": (1920, 1080), "9:16": (1080, 1920)}


# --------------------------------------------------------------------------- datenmodell


@dataclass
class Scene:
    index: int  # 1-basiert
    narration: str
    image_prompt: str = ""
    image: str | None = None
    pause: float = DEFAULT_PAUSE
    motion: str | None = None
    characters: list[str] = field(default_factory=list)


@dataclass
class Story:
    title: str
    scenes: list[Scene]
    style: str = ""
    characters: dict[str, str] = field(default_factory=dict)
    voice: dict = field(default_factory=dict)
    path: Path | None = None

    @property
    def slug(self) -> str:
        return slugify(self.title)


def load_story(path: Path) -> Story:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError as err:
        raise ToolError(f"Datei nicht gefunden: {path}") from err
    except json.JSONDecodeError as err:
        raise ToolError(f"{path.name} ist kein gueltiges JSON (Zeile {err.lineno}, Spalte {err.colno}): {err.msg}") from err

    if not isinstance(data, dict) or not data.get("title") or not isinstance(data.get("scenes"), list) or not data["scenes"]:
        raise ToolError(f"{path.name}: 'title' und eine nicht-leere Liste 'scenes' sind Pflicht.")
    chars = data.get("characters", {})
    scenes: list[Scene] = []
    for i, raw in enumerate(data["scenes"], 1):
        if not isinstance(raw, dict) or not str(raw.get("narration", "")).strip():
            raise ToolError(f"{path.name}: Szene {i} hat keinen 'narration'-Text.")
        motion = raw.get("motion")
        if motion and motion not in MOTIONS:
            raise ToolError(f"{path.name}: Szene {i}: motion {motion!r} unbekannt (erlaubt: {', '.join(MOTIONS)}).")
        unknown = [c for c in raw.get("characters", []) if c not in chars]
        if unknown:
            raise ToolError(f"{path.name}: Szene {i}: Figur(en) {unknown} fehlen unter 'characters'.")
        scenes.append(Scene(i, " ".join(str(raw["narration"]).split()), str(raw.get("image_prompt", "")).strip(),
                            raw.get("image"), float(raw.get("pause", DEFAULT_PAUSE)), motion, list(raw.get("characters", []))))
    return Story(str(data["title"]), scenes, str(data.get("style", "")).strip(), dict(chars), dict(data.get("voice", {})), path)


def select_scenes(story: Story, spec: str | None) -> list[Scene]:
    """'3-6' oder '4' -> Szenen (1-basiert, inklusive)."""
    if not spec:
        return story.scenes
    m = re.fullmatch(r"\s*(\d+)\s*(?:-\s*(\d+))?\s*", spec)
    if not m:
        raise ToolError(f"--scenes {spec!r}: erwartet z. B. 3-6 oder 4")
    a, b = int(m.group(1)), int(m.group(2) or m.group(1))
    picked = [s for s in story.scenes if a <= s.index <= b]
    if not picked:
        raise ToolError(f"--scenes {spec}: keine Szene im Bereich (Story hat {len(story.scenes)}).")
    return picked


# --------------------------------------------------------------------------- bild-prompts / bilder


def full_prompt(story: Story, scene: Scene) -> str:
    parts = [scene.image_prompt]
    parts += [f"{name}: {story.characters[name]}" for name in scene.characters]
    if story.style:
        parts.append(story.style)
    return ". ".join(p.rstrip(". ") for p in parts if p)


def write_prompts(story: Story, out: Path) -> Path:
    lines = [f"# Bild-Prompts: {story.title}", "",
             "Pro Zeile ein Bild erzeugen und unter dem genannten Dateinamen in den Ordner `images/` legen.",
             "Querformat fuer 16:9-Videos, Hochformat fuer 9:16. Moeglichst >= 1536 px Kantenlaenge.", ""]
    for s in story.scenes:
        lines += [f"## scene_{s.index:02d}.png", full_prompt(story, s) or "(kein image_prompt angegeben)", ""]
    out.write_text("\n".join(lines), encoding="utf-8")
    return out


def find_image(story: Story, scene: Scene, images_dir: Path) -> Path | None:
    if scene.image:
        p = (story.path.parent if story.path else Path(".")) / scene.image
        return p if p.exists() else None
    for ext in IMAGE_EXTS:
        p = images_dir / f"scene_{scene.index:02d}{ext}"
        if p.exists():
            return p
    return None


def make_placeholder_image(path: Path, index: int, size: tuple[int, int]) -> None:
    """Farbflaeche je Szene – nur zum Testen von Schnitt/Untertiteln ohne echte Bilder."""
    w, h = size
    color = f"0x{(index * 2654435761) % 0xFFFFFF:06x}"
    run_ffmpeg(["-f", "lavfi", "-i", f"color=c={color}:s={w}x{h}:d=1", "-frames:v", "1", str(path)], quiet=True)


# --------------------------------------------------------------------------- untertitel-timing


def estimate_words(text: str, speech_seconds: float) -> list[dict]:
    """Wort-Zeiten ohne Whisper: Sprechdauer nach Wortlaenge + Satzzeichen-Pausen verteilen."""
    tokens = text.split()
    if not tokens:
        return []
    weights = []
    for tok in tokens:
        w = len(re.sub(r"\W", "", tok)) + 2.0
        if tok.endswith((",", ";", ":")):
            w += 2.5
        elif tok.endswith((".", "?", "!", "…")):
            w += 5.0
        weights.append(w)
    scale = speech_seconds / sum(weights)
    out, t = [], 0.0
    for tok, w in zip(tokens, weights):
        out.append({"w": tok, "s": round(t, 3), "e": round(t + w * scale * 0.9, 3)})
        t += w * scale
    return out


# --------------------------------------------------------------------------- rendern


def motion_for(story: Story, scene: Scene) -> str:
    return scene.motion or MOTIONS[(scene.index - 1) % len(MOTIONS)]


def motion_filter(motion: str, frames: int, size: tuple[int, int]) -> str:
    w, h = size
    n = max(frames, 1)
    cx, cy = "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
    if motion == "zoom_in":
        z, x, y = f"'1+0.15*on/{n}'", cx, cy
    elif motion == "zoom_out":
        z, x, y = f"'1.15-0.15*on/{n}'", cx, cy
    elif motion == "pan_right":
        z, x, y = "1.15", f"'(iw-iw/zoom)*on/{n}'", cy
    elif motion == "pan_left":
        z, x, y = "1.15", f"'(iw-iw/zoom)*(1-on/{n})'", cy
    else:
        raise ToolError(f"Unbekannte Bewegung {motion!r}")
    # 2x vorskalieren: zoompan rundet auf ganze Pixel, das ruckelt sonst sichtbar
    return (f"scale={2 * w}:{2 * h}:force_original_aspect_ratio=increase,crop={2 * w}:{2 * h},setsar=1,"
            f"zoompan=z={z}:x='{x}':y='{y}':d={n}:s={w}x{h}:fps={FPS}")


def _sha(*parts: object) -> str:
    h = hashlib.sha1()
    for p in parts:
        h.update(repr(p).encode("utf-8"))
    return h.hexdigest()[:12]


def _file_sha(path: Path) -> str:
    return hashlib.sha1(path.read_bytes()).hexdigest()[:12]


def render_scene(story: Story, scene: Scene, image: Path, mp3: Path, work: Path, *, size: tuple[int, int],
                 encoder: str, subs: bool) -> tuple[Path, Path, float]:
    """Liefert (video_clip, audio_wav, dauer). Clip und WAV sind exakt gleich lang (ganze Frames)."""
    speech = probe(mp3).duration
    frames = math.ceil((speech + scene.pause) * FPS)
    total = frames / FPS
    motion = motion_for(story, scene)
    w, h = size

    key = _sha(_file_sha(image), scene.narration, round(speech, 2), frames, motion, size, subs, encoder, FPS)
    clip = work / "clips" / f"scene_{scene.index:02d}_{key}.mp4"
    wav = work / "clips" / f"scene_{scene.index:02d}_{key}.wav"
    if clip.exists() and wav.exists():
        return clip, wav, total
    clip.parent.mkdir(parents=True, exist_ok=True)

    run_ffmpeg(["-i", str(mp3), "-af", f"aresample=48000,apad=whole_dur={total:.6f}", "-ar", "48000", "-ac", "2",
                "-t", f"{total:.6f}", "-c:a", "pcm_s16le", str(wav)], quiet=True)

    vf = motion_filter(motion, frames, size)
    sub_dir = work / "subs"
    sub_dir.mkdir(parents=True, exist_ok=True)
    cwd = sub_dir
    if subs:
        vertical = h > w
        ass = subtitles.build_ass(
            estimate_words(scene.narration, speech), width=w, height=h,
            size=88 if vertical else 66, margin_v=560 if vertical else 90, per_chunk=3 if vertical else 4,
        )
        (sub_dir / f"scene_{scene.index:02d}.ass").write_text(ass, encoding="utf-8")
        vf += f",ass=scene_{scene.index:02d}.ass"  # relativ + cwd: umgeht Windows-Pfadproblem mit "C:\"
    vf += ",format=yuv420p"
    run_ffmpeg(["-i", str(image.resolve()), "-vf", vf, "-frames:v", str(frames), "-r", str(FPS),
                *video_encode_args(encoder), "-an", "-movflags", "+faststart", str(clip.resolve())], cwd=cwd, quiet=True)
    return clip, wav, total


def _concat(files: list[Path], out: Path, list_file: Path) -> None:
    def esc(p: Path) -> str:
        return p.resolve().as_posix().replace("'", "'\\''")

    list_file.write_text("".join(f"file '{esc(f)}'\n" for f in files), encoding="utf-8")
    run_ffmpeg(["-f", "concat", "-safe", "0", "-i", str(list_file), "-c", "copy", str(out)], quiet=True)


def build(
    story: Story,
    out_dir: Path,
    *,
    images_dir: Path,
    aspect: str = "16:9",
    scenes_spec: str | None = None,
    provider: str = "elevenlabs",
    placeholder_images: bool = False,
    subs: bool = True,
    encoder: str = "auto",
) -> Path:
    if aspect not in ASPECTS:
        raise ToolError(f"--aspect {aspect!r}: erlaubt {', '.join(ASPECTS)}")
    size = ASPECTS[aspect]
    scenes = select_scenes(story, scenes_spec)
    work = out_dir / "work"
    work.mkdir(parents=True, exist_ok=True)

    # 1) Bilder pruefen, bevor irgendetwas Geld kostet
    images: dict[int, Path] = {}
    missing = []
    for s in scenes:
        img = find_image(story, s, images_dir)
        if img is None and placeholder_images:
            img = work / "placeholders" / f"scene_{s.index:02d}.png"
            img.parent.mkdir(exist_ok=True)
            if not img.exists():
                make_placeholder_image(img, s.index, size)
        if img is None:
            missing.append(f"scene_{s.index:02d}.png")
        else:
            images[s.index] = img
    if missing:
        raise ToolError(
            f"Es fehlen {len(missing)} Bild(er) in {images_dir}: {', '.join(missing[:8])}{' ...' if len(missing) > 8 else ''}\n"
            "Prompts erzeugen mit: python -m ytgrind story prompts <story.json>   (oder zum Testen --placeholder-images)"
        )

    # 2) Stimme (gecacht)
    chars_paid = sum(len(s.narration) for s in scenes)
    print(f"{len(scenes)} Szenen | {aspect} | Encoder: {encoder_label(encoder)} | Stimme: {provider} (~{chars_paid} Zeichen)")
    audio: dict[int, Path] = {}
    cached = 0
    for s in scenes:
        mp3, hit = voice.synthesize(s.narration, work / "audio", story.voice, provider)
        audio[s.index] = mp3
        cached += hit
    print(f"Stimme fertig ({cached} aus dem Cache, {len(scenes) - cached} neu erzeugt)")

    # 3) Szenen rendern
    clips, wavs, total = [], [], 0.0
    for s in scenes:
        print(f"  Szene {s.index}/{scenes[-1].index} ...", flush=True)
        clip, wav, dur = render_scene(story, s, images[s.index], audio[s.index], work, size=size, encoder=encoder, subs=subs)
        clips.append(clip)
        wavs.append(wav)
        total += dur

    # 4) Zusammenfuegen (+ Lautheit -14 LUFS)
    video_all, audio_all = work / "all_video.mp4", work / "all_audio.wav"
    _concat(clips, video_all, work / "clips.txt")
    _concat(wavs, audio_all, work / "wavs.txt")
    suffix = "" if not scenes_spec else f"_s{scenes_spec.replace(' ', '')}"
    final = out_dir / f"{story.slug}{'' if aspect == '16:9' else '_vertical'}{suffix}.mp4"
    run_ffmpeg(["-i", str(video_all), "-i", str(audio_all), "-map", "0:v", "-map", "1:a", "-c:v", "copy",
                "-af", "loudnorm=I=-14:TP=-1.5:LRA=11", "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
                "-movflags", "+faststart", str(final)], quiet=True)
    print(f"Fertig: {final}  ({fmt_time(total)})")
    return final


# --------------------------------------------------------------------------- check


def check(story: Story, images_dir: Path | None = None, compare: list[Story] | None = None) -> list[str]:
    """Hinweise zu Tempo, Hook und Template-Wirkung. Leere Liste = nichts aufgefallen."""
    notes: list[str] = []
    words = [len(s.narration.split()) for s in story.scenes]
    total_words = sum(words)
    est = total_words / WORDS_PER_SECOND + sum(s.pause for s in story.scenes)
    info = f"{len(story.scenes)} Szenen, {total_words} Woerter, ca. {fmt_time(est)}, ~{sum(len(s.narration) for s in story.scenes)} Zeichen Stimme"
    notes.append(f"INFO    {info}")

    if words[0] > 25:
        notes.append(f"HOOK    Szene 1 hat {words[0]} Woerter – der Hook sollte in <= 25 Woertern (ca. 10 s) sitzen.")
    for s, n in zip(story.scenes, words):
        if n > 45:
            notes.append(f"TEMPO   Szene {s.index}: {n} Woerter (> 45) – ein Bild laenger als ~18 s wirkt statisch; teilen.")
        elif n < 4:
            notes.append(f"TEMPO   Szene {s.index}: nur {n} Woerter – ok als Pointe, sonst mit Nachbarszene verbinden.")
        if not s.image_prompt and not s.image and not (images_dir and find_image(story, s, images_dir)):
            notes.append(f"BILD    Szene {s.index}: weder image_prompt noch Bilddatei.")
    prompts = [s.image_prompt.lower() for s in story.scenes if s.image_prompt]
    if len(set(prompts)) < len(prompts):
        notes.append("BILD    Identische image_prompts in mehreren Szenen – Bilder wiederholen sich.")
    if len(words) >= 6 and statistics.pstdev(words) / (statistics.mean(words) or 1) < 0.15:
        notes.append("VARIANZ Alle Szenen sind fast gleich lang – das wirkt wie eine Vorlage. Laenge variieren (kurze Schlaege, lange Passagen).")
    if words[-1] > 30:
        notes.append("ENDE    Letzte Szene ist lang – ein kurzer Schlusssatz bleibt besser haengen.")

    for other in compare or []:
        a, b = story.scenes[0].narration.lower().split()[:4], other.scenes[0].narration.lower().split()[:4]
        if a == b:
            notes.append(f"TEMPLATE Gleicher Einstieg wie '{other.title}': \"{' '.join(a)} ...\"")
        if len(story.scenes) == len(other.scenes):
            notes.append(f"TEMPLATE Gleiche Szenenzahl ({len(story.scenes)}) wie '{other.title}' – Aufbau variieren.")
        if story.scenes[-1].narration.lower().split()[-4:] == other.scenes[-1].narration.lower().split()[-4:]:
            notes.append(f"TEMPLATE Gleicher Schluss wie '{other.title}'.")
    return notes
