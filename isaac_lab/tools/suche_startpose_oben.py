"""
suche_startpose_oben.py — start pose for the "top" grasp via a parallel search (2026-10-11; plan docs/protokoll/plan-griff-von-oben.md).

Modelled on grasp planners "propose → close → evaluate" (GraspIt!, DexGraspNet/UniDexGrasp: poses checked in simulation):
every environment gets its own fixed hand pose from a grid — tilt about x (fingers down), roll about y, thumb
rotator (start = target), height of the lowest fingertip above the table, offset of the object from the grasp centre along
the fingers —, several repetitions per combination (random scale/mass/position as in training). The rule "close all" (like
EXP-014, the rotator keeps its position) grasps, the table lowers as usual. Per environment: held, start contact hand↔object
(first 0.1 s), hand↔table before and during closing (thumb/fingers), palm on the object, object path.

Fingertip geometry per rotator from tools/probe_neigung_oben.py --dump (mesh points, hand root frame). For a rotation
R = Ry·Rx: lowest point per tip; grasp centre = midpoint between the thumb tip and the mean of the four fingertips; the hand
root is placed so that the lowest tip is h above the table and the grasp centre lies dy in front of/behind the object centre.
One object per process (Isaac Lab: one environment per process). Result: logs/startpose_oben/<objekt>.csv (per environment)
and summary isaac_sim/tools/_suche_startpose_oben.txt; evaluation over all objects: tools/auswertung_startpose_oben.py.

  ~/IsaacLab/isaaclab.sh -p isaac_lab/tools/probe_neigung_oben.py --headless --dump logs/startpose_oben/geometrie.npz
  ~/IsaacLab/isaaclab.sh -p isaac_lab/tools/suche_startpose_oben.py --headless --objekt kugel_d7
"""
import argparse
import csv
import itertools
import math
import os
import sys
import time
from pathlib import Path

from isaaclab.app import AppLauncher

REPO = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser()
parser.add_argument("--objekt", default="kugel_d7", help="Objekt aus env_cfg_oben.OBJECTS_OBEN")
parser.add_argument("--geometrie", default=str(REPO / "logs" / "startpose_oben" / "geometrie.npz"))
parser.add_argument("--wiederholungen", type=int, default=3)
parser.add_argument("--pose", default=None, help="feste Pose „Kippung,Rollen,Rotator“ statt des Rasters (Prüfung/Fenstertest)")
parser.add_argument("--hoehen", default=None, help="Höhen [m] mit Komma, nur mit --pose (Standard 0.015)")
parser.add_argument("--real_time", action="store_true", help="Echtzeit; mit Fenster läuft es nach der Wertung weiter")
AppLauncher.add_app_launcher_args(parser)
args = parser.parse_args()
app = AppLauncher(args).app

import numpy as np  # noqa: E402
import torch  # noqa: E402
from isaaclab.envs import ManagerBasedRLEnv  # noqa: E402
from isaaclab.managers import EventTermCfg  # noqa: E402
from isaaclab.sensors import ContactSensorCfg  # noqa: E402
from isaaclab.utils.math import quat_from_matrix  # noqa: E402

sys.path.insert(0, str(REPO / "isaac_lab"))
from pib_grasp import mdp  # noqa: E402
from pib_grasp.env_cfg import DROP_DEPTH, DROP_SPEED, GRASP_TIME_S  # noqa: E402
from pib_grasp.env_cfg_oben import PibGraspEnvCfg_Oben, apply_object_oben  # noqa: E402
from pib_hand_left_v5_cfg import SERVO_JOINTS  # noqa: E402

