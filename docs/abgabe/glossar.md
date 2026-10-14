# Glossary German → English (draft, 2026-10-13)

> Draft for `docs/plan-abgabe.md`. Command-line options, JSON keys, report headings and experiment files use German terms.
> They stay as they are (renaming would break existing reports and logs); this table translates them.

## Experiments and evaluation (`experiments.py`, `eval_policy.py`, reports)

| German | English | Meaning here |
|---|---|---|
| Experiment, Eltern | experiment, parent | Every experiment changes exactly one thing relative to its parent (ADR-016) |
| `--kurz`, Titel | short name, title | Folder name `EXP-NNN_<kurz>` |
| Hypothese, Änderung | hypothesis, change | Written before training, never changed afterwards |
| Ergebnis, Urteil, Schluss | result, verdict, conclusion | Filled in after evaluation; *Urteil* is set by a human, the script only proposes (*Vorschlag*) |
| Bedingung, Hauptbedingung (`haupt`) | condition, main condition | Object × start pose × requirement; the first one of an experiment is the main condition |
| Anforderung | requirement | e.g. `max_kipp_deg: 45` — tilt ≤ 45° for upright objects |
| Protokoll (eval-v1, eval-v2) | protocol | Evaluation protocol version; compare only within one protocol (ADR-021) |
| Aufgabenerfolg | task success | Held until the end **and** requirement met — main metric |
| Haltequote | hold rate | Held until the end, requirement ignored |
| Leistung | performance | IQM of task success over the **successful** seeds and benchmark objects |
| Zuverlässigkeit, erfolgreiche Seeds k/n | reliability, successful seeds | How many seeds learn to grasp at all (ADR-019) |
| Robust, Störbedingung, `--stoerung` | robustness, perturbed condition | Inaccurate pre-grasp pose, 1-step delay, sensor noise |
| Belastung, `--bewegung`, Rampe, Transport, Gieren, Nicken | load test, arm motion, ramp, transport, yaw, pitch | Fictitious forces of a moving arm (`mdp.apply_arm_motion`) |
| Grenzbeschleunigung | limit acceleration | Acceleration at which the object starts to slip (> 2 cm) |
| Leitplanke | guardrail | Secondary metric that must not get worse |
| Kippwinkel | tilt angle | Object tilt (max per episode) |
| Unterarm | forearm | Forearm rotation used during the episode |
| Griffkraft, Kraft > 15 N | grip force, force above 15 N | Sum of fingertip forces in the hold phase |
| Stall-Anteil, Servo-Last, Servo-Last real | stall share, servo load, servo load (real) | Share of steps with servo torque ≥ 90 % / 80 % of stall torque; *real* = all 8 servos, no pushing against the joint limit |
| Überlastschutz, Schutz > 2 s | overload protection | Episodes in which one servo stays ≥ 80 % for more than 2 s (STS3215 datasheet) |
| Unruhe, Unruhe wirksam | jitter, effective jitter | Mean squared change of the action (raw / as sent to the servos) |
| Schwingen | oscillation | Object velocity in the hold phase |
| Objektweg | object path | Object displacement in the table plane |
| Absinken | sinking | Object drop relative to the start height |
| Fingernutzung, Finger mit Kontakt | finger use, fingers in contact | Contact share/force per finger in the hold phase |
| Startfehler, gefallen, instabil | start failure, dropped, unstable | Failure modes |
| Wünschbarkeitsindex, Pareto | desirability index | Leaderboard v3: geometric mean of per-metric desirabilities (Derringer & Suich 1980) |
| Top (Seed), beste Videos | top seed, best videos | Best seed = deployment candidate |
| Regel, Regel-Baseline | rule, rule baseline | Scripted grasp without RL (ADR-020) |
| Medien, Verlauf | media, time series | Videos and per-step curves (`medien`) |
| umstellen | migrate | Lift an experiment to the current protocol |
| Sicherung | backup | Hugging Face backup in `done` |
| Kurztest, Fenstertest | smoke test, window test | Short training before a run; watching in the GUI |
| Nachtlauf | night run | Chain of experiments run overnight |

## Task and scene

| German | English | Meaning here |
|---|---|---|
| Greifart: seitlich, oben | grasp type: side, top | Specialist per grasp type (ADR-018) |
| Vorgreifpose | pre-grasp pose | Hand 3.5 cm in front of the object surface |
| Absenken, Haltephase | table lowering, hold phase | From 2 s the table drops 10 cm (≙ arm lifts); hold phase from 2.5 s |
| Gegengriff | opposition | Thumb and ≥ 1 finger in contact (Dexsuite `good_contact`) |
| Annäherung, Fortschritt | approach, progress | Fingertip approach reward; progress = only improvement counts (DexPBT) |
| Halten, Aufrecht, Erfolg | held, upright, success | Reward terms |
| Begrenzung ±1, Filter, Skala | clipping, filter, scale | Action post-processing / relative action scale |
| Objekte: Zylinder, Quader, Flasche, Saftpackung, Kugel, Dose, Schachtel | cylinder, box, bottle, juice carton, sphere, can, small box | Object catalogue `OBJECTS` |
| YCB: Cracker, Zucker, Senf, Suppendose | cracker box, sugar box, mustard bottle, soup can | YCB 003/004/006/005 |
| Daumen, Zeige-, Mittel-, Ringfinger, kleiner Finger | thumb, index, middle, ring, little finger | FSR order: thumb … little |
| Handgelenk, Pleuel, Rotator | wrist, linkage (connecting rod), thumb rotator | Wrist driven by a four-bar linkage (ADR-014) |
| Sehne, Rückstellfeder | tendon, return spring | Real finger drive (2026-10-13), not modelled yet |
