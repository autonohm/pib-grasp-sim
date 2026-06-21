# pib Hand Simulation

Simulationsprojekt für den RoboCup 2027 (@Home Liga).  
Ziel: Realitätsnahe Simulation der pib-Handmotorik in NVIDIA Isaac Sim — mit vollständiger
Ganzkörpersteuerung (44 DOF) und LSTM-gestützter Fingerkinematik, die schrittweise
auf echten AS5600-Sensordaten trainiert wird.

---

## Überblick

```
┌──────────────────────────────────────────────────────────────────┐
│                       Isaac Sim 5.1                              │
│                                                                  │
│   setup_stage.py ──→ Drives + Limits konfigurieren              │
│   test_hand_poses.py → Winken / Doppelbizeps / Peace             │
│   collect_data.py ──→ synthetische Trainingsdaten                │
│   run_inference.py ─→ LSTM compare / drive Modus                 │
│                                                                  │
│   robot_io.py ←──── einzige Isaac-API-Schicht (alle 44 DOF)     │
└──────────────────────────────────────────────────────────────────┘
         │                                    │
         ▼                                    ▼
   synthetic_*.npz                      real_*.npz
         └──────────── training/train.py ────┘
                              │
                       hand_lstm_*.pt
                    ┌─────────┴──────────┐
                    ▼                    ▼
           export_onnx.py        export_weights.py
                    │                    │
             *.onnx (STM32)     *_weights.npz
                                         │
                                  run_inference.py
                              ┌──────────┴──────────┐
                              ▼                     ▼
                         compare-Modus         drive-Modus
                         LSTM vs. PhysX        LSTM treibt Hand
```

Das LSTM lernt: `(Sollwinkel_t, Istwinkel_{t−1}) → Istwinkel_t`  
Es modelliert Trägheit, Reibung und Hysterese der Sehnenmechanik.

---

## Repository-Struktur

```
pib-hand-sim/
├── config/
│   └── pib_hand_config.py          # JOINT_SIGN, BODY_DOFS, HAND_DOFS,
│                                   # GRASP_POSES, servo_pose_to_joints()
├── control/
│   ├── __init__.py
│   └── direct.py                   # Direktsteuerung (Identity-Mapping)
│                                   # servo.py / neural.py kommen später
├── data/
│   ├── collect_real.py             # Echtdaten vom Nucleo aufzeichnen
│   ├── synthetic_*.npz             # Synthetische Trainingsdaten (nicht im Git)
│   └── real_*.npz                  # Echte AS5600-Daten (nicht im Git)
├── inference/
│   ├── evaluate_real.py            # LSTM vs. Messdaten offline vergleichen
│   ├── export_onnx.py              # PyTorch → ONNX (für STM32Cube.AI)
│   ├── export_weights.py           # PyTorch → .npz (für run_inference.py)
│   └── plot_inference.py           # Inferenzlogs aus Isaac Sim plotten
├── isaac_sim/
│   ├── usd/                        # USD-Modelle (v2–v7, selbst-enthaltend)
│   ├── _deprecated/                # alte Scripts (nicht mehr aktiv)
│   ├── _launch_helper.py           # Standalone-Launcher (lädt neueste USD)
│   ├── collect_data.py             # Synthetische Daten in Isaac sammeln
│   ├── inventory.py                # Debug: alle DOFs + Limits aus Stage ausgeben
│   ├── inventory_output.txt        # Letztes Inventar-Ergebnis (Referenz)
│   ├── manual_control_hand.py      # Interaktive Einzelgelenk-Steuerung
│   ├── robot_io.py                 # Einzige Isaac-API-Schicht — alle 44 DOF
│   ├── run_inference.py            # LSTM compare- und drive-Modus
│   ├── setup_stage.py              # Stage-Setup: Physics, Drives, Limits, Initpose
│   └── test_hand_poses.py          # Ganzkörper-Posen-Test
├── models/                         # Trainierte Modelle (nicht im Git)
│   ├── hand_lstm_*.pt
│   ├── hand_lstm_*.onnx
│   └── hand_lstm_*_weights.npz
├── training/
│   ├── dataset.py                  # PyTorch Dataset aus .npz-Dateien
│   ├── model.py                    # LSTM-Architektur (2 Layer, hidden=128)
│   └── train.py                    # Trainingsloop
├── Dockerfile
├── compose.yml
└── requirements.txt
```

