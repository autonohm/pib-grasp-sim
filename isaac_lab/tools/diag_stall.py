"""
diag_stall.py — Where does the measured servo stall come from? (2026-10-13, finding A: pushing against the own joint limit)

The relative action sets the position target in every physics step to current position + scale·a and does not clip it to the
joint limits; the torque is Isaac Lab's PD estimate (applied_torque). At a blocked joint, "stall" is therefore just
|a| ≥ ~0.7 — no matter whether the object, the stop or another finger blocks it. On the real hand the 6 hand servos (all except
forearm and wrist) pull via a tendon and a spring opens: there is no torque in the opening direction there.

Splits the stall (|τ| ≥ 80 % stall torque, as in training and the overload protection) per servo into pulling (τ > 0,
flexion/opposition) or pushing (τ < 0), each "at the stop" (≤ 1° from the limit in the torque direction), "finger on the
object" (a body of the finger > 1 N on the object), "other" (free, another finger, back of the finger …). Separately for the
grasp phase (t < 2 s) and the hold phase (t ≥ 2.5 s); plus the overload protection (run > 2 s) as before and with pulling only
for the tendon servos. Base task as in eval-v2, deterministic, seed 1000. Report: isaac_sim/tools/_diag_stall_<name>_<objekt>.txt/.json

  ~/IsaacLab/isaaclab.sh -p isaac_lab/tools/diag_stall.py --headless --name EXP-036_s42 \
      --policy <run>/exported/policy.pt --action_scale 0.1 [--action_clip 1.0 --action_filter 0.3] --objekt zylinder_d6
"""
import argparse
import json
import math
import os
import sys
from pathlib import Path

from isaaclab.app import AppLauncher

parser = argparse.ArgumentParser()
parser.add_argument("--policy", required=True)
parser.add_argument("--name", required=True)
parser.add_argument("--objekt", default="zylinder_d6")
parser.add_argument("--num_envs", type=int, default=256)
parser.add_argument("--action_clip", type=float, default=0.0)
parser.add_argument("--action_filter", type=float, default=0.0)
parser.add_argument("--action_scale", type=float, default=0.0)
parser.add_argument("--rauschen", type=float, default=0.0, help="σ des Aktionsrauschens wie im Training (Policy/mean_noise_std)")
parser.add_argument("--nur_rauschen", action="store_true", help="Mittelwert 0 statt Policy (Trainingsbeginn)")
AppLauncher.add_app_launcher_args(parser)
args = parser.parse_args()
app = AppLauncher(args).app

import gymnasium as gym  # noqa: E402
import torch  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # isaac_lab/
import pib_grasp  # noqa: E402,F401
from pib_grasp.env_cfg import PibGraspEnvCfg, apply_object, filtered_servo_action  # noqa: E402
from pib_hand_left_v5_cfg import SERVO_JOINTS, WRIST_JOINT  # noqa: E402
from isaaclab.sensors import ContactSensorCfg  # noqa: E402

FRACTION, PROTECT_S, LIMIT_TOL = 0.8, 2.0, math.radians(1.0)
GRASP_END_S, HOLD_START_S = 2.0, 2.5
JOINTS = [j for j in SERVO_JOINTS if j != WRIST_JOINT]                # like STALL_JOINTS (training) and eval_policy
TENDON = [j != "forearm_left" for j in JOINTS]                         # tendon + return spring: all except the forearm
FINGER = {"thumb_left_rotator": ["urdf_thumb_rotator_left", "urdf_thumb_proximal", "urdf_thumb_tip"],
          "thumb_left_proximal": ["urdf_thumb_proximal", "urdf_thumb_tip"]}
for _j, _sfx in (("index", ""), ("middle", "_2"), ("ring", "_3"), ("pinky", "_4")):
    FINGER[f"{_j}_left_proximal"] = [f"urdf_finger_{s}{_sfx}" for s in ("proximal", "distal", "tip")]
BODIES = sorted({b for v in FINGER.values() for b in v})

cfg = apply_object(PibGraspEnvCfg(), args.objekt)
cfg.scene.num_envs = args.num_envs
cfg.seed = 1000
if args.action_filter > 0:
    cfg.actions.servos = filtered_servo_action(args.action_filter)
if args.action_scale > 0:
    cfg.actions.servos.scale = args.action_scale
