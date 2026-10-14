"""
pruef_bewegung.py — Are the fictitious forces of the load test (mdp.apply_arm_motion) correct?

An object floats in the inertial frame (counter-force −m·g, rotated along in the hand frame), 0.45 m from the elbow as
in the scene, free of hand and table: x_I(t) = x0. In the frame of the hand, which moves with the arm, it must then
follow exactly
  translation:  p_H(t) = x_I(t) − D·s(t)·d                     (d = direction, s = minimum jerk or ramp)
  rotation:     p_H(t) = P + R(θ(t))ᵀ·(x_I(t) − P)             (P = pivot = hand root, θ about the fixed axis)
This checks all terms together (translation, rotated gravity, Euler, centrifugal and Coriolis forces), independently
of the formula in the code. Report: isaac_sim/tools/_pruef_bewegung.txt

  ~/IsaacLab/isaaclab.sh -p isaac_lab/tools/pruef_bewegung.py --headless
"""
import argparse
import math
import os
import sys
from pathlib import Path

from isaaclab.app import AppLauncher

parser = argparse.ArgumentParser()
parser.add_argument("--num_envs", type=int, default=12)
AppLauncher.add_app_launcher_args(parser)
args = parser.parse_args()
app = AppLauncher(args).app

import gymnasium as gym  # noqa: E402
import torch  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # isaac_lab/
import pib_grasp  # noqa: E402,F401
from pib_grasp import mdp  # noqa: E402
from pib_grasp.env_cfg import PibGraspEnvCfg  # noqa: E402

cfg = PibGraspEnvCfg()
cfg.scene.num_envs = args.num_envs
cfg.terminations.object_dropped = None          # the free object falls on purpose
env = gym.make("Pib-Grasp-Hand-Left-v0", cfg=cfg)
uenv = env.unwrapped
obj, robot = uenv.scene["object"], uenv.scene["robot"]
dev, N, dt = uenv.device, uenv.num_envs, uenv.step_dt
START = 0.1                                     # motion start [s] after the release
DAUER = 0.75                                    # observation [s]
g = torch.tensor((0.0, 0.0, -9.81), device=dev)
H = uenv.physics_dt                             # Physikschritt (1/120 s)

FAELLE = [("frei", 0.0), ("frei", 0.0), ("transport", 5.0), ("transport", 20.0), ("rampe", 20.0), ("gieren", 0.6), ("nicken", 0.6), ("nicken", 0.35)]
lines = [f"Prüfung Scheinkräfte (mdp.apply_arm_motion), {N} Umgebungen, Δt {dt:.4f} s, Start {START} s nach Freigabe", ""]


def rot_T(v, n, theta):
    """R(θ)ᵀ·v = v um −θ um n drehen (Rodrigues)."""
    return mdp._rotate(v, n, -theta[:, None])


