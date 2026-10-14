"""
machbarkeit_oben.py — Can the "top" grasp be solved with this hand, and with which pre-grasp distance/object position?
(Plan: docs/protokoll/plan-griff-von-oben.md, step 2; modelled on the feasibility test 2026-10-04: rotator 90° → 14–15/16 held.)

Scene env_cfg_oben (palm down) with one object from OBJECTS_OBEN, without a policy: rule "close all" like EXP-014
(rotator to its target until 0.4 s, then thumb + fingers close at 0.2 of the maximum step, forearm/wrist
hold); rotator target per environment in turn from --thumb_rot. One episode per environment: start contact hand↔object in
the first 0.1 s (contact sensor on the object with a filter on all hand bodies, over both physics substeps), held until
the end, object path in the table plane, fingers on the object in the hold phase. One distance/position per process (Isaac
Lab: one environment per process) → grid via a shell script. Report: isaac_sim/tools/_machbarkeit_oben.txt (appended)

  ~/IsaacLab/isaaclab.sh -p isaac_lab/tools/machbarkeit_oben.py --headless --objekt kugel_d7 --abstand 0.015 --y -0.34
With a window to watch: without --headless, with --real_time --num_envs 16 — keeps running after the scored first episode
until the window is closed.
"""
import argparse
import math
import os
import sys
import time
from pathlib import Path

from isaaclab.app import AppLauncher

parser = argparse.ArgumentParser()
parser.add_argument("--objekt", default="kugel_d7", help="Objekt aus env_cfg_oben.OBJECTS_OBEN")
parser.add_argument("--abstand", type=float, default=None,
                    help="feste Höhe der tiefsten Fingerspitze über dem Tisch [m] (Standard: Regel je Objekt, env_cfg_oben)")
parser.add_argument("--x", type=float, default=None, help="Objektmitte quer [m] (Standard GRASP_XY)")
parser.add_argument("--y", type=float, default=None, help="Objektmitte längs [m] (Standard GRASP_XY)")
parser.add_argument("--thumb_rot", type=str, default="45,90", help="Rotator-Ziele [°], reihum je Umgebung")
parser.add_argument("--rot_start_max", type=float, default=None,
                    help="Daumen-Rotator beim Reset 0…Wert [°] (Standard wie Training 0–90; UniDexGrasp startet offen = 0)")
parser.add_argument("--handgelenk", type=float, default=None,
                    help="Handgelenk ab 0,4 s auf diesen Winkel [°] (−60 … 0, gebeugt = Finger tiefer); Standard: halten")
parser.add_argument("--num_envs", type=int, default=48)
parser.add_argument("--real_time", action="store_true")
AppLauncher.add_app_launcher_args(parser)
args = parser.parse_args()
app = AppLauncher(args).app

import torch  # noqa: E402
from isaaclab.envs import ManagerBasedRLEnv  # noqa: E402
from isaaclab.sensors import ContactSensorCfg  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # isaac_lab/
from pib_grasp.env_cfg import DROP_DEPTH, DROP_SPEED, GRASP_TIME_S  # noqa: E402
from pib_grasp.env_cfg_oben import GRASP_XY, PibGraspEnvCfg_Oben, apply_object_oben  # noqa: E402
from pib_grasp import mdp  # noqa: E402
from pib_hand_left_v5_cfg import SERVO_JOINTS  # noqa: E402

BODIES = ["urdf_elbow_lower", "urdf_forearm_left", "urdf_palm_left", "urdf_thumb_rotator_left", "urdf_thumb_proximal",
          "urdf_thumb_tip"] + [f"urdf_finger_{seg}{sfx}" for sfx in ("", "_2", "_3", "_4")
                               for seg in ("proximal", "distal", "tip")]
gap = args.abstand
xy = (GRASP_XY[0] if args.x is None else args.x, GRASP_XY[1] if args.y is None else args.y)
rots = [float(v) for v in args.thumb_rot.split(",")]

