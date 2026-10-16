# pib-grasp-sim

Digitaler Zwilling des humanoiden Roboters **pib** (Oberkörper v4/v5) in NVIDIA Isaac Sim 5.1 — über ROS 2 steuerbar —
und **Greifen per Reinforcement Learning** in NVIDIA Isaac Lab 2.3.2 für die reale linke v5-Hand (8 Servos, 5 Kraftsensoren,
Ziel-Hardware STM32N657 mit NPU). Entstanden als Projektarbeit für RoboCup 2027 @Home.

![Pickup-Demo im digitalen Zwilling](videos/isaac_sim_pib_v5_pickup_putdown_demo.webm)

## Was funktioniert (Stand v0.1, 2026-10-15)

| Teil | Stand |
|---|---|
| Digitaler Zwilling v5: Fingerkopplung (Mimic Joints), Servo-Modell nach Datenblatt, Handgelenk über Pleuel, Kontaktsensoren an allen Fingerspitzen | ✓ ([ADR-011–014](docs/decisions.md)) |
| ROS 2 Jazzy über `ros2_control` und Action Graph, Pickup-/Putdown-Demo | ✓ v4 und v5 |
| Greif-Policy „Kraftgriff seitlich“ (blind: nur Gelenkwinkel + Fingerkräfte) | 83–87 % Erfolg, Regel-Baseline 69 % ([Leaderboard](experiments/leaderboard.md)); Basis **EXP-036** (CAPS + Stall-Grenze, ADR-023) |
| Griff „von oben“ | Regel mit guter Vorgreifpose 100 % — RL nicht nötig ([EXP-028](experiments/)) |
| Policy int8 auf der NPU des STM32N657 | geprüft mit `stedgeai analyze` (71 kB, alle Schichten auf der NPU) — noch nicht auf dem Board |
| Echte Hand | **noch nicht getestet** — offene Lücken in [Hardware-Annahmen](docs/hardware-annahmen.md) |

## Einstieg

1. **[Getting Started](docs/getting-started.md)** — Installation (Isaac Sim, Isaac Lab, ROS 2) und drei Wege:
   - **A — Zwilling mit ROS 2:** Isaac Sim starten, `ros2_control`, Pickup-Demo
   - **B — Fertige Greif-Policy ansehen:** Policy aus dem [Release v0.1](../../releases/tag/v0.1-praesentation) laden, im Fenster greifen lassen (~30 min inkl. Isaac-Lab-Installation)
   - **C — Selbst trainieren und vergleichen:** ein Experiment anlegen, trainieren, bewerten ([experiments/README.md](experiments/README.md))
2. **[Repo-Karte](docs/repo-karte.md)** — jeder Ordner und jedes Skript in einer Zeile: aktuell, Werkzeug, einmalige Diagnose oder Altlast.
3. **[Weitermachen](docs/weitermachen.md)** — offene Aufgaben nach Nutzen, je mit Einstiegsdatei.
4. **[Hardware-Annahmen](docs/hardware-annahmen.md)** — was die Simulation über die echte Hand annimmt und wie man es misst.

Vertiefung: [Architektur](docs/architecture.md) · [Konventionen](docs/conventions.md) (Einheiten, Vorzeichen, Namen,
Schnittstelle Policy ↔ Firmware) · [Entscheidungen ADR-001–023](docs/decisions.md) · [Experimente](experiments/README.md) ·
[Glossar Deutsch ↔ Code](docs/glossar.md) · [Projekt-Protokoll](docs/protokoll/) (Sprint-Tagebuch, Nachtläufe, Pläne).

**Sprache:** Dokumentation, Berichte und Ausgaben der Werkzeuge sind deutsch; Code-Kommentare englisch. Bezeichner,
Kommandozeilen-Optionen und JSON-Schlüssel bleiben, wie sie sind (z. B. `--objekt`, `--bedingung`), damit alte Berichte
und Logs gültig bleiben — Übersetzung im [Glossar](docs/glossar.md).

## Voraussetzungen

Ubuntu 24.04, NVIDIA-GPU mit ≥ 8 GB VRAM (entwickelt auf RTX 3060 Ti, Treiber 580), Isaac Sim 5.1, Isaac Lab 2.3.2 in einer
conda-Umgebung, ROS 2 Jazzy (nur für Weg A). Training: 1024 Umgebungen × 300 Iterationen ≈ 12 min je Seed.

## Branches

| Branch / Tag | Inhalt |
|---|---|
| `main` | aktueller Stand: Zwilling + RL-Greifen (2026-10-16 aus `feature/rl-grasping` übernommen) |
| `feature/rl-grasping` | bisheriger Arbeitsbranch, identisch mit `main` |
| Tag `v0.1-praesentation` | Stand zur Präsentation 2026-10-15, Release mit den 5 besten Policies |
| Tag `archiv/ros2-control` | ältere Team-Integration (robot_io, ControlMode, Sequenz-Executor, LSTM-Pipeline) — nicht weitergeführt |
| Tag `archiv/session-collision-dev` | WIP Servo-Steuerung + Collision Groups (Juni 2026), nie übernommen |
| Tags `backup/*` | Stände vor Umbauten (ADR-009/011) |

Die früheren Branches `experiment/omnigraph-lightweight`, `sandbox` und `feature/ros2-control` sind vollständig in `main`
enthalten und wurden 2026-10-14 gelöscht.

## Lizenz

**AGPL-3.0** ([LICENSE](LICENSE)), wie die pib-Repos von isento. Die pib-Geometrie (Meshes, URDF, USD) ist aus dem öffentlichen
Onshape-Modell von pib (isento GmbH, [pib.rocks](https://pib.rocks)) abgeleitet, das isento unter GPL-3.0
([pib-stls](https://github.com/pib-rocks/pib-stls)) bzw. AGPL-3.0 ([digital_twin](https://github.com/pib-rocks/digital_twin))
veröffentlicht. Fremdcode mit eigener Lizenz: `ros2_ws/src/topic_based_ros2_control/` (BSD, PickNik); Terme in
`isaac_lab/pib_grasp/` sind an Isaac Labs Dexsuite angelehnt (BSD-3-Clause, NVIDIA). YCB-Objekte und Isaac-Sim-Assets liegen
nicht im Repo, sie werden zur Laufzeit von NVIDIAs Asset-Server geladen. Trainierte Policies: [Release v0.1](../../releases/tag/v0.1-praesentation)
und alle Läufe auf Hugging Face [`churro206/pib-grasp-policies`](https://huggingface.co/churro206/pib-grasp-policies).

## Autor

Leon (Projektarbeit 2026).
