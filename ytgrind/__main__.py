"""Kommandozeile:  python -m ytgrind <befehl> --help"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

from . import library, project, shorts, silence, story
from .common import ToolError, probe, fmt_time


def _p(text: str) -> Path:
    return Path(text).expanduser()


def cmd_silence(a: argparse.Namespace) -> None:
    src = _p(a.input)
    if not src.exists():
        raise ToolError(f"Datei nicht gefunden: {src}")
    dst = _p(a.output) if a.output else src.with_name(f"{src.stem}_clean{'.wav' if a.audio_only or src.suffix.lower() in silence.AUDIO_EXTS else '.mp4'}")
    stats = silence.remove_silence(src, dst, db=a.db, min_silence=a.min_silence, pad=a.pad, track=a.track,
                                   all_tracks=not a.only_track, audio_only=a.audio_only, encoder=a.encoder,
                                   dry_run=a.dry_run)
    print(("Trockenlauf: " if a.dry_run else "Fertig: ") + silence.report(stats))
    if not a.dry_run:
        print(f"-> {dst}")


def cmd_shorts(a: argparse.Namespace) -> None:
    src = _p(a.input)
    if not src.exists():
        raise ToolError(f"Datei nicht gefunden: {src}")
    spec = _p(a.spec) if a.spec else src.parent / "shorts.txt"
    if not spec.exists():
        raise ToolError(f"Zeitliste fehlt: {spec}  (Vorlage: templates/shorts.example.txt)")
    out_dir = _p(a.out) if a.out else src.parent / "shorts"
    made = shorts.run(src, spec, out_dir, mode=a.mode, subs=a.subs, hook=a.hook, encoder=a.encoder,
                      whisper_model=a.model, track=a.track, font=a.font)
    print(f"\n{len(made)} Shorts fertig in {out_dir}")


def cmd_subs(a: argparse.Namespace) -> None:
    from . import subtitles
    src = _p(a.input)
    words = subtitles.transcribe(src, model=a.model, track=a.track, use_cache=not a.force)
    print(f"{len(words)} Woerter erkannt -> {subtitles.words_cache_path(src)}")
    if a.ass:
        out = _p(a.ass)
        out.write_text(subtitles.build_ass(words, uppercase=not a.no_upper), encoding="utf-8")
        print(f"ASS-Datei: {out}")


def cmd_lib(a: argparse.Namespace) -> None:
    root = _p(a.root)
    if a.lib_cmd == "init":
        dirs = library.init(root)
        print(f"{len(dirs)} Ordner angelegt unter {root}")
    elif a.lib_cmd == "scan":
        res = library.scan(root)
        print(f"{len(res['added'])} neu, {len(res['missing'])} fehlen, {res['total']} gesamt")
        for f in res["added"]:
            print(f"  + {f}")
        for f in res["missing"]:
            print(f"  ! fehlt: {f}")
    elif a.lib_cmd == "tag":
        files = library.tag(root, a.pattern, a.changes)
        print(f"{len(files)} Datei(en) aktualisiert:")
        for f in files:
            print(f"  {f}")
    elif a.lib_cmd == "find":
        rows = library.find(root, a.tags, any_tag=a.any, kind=a.kind, max_dur=a.max_dur)
        for r in rows:
            dur = f"{float(r['duration']):.1f}s" if r["duration"] else "-"
            print(f"{(root / r['file'])}  [{dur}]  {r['tags']}")
        print(f"{len(rows)} Treffer")
    elif a.lib_cmd == "check":
        problems = library.check(root, max_meme_seconds=a.max_meme_seconds)
        for p in problems:
            print(p)
        print(f"{len(problems)} Hinweise")
        if problems and a.strict:
            sys.exit(1)


def cmd_story(a: argparse.Namespace) -> None:
    st = story.load_story(_p(a.story))
    base = _p(a.story).parent
    images = _p(a.images) if getattr(a, "images", None) else base / "images"
    if a.story_cmd == "prompts":
        out = story.write_prompts(st, base / "image_prompts.md")
        print(f"{len(st.scenes)} Prompts -> {out}")
    elif a.story_cmd == "check":
        others = [story.load_story(_p(c)) for c in a.compare]
        notes = story.check(st, images, others)
        for n in notes:
            print(n)
        print(f"{len([n for n in notes if not n.startswith('INFO')])} Hinweise")
    elif a.story_cmd == "build":
        out_dir = _p(a.out) if a.out else base / "build"
        story.build(st, out_dir, images_dir=images, aspect=a.aspect, scenes_spec=a.scenes, provider=a.provider,
                    placeholder_images=a.placeholder_images, subs=a.subs, encoder=a.encoder)


def cmd_new(a: argparse.Namespace) -> None:
    when = date.fromisoformat(a.date) if a.date else None
    folder = project.create(_p(a.root), a.title, when)
    print(f"Projekt angelegt: {folder}")


def cmd_info(a: argparse.Namespace) -> None:
    from .common import amf_works, encoder_label
    info = probe(_p(a.input))
    print(f"Dauer {fmt_time(info.duration)} | Video: {info.width}x{info.height}@{info.fps:.2f} | "
          f"Audiospuren: {info.audio_streams}")
    print(f"Encoder (auto): {encoder_label('auto')}  (AMF verfuegbar: {amf_works()})")


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="ytgrind", description="Automatisierung fuer den YouTube-Workflow")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("silence", help="Stille Pausen entfernen (Voice-Aufnahme oder Video)")
    s.add_argument("input")
    s.add_argument("-o", "--output")
    s.add_argument("--db", type=float, default=-35.0, help="Lautstaerke-Schwelle in dB (Standard -35; Rauschen hoch -> z. B. -30)")
    s.add_argument("--min-silence", type=float, default=0.40, help="Pausen ab dieser Laenge entfernen (s)")
    s.add_argument("--pad", type=float, default=0.12, help="Luft vor/nach dem Sprechen (s), damit nichts abgehackt klingt")
    s.add_argument("--track", type=int, default=0, help="Audiospur mit deiner Stimme (0-basiert; OBS-Mikrospur z. B. 1)")
    s.add_argument("--only-track", action="store_true", help="nur die gewaehlte Spur ausgeben statt aller Spuren")
    s.add_argument("--audio-only", action="store_true", help="nur Audio ausgeben (WAV)")
    s.add_argument("--encoder", choices=["auto", "amf", "x264"], default="auto")
    s.add_argument("--dry-run", action="store_true", help="nur anzeigen, wieviel gespart wuerde")
    s.set_defaults(func=cmd_silence)

    s = sub.add_parser("shorts", help="Lange Videos anhand einer Zeitliste in 9:16-Shorts schneiden")
    s.add_argument("input", help="exportiertes langes Video")
    s.add_argument("--spec", help="Zeitliste (Standard: shorts.txt neben dem Video)")
    s.add_argument("--out", help="Ausgabeordner (Standard: shorts/ neben dem Video)")
    s.add_argument("--mode", choices=["blur", "crop"], default="blur", help="blur: Bild + unscharfer Hintergrund; crop: Hochkant-Ausschnitt")
    s.add_argument("--subs", action=argparse.BooleanOptionalAction, default=True, help="Untertitel einbrennen")
    s.add_argument("--hook", action=argparse.BooleanOptionalAction, default=True, help="Titel als Hook-Text oben einblenden")
    s.add_argument("--encoder", choices=["auto", "amf", "x264"], default="auto")
    s.add_argument("--model", default="small.en", help="Whisper-Modell: base.en (schnell) | small.en | medium.en (genauer, langsam)")
    s.add_argument("--track", type=int, default=0, help="Audiospur fuer die Transkription")
    s.add_argument("--font", default="Arial Black")
    s.set_defaults(func=cmd_shorts)

    s = sub.add_parser("subs", help="Nur transkribieren (Cache) und optional ASS-Datei schreiben")
    s.add_argument("input")
    s.add_argument("--model", default="small.en")
    s.add_argument("--track", type=int, default=0)
    s.add_argument("--ass", help="ASS-Untertiteldatei fuer das ganze Video schreiben")
    s.add_argument("--no-upper", action="store_true")
    s.add_argument("--force", action="store_true", help="Cache ignorieren")
    s.set_defaults(func=cmd_subs)

    s = sub.add_parser("lib", help="Meme-/SFX-Bibliothek")
    s.add_argument("--root", default="library")
    ls = s.add_subparsers(dest="lib_cmd", required=True)
    ls.add_parser("init", help="Ordnerstruktur + index.csv anlegen")
    ls.add_parser("scan", help="neue Dateien in den Index aufnehmen")
    t = ls.add_parser("tag", help="Tags setzen: tag <name-teil> +shock -sad")
    t.add_argument("pattern")
    t.add_argument("changes", nargs="+")
    f = ls.add_parser("find", help="suchen: find shock minecraft --max-dur 2")
    f.add_argument("tags", nargs="*")
    f.add_argument("--any", action="store_true", help="ein Tag genuegt (statt alle)")
    f.add_argument("--kind", choices=list(library.LAYOUT))
    f.add_argument("--max-dur", type=float)
    c = ls.add_parser("check", help="Qualitaets-Check (Laenge, Quelle/Lizenz, Tags)")
    c.add_argument("--max-meme-seconds", type=float, default=3.0)
    c.add_argument("--strict", action="store_true", help="Exit-Code 1 bei Hinweisen")
    s.set_defaults(func=cmd_lib)

    s = sub.add_parser("story", help="KI-Story-Pipeline: story.json -> Video (KI-Stimme, KI-Bilder)")
    st_sub = s.add_subparsers(dest="story_cmd", required=True)
    for name, help_ in (("prompts", "Bild-Prompts fuer die Szenen ausgeben"),
                        ("check", "Tempo/Hook/Template-Pruefung (kostenlos)"),
                        ("build", "Video bauen")):
        t = st_sub.add_parser(name, help=help_)
        t.add_argument("story", help="Pfad zu story.json")
        t.add_argument("--images", help="Ordner mit scene_01.png ... (Standard: images/ neben story.json)")
        if name == "check":
            t.add_argument("--compare", nargs="*", default=[], help="andere story.json zum Vergleich gegen Template-Wirkung")
        if name == "build":
            t.add_argument("--out", help="Ausgabeordner (Standard: build/ neben story.json)")
            t.add_argument("--aspect", choices=["16:9", "9:16"], default="16:9")
            t.add_argument("--scenes", help="nur Szenen-Bereich, z. B. 1-6 (fuer Shorts/Teaser)")
            t.add_argument("--provider", choices=["elevenlabs", "mock"], default="elevenlabs",
                           help="Stimm-Anbieter; mock = stumme Testspur ohne Kosten")
            t.add_argument("--placeholder-images", action="store_true", help="Farbflaechen statt Bilder (nur Test)")
            t.add_argument("--subs", action=argparse.BooleanOptionalAction, default=True)
            t.add_argument("--encoder", choices=["auto", "amf", "x264"], default="auto")
    s.set_defaults(func=cmd_story)

    s = sub.add_parser("new", help="Neues Video-Projekt mit Ordnern + Skript-Vorlage anlegen")
    s.add_argument("title")
    s.add_argument("--date", help="Veroeffentlichungsdatum YYYY-MM-DD (Standard: heute)")
    s.add_argument("--root", default="projects")
    s.set_defaults(func=cmd_new)

    s = sub.add_parser("info", help="Datei + Encoder-Check (laeuft die AMD-GPU-Kodierung?)")
    s.add_argument("input")
    s.set_defaults(func=cmd_info)
    return ap


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):  # Windows-Konsole: Umlaute nicht zerschiessen
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    args = build_parser().parse_args(argv)
    try:
        args.func(args)
    except ToolError as err:
        print(f"Fehler: {err}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Abgebrochen.", file=sys.stderr)
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