# Raster (Grad bzw. Meter)
KIPP_X = [0.0, 10.0, 20.0, 30.0, 36.5, 45.0]
ROLL_Y = [0.0, 4.0, 8.0]
ROTATOR = [60, 75, 90]
HOEHE = [0.010, 0.020, 0.030, 0.045, 0.060, 0.080]
VERSATZ_Y = [-0.02, 0.0, 0.02]                 # object centre vs. grasp centre along the fingers (− = towards the fingertips)
if args.pose:                                  # fixed pose (re-check, window test): only the heights vary
    _k, _r, _rot = (float(v) for v in args.pose.split(","))
    KIPP_X, ROLL_Y, ROTATOR, VERSATZ_Y = [_k], [_r], [int(_rot)], [0.0]
    HOEHE = [float(v) for v in (args.hoehen or "0.015").split(",")]
combos = list(itertools.product(KIPP_X, ROLL_Y, ROTATOR, HOEHE, VERSATZ_Y))
params = [c for c in combos for _ in range(args.wiederholungen)]
N = len(params)

BODIES = ["urdf_elbow_lower", "urdf_forearm_left", "urdf_palm_left", "urdf_thumb_rotator_left", "urdf_thumb_proximal",
          "urdf_thumb_tip"] + [f"urdf_finger_{seg}{sfx}" for sfx in ("", "_2", "_3", "_4") for seg in ("proximal", "distal", "tip")]
PALM = BODIES.index("urdf_palm_left")
THUMB = [BODIES.index(b) for b in ("urdf_thumb_rotator_left", "urdf_thumb_proximal", "urdf_thumb_tip")]
FINGERS = [i for i, b in enumerate(BODIES) if b.startswith("urdf_finger_")]
HAND = list(range(2, len(BODIES)))            # without elbow/forearm


def set_start_rotator(env, env_ids):
    """Reset: thumb rotator per environment to its grid position (pre-grasp pose; after reset_hand)."""
    if not hasattr(env, "pib_rot_start"):          # first reset during setup, before the grid positions are set
        return
    robot = env.scene["robot"]
    j = robot.joint_names.index("thumb_left_rotator")
    q = robot.data.joint_pos[env_ids].clone()
    q[:, j] = env.pib_rot_start[env_ids]
    robot.write_joint_state_to_sim(q, torch.zeros_like(q), env_ids=env_ids)
    tgt = robot.data.joint_pos_target[env_ids].clone()
    tgt[:, j] = env.pib_rot_start[env_ids]
    robot.set_joint_position_target(tgt, env_ids=env_ids)


cfg = apply_object_oben(PibGraspEnvCfg_Oben(), args.objekt)
cfg.scene.num_envs = N
cfg.seed = 1000
cfg.scene.object.spawn.activate_contact_sensors = True
cfg.scene.object_contact = ContactSensorCfg(prim_path="{ENV_REGEX_NS}/Object", history_length=cfg.decimation,
                                            filter_prim_paths_expr=[f"{{ENV_REGEX_NS}}/Robot/{b}" for b in BODIES])
cfg.scene.table.spawn.activate_contact_sensors = True
cfg.scene.table_contact = ContactSensorCfg(prim_path="{ENV_REGEX_NS}/Table", history_length=cfg.decimation,
                                           filter_prim_paths_expr=[f"{{ENV_REGEX_NS}}/Robot/{b}" for b in BODIES])
cfg.events.set_start_rotator = EventTermCfg(func=set_start_rotator, mode="reset")
env = ManagerBasedRLEnv(cfg=cfg)
robot, obj, table = env.scene["robot"], env.scene["object"], env.scene["table"]
obj_sensor, table_sensor = env.scene["object_contact"], env.scene["table_contact"]
dev = env.device

