# Repository map (draft, 2026-10-13)

> Draft for `docs/plan-abgabe.md`, Phase 1 step 5 — not linked yet. One line per folder or script, with a status:
> **current** (part of the working pipeline), **tool** (reusable check/diagnostic), **one-off** (diagnostic for a single
> question, kept for traceability), **legacy** (v4 or superseded, still runs). Files are deliberately not moved: experiment
> reports, logs and ADRs refer to these paths.

## Top level

| Path | Status | What it is |
|---|---|---|
| `README.md` | current | Entry point (to be rewritten, see plan) |
| `config/pib_hand_config_v5.py` | current | Joint names, limits, servo actuator model (ST3215/ST3095, ADR-012), wrist linkage (ADR-014) — single source for Isaac Sim and Isaac Lab |
| `config/pib_hand_config_v4.py` | legacy | Same for v4 |
| `isaac_sim/` | current | Digital twin in Isaac Sim 5.1: USD stages with Action Graph, start scripts, asset tools |
| `isaac_lab/` | current | RL grasping in Isaac Lab 2.3.2: task, training, evaluation, experiment framework |
| `experiments/` | current | One folder per experiment (plan, results, report, plots, best videos), `leaderboard.md`, `index.md` |
| `ros2_ws/` | current | ROS 2 Jazzy workspace: robot descriptions v4/v5, ros2_control bring-up, demo clients |
| `pib_hand_left_urdf_v5/` | current | `onshape-to-robot` export of the left v5 hand + forearm (source of `pib_hand_left_v5.usd`), `config.json` links the Onshape document |
| `pib_upperbody_urdf_v5/` | current | Raw `onshape-to-robot` export of the v5 upper body |
| `docs/` | current | Architecture, conventions, decisions (ADR-001–022), plans and night-run logs |
| `scripts/` | current | `launch.sh`, `start_isaac.sh`, `start_ros2.sh` — one-click start of the twin |
| `videos/` | current | Demo videos (twin, first policies, YCB) |
| `sensor_mount/` | unclear | 3D-print file `sensor_mount_distal_v3.1_+_v4.2.3mf` (distal sensor mount, added 2026-06-18 without description — to be clarified) |
| `logs/`, `outputs/` | ignored | Training runs, checkpoints, evaluations (backed up to Hugging Face) |
| `CLAUDE.md`, `.claude/` | current | Instructions for an AI coding assistant (to be generalised, see plan) |

## `isaac_sim/`

| Path | Status | What it is |
|---|---|---|
| `usd/pib_upperbody_v5.usd` | current | v5 upper body + Action Graph (ROS 2 joint states, fingertip forces) |
| `usd/pib_hand_left_v5.usd` | current | Left hand + forearm for Isaac Lab, mimic joints/limits/drives baked in |
| `usd/pib_upperbody_v4.usd` | legacy | v4 reference stage |
| `start.py`, `setup_stage.py` | current | Run before Play: drives, servo model, mimic joints, limits, initial pose |
| `autostart.py` | legacy | Fully automatic start, v4 only |
| `tools/bake_hand_asset_v5.py` | tool | Bake mimic/limits/drives into the hand USD (rerun after config changes) |
| `tools/audit_asset.py` | tool | Masses, colliders, drives, effective joint inertia, stability numbers |
| `tools/build_contact_sensors_v5.py`, `tools/build_fingertip_force_graph_v5.py` | tool | Rebuild fingertip sensors and their ROS 2 graph (ADR-013) |
| `tools/inspect_action_graph.py` | tool | Inventory of the Action Graph from the USD |
| `tools/flip_joint_sign.py` | tool | One-time joint sign fix after a new Onshape import (ADR-007) |
| `tools/dump_pose.py` | tool | Record a pose sequence for the demo clients |

## `isaac_lab/`

| Path | Status | What it is |
|---|---|---|
| `pib_hand_left_v5_cfg.py` | current | Isaac Lab asset: 7 implicit servos, wrist as `RemotizedPDActuator`, 9 passive mimic followers |
| `pib_grasp/env_cfg.py` | current | Side-grasp task (Dexsuite pattern), object catalogue `OBJECTS`, all training variants |
| `pib_grasp/env_cfg_oben.py` | current | Top-grasp task |
| `pib_grasp/mdp.py` | current | Rewards, observations, events, terminations, PID-Lagrange stall limit, arm-motion load test |
| `pib_grasp/agents/rsl_rl_ppo_cfg.py`, `pib_grasp/rsl_rl_ext.py` | current | PPO settings; bounds loss and CAPS added to rsl_rl |
| `pib_grasp/__init__.py` | current | Gym task IDs (one per training variant) |
| `train.py`, `play.py` | current | Thin wrappers around Isaac Lab's rsl_rl scripts |
| `eval_policy.py` | current | Evaluation protocol eval-v2 (task success, guardrails, load test, videos) |
| `experiments.py` | current | Experiment framework: `new`, `run`, `eval`, `belastung`, `medien`, `leaderboard`, `done` (ADR-016) |
| `plot_training.py` | current | TensorBoard → SVG for the reports |
| `backup_policies.py` | current | Backup of runs to the Hugging Face repo |
| `check_hand_asset.py`, `scripted_grasp_test.py` | tool | Asset check (mimic, sensors, drives); feasibility grasp without a policy |
| `tools/reward_diag.py` | tool | Magnitude of every reward term per phase — run before every training change |
| `tools/analyse_reset.py`, `tools/check_objekt.py`, `tools/check_multi.py`, `tools/ruhelage_objekt.py` | tool | Checks for new objects/scenes (no overlap at reset, rest pose, scene images) |
| `tools/kalibrierdaten_int8.py`, `tools/quantisiere_int8.py` | tool | int8 quantisation for the STM32N6 NPU (M2) |
| `tools/pruef_bewegung.py`, `tools/diag_stall.py`, `tools/diag_objektweg.py`, `tools/inspect_ycb.py` | tool | Load-test physics check, stall origin per servo, object path, YCB asset check |
| `tools/diag_anheben.py`, `tools/probe_*.py`, `tools/machbarkeit_oben.py`, `tools/suche_startpose_oben.py`, `tools/auswertung_startpose_oben.py`, `tools/debug_scene.py` | one-off | Diagnostics for single questions (2026-10-08 … 10-11), results in ADRs/docs |

## `ros2_ws/src/`

| Path | Status | What it is |
|---|---|---|
| `pib_description_v5/`, `pib_description_v4/` | current / legacy | URDF + meshes + `ros2_control` tags |
| `pib_bringup/` | current | Launch files, controller configs, demo clients (pickup/putdown, mimic tests) |
| `topic_based_ros2_control/` | third party | Hardware interface bridge (own licence) |

## `docs/`

| Path | Status | What it is |
|---|---|---|
| `architecture.md`, `conventions.md`, `decisions.md` | current | System layout, units/signs/names, decisions ADR-001–022 |
| `current-sprint.md`, `handoff.md` | working notes | Project diary and session hand-over (to move to `docs/protokoll/`) |
| `nachtlauf-*.md`, `plan-*.md`, `pruefung-aktionsweg.md`, `startpose-oben/`, `int8/` | working notes | Plans and results of single steps |
| `archiv/` | legacy | Old plans and prompts |
