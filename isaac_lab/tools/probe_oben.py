"""
probe_oben.py — geometry of the hand in the "top" pose (palm down, forearm horizontal; plan:
docs/protokoll/plan-griff-von-oben.md, step 1). Without gravity, without an object: hand root as in env_cfg_oben (no
rotation, height HAND_POS), all four finger MCPs together 0–90°, thumb at rotator 0/45/90° and thumb MCP 0–90°. Per
position the pose of the fingertip links (joint frames, not the surface) relative to the hand root: lowest point (z) and
where it lies (x across, y along) — from that the pre-grasp distance and object position for the feasibility test.
Report: isaac_sim/tools/_probe_oben.txt

  ~/IsaacLab/isaaclab.sh -p isaac_lab/tools/probe_oben.py --headless
"""
import argparse
import math
import os
import sys
from pathlib import Path

from isaaclab.app import AppLauncher

p = argparse.ArgumentParser()
AppLauncher.add_app_launcher_args(p)
a = p.parse_args()
app = AppLauncher(a).app

import torch  # noqa: E402
import isaaclab.sim as sim_utils  # noqa: E402
from isaaclab.assets import Articulation  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # isaac_lab/
from pib_hand_left_v5_cfg import PIB_HAND_LEFT_V5_CFG  # noqa: E402
from pib_grasp.mdp import FINGERTIP_LINKS  # noqa: E402

HAND_POS, HAND_ROT = (0.0, 0.0, 0.5), (1.0, 0.0, 0.0, 0.0)       # as in env_cfg_oben (HAND_POS, HAND_ROT_OBEN)
LINKS = ["urdf_palm_left", "urdf_thumb_rotator_left", "urdf_thumb_proximal"] + FINGERTIP_LINKS
NAMES = ["Handfläche", "D-Rotator", "D-Grund", "D-Spitze", "Zeige", "Mittel", "Ring", "Klein"]

sim = sim_utils.SimulationContext(sim_utils.SimulationCfg(dt=1 / 120, device=a.device, gravity=(0.0, 0.0, 0.0)))
r = Articulation(PIB_HAND_LEFT_V5_CFG.replace(prim_path="/World/Hand",
                                               init_state=PIB_HAND_LEFT_V5_CFG.init_state.replace(pos=HAND_POS, rot=HAND_ROT)))
sim.reset()
ids = [r.body_names.index(n) for n in LINKS]


def settle(finger_deg: float, thumb_deg: float, rot_deg: float) -> torch.Tensor:
    t = torch.zeros_like(r.data.joint_pos)
    for f in ("index", "middle", "ring", "pinky"):
        t[:, r.joint_names.index(f"{f}_left_proximal")] = math.radians(finger_deg)
    t[:, r.joint_names.index("thumb_left_proximal")] = math.radians(thumb_deg)
    t[:, r.joint_names.index("thumb_left_rotator")] = math.radians(rot_deg)
    for _ in range(240):                                  # 2 s: the servos (270 °/s) reach any position
        r.set_joint_position_target(t)
        r.write_data_to_sim()
        sim.step()
        r.update(sim.get_physics_dt())
    return r.data.body_link_pos_w[0, ids] - torch.tensor(HAND_POS, device=r.device)


def row(label: str, pos: torch.Tensor) -> str:
    return f"{label:18s} " + "  ".join(f"{n}({1000 * v[0]:+5.0f} {1000 * v[1]:+5.0f} {1000 * v[2]:+5.0f})"
                                       for n, v in zip(NAMES, pos.tolist()))


lines = ["Lage relativ zum Hand-Root [mm] (x quer: −Daumen/+kleiner Finger, y längs: − Richtung Fingerspitzen, "
         "z: − nach unten); Handfläche nach unten, keine Schwerkraft", "", "== Finger (Daumen offen, Rotator 0°)"]
for deg in range(0, 91, 10):
    pos = settle(deg, 0.0, 0.0)
    tips = pos[4:]
    k = int(tips[:, 2].argmin())
    lines.append(row(f"MCP {deg:2d}°", pos) + f"   tiefste Fingerspitze {NAMES[4 + k]} z = {1000 * tips[k, 2]:+.0f}")
for rot in (0.0, 45.0, 90.0):
    lines += ["", f"== Daumen (Rotator {rot:.0f}°, Finger offen)"]
    for deg in range(0, 91, 15):
        lines.append(row(f"D-MCP {deg:2d}°", settle(0.0, deg, rot)))
text = "\n".join(lines)
print(text, flush=True)
(Path(__file__).resolve().parents[2] / "isaac_sim" / "tools" / "_probe_oben.txt").write_text(text + "\n", encoding="utf-8")
os._exit(0)