cfg.scene.object.spawn.activate_contact_sensors = True
cfg.scene.object_contact = ContactSensorCfg(
    prim_path="{ENV_REGEX_NS}/Object", history_length=cfg.decimation,
    filter_prim_paths_expr=[f"{{ENV_REGEX_NS}}/Robot/{b}" for b in BODIES])
env = gym.make("Pib-Grasp-Hand-Left-v0", cfg=cfg)
u = env.unwrapped
robot, sens = u.scene["robot"], u.scene["object_contact"]
ids = [robot.joint_names.index(j) for j in JOINTS]
body_idx = [[BODIES.index(b) for b in FINGER.get(j, [])] for j in JOINTS]
tendon = torch.tensor(TENDON, device=u.device)
policy = torch.jit.load(args.policy, map_location=u.device).eval()
N, J, dev = u.num_envs, len(JOINTS), u.device
KEYS = ["zug_anschlag", "zug_objekt", "zug_sonst", "druck_anschlag", "druck_objekt", "druck_sonst"]
cnt = {ph: {k: torch.zeros(J, device=dev) for k in KEYS} for ph in ("greifen", "halten", "gesamt")}
for _ph in cnt:
    cnt[_ph]["schritte"] = torch.zeros((), device=dev)
run_all, run_zug, run_fw = (torch.zeros(N, J, device=dev) for _ in range(3))
max_all, max_zug, max_fw = (torch.zeros(N, device=dev) for _ in range(3))

with torch.inference_mode():
    obs, _ = env.reset(seed=1000)
    alive = torch.ones(N, dtype=torch.bool, device=dev)
    lo, hi = robot.data.joint_pos_limits[:, ids, 0], robot.data.joint_pos_limits[:, ids, 1]
    for k in range(1, int(u.max_episode_length)):
        a = policy(obs["policy"])
        if args.nur_rauschen:
            a = torch.zeros_like(a)
        if args.rauschen > 0:
            a = a + args.rauschen * torch.randn_like(a)
        if args.action_clip > 0:
            a = a.clamp(-args.action_clip, args.action_clip)
        obs, _, term, trunc, _ = env.step(a)
        alive &= ~term
        live = alive & ~trunc                                     # timeout: the step after it is already reset
        t = k * u.step_dt
        tau = robot.data.applied_torque[:, ids]
        q = robot.data.joint_pos[:, ids]
        stall = tau.abs() >= FRACTION * robot.data.joint_effort_limits[:, ids]
        zug, druck = stall & (tau > 0), stall & (tau < 0)
        f = sens.data.force_matrix_w_history[:, :, 0].norm(dim=-1).amax(dim=1)       # (N, bodies)
        touch = torch.stack([(f[:, b] > 1.0).any(-1) if b else torch.zeros(N, dtype=torch.bool, device=dev)
                             for b in body_idx], dim=-1)                              # (N, J)
        at_hi, at_lo = q >= hi - LIMIT_TOL, q <= lo + LIMIT_TOL
        cls = {"zug_anschlag": zug & at_hi, "zug_objekt": zug & ~at_hi & touch, "zug_sonst": zug & ~at_hi & ~touch,
               "druck_anschlag": druck & at_lo, "druck_objekt": druck & ~at_lo & touch,
               "druck_sonst": druck & ~at_lo & ~touch}
        phases = {"gesamt": live, "greifen": live & (t < GRASP_END_S), "halten": live & (t >= HOLD_START_S)}
        for ph, m in phases.items():
            cnt[ph]["schritte"] += m.sum()
            for key, c in cls.items():
                cnt[ph][key] += (c & m[:, None]).float().sum(0)
        real = torch.where(tendon[None, :], zug, stall)          # as on the real servo: the tendon only pulls
        fw = real & ~torch.where(tau > 0, at_hi, at_lo)           # and firmware angle limits: no pushing against the stop
        run_all = torch.where(stall & live[:, None], run_all + 1, torch.zeros_like(run_all))
        run_zug = torch.where(real & live[:, None], run_zug + 1, torch.zeros_like(run_zug))
        max_all = torch.where(live, torch.maximum(max_all, run_all.max(-1).values), max_all)
        max_zug = torch.where(live, torch.maximum(max_zug, run_zug.max(-1).values), max_zug)
        run_fw = torch.where(fw & live[:, None], run_fw + 1, torch.zeros_like(run_fw))
        max_fw = torch.where(live, torch.maximum(max_fw, run_fw.max(-1).values), max_fw)
    held = alive

