# Projektkontext für Claude Code

## Wer ich bin und was das Projekt ist

Ich bin Leon, Informatikstudent. Ich arbeite an einem Simulationsprojekt für den
RoboCup 2027 (@Home Liga). Meine 3er-Gruppe ist für das Greifen mit der Hand des
Roboters "pib" (von isento, Open-Source, 3D-gedruckt) zuständig. Meine spezifische
Aufgabe: eine realitätsnahe Simulation der Handmotorik in NVIDIA Isaac Sim aufbauen.

---

## Aktueller Projektstatus

Die Isaac-Sim-Simulation ist funktionsfähig. Alle **44 DOF** (Körper + beide Hände)
werden als Drive-basierte Gelenke gesteuert. Ein Ganzkörper-Posen-Test (`test_hand_poses.py`)
läuft durch Winken, Doppelbizeps und Peace-Zeichen.

Nächster Schritt: Echtdaten vom Nucleo (AS5600-Encoder) aufzeichnen und das LSTM
fine-tunen.

---

## Roboter: pib v4 Gesamtstruktur

USD-Pfad in Isaac Sim: `/World/pib_upperbody_URDF/pib_upperbody_URDF`

**44 DOF gesamt:**
- 14 Körper-DOFs (Kopf, Schultern, Arme, Handgelenke)
- 15 linke Hand-DOFs
- 15 rechte Hand-DOFs

### Körper-DOFs (BODY_DOFS in config)

| DOF-Name                        | Gelenk                   | Limits (Onshape) |
|---------------------------------|--------------------------|------------------|
| dof_head_horizontal             | Kopf drehen l/r          | [-90°, 90°]      |
| dof_head_vertical               | Kopf nicken              | [-45°, 70°]      |
| dof_shoulder_vertical_left/right| Schulter heben/senken    | [-90°, 90°]      |
| dof_shoulder_horizontal_left/right | Schulter vor/zurück   | [-90°, 90°]      |
| dof_upper_arm_left/right        | Oberarm Rotation         | [-90°, 90°]      |
| dof_elbow_left/right            | Ellbogen Flexion         | [-45°, 90°]      |
| dof_forearm_left/right          | Unterarm Pronation       | [-90°, 90°]      |
| dof_wrist_left/right            | Handgelenk Beugung       | [0°, 90°]        |

### Hand-DOFs pro Seite (15 Stück)

| DOF-Name (Beispiel links)       | Gelenk              | Limits (Onshape) |
|---------------------------------|---------------------|------------------|
| dof_thumb_left_rotator          | Daumen CMC          | [0°, 90°]        |
| dof_thumb_left_proximal         | Daumen MCP          | [0°, 90°]        |
| dof_thumb_left_distal           | Daumen IP           | [0°, 90°]        |
| dof_index_left_proximal/distal/tip   | Zeigefinger MCP/PIP/DIP | [0°, 90°] |
| dof_middle_left_proximal/distal/tip  | Mittelfinger        | [0°, 90°]  |
| dof_ring_left_proximal/distal/tip    | Ringfinger          | [0°, 90°]  |
| dof_pinky_left_proximal/distal/tip   | Kleiner Finger      | [0°, 90°]  |

**Wichtig:** Exakte DOF-Namen und Artikulations-Indizes immer per `isaac_sim/inventory.py`
verifizieren — nicht erfinden.

---

## Winkel- und Vorzeichenkonvention

### Winkelkonvention (Onshape-Konvention, gilt im gesamten Code)
- **Positive Winkel = Flexion** (Finger beugt sich zur Handfläche, Ellbogen beugt sich)
- 0° = vollständig offen / gestreckt (T-Pose)
- ~90° = vollständig gebeugt / geschlossen

### JOINT_SIGN = -1
Isaac Sim interpretiert die Drehachse aller Gelenke entgegengesetzt zu Onshape.
Kompensation: `JOINT_SIGN = -1` in `config/pib_hand_config.py`.

