# KI-Pipeline: Idee rein, Video raus

Neue Richtung: **Du lieferst die Idee, die KI macht den Rest.** Erzählte Story mit KI-Stimme (ElevenLabs) und KI-Bildern mit Kamerabewegung. Die bisherigen Werkzeuge (Shorts, Untertitel) laufen weiter mit.

```
Idee (du, 2–3 Sätze) → story.json (Claude) → Bilder (KI-Tool deiner Wahl) → story build → Video → shorts
```

## Ablauf pro Video (ca. 1 Stunde aktive Arbeit)

1. **Idee an Claude** (siehe "Ideen-Briefing" unten). Claude schreibt `story.json`.
2. `python -m ytgrind story check story.json` – kostenlos: Tempo, Hook, Template-Wirkung.
3. `python -m ytgrind story prompts story.json` – schreibt `image_prompts.md`. Pro Szene ein Bild in deinem KI-Bildtool erzeugen und als `images/scene_01.png`, `scene_02.png` … speichern. (Stil und Figurenbeschreibung stehen schon in jedem Prompt, damit die Bilder zusammenpassen.)
4. **Zum Testen ohne Kosten:** `python -m ytgrind story build story.json --provider mock --placeholder-images`
5. **Echt bauen:** `python -m ytgrind story build story.json` (nutzt ElevenLabs).
6. Ergebnis in `build/`. Szene geändert? Nochmal `build` – nur geänderte Szenen werden neu gerendert, nur neue Texte neu bezahlt (Cache).
7. **Shorts:**
   - Hochkant-Teaser direkt: `story build story.json --aspect 9:16 --scenes 1-3`
   - Oder aus dem langen Video: `shorts video.mp4 --spec shorts.txt --mode crop`

## Einmalig einrichten (Windows)

```powershell
# Stimme: Schluessel aus deinem ElevenLabs-Konto, einmalig speichern, danach neues Terminal
setx ELEVENLABS_API_KEY "dein-schluessel"
```
Schluessel **nie** in den Chat, in Dateien oder ins Git. In `story.json` trägst du nur die `voice_id` ein (die ID der gewählten Stimme in deinem Konto).

> **Lizenz prüfen:** Ob dein ElevenLabs-Tarif die kommerzielle Nutzung (Monetarisierung) erlaubt, steht in deren Bedingungen für deinen Tarif. Vor dem ersten Upload nachsehen.

## story.json

```json
{
  "title": "…",
  "style": "Stil-Zusatz, wird an JEDEN Bild-Prompt gehaengt (fuer einheitlichen Look)",
  "characters": { "Mia": "feste Aussehens-Beschreibung, wird bei Szenen mit Mia angehaengt" },
  "voice": { "provider": "elevenlabs", "voice_id": "…", "model_id": "eleven_multilingual_v2" },
  "scenes": [
    { "narration": "Sprechtext der Szene", "image_prompt": "was das Bild zeigt",
      "characters": ["Mia"], "motion": "zoom_in", "pause": 0.35 }
  ]
}
```

- `motion` (optional): `zoom_in`, `zoom_out`, `pan_left`, `pan_right`. Ohne Angabe wechseln die Bewegungen automatisch.
- `pause` (optional): Sekunden Luft nach der Szene (z. B. `1.0` vor der Pointe).
- `image` (optional): eigener Bilddateipfad statt `images/scene_XX.png`.
- Vollständiges Beispiel: `templates/story.example.json`.

**Bildqualität:** Je größer das Bild, desto schärfer der Zoom (ab ca. 1536 px Kantenlänge). Querformat für 16:9, Hochformat für `--aspect 9:16`.

## Ideen-Briefing (so gibst du mir eine Idee)

