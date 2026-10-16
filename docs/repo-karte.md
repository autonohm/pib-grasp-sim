# Repo-Karte

Jeder Ordner und jedes Skript in einer Zeile, mit Status:
**aktuell** (Teil der laufenden Kette) · **Werkzeug** (wiederverwendbare Prüfung/Diagnose) · **einmalig** (Diagnose für eine
einzelne Frage, zur Nachvollziehbarkeit behalten) · **Altlast** (v4 oder abgelöst, läuft noch). Dateien werden bewusst nicht
verschoben: Experimentberichte, Logs und ADRs verweisen auf diese Pfade.

## Oberste Ebene

| Pfad | Status | Was |
|---|---|---|
| `README.md` | aktuell | Einstieg |
| `AGENTS.md`, `CLAUDE.md`, `.claude/` | aktuell | Regeln für KI-Coding-Assistenten (API-Regeln, Einheiten, Experiment-Pflicht); `CLAUDE.md` bindet `AGENTS.md` ein |
| `config/pib_hand_config_v5.py` | aktuell | Gelenknamen, Grenzen, Servo-Aktuatormodell ST3215/ST3095 (ADR-012), Handgelenk-Pleuel (ADR-014) — gemeinsame Quelle für Isaac Sim und Isaac Lab |
| `config/pib_hand_config_v4.py` | Altlast | dasselbe für v4 |
| `isaac_sim/` | aktuell | Digitaler Zwilling in Isaac Sim 5.1: USD-Stages mit Action Graph, Startskripte, Asset-Werkzeuge |
| `isaac_lab/` | aktuell | RL-Greifen in Isaac Lab 2.3.2: Aufgabe, Training, Bewertung, Experiment-Framework |
| `experiments/` | aktuell | ein Ordner je Experiment (Plan, Ergebnisse, Bericht, Diagramme, beste Videos), `leaderboard.md`, `index.md` |
| `ros2_ws/` | aktuell | ROS-2-Jazzy-Workspace: Roboterbeschreibungen v4/v5, `ros2_control`-Start, Demo-Clients; `env.sh` = Umgebung je Terminal |
| `pib_hand_left_urdf_v5/` | aktuell | `onshape-to-robot`-Export linke v5-Hand + Unterarm (Quelle von `pib_hand_left_v5.usd`); `config.json` verweist auf das Onshape-Dokument |
| `docs/` | aktuell | siehe unten |
| `videos/` | aktuell | Demo-Videos (Zwilling, erste Policies, YCB) |
| `logs/`, `outputs/` | ignoriert | Trainingsläufe, Checkpoints, Bewertungen (nicht im Git; Sicherung auf Hugging Face) |
| `LICENSE` | aktuell | AGPL-3.0 (Herkunft der pib-Daten und Fremdcode: README → Lizenz) |

## `isaac_sim/`

| Pfad | Status | Was |
|---|---|---|
| `usd/pib_upperbody_v5.usd` | aktuell | v5-Oberkörper + Action Graph (ROS-2-Gelenkzustände, Fingerkräfte) |
| `usd/pib_hand_left_v5.usd` | aktuell | linke Hand + Unterarm für Isaac Lab, Mimic/Grenzen/Antriebe eingebrannt |
| `usd/configuration/` | aktuell | Teil-Layer der v5-Stage (Basis, Physik, Roboter, Sensoren) |
| `usd/pib_upperbody_v4.usd` | Altlast | v4-Referenzstage |
| `start.py`, `setup_stage.py` | aktuell | vor Play ausführen: Antriebe, Servo-Modell, Mimic Joints, Grenzen, Startpose |
| `tools/bake_hand_asset_v5.py` | Werkzeug | Mimic/Grenzen/Antriebe in die Hand-USD einbrennen (nach Änderungen an der Config erneut) |
| `tools/audit_asset.py` | Werkzeug | Massen, Collider, Antriebe, effektive Gelenkträgheit, Stabilitätskennzahlen |
| `tools/build_contact_sensors_v5.py`, `tools/build_fingertip_force_graph_v5.py` | Werkzeug | Fingerspitzen-Sensoren und ihren ROS-2-Graph neu bauen (ADR-013) |
| `tools/inspect_action_graph.py` | Werkzeug | Inventur des Action Graph aus der USD |
| `tools/flip_joint_sign.py` | Werkzeug | Vorzeichen-Korrektur nach einem Onshape-Neuimport (ADR-007) |
| `tools/dump_pose.py` | Werkzeug | Pose-Sequenz für die Demo-Clients aufnehmen |

## `isaac_lab/`