- **Hände:** angewendet in `robot_io._to_isaac_rad()` — dort ist die einzige Stelle.
  Außerdem wird der Handwinkel auf [0°, 90°] geclippt.
- **Körper:** angewendet direkt in `robot_io.set_body_targets()`, ohne Clip
  (asymmetrische Limits je nach Gelenk).
- **Onshape wird nicht angefasst** — die dortige Logik bleibt intuitiv.

### fix_joint_limits()
Die Onshape-Limits ([0°, 90°]) werden beim Import in Isaac mit der Onshape-Konvention
exportiert. Nach JOINT_SIGN-Anwendung landen die Targets bei z.B. −90°, was außerhalb
der USD-Limits [0°, 90°] liegt → Gelenk bewegt sich nicht.

Lösung: `setup_stage.fix_joint_limits()` invertiert alle PhysicsRevoluteJoint-Limits:
`new_lower = −old_upper, new_upper = −old_lower`

Idempotenz: Pro Prim wird ein USD-Custom-Data-Flag `pib_limits_inverted=True` gesetzt.
**Nur einmal ausführen** (in `setup_stage.py`), dann Stage mit Ctrl+S speichern.
`test_hand_poses.py` ruft `fix_joint_limits` NICHT auf — das wäre ein Bug.

---

## Technischer Stack

- **Isaac Sim 5.1** (NVIDIA, Python API) — Roboter-Simulation, USD-Format
- **PyTorch** — LSTM-Netz (geplant für Echtdaten-Fine-Tuning)
- **ONNX** — Export für STM32Cube.AI (Nucleo H723ZG)
- **Python 3.10+**, numpy, matplotlib, pyserial
- **Ubuntu 24.04** (Entwicklungsumgebung)
- **Docker** — Training auf Schul-Workstation (GPU), Basis: `nvcr.io/nvidia/pytorch:24.12-py3`

---

## Projektstruktur

```
pib-hand-sim/
├── config/
│   └── pib_hand_config.py          # JOINT_SIGN, BODY_DOFS, HAND_DOFS, GRASP_POSES,
│                                   # servo_pose_to_joints(), Normierungsfunktionen
├── control/
│   ├── __init__.py
│   └── direct.py                   # Direktsteuerung — Gelenkwinkel 1:1 (Identity)
│                                   # servo.py und neural.py kommen später
├── data/
│   ├── collect_real.py             # Echtdaten vom Nucleo aufzeichnen
│   └── *.npz                       # Trainingsdaten (nicht im Git)
├── inference/
│   ├── evaluate_real.py            # LSTM vs. Messdaten offline vergleichen
│   ├── export_onnx.py              # PyTorch → ONNX (für STM32Cube.AI)
│   ├── export_weights.py           # PyTorch → .npz (für run_inference.py)
│   └── plot_inference.py           # Inferenzlogs aus Isaac plotten
├── isaac_sim/
│   ├── usd/                        # USD-Modelle (pib_upperbody_2 bis 7)
│   │   └── pib_upperbody_*_flattened.usd  # aktive Modelle (flattened = self-contained)
│   ├── _deprecated/                # alte Scripts (fix_joints.py, unfix_joints.py)
│   ├── _launch_helper.py           # Standalone-Launcher — lädt neueste USD automatisch
│   ├── collect_data.py             # Synthetische Daten in Isaac sammeln
│   ├── inventory.py                # Debug: alle DOFs + Limits aus Stage ausgeben
│   ├── inventory_output.txt        # Letztes Inventar-Ergebnis (Referenz)
│   ├── manual_control_hand.py      # Interaktive Einzelgelenk-Steuerung
│   ├── robot_io.py                 # EINZIGE Isaac-API-Schicht — steuert alle 44 DOF
│   ├── run_inference.py            # LSTM-Inferenz: compare- und drive-Modus
│   ├── setup_stage.py              # Stage-Setup: Physics, Drives, Limits, Initpose
│   └── test_hand_poses.py          # Ganzkörper-Posen: Winken, Doppelbizeps, Peace
├── models/                         # Trainierte Modelle (nicht im Git)
├── training/
│   ├── dataset.py
│   ├── model.py
│   └── train.py
├── Dockerfile
├── compose.yml
└── requirements.txt
```

