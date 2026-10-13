# Nachtlauf 2026-10-13/14 — Servo-Stall wie am echten Servo, Fingereinsatz

Stand 2026-10-13 abends — **gestartet ~23:45** (Freigabe Leon, mit EXP-041; Index danach auf „Servo-Last real“). Letzter Lauf vor der Präsentation
(Do 2026-10-15); **EXP-036 bleibt Spitzenkandidat**, ein neues Experiment ersetzt es nur, wenn es gesichert besser ist und
die Videos überzeugen. Eltern **EXP-036** (CAPS + PID-Lagrange), je Experiment genau eine Änderung zum Vorgänger, 5 Seeds,
1024 Umgebungen × 300 Iterationen, eval-v2, Urteile als Entwurf (Leon). Stall-Grenze bleibt **20 %** (Leon).

## Ausgangslage

- Unruhe ist mit CAPS gelöst (EXP-036: 0,04). Offen: **Servo-Stall** (Last sammelt sich auf einem Servo, Überlastschutz
  > 2 s in 85 % der gehaltenen Episoden) und **Fingereinsatz** (im Mittel 3,25 Finger; Regel EXP-014: 4,9).
- Bisher gegen wenige Finger: EXP-005 und EXP-026 (Belohnung nach Fingerzahl) ohne Wirkung (2,9 bzw. 3,26 Finger), EXP-012/019
  (Annäherung aller Fingerspitzen) ebenso. Vermutung: Solange alle greifenden Servos im Stall stehen, bringt ein weiterer
  Finger nichts, und nichts bestraft das Sammeln der Last.
- Hardware (Leon, 2026-10-13): **alle Hand-Servos außer Unterarm und Handgelenk ziehen über eine Sehne**, eine
  **Rückstellfeder** öffnet. „Auf“ heißt loslassen — Moment in Öffnungsrichtung gibt es real nicht. Firmware kann
  Winkelgrenzen setzen (kein Drücken am Anschlag). Übersetzung Servo ↔ Finger unbekannt (Sim: 1:1, keine Feder).

## Diagnose „Woher kommt der Stall?“ (2026-10-13, `isaac_lab/tools/diag_stall.py`)

Am blockierten Gelenk ist Stall (|τ| ≥ 80 % Stall-Moment, PD-Schätzung von Isaac Lab) gleichbedeutend mit |a| ≳ 0,7: Die
relative Aktion setzt das Ziel jeden Physikschritt auf Ist + 0,1·a und kappt es nicht auf die Gelenkgrenzen. Aufgeteilt
je Servo in Zug (Beugen/Opposition) und Druck (Öffnen), jeweils am Anschlag (≤ 1°), Finger am Objekt (> 1 N), sonst;
256 Umgebungen, Seed 1000, deterministisch wie eval-v2. „Wie real“ = Sehnen-Servos nur Zug, kein Drücken am Anschlag.

| Policy · Objekt (Haltephase) | Servo-Last bisher | wie real | wer trägt (Zug am Objekt) | Artefakt |
|---|---|---|---|---|
| EXP-036 s42 · Ø 6 | 7,8 % | 7,8 % | Zeigefinger 51 % | – |
| EXP-036 s42 · Senf | 15,2 % | 15,0 % | Zeigefinger 85 %, Mittel 18 % | – |
| EXP-036 s43 · Ø 6 / Senf | 16,5 / 17,8 % | gleich | Daumen-MCP 93 / 95 %, Zeige 20 / 23 % | – |
| EXP-024 s44 · Ø 6 | 44,0 % | **20,9 %** | Zeige 91 %, klein 41 % | Rotator am 90°-Anschlag 89 %, Mittelfinger drückt auf (0°) 72 % |
| EXP-024 s44 · Senf | 40,7 % | **18,7 %** | Zeige 100 %, klein 31 % | Rotator am Anschlag 98 %, Mittelfinger drückt auf 54 % |

Mit Trainingsrauschen (EXP-036 s42, Ø 6, Haltephase): σ 0,43 (Ende des Trainings) → Servo-Last 21,7 %, wie real 16,7 %;
Mittelfinger 41 % statt 4 %, Ring/klein drücken 12–14 % gegen den offenen Anschlag. Nur Rauschen σ 1,0 (Trainingsbeginn,
ohne Objektkontakt) → 18,8 %, davon die Hälfte Druck (Öffnen), Rest kurze Vollmoment-Spitzen bei freier Bewegung.

