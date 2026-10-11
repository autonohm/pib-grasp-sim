# Handoff

_Wird durch `/handoff` am Session-Ende aktualisiert._

---

## Stand 2026-10-11 (morgens, nach dem Nachtlauf — committet, gepusht, Hugging Face gesichert)

### Zuletzt gearbeitet an

1. **Nachtlauf EXP-024–026** (je eine Änderung ggü. EXP-022, 5 Seeds): **EXP-024 Aktionsfilter** (α 0,3, `mdp.FilteredRelativeJointPositionAction`) 87 %, 5/5, Platz 1, Unruhe an den Servos 0,17 (0,36), Kippen 13°, Unterarm 11°, 78 N; EXP-025 Moment-Strafe (`mdp.servo_torque_l2`, −0,1) ohne Wirkung auf Stall; EXP-026 Fingerzahl keine Wirkung, unruhiger. Urteile als Entwurf in den YAMLs.
2. **int8 EXP-023 s43** (`docs/int8/EXP-023_s43.md`, `tools/kalibrierdaten_int8.py`, `tools/quantisiere_int8.py`, `eval_policy --onnx`): alle 4 Schichten NPU, 71 kB; int8 ggü. float −1,4 PP (nicht gesichert).
3. **Startpose „von oben“ gesucht** (`tools/suche_startpose_oben.py`, `tools/auswertung_startpose_oben.py` → `docs/startpose-oben/ergebnis.md`): 20° gekippt, Rollen 0°, Rotator 75°, Höhe je Objekt → Regel 90–100 % auf allen 6 Objekten (48 Episoden nachgeprüft, Plan „Ergebnis der Suche“).
4. **Framework**: Stall je Servo (eval_policy, beschreibend); Urteil/Befund/Leaderboard nutzen bei Filter-Policies „Unruhe wirksam“ statt rohe Unruhe (`experiments.verdict`); Durchsatz `experiments/_bench.json` (1024/2048/4096 → 19,9k/26,8k/56,4k Schritte/s).

### Offene Punkte

- **Entscheidungen Leon**: EXP-024 als neue Basis (Videos `EXP-024_aktionsfilter/beste_videos/`); Einsatz-Kandidat seitlich s43 (EXP-023) vs. bester Filter-Seed; Urteile EXP-012–026 bestätigen.
- `env_cfg_oben.py` steht noch auf 36,5° gekippt mit der Höhenregel `tip_height_for_object` — **nicht** auf die gefundene Pose umgestellt (Leon wollte erst sehen).
- Stall bleibt in allen Policies hoch; Ursache: volle relative Aktion (0,1 rad) > 5° Sättigungsfehler → blockierter Finger = volles Moment. Regel hält mit 0,2 ohne Stall (47 N).
- „Stall-Anteil“ (irgendein Servo) täuscht — EXP-024 s42: nur Zeigefinger 89 %, übrige ≤ 21 %; besser „Stall je Servo“ ansehen.
- Ungeklärt von gestern: Kugel-Rollen/Rotator-Sprung (waagrechte Pose) — mit neuer Pose erneut prüfen.

### Nächste Schritte (in Reihenfolge)

1. Leon: Videos EXP-024 sichten, Basis festlegen; Fenstertest „von oben“ mit der gefundenen Pose zeigen.
2. `env_cfg_oben.py` auf 20°/0°/Rotator 75° umstellen (Höhe je Objekt aus `docs/startpose-oben/ergebnis.md`), `analyse_reset.py --greifart oben` (≥ 256), dann Regel-Baseline „von oben“ (ADR-020) und Spezialist (Task `ObenMulti-v0`, Eltern: neue Basis).
3. Stall: Experiment auf EXP-024 mit kleinerer Aktionsskala der Finger oder stärkerer Moment-Strafe (Leon wählt), Kennzahl Stall je Servo.
4. M2 auf dem Board: `stedgeai validate` auf dem NUCLEO-N657X0 (STM32CubeIDE/-Programmer fehlen noch); Firmware: ±1-Clip und ggf. Filter α 0,3.
5. Optional: Experiment „4096 Umgebungen“ (2,8× Durchsatz, ändert PPO-Batch → eigenes Experiment).

### Wichtige Kontextdetails

- Gefilterte Policies: Bewertung braucht `--action_filter` (setzt `experiments.clip_args` automatisch aus `params/env.yaml` → `actions.servos.alpha`); roher Netzausgang springt stark (Unruhe roh ~3), das ist erwartet.
- Startpose-Suche: Hand-Root je Umgebung über `robot.data.default_root_state` gesetzt; Geometrie aus `probe_neigung_oben.py --dump` (`logs/startpose_oben/geometrie.npz`); Höhe = tiefste Spitze (auch Daumen).
- Prüfskript der gewählten Pose liegt nur im Scratchpad (Kopie von `suche_startpose_oben.py` mit `--pose/--hoehen`); bei Bedarf als Option ins Werkzeug übernehmen.
- Während `experiments.py run` keine Dateien unter `isaac_lab/` ändern — `run` prüft den Commit je Experiment (sonst „+lokal“) und jeder Seed importiert neu.
- `pkill -f`/`pgrep -f` mit Muster aus dem eigenen Befehl beendet die eigene Shell (Exit 144) — Prozesse über `ps -eo pid,comm,args | awk '$2 ~ /python|kit/'` finden.
- Der erste `bench`-Versuch brach bei 4096 ohne Spur ab, die Wiederholung lief — bei Abbrüchen einmal wiederholen.