for nr, (art, param) in enumerate(FAELLE):
    env.reset(seed=0)
    # release the object: behind the back of the hand (+x), 25 cm above the hand, at rest — r ≈ 0.45 m to the elbow
    pose = obj.data.root_state_w[:, :7].clone()
    pose[:, :3] = uenv.scene.env_origins + torch.tensor((0.3, -0.34, 0.75), device=dev)
    obj.write_root_pose_to_sim(pose)
    obj.write_root_velocity_to_sim(torch.zeros(N, 6, device=dev))
    x0 = pose[:, :3].clone()
    pivot = robot.data.root_pos_w.clone()
    t, worst, worst_rel, weg_max = 0.0, 0.0, 0.0, 0.0
    act = torch.zeros(N, uenv.action_manager.total_action_dim, device=dev)
    k = torch.arange(N, device=dev) % len(mdp.BEWEGUNG_RICHTUNGEN.get(art, (0,)))
    while t < DAUER - 1e-9:
        if art != "frei":                       # free = floating force only (control)
            mdp.apply_arm_motion(uenv, art, param, torch.full((N,), t, device=dev), start_s=START)
        else:
            obj.permanent_wrench_composer.set_forces_and_torques(forces=torch.zeros(N, 1, 3, device=dev),
                                                                 torques=torch.zeros(N, 1, 3, device=dev), is_global=True)
        # floating force −m·g in the inertial frame, rotated with R(θ)ᵀ in the hand frame (rotation at mid-step as in the mdp)
        m_obj = obj.root_physx_view.get_masses().to(dev)[:, :, None]
        th = torch.zeros(N, device=dev)
        if art in ("gieren", "nicken"):
            n_ax = torch.tensor((0.0, 0.0, 1.0) if art == "gieren" else (1.0, 0.0, 0.0), device=dev)
            sgn = torch.tensor((1.0, -1.0), device=dev)[k]
            th = sgn * mdp.DREH_RAD * mdp.min_jerk(torch.full((N,), t + dt / 2 - START, device=dev), param)[0]
            up = rot_T(-g.expand(N, 3), n_ax, th)
        else:
            up = -g.expand(N, 3)
        obj.permanent_wrench_composer.add_forces_and_torques(forces=(m_obj * up[:, None, :]).contiguous(),
                                                             torques=torch.zeros(N, 1, 3, device=dev), is_global=True)
        env.step(act)
        t += dt
        tt = torch.full((N,), t, device=dev)
        x_i = x0                                     # floats in the inertial frame
        tau = tt - START
        if art == "frei":
            pred, bewegung = x_i, torch.zeros(N, device=dev)
        elif art in ("transport", "rampe"):
            d = torch.tensor(mdp._ACHSEN6, dtype=torch.float32, device=dev)[k]
            if art == "transport":
                s, _, _ = mdp.min_jerk(tau, mdp.transport_dauer(param))
                weg = mdp.TRANSPORT_M * s
            else:
                tc = tau.clamp(0.0, mdp.RAMPE_S)
                weg = param / mdp.RAMPE_S * tc ** 3 / 6                # Fenster < RAMPE_S
            pred = x_i - weg[:, None] * d
            bewegung = weg.abs()
        else:
            n = torch.tensor((0.0, 0.0, 1.0) if art == "gieren" else (1.0, 0.0, 0.0), device=dev)
            sign = torch.tensor((1.0, -1.0), device=dev)[k]
            s, _, _ = mdp.min_jerk(tau, param)
            theta = sign * mdp.DREH_RAD * s
            pred = pivot + rot_T(x_i - pivot, n, theta)
            bewegung = torch.norm(pred - x_i, dim=-1)
        err = torch.norm(obj.data.root_pos_w - pred, dim=-1)
        worst = max(worst, err.max().item())
        weg_max = max(weg_max, bewegung.max().item())
        if bewegung.max() > 0.01:
            worst_rel = max(worst_rel, (err / bewegung.clamp(min=0.01)).max().item())
    if nr == 0:                                 # first run after the start: the teleport takes effect with a delay (warm-up)
        continue
    lines.append(f"{art}:{param:<5} Abweichung max {1000 * worst:6.2f} mm bei Weg max {1000 * weg_max:5.0f} mm "
                 f"({100 * worst / max(weg_max, 1e-3):4.1f} %)")
    print(lines[-1], flush=True)

lines += ["", f"Drehpunkt (Hand-Root, Umgebung 0, relativ zum Ursprung): "
          f"{(robot.data.root_pos_w[0] - uenv.scene.env_origins[0]).tolist()}",
          f"Objekt-Startlage (Umgebung 0, relativ): {(obj.data.default_root_state[0, :3]).tolist()}",
          "Erwartung: Abweichung wenige mm (Zeitdiskretisierung, Kraft je Schritt konstant)."]
out = Path(__file__).resolve().parents[2] / "isaac_sim" / "tools" / "_pruef_bewegung.txt"
out.write_text("\n".join(lines) + "\n", encoding="utf-8")
print("\n".join(lines), flush=True)
sys.stdout.flush()
os._exit(0)