out = {"name": args.name, "objekt": args.objekt, "num_envs": N, "gehalten": int(held.sum()), "servos": JOINTS,
       "sehne": TENDON, "phasen": {}}
lines = [f"== Stall-Herkunft {args.name} · {args.objekt} · {N} Umgebungen, Seed 1000, gehalten {int(held.sum())}/{N}"
         + (f" · Aktionsrauschen σ {args.rauschen}" if args.rauschen > 0 else "") + (" · nur Rauschen" if args.nur_rauschen else ""),
         "Anteil der Schritte je Servo mit |τ| ≥ 80 % Stall-Moment; Zug = Beugen/Opposition (Sehne), Druck = Öffnen "
         "(real nur Feder). Anschlag = ≤ 1° vor der Grenze, Objekt = ein Körper des Fingers > 1 N am Objekt.", ""]
for ph in ("greifen", "halten", "gesamt"):
    n = cnt[ph]["schritte"].clamp(min=1)
    tab = {key: (cnt[ph][key] / n).tolist() for key in KEYS}
    out["phasen"][ph] = tab
    lines.append(f"-- Phase {ph} ({int(cnt[ph]['schritte'].item())} Umgebungs-Schritte)")
    lines.append(f"{'Servo':22s} {'Stall':>6s} | " + " ".join(f"{k:>14s}" for k in KEYS) + f" | {'Zug':>6s} {'wie real':>8s}")
    for j, name in enumerate(JOINTS):
        tot = sum(tab[key][j] for key in KEYS)
        real = sum(tab[key][j] for key in KEYS if key.startswith("zug") or not TENDON[j])
        fwj = sum(tab[key][j] for key in KEYS if (key.startswith("zug") or not TENDON[j]) and not key.endswith("anschlag"))
        lines.append(f"{name:22s} {100 * tot:5.1f}% | " + " ".join(f"{100 * tab[key][j]:13.1f}%" for key in KEYS)
                     + f" | {100 * real:5.1f}% {100 * fwj:7.1f}%")
    mean_tot = sum(sum(tab[key][j] for key in KEYS) for j in range(J)) / J
    mean_real = sum(sum(tab[key][j] for key in KEYS if key.startswith("zug") or not TENDON[j]) for j in range(J)) / J
    mean_fw = sum(sum(tab[key][j] for key in KEYS if (key.startswith("zug") or not TENDON[j]) and not key.endswith("anschlag"))
                  for j in range(J)) / J
    out["phasen"][ph].update(mittel_alle=mean_tot, mittel_zug=mean_real, mittel_wie_real=mean_fw)
    lines.append(f"{'Mittel (= Servo-Last)':22s} {100 * mean_tot:5.1f}% | Sehnen-Servos nur Zug {100 * mean_real:5.1f}% | "
                 f"dazu ohne Anschlag (Firmware-Grenzen) {100 * mean_fw:5.1f}%")
    lines.append("")
dt = u.step_dt
def _schutz(mx):
    if not held.any():
        return float("nan"), float("nan")
    return (mx[held] * dt > PROTECT_S).float().mean().item(), (mx[held] * dt).median().item()


(s_all, med_all), (s_zug, med_zug), (s_fw, med_fw) = _schutz(max_all), _schutz(max_zug), _schutz(max_fw)
out["schutz"] = {"anteil_alle": s_all, "anteil_zug": s_zug, "anteil_wie_real": s_fw,
                 "lauf_median_alle_s": med_all, "lauf_median_zug_s": med_zug, "lauf_median_wie_real_s": med_fw}
lines.append(f"Überlastschutz (gehaltene Episoden, Lauf ≥ 80 % am Stück > {PROTECT_S:.0f} s): bisher {100 * s_all:.0f} % "
             f"(längster Lauf Median {med_all:.2f} s) · Sehnen nur Zug {100 * s_zug:.0f} % ({med_zug:.2f} s) · "
             f"dazu ohne Anschlag {100 * s_fw:.0f} % ({med_fw:.2f} s)")
base = Path(__file__).resolve().parents[2] / "isaac_sim" / "tools" / f"_diag_stall_{args.name}_{args.objekt}"
base.with_suffix(".txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
base.with_suffix(".json").write_text(json.dumps(out, indent=1), encoding="utf-8")
print("\n".join(lines), flush=True)
sys.stdout.flush()
os._exit(0)