# ── Hand pose per environment from the geometry ──────────────────────────────────────────────────────────────────────
geo = np.load(args.geometrie)
P = np.array(params)                          # kipp, roll, rot, h, dy
root_pos = np.zeros((N, 3))
root_quat = np.zeros((N, 4))
table_top = (table.data.default_root_state[:, 2] + cfg.scene.table.spawn.size[2] / 2).cpu().numpy()
obj_xy = obj.data.default_root_state[:, :2].cpu().numpy()
cache = {}
for i, (ax, ay, rot, h, dy) in enumerate(params):
    key = (ax, ay, rot)
    if key not in cache:
        a, b = math.radians(ax), math.radians(ay)
        Rx = np.array([[1, 0, 0], [0, math.cos(a), -math.sin(a)], [0, math.sin(a), math.cos(a)]])
        Ry = np.array([[math.cos(b), 0, math.sin(b)], [0, 1, 0], [-math.sin(b), 0, math.cos(b)]])
        R = Ry @ Rx
        low = []
        for k in range(5):
            Q = geo[f"r{int(rot)}_tip{k}"] @ R.T
            low.append(Q[int(Q[:, 2].argmin())])
        low = np.array(low)
        grasp = (low[0, :2] + low[1:, :2].mean(0)) / 2
        q = quat_from_matrix(torch.tensor(R, dtype=torch.float32)).numpy()
        cache[key] = (low[:, 2].min(), grasp, q)
    zmin, grasp, q = cache[key]
    root_pos[i, :2] = obj_xy[i] - np.array([0.0, dy]) - grasp
    root_pos[i, 2] = table_top[i] + h - zmin
    root_quat[i] = q
robot.data.default_root_state[:, :3] = torch.tensor(root_pos, dtype=torch.float32, device=dev)
robot.data.default_root_state[:, 3:7] = torch.tensor(root_quat, dtype=torch.float32, device=dev)
env.pib_rot_start = torch.tensor(np.radians(P[:, 2]), dtype=torch.float32, device=dev)

ids = [robot.joint_names.index(n) for n in SERVO_JOINTS]
scale = torch.tensor([0.03, 0.03] + [0.1] * 6, device=dev)
rot_target = env.pib_rot_start.clone()
dt = env.step_dt
early, close_step = round(0.1 / dt), round(0.4 / dt)
drop_step = round(GRASP_TIME_S / dt)
hold_start = round((GRASP_TIME_S + DROP_DEPTH / DROP_SPEED) / dt)


def zeros():
    return torch.zeros(N, device=dev)


def rule_action(hold_q):
    """Rule per environment by its episode time (also after an automatic reset): hold forearm/wrist, the rotator
    keeps its position, from 0.4 s on thumb + fingers close at 0.2."""
    q = robot.data.joint_pos[:, ids]
    new = env.episode_length_buf == 0
    hold_q[new] = q[new]
    a = torch.zeros(N, 8, device=dev)
    a[:, :2] = ((hold_q[:, :2] - q[:, :2]) / scale[:2]).clamp(-1, 1)
    a[:, 2] = ((rot_target - q[:, 2]) / scale[2]).clamp(-1, 1)
    a[:, 3:] = 0.2 * (env.episode_length_buf + 1 >= close_step).float()[:, None]
    return a


with torch.inference_mode():
    env.reset(seed=1000)
    hold_q = robot.data.joint_pos[:, ids].clone()
    alive = torch.ones(N, dtype=torch.bool, device=dev)
    start_contact, table_early, table_thumb, table_fingers = zeros(), zeros(), zeros(), zeros()
    palm, fingers = zeros(), zeros()
    n_hold = 0
    xy0 = obj.data.root_pos_w[:, :2].clone()
    for step in range(1, int(env.max_episode_length)):
        t0 = time.time()
        _, _, term, trunc, _ = env.step(rule_action(hold_q))
        if args.real_time:
            time.sleep(max(0.0, dt - (time.time() - t0)))
        alive &= ~(term | trunc)
        of = obj_sensor.data.force_matrix_w_history[:, :, 0].norm(dim=-1).amax(dim=1)      # (N, bodies)
        tf = table_sensor.data.force_matrix_w_history[:, :, 0].norm(dim=-1).amax(dim=1)
        if step <= early:
            start_contact = torch.maximum(start_contact, of[:, HAND].amax(-1))
            xy0 = obj.data.root_pos_w[:, :2].clone()
        if step < close_step:
            table_early = torch.maximum(table_early, tf[:, HAND].amax(-1) * alive)
        elif step < drop_step:
            table_thumb = torch.maximum(table_thumb, tf[:, THUMB].amax(-1) * alive)
            table_fingers = torch.maximum(table_fingers, tf[:, FINGERS].amax(-1) * alive)
        if step >= hold_start:
            palm += (obj_sensor.data.force_matrix_w[:, 0, PALM].norm(dim=-1) > 1.0).float() * alive
            fingers += (mdp.fingertip_object_forces(env) > 1.0).float().sum(-1) * alive
            n_hold += 1
    path = torch.norm(obj.data.root_pos_w[:, :2] - xy0, dim=-1)