---

## Setup

### Voraussetzungen

- Ubuntu 22.04 / 24.04
- NVIDIA GPU + CUDA 12.x
- Docker + NVIDIA Container Toolkit (für Training)
- NVIDIA Isaac Sim 5.1 (separat installieren)

### Lokale Python-Umgebung

```bash
git clone https://github.com/churro206/pib-hand-sim
cd pib-hand-sim

python3 -m venv .venv
source .venv/bin/activate
pip install torch==2.6.0 torchvision==0.21.0 --index-url https://download.pytorch.org/whl/cu124
pip install -r requirements.txt
```

### Docker (Schul-Workstation)

```bash
docker compose build                      # einmalig ~5 Min
docker compose run --rm train             # Training starten
docker compose run --rm export            # ONNX exportieren
docker compose run --rm export-weights    # Numpy-Gewichte exportieren
```

---

## Isaac Sim — Workflow

### Erste Inbetriebnahme (neue USD)

Skripte laufen im **Script Editor** (Window → Script Editor → Datei öffnen → Run).

| Schritt | Aktion | Warum |
|---------|--------|-------|
| 1 | USD aus `isaac_sim/usd/pib_upperbody_*_flattened.usd` öffnen | Modell laden |
| 2 | `setup_stage.py` ausführen | PhysicsScene, Drives, Limitinvertierung, Initpose |
| 3 | Stage speichern (Ctrl+S) | Limits + Flags bleiben in der USD erhalten |
| 4 | Play drücken | Physik starten |
| 5 | Skript ausführen (z.B. `test_hand_poses.py`) | |

### Folge-Sessions (USD bereits konfiguriert)

USD öffnen → Play → Skript ausführen.  
`setup_stage.py` muss nicht erneut laufen. `test_hand_poses.py` setzt Stiffness/Damping
automatisch neu (PhysX cached diese nicht über Sessions).

### Standalone (ohne GUI)

```bash
~/isaacsim/python.sh isaac_sim/_launch_helper.py test_hand_poses
```

Der Launcher wählt automatisch die neueste `pib_upperbody_*_flattened.usd`.

---

## Roboter-DOFs (44 gesamt)

### Körper (14 DOF)

| DOF-Name | Gelenk | Limits |
|----------|--------|--------|
| dof_head_horizontal | Kopf drehen | [-90°, 90°] |
| dof_head_vertical | Kopf nicken | [-45°, 70°] |
| dof_shoulder_vertical_left/right | Schulter heben/senken | [-90°, 90°] |
| dof_shoulder_horizontal_left/right | Schulter vor/zurück | [-90°, 90°] |
| dof_upper_arm_left/right | Oberarm Rotation | [-90°, 90°] |
| dof_elbow_left/right | Ellbogen Flexion | [-45°, 90°] |
| dof_forearm_left/right | Unterarm Pronation | [-90°, 90°] |
| dof_wrist_left/right | Handgelenk Beugung | [0°, 90°] |

### Hände (je 15 DOF pro Seite, Beispiel links)

| DOF-Name | Gelenk | Limits |
|----------|--------|--------|
| dof_thumb_left_rotator | Daumen CMC (Opposition) | [0°, 90°] |
| dof_thumb_left_proximal | Daumen MCP | [0°, 90°] |
| dof_thumb_left_distal | Daumen IP | [0°, 90°] |
| dof_index_left_proximal/distal/tip | Zeigefinger MCP/PIP/DIP | [0°, 90°] |
| dof_middle_left_proximal/distal/tip | Mittelfinger MCP/PIP/DIP | [0°, 90°] |
| dof_ring_left_proximal/distal/tip | Ringfinger MCP/PIP/DIP | [0°, 90°] |
| dof_pinky_left_proximal/distal/tip | Kleiner Finger MCP/PIP/DIP | [0°, 90°] |

