# Nachtlauf So 2026-10-11 22:00 → Mo 2026-10-12 14:00 (Plan, Leon freigegeben)

Leon ist bis Montag 14:00 weg und antwortet nicht. Präsentation der Projektarbeit am Donnerstag 2026-10-15 — Ziel: vorzeigbarer
Stand für **seitlich** und **von oben**. Alles wie gewohnt sichern: Commit + Push (`origin/feature/rl-grasping`) +
Hugging Face (`experiments.py done`). Sim-to-Real-Lücken werden nur in der Präsentation genannt, nicht behoben
(`docs/pruefung-aktionsweg.md`).

## Grundsatz (Leon)

Die Servos behalten ihr volles Potential, das Netz lernt es vernünftig zu nutzen: echte Hardware-Grenzen in der Sim, alles
andere über Kosten im Training — **keine Eingriffe zur Laufzeit** (kein Aktionsfilter, kein hartes Abschneiden), keine
künstlich kleine Aktionsskala.

## 1. Leaderboard v3 (zuerst)

- `eval_policy.py` (erledigt 22:50): **Schwingen** (Objekt-Geschwindigkeit/Drehrate in der Haltephase, RMS) und
  **Aktionsfrequenz** (amplitudengewichtete mittlere Frequenz der Servo-Befehle, CAPS-artig); **Störbedingung** `--stoerung`
  (Objektlage seitlich x −2…+1 cm / y ±3 cm, von oben ±1,5 cm; 1 Policy-Schritt Verzögerung; Rauschen Gelenkwinkel σ 0,01 rad,
  FSR σ 0,5 N). Test EXP-022 s42 Ø 6: normal 93,4 %, gestört 71,9 %.
- `experiments.py`: Störbedingung je Greifart (`STOERUNG`, `zylinder_seitlich_gestoert` / `kugel_d7_oben_gestoert`), wird bei
  jeder Bewertung mitgemessen; Leaderboard v3 = **Wünschbarkeitsindex** (geometrisches Mittel, Derringer & Suich) + **Pareto**;
  bisherige Tabelle (nach Leistung) bleibt darunter.
- Nachbewertung (Hauptbedingung neu + Störbedingung) aller eval-v2-Rezepte außer EXP-013/017 (alte Linie): EXP-014, 015
  (Regeln), 018–026 — ~2,5 h GPU.

Zielwerte des Index (0 = inakzeptabel, 1 = Ziel; aus gespeicherten Daten, später ohne Messung änderbar):

| Größe | 0 | 1 |
|---|---|---|
| Leistung (IQM erfolgreiche Seeds) | 70 % | 95 % |
| Robustheit (Erfolg Störbedingung, Mittel der Seeds) | 50 % | 90 % |
| Unruhe an den Servos (`unruhe_wirksam`) | 1,0 | 0,1 |
| Schwingen Objekt | schlechtestes Rezept | Regel (EXP-014) |
| Objektweg | 100 mm | 35 mm |
| Kippwinkel (Median) | 35° | 5° |
| Unterarm (Median) | 45° | 5° |
| Servo-Last (Stall je Servo, Mittel über 7 Servos) | **100 %** (Leon) | 20 % |

Nur Info: Zuverlässigkeit (Seeds), Griffkraft, Finger am Objekt.

## 2. Eltern für EXP-027

EXP-027 tauscht den Aktionsweg ohnehin aus → die Eltern bestimmen nur das **Belohnungsrezept**: Grundrezept (EXP-019/022/024),
xy-Strafe (EXP-023), Moment-Strafe (EXP-025), Fingerzahl (EXP-026), Critic mit Objekt (EXP-021). Regel: Rezept des
RL-Experiments mit dem höchsten Index; bei < 0,05 Abstand gewinnt das einfachere (Grundrezept). Begründung in den Handoff.

## 3. Vorbereitung

- **`bounds_loss`** in rsl_rl (eigene PPO-Unterklasse, Isaac Lab unverändert; Koeffizient und Grenze 1,1 aus Dexsuite
  rl_games prüfen).
- **EXP-027 „Aktionsraum wie Dexsuite“**: Skala 0,1 für **alle** 8 Servos, `bounds_loss` statt `clip_actions`, kein Filter.
- **Von oben**: `env_cfg_oben.py` auf die gefundene Pose (20° um x, 0° um y, Rotator 75° fest beim Start, Höhe der tiefsten
  Spitze je Objekt nach `docs/startpose-oben/ergebnis.md`), Vorgreifpose gestreut (Höhe ±5 mm, Lage ±10 mm, Kippung ±3°);
  `analyse_reset.py --greifart oben` (≥ 256 Starts); Objektkatalog/Benchmark „von oben“ prüfen.
- `reward_diag` + Kurztest je neuem Task; Commit + Push + Backup vor dem Start.

## 4. Experimente (Reihenfolge nach Wichtigkeit, je 5 Seeds, eval-v2 + Störbedingung)

| # | Experiment | Eltern / Rezept | ca. |
|---|---|---|---|
| 1 | EXP-027 Aktionsraum wie Dexsuite (neue saubere Basis) | Gewinner aus Schritt 2 | 1,8 h |
| 2 | EXP-028 Regel-Baseline „von oben“ (gestreute Vorgreifpose, ADR-020) | – | 0,3 h |
| 3 | EXP-029 Spezialist „von oben“ | Rezept EXP-027 | 1,5 h |
| 4 | EXP-030 Spezialist „von oben“ (Rückfallebene) | Rezept EXP-022 | 1,5 h |
| 5 | EXP-031 großes Netz 512-256-128 (Dexsuite) | EXP-027 | 1,8 h |
| 6 | EXP-032 großes Netz + Budget ×8 (4096 Umg. × 600 It.) | EXP-027 | 3,3 h |

Läuft die Zeit über 14:00, läuft das letzte Experiment weiter und wird im Handoff als laufend vermerkt.

## 5. Abschluss (bis 14:00)

Beste Videos (seitlich + von oben), Leaderboard v3, Berichte als Entwurf (Urteile Leon), Handoff mit Zahlen für die Folien
(seitlich: bestes Rezept, Regel-Vergleich, int8; von oben: Startpose-Suche, Regel, Spezialist), Commit + Push + Backup.

## Arbeitsregeln für die Nacht

- Während eines `experiments.py run` keine Dateien unter `isaac_lab/` ändern (Commit-Markierung „+lokal“, neue Prozesse
  importieren neu); während der Nachbewertung nichts an `eval_policy.py`.
- Prozesse nie mit `pkill -f`/`pgrep -f` auf eigene Befehlsmuster (Exit 144) — `ps -eo pid,comm,args | awk '$2 ~ /python|kit/'`.
- Nur ein Isaac-Prozess gleichzeitig (8 GB VRAM).