**Befunde**
1. **EXP-036 ist nicht betroffen**: Sein Stall ist echte Last — ein Servo zieht gegen das Objekt. Die Zahlen gelten.
2. **EXP-024 ist stark betroffen**: Die Hälfte seiner Servo-Last ist Artefakt (Rotator drückt in Opposition gegen den
   Anschlag, Mittelfinger drückt nach außen). Wie real liegt es bei ~20 %, auf dem Niveau von EXP-036 →
   **Platz 1 im Index (0,66 vs. 0,64) kann an diesem Artefakt hängen** (gemessen nur s44) — für die Präsentation
   „gleichauf“; Nachbewertung aller Seeds im Lauf.
3. **Im Training ist das Rauschen der größte Teil der Kosten** (deterministisch 7,8 %, mit σ 0,43 21,7 %). Die Lagrange-
   Grenze gilt für die verrauschte Policy, eingesetzt wird der Mittelwert → die Grenze wirkt strenger als 20 %; vor dem
   ersten Griff besteht J_c ≈ 0,2 schon aus Zufallsbewegung (im Kurztest am 2026-10-12 bemerkt, nicht weiterverfolgt).

## Experimente (Reihenfolge = Kette)

| EXP | Eltern | eine Änderung | Hypothese | Dauer |
|---|---|---|---|---|
| 038 | 036 | Stall-Kosten **wie am echten Servo**: alle 8 Servos inkl. Handgelenk, kein Drücken am Anschlag (Firmware-Grenzen) | Kosten messen echte Last, weniger Strafe fürs Erkunden; Leistung/Zuverlässigkeit mindestens gleich, Servo-Last real ≤ EXP-036 | ~2 h |
| 039 | 038 | Grenze **je Servo**: 8 λ, jeder Servo ≤ 20 % | Last verteilt sich: kein Servo > 30 %, Schutz > 2 s ≤ 50 %, Finger ≥ 3,5; Leistung nicht gesichert schlechter | ~2 h |
| 040 | 039 | + Belohnung nach Fingerzahl (Term aus EXP-026, Gewicht 1,0) | Die Grenze zwingt zum Verteilen, die Belohnung zeigt wohin: im Mittel ≥ 4 Finger | ~2 h |
| 041 | 038 | + Fingerzahl ohne Grenze je Servo — Kontrolle zu 040 (2 × 2 mit 038/039) | Ohne Grenze je Servo wirkt die Fingerzahl nicht (wie EXP-026) | ~2 h |

Danach (nur Bewertung): neue Kennzahl „Servo-Last real“ für **alle** Policies der Leaderboards v3 nachholen (24, Hauptbedingung,
`eval --neu --bedingung haupt`, ~80 min) — erst dann stellt der Index auf sie um (Leon: ja), Belastungstest 038–041, beste
Videos 038–041 (`medien --beste`, YCB erst nach der Wahl), `done` mit HF-Backup. Gesamt ≈ 11,5 h: Start ~23:45 → Ende ~11:15.
Fällt ein Kurztest durch, läuft die Kette weiter.

**Vorher festgelegte Kriterien** (nur erfolgreiche Seeds): Leistung nicht gesichert schlechter als EXP-036 (P(besser) KI
nicht unter 0,5 ganz unten), Unruhe ≤ 0,1, Transport ≥ 95 %. EXP-039: kein Servo über 30 % (wie real, Haltephase), Schutz
> 2 s ≤ 50 %. EXP-040: Fingerzahl ≥ 4. Index nur zur Info.

## Prüfung vor dem Start (2026-10-13 abends)

Vor dem Start noch einmal gegen das Gelernte und die Literatur geprüft (Leon: „so wie es gescheit ist“). Zwei Korrekturen,
der Rest bleibt:

1. **Handgelenk gehört dazu (8 statt 7 Servos).** Es fehlte seit eval-v1 (2026-10-06) nur aus einem technischen Grund: Das
   Pleuel läuft als `RemotizedPDActuator` (ADR-014), dessen Grenze in Isaac Lab auf 10⁹ steht (Standard für explizite
   Aktuatoren, `actuator_base.py`) — |τ| ≥ 80 % der Grenze war dort nie möglich. Am Handgelenk sitzt aber ein echter ST3215.
   Jetzt: Stall-Moment winkelabhängig aus der Tabelle des Aktuators (2,94 Nm × n(θ), bis 12 Nm) → |τ|/Grenze ist für alle 8
   Servos dieselbe Größe (Moment am Servo / Stall-Moment), `mdp.servo_effort_limit`. EXP-036 s42 (Ø 6, 1000 Episoden):
   Handgelenk 0,9 % der Schritte ≥ 80 % — kaum Last, aber jetzt gemessen.
