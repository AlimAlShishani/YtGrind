# Workflow & Zeitbudget (Windows · DaVinci Resolve · AMD-GPU)

Ziel: **5–7 Stunden pro Woche** bei 1 langen Video alle 2 Wochen + 1 Short pro Tag.

## Die drei Hebel, die den meisten Schnittaufwand sparen

1. **Voice-first statt Gameplay-first.** Erst Skript einsprechen (nur Mikro, kein Gameplay), Pausen per Skript entfernen. Die gesäuberte Stimme ist die Basis-Timeline, Gameplay und Memes werden *darüber* gelegt. So schneidest du Bild nach Ton – nicht umgekehrt.
2. **Eine Meme-Bibliothek statt jedes Mal neu suchen.** Ordner + Tags + Lizenz-Eintrag (`python -m ytgrind lib ...`). 60 % Meme-Schnitt wird zu "Suchen → Ziehen → Fertig" statt Recherche.
3. **Shorts nicht in Resolve bauen.** Du exportierst das lange Video **einmal**, danach erzeugt das Skript alle 7 Shorts (9:16, Untertitel, Hook-Text, Lautheit) aus dieser Datei. Du schreibst nur Zeitstempel in `shorts.txt`.

## Zeitbudget pro 2-Wochen-Zyklus (Zielzustand, nicht Monat 1)

| Block | Aufgabe | Std. |
|---|---|---|
| Planung | Thema, Skript nach Vorlage (`templates/ranking_script_template.md`), Meme-/Footage-Liste | 2,0 |
| Aufnahme | Gameplay für die Einträge (läuft teils sowieso beim Spielen) + Voiceover einsprechen | 3,0 |
| Cleanup | `silence`-Skript, Sichtprüfung | 0,5 |
| Schnitt lang | Resolve: Gameplay + Memes + SFX auf Stimme legen, Tier-Grafiken | 4,5 |
| Export + Shorts | 1× Export, `shorts.txt` füllen, Skript laufen lassen, Shorts kurz durchsehen | 1,5 |
| Thumbnail + Titel + Upload | | 1,0 |
| Scheduling Shorts | 14 Shorts in 3 Plattformen vorplanen (Planer, nicht täglich händisch) | 1,0 |
| **Summe** | | **≈ 13,5 → 6,75 Std./Woche** |

**Ehrlicher Hinweis:** In den ersten 4–6 Wochen wird es länger dauern (Bibliothek aufbauen, Vorlagen bauen, Lernkurve). Der Kalender in `03-content-kalender.md` enthält auf Wunsch **4 lange Videos im ersten Monat** = ein Video pro Woche. Das ist doppelt so viel wie dein Zielrhythmus und passt **nicht** in 5–7 Std./Woche. Siehe dort "Variante B (Zielrhythmus)".

## Einmaliges Setup (Windows)

```powershell
winget install Python.Python.3.12
winget install Gyan.FFmpeg
# Terminal neu oeffnen, dann im Projektordner:
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m ytgrind info <irgendein-video.mp4>      # zeigt, ob die AMD-Kodierung (AMF) erkannt wird
python -m ytgrind lib init                         # legt library\ an
```

**AMD-spezifisch:** Das Skript nutzt für die Ausgabe den AMD-Hardware-Encoder (`h264_amf`), wenn er funktioniert, sonst CPU (`x264`) – automatisch (`--encoder auto|amf|x264` zum Erzwingen). Whisper (Untertitel) läuft auf der **CPU**, weil die Standard-Whisper-Bibliotheken unter Windows keine AMD-GPU nutzen. Das ist okay: Das Modell `small.en` transkribiert ein 12-Min-Video grob in wenigen Minuten (einmal pro Video, danach gecacht). Zu langsam? `--model base.en`.

## OBS-Einstellungen (für sauberes Material)

- **Konstante Bildrate** (CFR), z. B. 60 fps oder 30 fps – Resolve mag keine variable Framerate.
- **Mehrere Audiospuren:** Spur 1 = alles (Backup), Spur 2 = **nur Mikrofon**. Das Skript erkennt Stille nur auf der Stimme: `--track 1`.
- Format: MKV aufnehmen (absturzsicher) und danach "Remux to mp4" – oder direkt Hybrid MP4/MOV.
- Mikro: Rauschunterdrückung/Noise-Gate leicht, Abstand konstant → `--db` bleibt für alle Aufnahmen gleich.

## Wöchentlicher Ablauf (Beispiel, 6 Std.)

| Tag | Dauer | Was |
|---|---|---|
| Mo | 1,5 h | Skript + Eintrags-/Meme-Liste, Footage-Liste |
| Di | 1,5 h | Gameplay aufnehmen (gezielt für die Einträge) |
| Mi | 1,0 h | Voiceover aufnehmen → `silence` → Timeline-Grundgerüst in Resolve |
| Do/Fr | 2,0 h | Memes + SFX + Tier-Grafiken, Feinschnitt |
| Sa | 1,0 h | Export, `shorts`, Thumbnail, Upload/Scheduling |