| Pfad | Status | Was |
|---|---|---|
| `pib_hand_left_v5_cfg.py` | aktuell | Isaac-Lab-Asset: 7 Servos implizit, Handgelenk als `RemotizedPDActuator`, 9 passive Folgegelenke |
| `pib_grasp/env_cfg.py` | aktuell | Aufgabe „seitlich“ (Dexsuite-Muster), Objektkatalog `OBJECTS`, alle Trainingsvarianten |
| `pib_grasp/env_cfg_oben.py` | aktuell | Aufgabe „von oben“ |
| `pib_grasp/mdp.py` | aktuell | Belohnungen, Beobachtungen, Events, Abbrüche, PID-Lagrange-Grenze, Servo-Last, Armbewegung (Belastungstest) |
| `pib_grasp/agents/rsl_rl_ppo_cfg.py`, `pib_grasp/rsl_rl_ext.py` | aktuell | PPO-Einstellungen; bounds_loss und CAPS für rsl_rl |
| `pib_grasp/__init__.py` | aktuell | Gym-Task-IDs (eine je Trainingsvariante) |
| `train.py`, `play.py` | aktuell | dünne Hüllen um Isaac Labs rsl_rl-Skripte |
| `eval_policy.py` | aktuell | Bewertungsprotokoll eval-v2 (Aufgabenerfolg, Leitplanken, Belastungstest, Videos, Regel-Baselines) |
| `experiments.py` | aktuell | Experiment-Framework: `new`, `run`, `eval`, `belastung`, `medien`, `leaderboard`, `done` (ADR-016) |
| `plot_training.py` | aktuell | TensorBoard → SVG für die Berichte |
| `backup_policies.py` | aktuell | Läufe in ein Hugging-Face-Repo sichern |
| `check_hand_asset.py`, `scripted_grasp_test.py` | Werkzeug | Asset-Prüfung (Mimic, Sensoren, Antriebe); Machbarkeitsgriff ohne Policy |
| `tools/reward_diag.py` | Werkzeug | Größenordnung jedes Belohnungsterms je Phase — vor jeder Trainingsänderung |
| `tools/analyse_reset.py`, `tools/check_objekt.py`, `tools/check_multi.py`, `tools/ruhelage_objekt.py` | Werkzeug | Prüfungen für neue Objekte/Szenen (kein Kontakt beim Start, Ruhelage, Szenenbilder) |
| `tools/kalibrierdaten_int8.py`, `tools/quantisiere_int8.py` | Werkzeug | int8-Quantisierung für die NPU des STM32N6 (M2) |
| `tools/pruef_bewegung.py`, `tools/diag_stall.py`, `tools/diag_objektweg.py`, `tools/inspect_ycb.py` | Werkzeug | Physik des Belastungstests, Herkunft des Stalls je Servo, Objektweg, YCB-Assets |
| `tools/diag_anheben.py`, `tools/probe_*.py`, `tools/machbarkeit_oben.py`, `tools/suche_startpose_oben.py`, `tools/auswertung_startpose_oben.py`, `tools/debug_scene.py` | einmalig | Diagnosen zu einzelnen Fragen (2026-10-08 … 10-11), Ergebnisse in ADRs und `docs/protokoll/` |

## `ros2_ws/src/`

| Pfad | Status | Was |
|---|---|---|
| `pib_description_v5/` · `pib_description_v4/` | aktuell · Altlast | URDF + Meshes + `ros2_control`-Tags; v5-URDF = `onshape-to-robot`-Export + `ros2_control`-Block (Quelle der Gelenknamen), `onshape_config.json` = Link zum Onshape-Dokument |
| `pib_bringup/` | aktuell | Launch-Dateien, Controller-Konfiguration, Demo-Clients (Pickup/Putdown, Mimic-Tests) |
| `topic_based_ros2_control/` | Fremdpaket | Hardware-Interface-Bridge (eigene Lizenz) |

## `docs/`

| Pfad | Status | Was |
|---|---|---|
| `getting-started.md` | aktuell | Installation und drei Einstiegswege |
| `architecture.md`, `conventions.md`, `decisions.md` | aktuell | Aufbau, Einheiten/Vorzeichen/Namen/Schnittstellen, Entscheidungen ADR-001–023 |
| `repo-karte.md`, `glossar.md` | aktuell | diese Karte; Begriffe Doku (deutsch) ↔ Code |
| `weitermachen.md`, `hardware-annahmen.md` | aktuell | offene Aufgaben; Annahmen der Sim über die echte Hand |
| `literatur.md`, `literatur.bib` | aktuell | Quellen, auf denen das Repo aufbaut (BibTeX) |
| `tdp/` | aktuell | Abschnitt Greifen für das Team Description Paper RoboCup@Home: `grasping.tex` (zum Einfügen), `greifen.pdf` (Vorschau) |
| `int8/` | aktuell | Ergebnis der int8-Prüfung (M2) |
| `env_isaaclab-freeze.txt` | aktuell | `pip freeze` der conda-Umgebung (Referenz für exakte Versionen) |
| `protokoll/` | Protokoll | Projekt-Tagebuch: Sprint (`current-sprint.md`), Session-Übergabe (`handoff.md`), Nachtläufe, Pläne, Startpose-Suche |
| `archiv/` | Altlast | alte Pläne und Prompts |
