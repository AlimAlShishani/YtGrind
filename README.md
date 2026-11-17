# YtGrind

Werkzeuge + Pläne für einen englischsprachigen Gaming-Commentary-Kanal (Rankings/Tier-Lists, eigene Stimme, schneller Meme-Schnitt).
Ziel: **5–7 Std./Woche**, 1 langes Video alle 2 Wochen + 1 Short pro Tag auf YouTube Shorts, TikTok und Reels.

**Zwei Richtungen:** (1) Gaming-Commentary mit eigener Stimme (Docs 01–04), (2) **KI-Pipeline**: du gibst die Idee, KI macht Skript, Stimme, Bilder und Schnitt (`docs/05-ki-pipeline.md`).

Plattform: Windows · DaVinci Resolve · AMD-GPU · Python 3.10+ · ffmpeg.

## Was ist drin

| Pfad | Inhalt |
|---|---|
| `ytgrind/` | Python-Werkzeuge (`python -m ytgrind ...`) |
| `docs/01-workflow-und-zeitbudget.md` | Setup, Zeitbudget, OBS/Resolve-Tipps, Veröffentlichen, Schutz vor "Inauthentic Content" |
| `docs/02-ranking-vorlage.md` | Aufbau eines Ranking-Videos, Eintrags-Muster, Hook |
| `docs/03-content-kalender.md` | Monat 1: 4 Ranking-Videos + 28 Shorts (+ Variante B für den 2-Wochen-Rhythmus) |
| `docs/04-hooks-und-titel.md` | Hook-Formeln, Titel- und Thumbnail-Ideen |
| `docs/05-ki-pipeline.md` | KI-Story-Pipeline: Idee → `story.json` → Video, Aufbau-Varianten, Prüfliste |
| `templates/` | Skript-Vorlage, `shorts.txt`-Vorlage, `story.example.json` |

## Schnellstart (Windows, PowerShell)

```powershell
winget install Python.Python.3.12
winget install Gyan.FFmpeg          # Terminal danach neu oeffnen
python -m venv .venv ; .venv\Scripts\activate
pip install -r requirements.txt
python -m ytgrind info video.mp4    # Encoder-Check: AMD-GPU (AMF) oder CPU
python -m ytgrind lib init
python -m ytgrind new "Ranking every Minecraft mob" --date 2026-11-20
```

## Befehle

| Befehl | Zweck |
|---|---|
| `silence <datei> [--dry-run] [--track N]` | Stille Pausen aus Voiceover/Video entfernen (Mikro-Spur wählbar) |
| `shorts <video> --spec shorts.txt` | Shorts (1080×1920) per Zeitliste: Zuschnitt `blur`/`crop`, Untertitel, Hook-Text, Lautheit −14 LUFS |
| `subs <video> [--ass out.ass]` | Whisper-Transkription (gecacht) bzw. ASS-Untertitel |
| `lib init / scan / tag / find / check` | Meme-/SFX-Bibliothek mit Ordnern, Tags, Quelle/Lizenz, Längen-Check (≤ 3 s) |
| `story prompts / check / build <story.json>` | KI-Pipeline: Bild-Prompts, Tempo-/Template-Check, Video mit KI-Stimme (ElevenLabs), Zoom/Pan und Untertiteln; Stimme wird gecacht |
| `new "<Titel>"` | Projektordner + Skriptvorlage |
| `info <datei>` | Dateiinfo + Encoder-Erkennung |

`--help` an jedem Befehl zeigt alle Optionen.

## Tests

```bash
python -m unittest discover -s tests -v
```

## Bekannte Grenzen

- Whisper läuft auf der **CPU** (keine AMD-GPU-Beschleunigung unter Windows). Für 12-Min-Videos ok, einmal pro Video, danach gecacht.
- `--mode crop` skaliert 1080p auf 1920 Höhe hoch → etwas weicher; bei 1440p-Aufnahmen schärfer.
- Die AMD-Kodierung (`h264_amf`) wurde in der Entwicklungsumgebung **nicht** auf echter AMD-Hardware getestet; das Skript prüft per Kurztest und fällt sonst auf x264 (CPU) zurück.
- Schrift "Arial Black" ist unter Windows vorhanden; Alternativen per `--font`.
