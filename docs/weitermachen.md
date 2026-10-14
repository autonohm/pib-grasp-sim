# Weitermachen — offene Aufgaben

Nach Nutzen für das Ziel „pib greift mit der echten Hand“ sortiert, je mit Einstieg (Datei/ADR). Stand v0.1 (2026-10-15).

## 1. Policy auf den Chip (M2)

- **Was:** die int8-Policy auf dem NUCLEO-N657X0 laufen lassen (`stedgeai validate`), Rechenzeit je Schritt messen.
- **Stand:** int8-Quantisierung nach ST-Vorgabe ist geprüft — alle Schichten auf der NPU, 71 kB, int8 gegenüber float
  −1,4 Prozentpunkte (nicht gesichert). Es fehlen STM32CubeIDE/-Programmer und der Test auf dem Board.
- **Einstieg:** `docs/int8/EXP-023_s43.md`, `isaac_lab/tools/kalibrierdaten_int8.py`, `isaac_lab/tools/quantisiere_int8.py`,
  `docs/conventions.md` → „ST Edge AI“; Policies im Release v0.1.

## 2. Echte Hand vermessen (M3)

- **Was:** Servo-Kennwerte, Sehne, Feder, Übersetzung, FSR-Kennlinie messen und in die Sim übernehmen.
- **Einstieg:** [hardware-annahmen.md](hardware-annahmen.md) (Liste mit Messvorschlägen), `config/pib_hand_config_v5.py`.

## 3. Sehne und Feder ins Aktuatormodell

- **Was:** Finger-Servos können real nur ziehen, eine Feder öffnet. In der Sim ein explizites Aktuatormodell mit
  asymmetrischer Momentgrenze (Zug: Servo, Öffnen: Federkennlinie) statt des symmetrischen PD; danach neu trainieren.
- **Warum:** größte bekannte Sim-to-Real-Lücke; heute kann die Policy Finger aktiv öffnen.
- **Einstieg:** `isaac_lab/pib_hand_left_v5_cfg.py` (Vorbild für explizite Aktuatoren: Handgelenk mit `RemotizedPDActuatorCfg`,
  ADR-014), `docs/protokoll/nachtlauf-2026-10-14.md` (Diagnose).

## 4. Firmware-Schnittstelle (mit Motorcontrol)

- **Was:** Die Firmware muss genau den Aktionsweg des Trainings umsetzen: relative Ziele × Skala, Begrenzung bzw. Filter je
  Rezept, Winkelgrenzen, Umrechnung Fingerwinkel ↔ Servo-Schritte, Beobachtungsvektor in derselben Reihenfolge und mit Verlauf.
  Dazu eine Moment- oder Stromgrenze im Servo (bewährt bei LEAP Hand, OpenAI Dactyl).
- **Einstieg:** `docs/conventions.md` → „Schnittstelle Policy ↔ echte Hand“, `params/env.yaml` jedes Laufs.

## 5. Policy verbessern

| Thema | Stand | Einstieg |
|---|---|---|
| **Kippen** (häufigste Fehlerart: hält, aber > 45° gekippt) | gelöst nur über kleinere Unterarm-Schrittweite oder Filter (EXP-024, EXP-033) | eigene Nebenbedingung auf den Kippwinkel (wie die Stall-Grenze, `mdp.StallLagrange`) |
| **Servo-Last verteilen** | Grenze je Servo + Fingerzahl senkt den Überlastschutz 85 → 21 %, kostet Griffreserve (EXP-040, 2/5 Seeds) | mehr Seeds (10), Grenze langsam einblenden wie CaT, Grenze auf die Lauflänge statt den Anteil |
| **Mehr Finger** | Belohnungen allein wirken nicht (EXP-005, 026, 041) | Zielgriffposen oder Demonstrationen (UniDexGrasp, DAPG), z. B. aus der Regel-Baseline mit 4,9 Fingern |
| **Objekt nicht verschieben** | Strafe wirkte, machte aber unruhig (EXP-023) | dieselbe Strafe auf der CAPS-Basis (EXP-036) |
| **Kraft dosieren** | Policies drücken voll | nach der Messung der echten Servo-Grenzen |
| **Zuverlässigkeit** | oft nur 2–4 von 5 Seeds | mehr Budget (EXP-032: 5/5, aber unruhig), Curriculum |

Vor jeder Änderung: ein Experiment anlegen (`experiments.py new`), `tools/reward_diag.py`, genau eine Änderung, 5 Seeds
([experiments/README.md](../experiments/README.md)). Ausgangspunkt ist die **Basis EXP-036** (CAPS + Stall-Grenze, ohne Aktionsfilter; ADR-023), Alternative mit Filter EXP-024 —
[Leaderboard](../experiments/leaderboard.md).

## 6. Weitere Greifarten und Team-Anbindung

- **Von oben:** Mit der gefundenen Vorgreifpose reicht eine Regel (EXP-028, 100 %) — `docs/protokoll/plan-griff-von-oben.md`,
  `docs/protokoll/startpose-oben/`.
- **Planer und Arm:** Greifart je Objektkategorie wählen (zuerst Regeltabelle), Vorgreifpose und Signal „Griff steht“ mit dem
  IK-Team abstimmen — [architecture.md](architecture.md) → „Ziel-Architektur Greifen“, ADR-018.
- **Hakengriff** (Tasche): zurückgestellt.

## 7. Infrastruktur

- Bewertung in einem Isaac-Prozess je Seed statt je Bedingung (~¼ schneller), `docs/protokoll/current-sprint.md` Punkt 6.
- Selbsttest-Skript (Asset, Mini-Training, Bewertung in ~5 min) und Durchlauf der Anleitung auf einem frischen Klon.
- Absolute Pfade in drei USD-Dateien (Metadaten aus dem Import) im GUI prüfen und relativ speichern.
- Leaderboard zusätzlich als CSV/HTML (sortierbar).