out_dir = REPO / "logs" / "startpose_oben"
out_dir.mkdir(parents=True, exist_ok=True)
cols = ["kipp_x", "roll_y", "rotator", "hoehe_m", "versatz_y_m", "gehalten", "startkontakt_n", "tisch_vor_schliessen_n",
        "tisch_daumen_n", "tisch_finger_n", "handflaeche_anteil", "finger_am_objekt", "objektweg_m", "spitzenhoehe_regel_m"]
rows = np.column_stack([P, alive.float().cpu(), start_contact.cpu(), table_early.cpu(), table_thumb.cpu(),
                        table_fingers.cpu(), (palm / max(n_hold, 1)).cpu(), (fingers / max(n_hold, 1)).cpu(), path.cpu(),
                        env.pib_tip_height.cpu()])
# fixed pose (check/window): own file, the grid results of the search stay unchanged
with open(out_dir / (f"{args.objekt}_pose.csv" if args.pose else f"{args.objekt}.csv"), "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(cols)
    w.writerows(rows.tolist())

# Summary: per combination fractions over the repetitions; "clean" = no start contact, no table contact before
# closing; ranked by held, then little table contact while closing
r = args.wiederholungen
agg = rows.reshape(len(combos), r, -1)
held = agg[:, :, 5].mean(1)
clean = ((agg[:, :, 6] <= 0.5) & (agg[:, :, 7] <= 1.0)).mean(1)
tisch = ((agg[:, :, 8] > 1.0) | (agg[:, :, 9] > 1.0)).mean(1)
order = sorted(range(len(combos)), key=lambda k: (-(held[k] * (clean[k] == 1.0)), tisch[k]))
lines = [f"== {args.objekt} | {N} Umgebungen ({len(combos)} Kombinationen × {r}) | Regel „alle schließen“ 0,2, Seed 1000",
         f"   gehalten gesamt {held.mean():.2f}, sauberer Start {clean.mean():.2f}; Regel-Spitzenhöhe (env) "
         f"{1000 * float(env.pib_tip_height.mean()):.0f} mm",
         "   Beste 12 (sauberer Start): Kipp° Roll° Rot° Höhe[mm] dy[mm] | gehalten  Tisch beim Schließen  Handfläche  Finger"]
for k in [k for k in order if clean[k] == 1.0][:12]:
    ax, ay, rot, h, dy = combos[k]
    lines.append(f"   {ax:5.1f} {ay:4.0f} {rot:4.0f} {1000 * h:5.0f} {1000 * dy:+5.0f} | {held[k]:.2f}  {tisch[k]:.2f}  "
                 f"{agg[k, :, 10].mean():.2f}  {agg[k, :, 11].mean():.1f}")
text = "\n".join(lines)
print(text, flush=True)
with open(REPO / "isaac_sim" / "tools" / "_suche_startpose_oben.txt", "a", encoding="utf-8") as f:
    f.write(text + "\n")
if not args.headless:                  # with window: keep running (only the first episode is scored)
    print("Fenster: läuft weiter, bis es geschlossen wird", flush=True)
    with torch.inference_mode():
        while app.is_running():
            t0 = time.time()
            env.step(rule_action(hold_q))
            if args.real_time:
                time.sleep(max(0.0, dt - (time.time() - t0)))
os._exit(0)