(In der Woche ohne langes Video: Aufnahme für das nächste + Shorts-Ernte + Bibliothek pflegen.)

## Skript-Befehle (Kurzreferenz)

```powershell
# 1) Stille aus Voiceover entfernen (erst ansehen, dann machen)
python -m ytgrind silence voice.wav --dry-run
python -m ytgrind silence voice.wav -o voice_clean.wav
python -m ytgrind silence aufnahme.mkv --track 1        # Video mit Mikro auf Spur 2

# 2) Shorts aus dem exportierten Video (Zeiten in shorts.txt)
python -m ytgrind shorts 04_export\video.mp4 --spec 05_shorts\shorts.txt --out 05_shorts

# 3) Nur Untertitel/Transkript
python -m ytgrind subs video.mp4 --ass video.ass

# 4) Meme-Bibliothek
python -m ytgrind lib scan
python -m ytgrind lib tag shocked-pikachu +shock +pokemon
python -m ytgrind lib find shock --max-dur 2
python -m ytgrind lib check

# 5) Neues Projekt mit Ordnern + Skriptvorlage
python -m ytgrind new "Ranking every Minecraft mob" --date 2026-11-20
```

Stilisierte Optionen für Shorts: `--mode blur` (Standard: Gameplay in voller Breite, unscharfer Hintergrund – nichts wird abgeschnitten) oder `--mode crop` mit `x=0..1` pro Short (Hochkant-Ausschnitt, wenn die Action an einer Stelle passiert, z. B. `x=0.3` = eher links).

## DaVinci Resolve (Free) — Setup, das Zeit spart

- **Timeline-Vorlage** bauen und duplizieren: V1 Gameplay, V2 Memes/Overlays, V3 Text/Tier-Grafik, A1 Stimme, A2 SFX. Nie wieder Spuren neu anlegen.
- **Power Bin** für die Bibliothek: Den Ordner `library\` einmal in einen Power Bin ziehen, damit er in jedem Projekt verfügbar ist (im Media Pool die Power Bins einblenden; je nach Resolve-Version im Bin-Menü). Beim Import eines Ordners entstehen die Unterordner als Bins.
- **Tier-Grafiken (S–F)** einmal als Compound-Clip/Titel bauen und in den Power Bin legen.
- **Tastatur statt Maus:** Klingenwerkzeug `B`, Schnitt am Playhead `Ctrl+B`, Ripple Delete, Clips mit `Alt+Ziehen` duplizieren. Je weniger Mausarbeit pro Meme, desto schneller wird der 60-%-Meme-Schnitt – zeitnah die Shortcuts üben.
- **Export:** 1080p, 60 oder 30 fps (so wie aufgenommen), H.264, einmal pro Video. Die Shorts kommen vom Skript.
- Marker setzen (`M`), wenn dir beim Schneiden ein Short-Moment auffällt; Zeitstempel danach in `shorts.txt` übernehmen.

## Veröffentlichen auf drei Plattformen ohne Mehrarbeit

- **YouTube Studio:** Videos/Shorts einplanen (Zeitplan). **TikTok** (Web-Upload) und **Instagram/Facebook** (Meta Business Suite) haben ebenfalls einen eigenen Planer. Plane die Woche an einem Termin vor, statt täglich.
- **Keine inoffiziellen Upload-Bots/Tools mit Passwort-Login** – das riskiert Kontosperren. Offizielle Planer reichen für 1 Short/Tag.
- **Keine Wasserzeichen-Dateien weiterverteilen:** Immer das Original aus `05_shorts` hochladen, nicht ein von TikTok heruntergeladenes Video auf YouTube/Instagram.
- **Beschreibung/Hashtags pro Plattform** minimal anpassen (Kontext, nicht identischer Copy-Paste-Spam).

## Schutz vor "Inauthentic Content" (praktische Regeln)

- Jedes Video/jeder Short enthält **deine Stimme + deine Meinung**. Reine Meme-Zusammenschnitte ohne Kommentar nicht als Short veröffentlichen.
- Einheitliche Optik (Untertitel, Farben, Tier-Grafik) ist unproblematisch; **identische Struktur mit ausgetauschten Platzhaltern** ohne echten neuen Inhalt wäre das Risiko. Variiere Hook-Typ, Länge und Aufbau der Shorts (siehe Kalender).
- Eigenes Gameplay behalten (Rohmaterial aufheben) – falls die Plattform nachfragt, kannst du es zeigen.
- **Meme-Rechte:** "1–3 s" macht Material nicht automatisch erlaubt – Content-ID kann trotzdem anschlagen. Darum Quelle/Lizenz in `index.csv` eintragen und keine Musik-/Film-/Serienausschnitte verwenden. Wenn ein Claim kommt, Clip ersetzen.
