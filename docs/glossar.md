# Glossar Deutsch ↔ Englisch

Dokumentation, Berichte, Ausgaben der Werkzeuge sowie Kommandozeilen-Optionen und JSON-Schlüssel sind deutsch, die
Code-Kommentare und die Literatur englisch. Bezeichner und Optionen bleiben, wie sie sind (Umbenennen würde alte Berichte und
Logs entwerten) — diese Tabelle übersetzt sie.

## Experimente und Bewertung (`experiments.py`, `eval_policy.py`, Berichte)

| Deutsch | Englisch | Bedeutung hier |
|---|---|---|
| Experiment, Eltern | experiment, parent | jedes Experiment ändert genau eine Sache gegenüber den Eltern (ADR-016) |
| `--kurz`, Titel | short name, title | Ordnername `EXP-NNN_<kurz>` |
| Hypothese, Änderung | hypothesis, change | vor dem Training festgelegt, danach nicht mehr geändert |
| Ergebnis, Urteil, Schluss | result, verdict, conclusion | nach der Bewertung; das *Urteil* setzt ein Mensch, das Skript macht nur einen *Vorschlag* |
| Bedingung, Hauptbedingung (`haupt`) | condition, main condition | Objekt × Startpose × Anforderung; die erste eines Experiments ist die Hauptbedingung |
| Anforderung | requirement | z. B. `max_kipp_deg: 45` — höchstens 45° gekippt |
| Protokoll (eval-v1, eval-v2) | protocol | Version des Bewertungsprotokolls; nur innerhalb eines Protokolls vergleichen (ADR-021) |
| Aufgabenerfolg | task success | bis zum Ende gehalten **und** Anforderung erfüllt — Hauptmetrik |
| Haltequote | hold rate | bis zum Ende gehalten, Anforderung egal |
| Leistung | performance | IQM des Aufgabenerfolgs über die **erfolgreichen** Seeds und die Benchmark-Objekte |
| Zuverlässigkeit, erfolgreiche Seeds k/n | reliability | wie viele Seeds überhaupt greifen lernen (ADR-019) |
| Robust, Störbedingung, `--stoerung` | robustness, perturbed condition | ungenaue Vorgreifpose, 1 Schritt Verzögerung, Sensorrauschen |
| Belastung, `--bewegung`, Rampe, Transport, Gieren, Nicken | load test, arm motion, ramp, transport, yaw, pitch | Scheinkräfte eines bewegten Arms (`mdp.apply_arm_motion`) |
| Grenzbeschleunigung | limit acceleration | Beschleunigung, bei der das Objekt > 2 cm rutscht |
| Leitplanke | guardrail | Nebenmetrik, die nicht schlechter werden darf |
| Kippwinkel, Unterarm | tilt angle, forearm | Kippen des Objekts; genutzte Unterarmdrehung |
| Griffkraft | grip force | Summe der Fingerspitzenkräfte in der Haltephase |
| Stall-Anteil, Servo-Last, Servo-Last real | stall share, servo load | Anteil der Schritte mit Servo-Moment ≥ 90 % / 80 % des Stall-Moments; *real* = alle 8 Servos, kein Drücken gegen den Anschlag |
| Überlastschutz, Schutz > 2 s | overload protection | Episoden, in denen ein Servo > 2 s am Stück ≥ 80 % liegt (STS3215-Datenblatt) |
| Unruhe, Unruhe wirksam | jitter, effective jitter | mittlere quadratische Änderung der Aktion (roh / wie an die Servos geschickt) |
| Schwingen, Objektweg, Absinken | oscillation, object path, sinking | Objektgeschwindigkeit in der Haltephase; Verschiebung in der Tischebene; Absinken ggü. Starthöhe |
| Fingernutzung, Finger mit Kontakt | finger use, fingers in contact | Kontaktanteil/Kraft je Finger in der Haltephase |
| Startfehler, gefallen, instabil | start failure, dropped, unstable | Fehlerarten |
| Wünschbarkeitsindex, Pareto | desirability index | Leaderboard v3: geometrisches Mittel der Wünschbarkeiten (Derringer & Suich 1980) |
| Top (Seed), beste Videos | top seed, best videos | bester Seed = Einsatz-Kandidat |
| Regel, Regel-Baseline | rule, rule baseline | programmierter Griff ohne RL (ADR-020) |
| Medien, Verlauf | media, time series | Videos und Verläufe je Schritt (`medien`) |
| umstellen, Sicherung | migrate, backup | Experiment auf das aktuelle Protokoll heben; Sicherung auf Hugging Face in `done` |
| Kurztest, Fenstertest, Nachtlauf | smoke test, window test, night run | kurzes Training vor einem Lauf; Zuschauen im Fenster; Kette über Nacht |

## Aufgabe und Szene

| Deutsch | Englisch | Bedeutung hier |
|---|---|---|
| Greifart: seitlich, oben | grasp type: side, top | ein Spezialist je Greifart (ADR-018) |
| Vorgreifpose | pre-grasp pose | Handfläche 3,5 cm vor der Objektoberfläche |
| Absenken, Haltephase | table lowering, hold phase | ab 2 s sinkt der Tisch um 10 cm (≙ Arm hebt an); Haltephase ab 2,5 s |
| Gegengriff | opposition | Daumen und ≥ 1 Finger in Kontakt (Dexsuite `good_contact`) |
| Annäherung, Fortschritt | approach, progress | Annäherungsbelohnung; Fortschritt = nur Verbesserung zählt (DexPBT) |
| Halten, Aufrecht, Erfolg | held, upright, success | Belohnungsterme |
| Begrenzung ±1, Filter, Skala | clipping, filter, scale | Nachbearbeitung der Aktion / Schrittweite der relativen Aktion |
| Zylinder, Quader, Flasche, Saftpackung, Kugel, Dose, Schachtel | cylinder, box, bottle, juice carton, sphere, can, small box | Objektkatalog `OBJECTS` |
| YCB: Cracker, Zucker, Senf, Suppendose | cracker box, sugar box, mustard bottle, soup can | YCB 003/004/006/005 |
| Daumen, Zeige-, Mittel-, Ringfinger, kleiner Finger | thumb, index, middle, ring, little finger | Reihenfolge der FSR: Daumen … klein |
| Handgelenk, Pleuel, Rotator | wrist, linkage, thumb rotator | Handgelenk über ein Viergelenk angetrieben (ADR-014) |
| Sehne, Rückstellfeder | tendon, return spring | realer Fingerantrieb (2026-10-13), in der Sim nicht modelliert |