**Winkelkonvention:** 0° = offen (T-Pose), 90° = vollständig gebeugt.  
Alle Limits gelten in Onshape-Konvention — `fix_joint_limits()` in `setup_stage.py`
invertiert sie für Isaac Sim.

---

## Vorzeichenkonvention

Isaac Sim interpretiert alle Drehachsen entgegengesetzt zu Onshape.  
Kompensation über `JOINT_SIGN = -1` in `config/pib_hand_config.py`:

- **Hände:** `robot_io._to_isaac_rad()` — einzige Stelle, clippt außerdem auf [0°, 90°]
- **Körper:** `robot_io.set_body_targets()` — ohne Clip (asymmetrische Limits)

**Nie** `JOINT_SIGN` an anderer Stelle anwenden — doppelte Kompensation führt zu
falschem Verhalten.

---

## Synthetische Daten & Training

### Datengenerierung (`isaac_sim/collect_data.py`)

Pro Episode werden Stiffness (50–200) und Damping (5–30) zufällig gezogen,
damit das LSTM mit unterschiedlicher Gelenksteifigkeit umgehen kann.

Jede Episode fährt 5 Trajektorien ab:

| Trajektorie | Beschreibung |
|-------------|-------------|
| slow_close | 3 s: 0° → 90° |
| slow_open | 3 s: 90° → 0° |
| fast_close | 0.5 s: 0° → 90° |
| fast_open | 0.5 s: 90° → 0° |
| sweep | 4 s: 0° ↔ 90° (Hysterese sichtbar) |

Ergebnis: `data/synthetic_<timestamp>.npz`, ~20.000 Samples.

### Datenformat (synthetisch und real)

| Variable | Shape | Beschreibung |
|----------|-------|-------------|
| `t` | (N,) | Zeitstempel [s] |
| `cmd` | (N, 15) | Sollwinkel [Grad] |
| `pos` | (N, 15) | Istwinkel [Grad] — PhysX oder AS5600 |
| `dof_names` | (15,) | DOF-Namen |

Synthetische Dateien enthalten zusätzlich `stiffness` (N,) und `damping` (N,).

### Training

```bash
.venv/bin/python training/train.py
# Lädt alle data/synthetic_*.npz und data/real_*.npz automatisch
```

### Export

```bash
# ONNX für STM32Cube.AI:
.venv/bin/python inference/export_onnx.py

# Numpy-Gewichte für isaac_sim/run_inference.py:
.venv/bin/python inference/export_weights.py
```

---

## LSTM in Isaac Sim (`run_inference.py`)

Am Dateianfang konfigurieren:

```python
MODE              = "compare"      # "compare" | "drive"
RUN_TEST_TRAJ     = True
TRAJ_SPEEDS_DEG_S = [30.0, 180.0]
```

| Modus | Beschreibung | Einsatz |
|-------|-------------|---------|
| `compare` | PhysX läuft normal, LSTM sagt parallel vorher, Fehler wird geloggt | Sanity-Check nach Training |
| `drive` | PhysX für Finger deaktiviert, LSTM setzt Positionen direkt | Nach Fine-tuning auf Echtdaten |

Voraussetzungen: setup_stage.py ausgeführt, export_weights.py ausgeführt, Play aktiv.

Nach dem Lauf: `data/inference_<modus>_<timestamp>.npz`

```bash
# Inferenzlog plotten:
.venv/bin/python inference/plot_inference.py
```

---

## LSTM-Architektur

| Kenngröße | Wert |
|-----------|------|
| Architektur | 2-Layer LSTM |
| Hidden size | 128 |
| Input | `[cmd_t (15), pos_{t-1} (15)]` = 30 Features |
| Output | `pos_t (15)` — vorhergesagte Istposition |
| Normierung | 0.0 = offen, 1.0 = geschlossen (linear über [0°, 90°]) |
| ONNX-Parameter | ~219.000 |
| Größe float32 | ~855 KB |
| Größe int8 | ~214 KB (nach Quantisierung, passt in STM32N6 RAM) |