cfg = apply_object_oben(PibGraspEnvCfg_Oben(), args.objekt)
cfg.scene.num_envs = args.num_envs
cfg.seed = 1000
cfg.events.place_objects.params.update(center_xy=xy)
if gap is not None:                          # fixed height instead of the rule: offsets so large that min_tip_height applies
    cfg.events.place_objects.params.update(min_tip_height=gap, sphere_offset=1.0, block_offset=1.0)
if args.rot_start_max is not None:
    cfg.events.reset_hand.params["ranges_deg"]["thumb_left_rotator"] = (0.0, args.rot_start_max)
cfg.scene.object.spawn.activate_contact_sensors = True
cfg.scene.object_contact = ContactSensorCfg(
    prim_path="{ENV_REGEX_NS}/Object", history_length=cfg.decimation,
    filter_prim_paths_expr=[f"{{ENV_REGEX_NS}}/Robot/{b}" for b in BODIES])
# table ↔ hand (window test 2026-10-10: "thumb hits the table"): sensor on the kinematic table
cfg.scene.table.spawn.activate_contact_sensors = True
cfg.scene.table_contact = ContactSensorCfg(
    prim_path="{ENV_REGEX_NS}/Table", history_length=cfg.decimation,
    filter_prim_paths_expr=[f"{{ENV_REGEX_NS}}/Robot/{b}" for b in BODIES])
env = ManagerBasedRLEnv(cfg=cfg)
robot, obj, sensor = env.scene["robot"], env.scene["object"], env.scene["object_contact"]
table_sensor = env.scene["table_contact"]
PALM = BODIES.index("urdf_palm_left")
THUMB = [BODIES.index(b) for b in ("urdf_thumb_rotator_left", "urdf_thumb_proximal", "urdf_thumb_tip")]
FINGERS = [i for i, b in enumerate(BODIES) if b.startswith("urdf_finger_")]
ids = [robot.joint_names.index(n) for n in SERVO_JOINTS]
scale = torch.tensor([0.03, 0.03] + [0.1] * 6, device=env.device)
rot_target = torch.tensor([math.radians(rots[i % len(rots)]) for i in range(env.num_envs)], device=env.device)
dt = env.step_dt
early = round(0.1 / dt)
hold_start = round((GRASP_TIME_S + DROP_DEPTH / DROP_SPEED) / dt)
N = env.num_envs


def rule_action(hold_q):
    """Rule per environment by its episode time (also after an automatic reset): hold forearm/wrist, rotator
    to its target, from 0.4 s on close thumb + fingers. hold_q is set from the start position at episode start."""
    q = robot.data.joint_pos[:, ids]
    new = env.episode_length_buf == 0
    hold_q[new] = q[new]
    t = ((env.episode_length_buf + 1) * dt)[:, None]
    a = torch.zeros(N, 8, device=env.device)
    a[:, :2] = ((hold_q[:, :2] - q[:, :2]) / scale[:2]).clamp(-1, 1)
    if args.handgelenk is not None:                                # wrist (index 1) to its target angle from 0.4 s on
        wrist = ((math.radians(args.handgelenk) - q[:, 1:2]) / scale[1]).clamp(-1, 1)
        a[:, 1:2] = torch.where(t >= 0.4, wrist, a[:, 1:2])
    a[:, 2] = ((rot_target - q[:, 2]) / scale[2]).clamp(-1, 1)
    a[:, 3:] = 0.2 * (t >= 0.4).float()
    return a


