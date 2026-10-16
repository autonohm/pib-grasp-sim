# Getting Started

Von null bis „die Hand greift“. Alle Befehle aus dem Wurzelverzeichnis des Klons (beliebiger Ort) — in jedem neuen Terminal zuerst dorthin `cd`.
Versionen, mit denen alles entwickelt und geprüft wurde, stehen am Ende.

## 0 — Voraussetzungen

- Ubuntu 24.04, NVIDIA-GPU mit ≥ 8 GB VRAM, Treiber ≥ 550 (entwickelt mit 580).
- **Isaac Sim 5.1** nativ nach `~/isaacsim/` — NVIDIA-Doku [docs.isaacsim.omniverse.nvidia.com](https://docs.isaacsim.omniverse.nvidia.com)
  → Installation → Workstation.
- Für Weg A zusätzlich **ROS 2 Jazzy**:
  ```bash
  sudo apt install ros-jazzy-desktop ros-jazzy-ros2-control ros-jazzy-ros2-controllers \
                   ros-jazzy-controller-manager ros-jazzy-robot-state-publisher
  ```
- Für Weg B und C zusätzlich **Isaac Lab 2.3.2** (unten).

```bash
git clone <repo-url> pib-grasp-sim && cd pib-grasp-sim
```

Feste Pfade gibt es nicht: Die Isaac-Sim-Skripte finden das Repo über die geöffnete Stage bzw. ihren eigenen Ort
(sonst `PIB_GRASP_SIM_ROOT` setzen), die Isaac-Lab-Skripte über `ISAACLAB_PATH` aus der conda-Umgebung
(Standard `~/IsaacLab`).

---

## Weg A — Digitaler Zwilling mit ROS 2

**v4 und v5 laufen parallel** (eigene USD, eigenes ROS-2-Paket, eigene Launch-Dateien). Gearbeitet wird mit v5; v4 ist die
ältere, verifizierte Referenz.

| | v4 (Referenz) | v5 (aktuell) |
|---|---|---|
| USD | `isaac_sim/usd/pib_upperbody_v4.usd` | `isaac_sim/usd/pib_upperbody_v5.usd` |
| ROS-2-Paket | `pib_description_v4` | `pib_description_v5` |
| Launch | `pib_sim.launch.py` | `pib_sim_v5.launch.py` |
| Demo | `test_client_pickup` / `_putdown` | `test_client_pickup_v5` / `_putdown_v5` |
| Gelenknamen | `dof_*` | ohne Präfix, Daumen-Mittelgelenk `tip` statt `distal` |

> **Nie beide Stacks gleichzeitig** — sie nutzen dieselben Topics (`/pib/hw/joint_commands`, `/pib/hw/joint_states`).

**1. Workspace bauen** (einmalig): `source /opt/ros/jazzy/setup.bash && cd ros2_ws && colcon build && cd ..`

Jedes Terminal braucht einmal `source ros2_ws/env.sh` (aus dem Repo-Ordner): schaltet `.venv`/conda ab, sourct ROS 2 Jazzy
und den Workspace, setzt `ROS_DOMAIN_ID=0` (überall gleich, sonst sehen sich Isaac und ros2_control nicht; anderer Wert über
`PIB_ROS_DOMAIN_ID`). Umgebungsvariablen gelten nur in der Shell, die sie setzt — deshalb je Terminal. Bequemer mit einem Alias
in `~/.bashrc`: `alias pib='source <Pfad zum Klon>/ros2_ws/env.sh'`.

**2. Isaac Sim starten** (Terminal 1) — ROS 2 **vorher** in derselben Shell sourcen (Isaac nutzt sein eigenes rclpy):
```bash
source ros2_ws/env.sh
~/isaacsim/isaac-sim.sh
```
Im Fenster: *File → Open* → `isaac_sim/usd/pib_upperbody_v5.usd`, *Window → Script Editor* → `isaac_sim/start.py` ausführen
(setzt Antriebe, Servo-Modell, Fingerkopplung, Grenzen, T-Pose), dann **Play**. Der Action Graph ist Teil der USD und läuft
mit.

**3. ros2_control starten** (Terminal 2):
```bash
source ros2_ws/env.sh
ros2 launch pib_bringup pib_sim_v5.launch.py       # läuft im Vordergrund weiter
```

**4. Prüfen und Demo** (Terminal 3, ebenfalls `source ros2_ws/env.sh`): `ros2 topic list` (zeigt `/pib/hw/joint_states`,
`/pib/hw/joint_commands`, `/pib/fingertip_forces`), `ros2 control list_controllers` (beide „active“), dann
`ros2 run pib_bringup test_client_pickup_v5` und `test_client_putdown_v5`.
Weitere Tests: `test_client_mimic_v5 --finger all` (Fingerkopplung), `test_client_mimic_load_v5 --reset` (Finger gegen Tisch).

Schnittstelle für andere Teams (Topics, Einheiten, Fingerkräfte): [conventions.md](conventions.md) → „ROS2-Konventionen“.

---

## Isaac Lab installieren (für Weg B und C)

Nach NVIDIA-Doku „Installation using Isaac Sim Binaries“, in einer **eigenen conda-Umgebung** — nie in Isaac Sims Python:
```bash
git clone -b v2.3.2 https://github.com/isaac-sim/IsaacLab.git ~/IsaacLab && cd ~/IsaacLab
ln -s ~/isaacsim _isaac_sim
./isaaclab.sh --conda env_isaaclab          # legt die Umgebung an (Miniconda)
conda activate env_isaaclab
./isaaclab.sh --install                     # Isaac Lab + rsl_rl
pip install onnxruntime==1.30.0 huggingface_hub   # optional: int8-Prüfung (M2), Policy-Sicherung
```
Fallstricke (ADR-015): eine aktive Projekt-`.venv` vorher mit `deactivate` verlassen (`isaaclab.sh` nimmt die gerade aktive
Python); baut `flatdict` nicht, `pip install "setuptools<81"` und ohne Build-Isolation nachinstallieren; numpy bleibt auf 1.26.

Isaac-Lab-Skripte immer so starten: `~/IsaacLab/isaaclab.sh -p isaac_lab/<skript>.py …` (bei aktiver `env_isaaclab`).

Prüfen: `~/IsaacLab/isaaclab.sh -p isaac_lab/check_hand_asset.py` (Fenster: Mimic-Kopplung, Sensoren, Antriebe).

---

## Weg B — Fertige Greif-Policy ansehen

1. ZIP einer Policy aus dem [Release v0.1](../../../releases/tag/v0.1-praesentation) laden und
   entpacken, z. B. `pib-grasp-exp-036-s42.zip` (CAPS + Stall-Grenze, ruhigste der fünf). Inhalt: `policy.pt`, `policy.onnx`,
   Trainingskonfiguration, Bewertung, README mit dem passenden Befehl.
2. Im Fenster ansehen (16 Hände, Echtzeit):
   ```bash
   ~/IsaacLab/isaaclab.sh -p isaac_lab/eval_policy.py --policy pib-grasp-exp-036-s42/policy.pt --action_scale 0.1 \
       --max_kipp_deg 45 --num_envs 16 --episodes 16 --real_time
   ```
   Andere Objekte mit `--objekt` (Katalog `OBJECTS` in `isaac_lab/pib_grasp/env_cfg.py`, z. B. `quader_7x7x20`,
   `ycb_006_senf`). Die Optionen zum Aktionsweg (`--action_scale`, `--action_filter`, `--action_clip`) müssen zum Training
   passen — sie stehen in der README jeder ZIP.
3. Ohne Fenster bewerten wie im Protokoll eval-v2: Optionen `--headless --num_envs 256 --episodes 1000`.

Was die Policy sieht und tut (105 Eingänge, 8 Aktionen, Reihenfolge, Skalen): [conventions.md](conventions.md) →
„Schnittstelle Policy ↔ echte Hand“.

---

## Weg C — Selbst trainieren und vergleichen

Training und Bewertung laufen über das Experiment-Framework (ADR-016): je Experiment eine Hypothese und **genau eine
Änderung** gegenüber den Eltern, 5 Seeds, festes Bewertungsprotokoll, automatischer Bericht. Orchestrierung mit System-Python
bei aktiver conda-Umgebung (System-Python braucht einmalig `sudo apt install python3-numpy python3-yaml python3-scipy`):
```bash
conda activate env_isaaclab
/usr/bin/python3 isaac_lab/experiments.py new --eltern EXP-036 --kurz mein_test --titel "…"   # Ordner + YAML anlegen
# experiments/EXP-NNN_mein_test/EXP-NNN_experiment.yaml: hypothese, aenderung, training.task ausfüllen
/usr/bin/python3 isaac_lab/experiments.py run EXP-NNN       # Kurztest → 5 × Training → Bewertung → Bericht
/usr/bin/python3 isaac_lab/experiments.py done              # index.md, leaderboard.md (+ Sicherung, falls eingerichtet)
```
Eine neue Trainingsvariante ist eine Konfigurationsklasse in `isaac_lab/pib_grasp/env_cfg.py` plus Task-ID in
`isaac_lab/pib_grasp/__init__.py`. Vor jedem Lauf: `isaac_lab/tools/reward_diag.py` (Größenordnung der Belohnungsterme), bei
neuen Objekten `tools/analyse_reset.py` und `tools/check_objekt.py`. Ablauf, Metriken, Statistik: [experiments/README.md](../experiments/README.md).

Nur ein Isaac-Prozess gleichzeitig (8 GB VRAM). Logs und Checkpoints landen in `logs/` (nicht im Git).

---

## Bekannte Fallstricke

| Problem | Lösung |
|---|---|
| `ModuleNotFoundError: rclpy._rclpy_pybind11` | ROS 2 **vor** Isaac Sim in derselben Shell sourcen |
| `controller_manager` wartet auf `/robot_description` | `robot_state_publisher` läuft im Launch mit — Launch-Datei aus dem Repo nutzen |
| `Package 'pib_bringup' not found` | `source ros2_ws/env.sh` in dieser Shell (aus dem Repo-Ordner) |
| Hand schließt in die falsche Richtung | nach einem Onshape-Neuimport `isaac_sim/tools/flip_joint_sign.py` ausführen (ADR-007) |
| `/pib/fingertip_forces` leer nach Graph-Änderung | per Skript gesetzte OmniGraph-Werte stehen nur im laufenden Graph → speichern **und neu öffnen** (ADR-013) |
| v5-Stage stürzt bei Play ab (`isaacsim.sensors.physics.plugin`) | Compound-Subgraph im Action Graph entfernen, Kraft-Knoten flach neu bauen (ADR-013) |
| Isaac Lab installiert in die falsche Python | nur in `conda activate env_isaaclab` arbeiten |
| Skript hängt am Ende | bekannt: `simulation_app.close()` hängt — Skripte schreiben ihren Bericht und enden mit `os._exit(0)` |

## Versionen (geprüft)

| Komponente | Version |
|---|---|
| Ubuntu / Treiber / GPU | 24.04 / 580.178 / RTX 3060 Ti 8 GB |
| Isaac Sim | 5.1.0 |
| Isaac Lab | 2.3.2, rsl-rl-lib 3.1.2 |
| Python (env_isaaclab) | 3.11, torch 2.7.0+cu128, numpy 1.26.0, gymnasium 1.2.1, onnxruntime 1.30.0 — alle Pakete: [env_isaaclab-freeze.txt](env_isaaclab-freeze.txt) |
| ROS 2 | Jazzy |
| ST Edge AI Core (M2) | 4.0.1 |