---

## Echtdaten (AS5600-Encoder)

### Warum Echtdaten?

Die synthetischen Daten lehren das LSTM den linearen PhysX-PD-Regler — keine echten
Nichtlinearitäten. Erst mit AS5600-Daten lernt das Netz:

- **Hysterese:** Finger-Istposition hängt von der Bewegungsrichtung ab
- **Kabelreibung:** Öffnen und Schließen haben unterschiedliche Dynamik
- **Compliance:** 3D-Druck gibt bei Last nach

### Aufzeichnen

```bash
# ASCII-Protokoll:
.venv/bin/python data/collect_real.py --port /dev/ttyACM0 --duration 60

# Wenn Nucleo AS5600-Rohwerte (0–4095) statt Winkel schickt:
.venv/bin/python data/collect_real.py --port /dev/ttyACM0 --raw
```

**Vor dem ersten Einsatz** in `data/collect_real.py` eintragen:
- `AS5600_CALIB` — `(raw_open, raw_closed)` pro Gelenk
- Protokollformat bestätigen (ASCII oder Binär)

### AS5600-Kalibrierung

```
Einmalig pro Gelenk messen:
  raw_open   = AS5600-Wert bei 0° (vollständig offen)
  raw_closed = AS5600-Wert bei 90° (vollständig geschlossen)

Umrechnung:
  angle_deg = (raw − raw_open) / (raw_closed − raw_open) × 90.0
```

### Fine-tuning

```bash
.venv/bin/python training/train.py
# Lädt real_*.npz + synthetic_*.npz zusammen — kein Code ändern
```

### Offline-Evaluation

```bash
.venv/bin/python inference/evaluate_real.py          # neueste real_*.npz
.venv/bin/python inference/evaluate_real.py data/real_XYZ.npz
```

---

## ONNX auf dem STM32 (H723ZG / STM32Cube.AI)

| Kenngröße | Wert |
|-----------|------|
| Input | 30 float (15 cmd + 15 pos_prev) |
| Output | 15 float (pos_pred) |
| Zielfrequenz | 60 Hz → 16.67 ms/Inferenz |
| RAM | ~214 KB nach int8-Quantisierung |

**Wichtig:** LSTM-State (h, c) zwischen Inferenzaufrufen **nicht** zurücksetzen —
nur beim Start eines neuen Greifvorgangs.

Schritte STM32Cube.AI:
1. STM32CubeIDE → Help → Manage Embedded Software Packages → X-CUBE-AI installieren
2. Projekt für NUCLEO-H723ZG anlegen
3. X-CUBE-AI → Add Network → `.onnx`-Datei wählen
4. Analyze → RAM/Flash prüfen → Generate Code

---

## Protokoll Nucleo → PC

Wir brauchen pro Tick (~60 Hz):
1. Kommandierte Winkel [Grad]
2. AS5600-Position (Rohwert 0–4095 oder kalibrierter Winkel)
3. Timestamp [ms]

**Option A — ASCII:**
```
t=1234,cmd=0.0;45.2;...;pos=0.0;42.1;...\n
```

**Option B — Binär (92 Bytes/Paket):**
```
[timestamp_ms: uint32][cmd_0..14: float32×15][pos_0..14: float32×15]
```

---

## Offene Punkte

- [ ] AS5600-Kalibrierungswerte messen → in `data/collect_real.py` eintragen
- [ ] Kommunikationsprotokoll abstimmen: ASCII oder Binär?
- [ ] Baudrate und Paketformat mit Nucleo-Seite bestätigen
- [ ] Klären welche der 15 Gelenke mit AS5600 bestückt werden
- [ ] `control/servo.py` implementieren (lineare Sehnenkopplung)
- [ ] Fine-tuning starten sobald erste Echtdaten da sind
- [ ] `control/neural.py` implementieren (LSTM-Inferenz als Steuermodul)
- [ ] ROS2-Integration klären (Topic-Namen, Nachrichtentypen)