2. **Drücken in Öffnungsrichtung zählt weiter, nur nicht am Anschlag.** Der Plan sah „Sehnen-Servos nur Zug“ vor. Die Physik der
   Sim kann aber aktiv öffnen (real nur die Feder); ohne Kosten würde die Policy diese nicht übertragbare Kraft frei nutzen —
   ein Sim-to-Real-Schlupfloch, das man im Aktuatormodell schließt, nicht in den Kosten (asymmetrische Grenze = explizites
   Aktuatormodell, nach der Präsentation). Alle in der Diagnose gefundenen Artefakte waren ohnehin **Drücken gegen den
   Anschlag** (EXP-024: Rotator am 90°-Anschlag, Mittelfinger am offenen Anschlag) — die Firmware-Grenzen erfassen sie
   vollständig; für EXP-024 s44 ändert sich „wie real“ dadurch nicht (20,9 %).

Bestätigt:
- **Grenze je Servo** ist Standard bei mehreren Nebenbedingungen: je Nebenbedingung ein eigener Multiplikator (Stooke 2020; Lee
  et al. 2023, *Evaluation of Constrained RL Algorithms for Legged Locomotion*: Momentgrenzen je Gelenk), CaT je Gelenk. Gemessen
  an EXP-036 s42: Zeigefinger 54 % der Episode ≥ 80 % — die Grenze greift genau dort. Kurztraining 40 It. (Task JeServo):
  λ_Zeige 7,9 bei J_c 0,54, λ = 0 an Unterarm/Handgelenk/Rotator/Ring; Halten nach 40 It. 0,28/s (EXP-036 s42: 0,03) — kein
  Hinweis, dass die Grenze das Lernen abwürgt.
- **Kosten auf der verrauschten Policy** sind Standard (Safety Gym, CaT: die Nebenbedingung gilt für die Verhaltens-Policy);
  eingesetzt wird der Mittelwert, der weniger Last hat — die Grenze ist damit konservativ, nicht falsch.
- **2 × 2-Anlage** (038/039 × ohne/mit Fingerzahl = 038, 039, 041, 040) trennt die Wirkung der Grenze je Servo von der der
  Fingerzahl-Belohnung und ihre Wechselwirkung — die Hypothese zu 040 ist genau diese Wechselwirkung.
- Fingerzahl-Term unverändert aus EXP-026 (Gewicht 1,0, dort per `reward_diag` geprüft: ≤ 1/s ggü. Gegengriff 0,5/s).

## Warum diese Methoden

- **Kosten wie real**: Die Sim misst Stall auch dort, wo der echte Servo keinen hätte (Firmware kappt am Anschlag), und
  nicht dort, wo er einen hätte (Handgelenk) — die Grenze soll echte Last begrenzen, nicht Erkundung bestrafen. Die Physik der Sim bleibt
  unverändert (aktive Öffnungskraft bleibt eine Sim-to-Real-Lücke, siehe unten).
- **Grenze je Servo**: CaT (Chane-Sane et al. 2024) setzt eine Grenze **je Gelenk** auf das Moment, „to prevent damaging the
  actuators“; PID-Lagrange (Stooke et al. 2020) unverändert, ein λ je Servo. Kosten c_i = 1[Servo i im Stall wie real],
  Strafe −(1/7)·Σ λ_i·c_i (gleiche Größenordnung wie bisher), λ_i ≤ 100.
- **Fingerzahl**: Kontaktbelohnungen je Finger sind üblich (DexPoint: Daumen + ≥ 2 Finger; RobustDexGrasp: Kontakt je Glied,
  Fingerspitze 6,0; Reactive Grasping: Zahl der Kontakte bis 7). Unser Term wirkte zweimal nicht — neu ist hier nur, dass
  die Grenze je Servo das Sammeln der Last verbietet.

## Risiken

