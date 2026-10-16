"""
dump_pose.py — reads the current drive targets (degrees, Onshape convention
since ADR-007) of the joints from the open stage and appends them as a waypoint
to isaac_sim/tools/_pose_dump.json — for turning them into a new
test client (test_client_*.py) without having to copy-paste the values from the
Isaac Sim console (often not cleanly selectable there).

Background: test pose sequences are still created manually — the robot is posed by hand
in Isaac Sim (Physics Inspector / drive target sliders), see
docs/protokoll/handoff.md. This script only replaces the error-prone typing/
copying of the values. It reads the same attribute that setup_stage.set_initial_pose()
sets (UsdPhysics.DriveAPI "angular" → TargetPosition, degrees) — i.e. exactly the
values that were actually set while posing manually.

Usage (one run per waypoint):
  1. Bring the robot into the desired pose manually in Isaac Sim (Play on,
     move to the target pose via drive targets/Physics Inspector, let it
     settle briefly).
  2. Adjust WAYPOINT_LABEL/WAYPOINT_TIME_S below.
  3. Run this script in the Script Editor — it appends the waypoint to
     _pose_dump.json (existing waypoints are kept).
  4. When all waypoints are in: hand the file over for processing.

Run in the Script Editor.
"""
from pathlib import Path
import json
import os
import omni.usd
from pxr import UsdPhysics

stage = omni.usd.get_context().get_stage()


def _find_root() -> Path:
    # Repo root without a fixed install path: PIB_GRASP_SIM_ROOT, else upwards from this file, the open stage or the
    # working directory until config/ is found (__file__ is not defined in the Script Editor's exec context)
    if os.environ.get("PIB_GRASP_SIM_ROOT"):
        return Path(os.environ["PIB_GRASP_SIM_ROOT"])
    starts = [Path.cwd()]
    try:
        import omni.usd  # type: ignore
        starts.insert(0, Path(omni.usd.get_context().get_stage().GetRootLayer().realPath or "."))
    except Exception:
        pass
    if "__file__" in globals():
        starts.insert(0, Path(__file__))
    for start in starts:
        for d in [start.resolve(), *start.resolve().parents]:
            if (d / "config" / "pib_hand_config_v4.py").is_file():
                return d
    raise FileNotFoundError("Repo-Wurzel nicht gefunden — Stage aus dem Repo öffnen oder PIB_GRASP_SIM_ROOT setzen")


DUMP_FILE = os.path.join(_find_root(), "isaac_sim", "tools", "_pose_dump.json")

# --- Pro Waypoint anpassen -------------------------------------------------
WAYPOINT_LABEL = "neutral"   # z.B. "neutral", "approach", "grasp", "lift"
WAYPOINT_TIME_S = 2.0         # target time relative to the sequence start (seconds)

# Leave empty = all PhysicsRevoluteJoint prims in the stage (all 44 DOFs).
# Restrict it for a specific sequence, e.g.:
# JOINT_FILTER = [
# "dof_shoulder_vertical_right", "dof_shoulder_horizontal_right",
# "dof_elbow_right", "dof_forearm_right", "dof_wrist_right",
# "dof_thumb_right_rotator", "dof_index_right_proximal",
# ]
JOINT_FILTER: list = []
# ---------------------------------------------------------------------------

pose = {}
for prim in stage.Traverse():
    if prim.GetTypeName() != "PhysicsRevoluteJoint":
        continue
    name = prim.GetPath().name
    if JOINT_FILTER and name not in JOINT_FILTER:
        continue
    drive = UsdPhysics.DriveAPI.Get(prim, "angular")
    if not drive:
        continue
    pose[name] = round(drive.GetTargetPositionAttr().Get(), 1)

data = {}
if os.path.isfile(DUMP_FILE):
    with open(DUMP_FILE) as f:
        data = json.load(f)

data[WAYPOINT_LABEL] = {"t": WAYPOINT_TIME_S, "positions_deg": pose}

with open(DUMP_FILE, "w") as f:
    json.dump(data, f, indent=2, ensure_ascii=False, sort_keys=False)

print(f"Waypoint '{WAYPOINT_LABEL}' (t={WAYPOINT_TIME_S}s, {len(pose)} Gelenke) -> {DUMP_FILE}")
print("Bisherige Waypoints in der Datei:", list(data.keys()))

