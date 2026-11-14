# Ranking-Video-Vorlage

Die ausfüllbare Skript-Vorlage liegt in [`templates/ranking_script_template.md`](../templates/ranking_script_template.md) und wird bei `python -m ytgrind new "<Titel>"` automatisch in `01_script/script.md` kopiert. Hier die Struktur in einer Übersicht.

## Grundgerüst (12 Min Beispiel)

| Zeit | Block | Inhalt | Schnitt-Takt |
|---|---|---|---|
| 0:00–0:05 | **Hook** | 1 Satz, Behauptung oder Ergebnis zuerst | Schnitt alle 1–2 s |
| 0:05–0:30 | **Setup** | Was wird gerankt, nach welchen 3 Kriterien, Open Loop ("Platz 1 überrascht") | 2–3 s |
| 0:30–5:30 | **Block 1** | Einträge unten → Mitte (je 35–50 s) | 2–4 s, 60 % Meme/Overlay |
| ~5:30–6:00 | **Mid-Retention** | Zwischenstand-Tier-List, 2. Open Loop | Tempo-Wechsel |
| 6:00–11:00 | **Block 2** | Einträge Mitte → oben, 1 bewusster Ausreißer | |
| 11:00–12:00 | **Finale** | #1-Auflösung, komplette Tier-List, Kommentar-Frage, nächstes Video anteasern | Ruhiger, dann Payoff |

## Der wiederholbare Eintrag (Herzstück, 35–50 s)

1. **Name + Footage** (3 s) – eigene Szene
2. **Urteil zuerst** (3 s) – Tier-Sticker + Soundeffekt, bevor du erklärst
3. **Begründung** (15–25 s) – *deine* Meinung + *ein konkretes eigenes Erlebnis*
4. **Punchline** (3–5 s) – Pointe, dann Meme-Beat (1–3 s)
5. **Übergang** (2 s) – Whoosh/Schnitt

Das Muster ist für dich schnell einsprechbar und für den Schnitt reproduzierbar – der Aufwand pro Eintrag ist planbar. Das Eigene (Meinung + Erlebnis) kommt aus Schritt 3 und ist das, was dein Video von Template-Content unterscheidet.

## Hooks in den ersten 5 Sekunden

Siehe `docs/04-hooks-und-titel.md` für alle Formeln. Kurzfassung:

- **Erstes Wort in 0,5 s**, ein Satz, kein Intro.
- **Hook-Test:** Würde ich weiterschauen, wenn ich das Video nicht kennen würde? Wenn nein → umschreiben.
- **Beispiele:**
  - "I ranked every Minecraft mob — and #1 will make you angry."
  - "Everyone says [Spiel] is a masterpiece. They're wrong."
  - (Bild: F-Tier-Meme) "This is the worst mob in the game — but the real answer is way worse."

## Länge des Skripts

~1.800–2.200 Wörter für 10–15 Min bei schnellem Sprechtempo. 12–16 Einträge × 35–50 s ≈ 8–11 Min plus Hook/Setup/Finale. **Mehr als 16 Einträge nur, wenn jeder wirklich Footage + Meinung hat** – sonst streichen.

## Aufnahme-Reihenfolge, die Schnitt spart

1. Skript schreiben und nur Listen mit Footage-Bedarf extrahieren.
2. **Gameplay gezielt pro Eintrag** aufnehmen (kein Stunden-Material sichten).
3. **Voiceover am Stück** einsprechen (Spur "nur Mikro").
4. `python -m ytgrind silence voice.wav` → saubere Basis-Timeline.
5. In Resolve: Gameplay + Memes + SFX über die Stimme legen.
6. Export einmal, Shorts per Skript.