```
Idee: (2–3 Sätze, worum geht's, was ist die Pointe/der Twist)
Genre/Ton: (Horror, Comedy, Drama, Gaming-Insider …)
Länge: (z. B. 45 s Short / 3 Min / 10 Min)
Format: (Story erzählt / Ranking / Reaktion)
Sonderwünsche: (Figuren, Look, Ende offen/geschlossen)
```
Ich liefere `story.json` (Szenen, Sprechtext, Bild-Prompts, Figurenbeschreibung). Du entscheidest Idee, Richtung und Freigabe.

## Aufbau-Varianten (gegen den Template-Eindruck)

Wechsle den Aufbau von Video zu Video. Nimm nie dreimal hintereinander denselben:

| Struktur | Ablauf | Gut für |
|---|---|---|
| **Cold Open** | Mitten im Höhepunkt starten, dann "Zwei Stunden früher …" | Horror, Thriller |
| **Countdown** | Ranking/Liste, Platz 1 als Auflösung | Gaming-Listen, Facts |
| **Falsche Fährte** | Erwartung aufbauen, in der vorletzten Szene brechen | Comedy, Twist |
| **Brief/Tagebuch** | Ich-Perspektive, Einträge mit Datum | Mystery |
| **Zwei Zeitlinien** | Vorher/Nachher im Wechsel, treffen sich am Ende | Drama |
| **Eine Frage** | Das ganze Video beantwortet eine Frage, Antwort kommt zuletzt | Erklär-Stories |

Dazu variieren: Länge (45 s / 3 Min / 10 Min), Szenenzahl, Anzahl der Figuren, Genre, Schlusssatz. `story check --compare andere.json` warnt, wenn Einstieg, Szenenzahl oder Schluss zu ähnlich sind.

## Schutz vor "Inauthentic Content" – Prüfliste (vor jedem Upload)

- [ ] **Die Idee ist neu und von dir** (kein Nacherzählen bekannter Reddit-/Creepypasta-Texte, keine Copy-Paste-Stories).
- [ ] Hat jedes Video eine **eigene Pointe oder These**, die man in einem Satz sagen kann?
- [ ] **Aufbau, Länge und Ton unterscheiden sich** von den letzten 3 Videos (`story check --compare`).
- [ ] Du hast Skript und Bilder **gesichtet und angepasst** (nicht ungeprüft durchgelaufen).
- [ ] Stimme und Kanalname/Optik bleiben **einheitlich** (Marke), der **Inhalt nicht**.
- [ ] **Kennzeichnung:** Wirken Bilder/Stimme realistisch, in YouTube Studio die Angabe zu veränderten/synthetischen Inhalten setzen. Auf TikTok und Instagram die dortige KI-Kennzeichnung nutzen.
- [ ] Keine Musik, keine fremden Bilder/Clips, keine Stimme nachgeahmter realer Personen.

Ehrlich: Vollautomatische KI-Story-Kanäle sind genau die Kategorie, die YouTube mit dem Update im Juli 2026 genauer prüft. Die Pipeline spart Arbeit, ersetzt aber nicht die originale Idee. Wenn nach 4–6 Videos die Zuschauerbindung niedrig ist oder die Monetarisierung abgelehnt wird, ist der erste Hebel mehr eigener Inhalt, nicht mehr Output.

## Grenzen

- **Live nicht getestet:** Die ElevenLabs-Anbindung ist nur gegen die dokumentierte Anfrage-Form geprüft (Unit-Tests), nicht mit echtem Schlüssel. Beim ersten Lauf zuerst eine Szene testen: `--scenes 1`.
- **Bilder werden nicht per API erzeugt.** Du erzeugst sie im Tool deiner Wahl über `image_prompts.md`. Wenn du ein Bild-Tool mit API festlegst, kann ich es einbauen.
- **Untertitel-Timing ist geschätzt** (Wortlänge und Satzzeichen), nicht erkannt. Für Lesbarkeit in Stories reicht das; exakteres Timing geht über `subs` (Whisper) auf deinem PC.
- **Blender-Animation und KI-Video** sind noch nicht eingebaut. Der Szenen-Aufbau von `story.json` lässt sich dafür wiederverwenden.
