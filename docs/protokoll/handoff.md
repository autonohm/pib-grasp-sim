# Handoff

_Wird durch `/handoff` am Session-Ende aktualisiert._

---

## Stand 2026-10-16 — Übergabe (Ende der Projektarbeit)

Die Projektarbeit endete mit der Präsentation am 2026-10-15; der ursprüngliche Autor arbeitet nicht weiter daran.
Diese Seite ist der Einstieg für alle, die übernehmen — Menschen wie KI-Assistenten. Allgemeiner Einstieg: `README.md`,
`docs/getting-started.md`, `docs/weitermachen.md`, `AGENTS.md`.

### Was gilt

- **Basis Kraftgriff seitlich: EXP-036** (CAPS + PID-Lagrange auf den Servo-Stall, ohne Aktionsfilter; ADR-023). Leistung
  83 %, 4/5 Seeds, Unruhe 0,04, Servo-Last real 13 %, Transport 95 %. Top-Seed s42 im Release `v0.1-praesentation`.
  Alternative mit Aktionsfilter: EXP-024 (Index v3 knapp vorn, braucht den Filter in der Firmware).
- **Von oben**: Regel EXP-028 mit gefundener Vorgreifpose (100 %) — RL nicht nötig.
- **Bewertung**: Protokoll eval-v2, Leaderboard v3 (Wünschbarkeitsindex mit „Servo-Last real“); alle Urteile EXP-000–041
  bestätigt (2026-10-14).
- **Repo**: Name **pib-grasp-sim** (vorher pib-hand-sim), Lizenz **AGPL-3.0** wie die pib-Repos von isento (pib-Geometrie
  dort GPL-3.0/AGPL-3.0, README → Lizenz); Arbeitsbranch `main` (`feature/rl-grasping` identisch); Doku deutsch, Code-Kommentare englisch; alte
  Branches als Tags `archiv/*`. Keine festen Pfade: Isaac-Sim-Skripte finden das Repo selbst (`PIB_GRASP_SIM_ROOT`),
  Isaac Lab über `ISAACLAB_PATH`; HF-Sicherung nur mit `PIB_HF_REPO`.
- **Policies**: alle 185 Läufe öffentlich auf Hugging Face `churro206/pib-grasp-policies` (Model Card AGPL-3.0), die fünf
  besten als ZIP im Release `v0.1-praesentation`; Nahansicht-Videos (2x2) für EXP-036, EXP-014, EXP-040.

### Zuletzt gearbeitet an

1. Nachtlauf 2026-10-13/14: EXP-038–041 (Stall wie am echten Servo, Grenze je Servo, Fingerzahl) —
   `docs/protokoll/nachtlauf-2026-10-14.md`; neue Kennzahl „Servo-Last real“, alle 24 Policies nachbewertet.
2. Abgabe für künftige pib-Studierende (`docs/protokoll/plan-abgabe.md`): neue Einstiegsdoku, Release mit 5 Policies,
   Aufräumen (Duplikate, alte Branches), absolute USD-Pfade relativ, Kommentare englisch, `gitleaks` ohne Funde.
3. ADR-023 (Basis EXP-036, Servo-Last real), Urteile eingetragen, `docs/env_isaaclab-freeze.txt`.

### Offene Punkte

- **Ungeprüft im GUI**: `isaac_sim/usd/pib_upperbody_v5.usd` lädt seine Roboter-Layer seit 2026-10-14 über relative Pfade
  (vorher `file:/home/…`). Offline geprüft (alle Layer aufgelöst, 44 Gelenke) — einmal öffnen, `start.py`, Play, Pickup-Demo.
- Anleitung `docs/getting-started.md` nie auf einem frischen Klon durchgespielt; kein Selbsttest-Skript.
- **Ungeprüft im GUI**: neue Repo-Suche der Isaac-Sim-Skripte (2026-10-16, außerhalb von Isaac getestet) — beim GUI-Test oben mit.
- Repo seit 2026-10-16 bei der Schule: `autonohm/pib-grasp-sim` (alte Adressen leiten weiter). HF-Repo
  `churro206/pib-grasp-policies` bleibt beim Autor, öffentlich. Integration in den Roboter macht das Team als eigenes Paket,
  das dieses Repo klont (Absprache 2026-10-16) — dieses Repo bleibt eigenständig.
- `--kamera einzeln` (Nahansicht aus zwei Winkeln) nie gelaufen.

### Nächste Schritte (in Reihenfolge)

1. v5-Stage im GUI prüfen (Zwilling + ros2_control liefen 2026-10-16), Anleitung auf frischem Klon durchspielen.
2. Inhaltlich (`docs/weitermachen.md`): Policy auf den Nucleo (M2), echte Hand vermessen (M3, `docs/hardware-annahmen.md`),
   Sehne + Feder ins Aktuatormodell, Kippen als Nebenbedingung, EXP-040 mit 10 Seeds.

### Wichtige Kontextdetails

- Experimente nur über `isaac_lab/experiments.py` (Hypothese, genau eine Änderung, 5 Seeds, eval-v2) — `experiments/README.md`.
- Während `experiments.py run` nichts unter `isaac_lab/` ändern; Prozesse nie per `pkill -f`; nur ein Isaac-Prozess (8 GB VRAM).
- `RelativeJointPositionAction` kappt das Ziel nicht auf die Gelenkgrenzen → „Stall“ am blockierten Gelenk heißt |a| ≳ 0,7;
  das Handgelenk (RemotizedPDActuator) hat in Isaac Lab die Grenze 1e9 — Stall-Moment über `mdp.servo_effort_limit`.
- Isaac Lab 2.3.2: externe Kräfte über `asset.permanent_wrench_composer.set_forces_and_torques(..., is_global=True)`.
- PhysX integriert semi-implizit: freier Fall läuft um ½·g·h·t vor (h = 1/120 s) — bei Bahnvergleichen berücksichtigen.
- TensorBoard: λ/J_c unter `Lagrange/*` (je Servo bei EXP-039/040), CAPS unter `Loss/caps_*`.