---

## Wichtige Architekturentscheidungen

### Alle Gelenke als Drive (Servo-Mimik)
Jedes der 44 Gelenke ist ein `PhysicsRevoluteJoint` mit `DriveAPI` (angular).
Stiffness/Damping per Gelenk-Typ:
- Kopf: 3000 / 150
- Schulter/Ellbogen/Unterarm: 5000 / 200
- Handgelenk: 2000 / 100
- Daumen-Rotator: 1000 / 50
- Fingerglieder (proximal/distal/tip): 500 / 20

### robot_io.py ist die einzige Isaac-API-Schicht
Alle anderen Skripte rufen nur `set_hand_targets()`, `set_body_targets()` oder
`set_all_targets()` auf — keine direkte Isaac-API außerhalb von `robot_io.py`.

### set_all_targets(joint_angles_deg: dict)
Unified Dispatcher: nimmt ein `{dof_name: angle_deg}`-Dict und routet automatisch
nach Körper / linke Hand / rechte Hand.

### _launch_helper.py
Standalone-Launcher für `~/isaacsim/python.sh`. Lädt automatisch die neueste
`pib_upperbody_*_flattened.usd` aus `isaac_sim/usd/` (lexikografische Sortierung →
höchste Versionsnummer gewinnt). Ruft `configure_drives()` und `fix_joint_limits()`
beim Start auf.

---

## Isaac Sim Workflow (Script Editor)

**Pflicht-Reihenfolge beim ersten Start mit einer neuen USD:**

1. USD aus `isaac_sim/usd/pib_upperbody_*_flattened.usd` in Isaac öffnen
2. `setup_stage.py` im Script Editor ausführen
   → konfiguriert Physics, Drives, invertiert Limits, setzt Initpose
3. Stage speichern (Ctrl+S) — Limits und Custom-Data-Flags bleiben im USD
4. Play drücken
5. `test_hand_poses.py` oder andere Skripte ausführen

**Bei Folge-Sessions** (USD bereits konfiguriert und gespeichert):
- USD öffnen → Play → Skript ausführen
- `setup_stage.py` muss nicht nochmal laufen (Limits sind gespeichert),
  aber `configure_drives()` in `test_hand_poses.py` setzt Stiffness/Damping
  neu (PhysX cached diese nicht)

---

## Steuer-Modi

| Modus | Datei | Eingabe |
|-------|-------|---------|
| Direktsteuerung | `control/direct.py` | {dof_name: angle_deg} → 1:1 |
| Servo-Näherung | `control/servo.py` (ausstehend) | Servo-Wert → 3 Gelenke per Sehne |
| LSTM-Inferenz | `control/neural.py` (ausstehend) | Servo + Sensorik → präzise Winkel |

Sehnenkopplung (Startwerte, später mit AS5600 kalibrieren):
`proximal × 1.0, distal × 0.8, tip × 0.6`

---

## Was ich von Claude brauche

- Kenne den Kontext. Arbeite direkt mit den vorhandenen Dateien.
- Frag nach, bevor du DOF-Namen oder Vorzeichen erfindest — immer per `inventory.py` verifizieren.
- Keine Änderungen an `robot_io.py` ohne genau zu verstehen was `JOINT_SIGN` und
  `_to_isaac_rad()` machen — das ist die einzige Vorzeichenstelle für Hände.
- `fix_joint_limits()` darf nur in Setup-Kontext aufgerufen werden, nicht pro Run.
- Aktuell liegt der Fokus auf Echtdaten (AS5600) und LSTM-Fine-Tuning.
  Isaac-Simulation läuft stabil.
