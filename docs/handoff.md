# Handoff

_Wird durch `/handoff` am Session-Ende aktualisiert._

---

## Stand 2026-10-12 nachmittags (Nachtlauf 2026-10-11/12 fertig ausgewertet, Plan `docs/nachtlauf-2026-10-12.md`)

### Zuletzt gearbeitet an

1. **Leaderboard v3** (`experiments.py` → `WUNSCH`, `leaderboard_v3`; Störbedingung in `eval_policy.py --stoerung`), am Nachmittag überarbeitet (Leon): alle Größen nur über erfolgreiche Seeds, Kippen inakzeptabel bei 45°, Objektweg 150 mm, Unterarm nur Info, Untergrenze 0,1, Spalte Top = bester Seed. Seitlich EXP-024 0,64 ★ (Top 0,79) vor Regel EXP-014 0,55, EXP-022 0,49, EXP-027 0,45 ★.
2. **Aktionsraum wie Dexsuite** (`pib_grasp/rsl_rl_ext.py` bounds_loss über die entropy-Property, `RslRlPpoActorCriticBoundsCfg`, `dexsuite_action_space()`): EXP-027 80 %, 2/5, Kippen 44°, Unterarm 51°, Index 0,06; EXP-031 (Actor 512-256-128) 75 %, 3/5, gleiches Kippen; **EXP-033** (bounds_loss, Unterarm/Handgelenk wieder 0,03) 79 %, 4/5, Kippen 30°, Unterarm 34°, Index 0,17; **EXP-032** (großes Netz, 4096 Umg. × 600 It.) 85 %, 5/5, Kippen 30°, Unterarm 43°, aber Unruhe 3,85 (Leitplanke), Index 0,08.
3. **Von oben** (`env_cfg_oben.py` auf gefundene Pose 20°/Rotator 75°/Höhe je Objekt, `analyse_reset --greifart oben` 2/256 ≤ 1 N): Regel EXP-028 **100 %, Robust 99 %, Index 0,92**; Spezialisten EXP-029 (Rezept 027) 99 % / EXP-030 (Rezept 022) 100 % — beide drehen den Unterarm auf 90°, Objekt gekippt (81–106°) und ~10 cm verschoben, Index (ohne Kippwinkel) 0,12/0,18.
4. Ergebnis/Schluss als **Entwurf** in `EXP-027…033_experiment.yaml` (Urteile Leon); Kette umgestellt (`scratchpad/nacht2/kette3.sh`: 031 → 033 → 032), damit die Ursachenklärung früher vorlag.

### Offene Punkte

- **Kippen seitlich**: Reihenfolge bei Skala 0,03 Filter 13° < ±1 20° < nur bounds_loss 30°; Skala 0,1 → 44°, großes Netz + Budget 30°. Leistung nirgends gesichert verschieden. bounds_loss ersetzt die Begrenzung nicht (Rauschen geht ungekappt an die Servos). Nachtrag ADR-022 („Aktionsraum als Regularisierer“).
- **Kippen von oben** liegt an der Aufgabe (Belohnung ohne Orientierung, wie Dexsuite Lift), nicht an der Skala — EXP-030 mit 0,03 + ±1 dreht genauso.
- Grundsatzfrage an Leon: Unterarm/Handgelenk aus dem Aktionsraum (Arm hält die Vorgreifpose, ADR-018) oder Kosten auf die Abweichung (`joint_deviation_l1`) — Entscheidung vom 2026-10-06 war „Unterarm bleibt“ (current-sprint 5h).
- Videos von EXP-027/029/030 noch nicht von Leon gesichtet — „Objekt auf der Handfläche“ ist Vermutung.
- Urteile in `EXP-027…033_experiment.yaml` sind Entwürfe (Feld `urteil` leer).
- Index „oben“ misst die Objektlage nicht mehr (Kipp raus, Unterarm nur Info) — Spezialisten EXP-029/030 kommen auf 0,49/0,55, obwohl sie das Objekt 81–106° kippen. Klären: Lage-Kriterium je Objekt (Kugel egal, Dose/Schachtel nicht)?

### Nächste Schritte (in Reihenfolge)

1. Leon: Videos sichten (`beste_videos/` von EXP-024, EXP-027, EXP-028, EXP-030), Urteile in den YAMLs bestätigen.
2. Präsentation Do 2026-10-15 — Folien-Zahlen unten; Sim-to-Real-Lücken nur nennen (Skala/Servo-Steifigkeit, Latenz, Pleuel-Umrechnung in der Firmware).
3. Nach der Pause: Kosten gegen Kippen wählen — (1) `joint_deviation_l1` auf Unterarm/Handgelenk, (2) Kippstrafe ab t = 0, (3) CaT (Chane-Sane et al. 2024); Gewicht per `reward_diag`, Eltern EXP-033.
4. Offen: Budget fürs kleine Netz (EXP-024-Rezept × 4096/600), M2 auf dem Board.

### Wichtige Kontextdetails

- **Folien-Zahlen**: seitlich bestes Rezept EXP-024 (87 %, 5/5, Robust 72 %), Regel 69 %; von oben Regel 100 %/Robust 99 % — mit guter Vorgreifpose genügt eine Regel; int8 EXP-023 s43: alle Schichten NPU, 71 kB, −1,4 PP.
- Reward-Abschätzung (Haltephase je s): aufrecht 10° ≈ 12,2, gekippt 44° ≈ 5,0 → Belohnung bevorzugt aufrecht; Kippen ist lokales Optimum (robuster gegen Aktionsrauschen, kostet in der Greifphase < 2 s nichts). Trainingslogs: success EXP-024 3,5–4,2 vs EXP-027 1,7–2,4 (max ≈ 5,6).
- Skala 0,03 an Unterarm/Handgelenk heißt ≤ 34 % Moment und ~100 °/s — wirkt als Regularisierer; Finger (0,1 > 5° Sättigung) hatten immer volles Moment. Vergleiche EXP-004–026 bleiben gültig (gleicher Aktionsraum).
- EXP-027 hatte ggü. EXP-024 drei Änderungen (Skala, Filter weg, Begrenzung weg) — im Bericht so benennen.
- Kipp-Streuung ±3° der Vorgreifpose oben bewusst weggelassen (Plan sah sie vor); Training nur Höhe ±5 mm, Lage ±1 cm.
- TensorBoard-Werte lesen: `~/IsaacLab/isaaclab.sh -p <skript>` (conda-Python hat kein numpy); Hilfsskript `scratchpad/tb_rewards.py`.
- Firmware: Ziel = gemessene Stellung + Skala·a (Skala je Lauf in `params/env.yaml` → `actions.servos.scale`), dazu Begrenzung/Filter wie im Training; Handgelenk über die Umkehrung von `wrist_transmission()` aufs Pleuel.
- Während `experiments.py run` nichts unter `isaac_lab/` ändern; Prozesse nie per `pkill -f`; Kette nicht durch Editieren des laufenden Bash-Skripts ändern, sondern Eltern-Bash beenden und neues Skript auf die PID warten lassen.