- **Grenze je Servo unter Rauschen zu streng**: Mittelfinger hätte mit σ 0,43 41 % Stall, obwohl der Mittelwert 4 % nutzt →
  λ steigt, auch wo der Einsatz kein Problem ist; kann den Griff schwächen (Leistung, Transport). Gegenmittel (nach der
  Präsentation): Grenze langsam einblenden wie CaT (p_max 0,05 → 0,25), eigener Kosten-Critic (Safety Gym).
- **Machbarkeit**: 0,4 kg brauchen bei Reibung 0,5–1 ~4–8 N Normalkraft, ein Finger im Stall bringt ~45 N; die Regel hält
  mit 0 % Stall → 20 % je Servo ist erreichbar. Der Senf (603 g) ist nicht im Training.
- 300 Iterationen: EXP-036 hatte am Ende noch nicht ausgelernt; mit 8 λ dauert das Einpendeln länger.
- λ steht nicht im Checkpoint (Weitertrainieren nicht möglich, wie EXP-035/036).

## Umsetzung (erledigt 2026-10-13 abends)

1. `pib_grasp/mdp.py`: `servo_effort_limit` (Stall-Moment je Servo, Handgelenk winkelabhängig), `servo_stall` (Stall wie am
   echten Servo, gemeinsam für Training und Bewertung), `StallLagrange` mit `firmware_limits` und `per_joint` (λ, J_c, I je
   Servo; Strafe (1/8)·Σ λ_i·c_i; Reglerzustand auf der CPU), Log `Lagrange/lambda_<servo>`, `Lagrange/J_c_<servo>`,
   `…_max`. Ohne die neuen Parameter rechnet der Term wie in EXP-035–037.
2. `env_cfg.py`, `__init__.py`: Tasks `HeavyMultiProgressDexCapsLagrange{Real,JeServo,JeServoFinger,RealFinger}-v0`, Agent `_Caps`.
3. `eval_policy.py` (zusätzlich, alte Zahlen unverändert): `servo_last_real` (8 Servos, ≥ 80 %, ohne Anschlag; ganze Episode und
   Haltephase, je Servo), `servo_schutz.schutz_anteil_real`. Geprüft an EXP-036 s42: alte Kennzahl „Servos ≥ 80 %“ 9,0 % (7
   Servos), neu 7,9 % (8 Servos) — passt.
4. `experiments.py`: Leaderboard v3 nimmt „Servo-Last real“ in den Index, sobald alle Rezepte mit Servo-Last sie haben
   (Nachbewertung in der Kette); die alte Größe als Info-Spalte „Servo-Last bisher“. Vorher unverändert (geprüft: gleiches
   `leaderboard.md`).
5. EXP-038–041 angelegt (`fenstertest: false`), Kurztraining JeServo 40 It. (oben).
6. Kette `scratchpad/nacht4/kette.sh`: run 038 → 039 → 040 → 041, Nachbewertung Hauptbedingung (24 Policies), belastung 038–041,
   medien --beste 038–041, done.

## Sim-to-Real-Lücken aus dieser Prüfung (für die Präsentation)

- **Sehnentrieb mit Rückstellfeder nicht modelliert**: Die Sim kann Finger aktiv mit vollem Moment öffnen (real nur
  Federkraft); Schließkraft ohne Federmoment; schlaffe Sehne (Objekt beugt den Finger weiter → Servo-Winkel ≠ Fingerwinkel,
  Spiel beim Wiederanziehen) fehlt; Sehnendehnung und Reibung fehlen.
- **Übersetzung Servo ↔ Finger** unbekannt (Sim 1:1): bei n = 2 doppeltes Moment, halbe Geschwindigkeit am Finger. Messbar
  über Servo-Schritte bei Finger 0/45/90°; Federkennlinie über „Present Load“ ohne Kontakt (M3).
- Firmware muss Winkelgrenzen und die Umrechnung Fingerwinkel ↔ Servo-Schritte übernehmen (Schnittstelle Policy ↔ Firmware).

## Quellen

Chane-Sane et al. 2024, CaT (arXiv 2403.18765) · Stooke, Achiam & Abbeel 2020, PID Lagrangian (ICML) · Ray, Achiam & Amodei
2019, Safety Gym · Qin et al. 2022, DexPoint (arXiv 2211.09423) · Zhang et al. 2025, RobustDexGrasp (arXiv 2504.05287) ·
Lee et al. 2026, Reactive Dexterous Grasping (arXiv 2605.03363) · Shi et al. 2025, AdaDexGrasp (arXiv 2503.20208)