with torch.inference_mode():
    env.reset(seed=1000)
    hold_q = robot.data.joint_pos[:, ids].clone()
    alive = torch.ones(N, dtype=torch.bool, device=env.device)
    start_contact = torch.zeros(N, device=env.device)
    fingers = torch.zeros(N, device=env.device)
    palm = torch.zeros(N, device=env.device)                      # steps of the hold phase with the palm on the object
    table_thumb = torch.zeros(N, device=env.device)               # largest force table ↔ thumb / fingers [N]
    table_fingers = torch.zeros(N, device=env.device)
    table_fingers_early = torch.zeros(N, device=env.device)       # … before closing (until 0.4 s): reset overlap
    n_hold = 0
    xy0 = obj.data.root_pos_w[:, :2].clone()
    for step in range(1, int(env.max_episode_length)):
        t0 = time.time()
        _, _, term, trunc, _ = env.step(rule_action(hold_q))
        alive &= ~(term | trunc)
        if step <= early:
            # (N, history, bodies=1, filters, 3): largest force of a hand body over both substeps
            start_contact = torch.maximum(start_contact, sensor.data.force_matrix_w_history[:, :, 0].norm(dim=-1)
                                          .amax(dim=(1, 2)))
            xy0 = obj.data.root_pos_w[:, :2].clone()
        tf = table_sensor.data.force_matrix_w_history[:, :, 0].norm(dim=-1).amax(dim=1)     # (N, bodies)
        table_thumb = torch.maximum(table_thumb, tf[:, THUMB].amax(-1) * alive)
        table_fingers = torch.maximum(table_fingers, tf[:, FINGERS].amax(-1) * alive)
        if step * dt < 0.4:
            table_fingers_early = torch.maximum(table_fingers_early, tf[:, FINGERS].amax(-1) * alive)
        if step >= hold_start:
            fingers += (mdp.fingertip_object_forces(env) > 1.0).float().sum(-1) * alive
            palm += (sensor.data.force_matrix_w[:, 0, PALM].norm(dim=-1) > 1.0).float() * alive
            n_hold += 1
        if args.real_time:
            time.sleep(max(0.0, dt - (time.time() - t0)))
    path = torch.norm(obj.data.root_pos_w[:, :2] - xy0, dim=-1)

lines = [f"== {args.objekt} | Pose env_cfg_oben, tiefste Spitze {1000 * env.pib_tip_height.mean():.0f} mm "
         f"über dem Tisch (Mittel) | Mitte x {1000 * xy[0]:+.0f} y {1000 * xy[1]:+.0f} mm | "
         + (f"Rotator-Start 0–{args.rot_start_max:.0f}° | " if args.rot_start_max is not None else "")
         + (f"Handgelenk {args.handgelenk:.0f}° | " if args.handgelenk is not None else "")
         + f"{N} Umgebungen, Regel „alle schließen“ (0,2), Seed 1000"]
for k, rot in enumerate(rots):
    m = torch.tensor([i % len(rots) == k for i in range(N)], device=env.device)
    held = alive & m
    n, nh = int(m.sum()), int(held.sum())
    lines.append(f"  Rotator {rot:3.0f}°: gehalten {nh:2d}/{n}  Startkontakt > 0,5 N {int((start_contact[m] > 0.5).sum()):2d}/{n}"
                 f" (max {start_contact[m].max():.1f} N)  Objektweg gehalten "
                 + (f"{1000 * path[held].mean():.0f} mm" if nh else "–")
                 + "  Finger am Objekt " + (f"{(fingers[held] / max(n_hold, 1)).mean():.1f}" if nh else "–")
                 + "  Handfläche am Objekt " + (f"{100 * (palm[held] / max(n_hold, 1)).mean():.0f} %" if nh else "–")
                 + f"  Tisch↔Daumen > 1 N {int((table_thumb[m] > 1).sum())}/{n} (max {table_thumb[m].max():.0f} N)"
                 + f"  Tisch↔Finger > 1 N {int((table_fingers[m] > 1).sum())}/{n} (max {table_fingers[m].max():.0f} N;"
                 f" vor dem Schließen {int((table_fingers_early[m] > 1).sum())}/{n})")
text = "\n".join(lines)
print(text, flush=True)
with open(Path(__file__).resolve().parents[2] / "isaac_sim" / "tools" / "_machbarkeit_oben.txt", "a", encoding="utf-8") as f:
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
