"""
setup_stage.py — stage setup for pib in Isaac Sim.

Run in the Script Editor to:
  1. set up the physics scene, ground and light
  2. configure the joint drives — v5: servo actuator model from datasheets
     (ADR-012), passive mimic followers (ADR-011); v4: reference values of 0fdbc62
  3. set mimic joints (v5), joint limits and the initial pose (T pose, all targets 0°)

Then save the stage (Ctrl+S) and press Play.

Importable from start.py — _SKIP_AUTO_SETUP = True (set before exec_module)
prevents automatic execution on import.
"""
import os
import importlib.util
from pathlib import Path

import omni.usd  # type: ignore
from pxr import UsdGeom, UsdLux, UsdPhysics, PhysxSchema, Gf  # type: ignore

stage = omni.usd.get_context().get_stage()

# ── Config laden ──────────────────────────────────────────────────────────────
def _find_project_root() -> str:
    if "PIB_HAND_SIM_ROOT" in os.environ:
        return os.environ["PIB_HAND_SIM_ROOT"]
    stage_file = Path(stage.GetRootLayer().realPath)
    for ancestor in [stage_file.parent, stage_file.parent.parent]:
        if (ancestor / "config" / "pib_hand_config_v4.py").is_file():
            return str(ancestor)
    for candidate in [Path.home() / "repos" / "pib-hand-sim", Path.home() / "pib-hand-sim"]:
        if (candidate / "config" / "pib_hand_config_v4.py").is_file():
            return str(candidate)
    raise FileNotFoundError("pib-hand-sim nicht gefunden. PIB_HAND_SIM_ROOT setzen.")

_root = _find_project_root()
_spec = importlib.util.spec_from_file_location("pib_hand_config_v4", f"{_root}/config/pib_hand_config_v4.py")
_cfg  = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_cfg)
ROBOT_PRIM_PATH = _cfg.ROBOT_PRIM_PATH


# ── v4: reference drives (unchanged since 0fdbc62) ────────────────────────────
# v4 stays the verified reference: these gains, maxForce=inf, no armature/
# velocity limit. The servo actuator model (below) only applies to v5 — v4 names
# have the prefix "dof_".

def _v4_gains(name: str) -> tuple:
    """(stiffness Nm/°, damping Nm·s/°) for v4 joints."""
    n = name.lower()
    if "head" in n:
        return 3000.0, 150.0
    if any(k in n for k in ("shoulder", "upper_arm", "elbow", "forearm")):
        return 5000.0, 200.0
    if "wrist" in n:
        return 2000.0, 100.0
    if "rotator" in n:
        return 1000.0, 50.0
    if any(k in n for k in ("proximal", "distal", "tip")):
        return 500.0, 20.0
    return 1000.0, 50.0                                 # Fallback


# ── v5: servo actuator model (ADR-012) ────────────────────────────────────────
# Datasheet values, joint groups and recipe live in config/pib_hand_config_v5.py
# (SERVOS, V5_ACTUATORS, servo_actuator) — one source for Isaac Sim and Isaac Lab.
# Only the prim units (Nm/°, Nm·s/°, °/s) are used here.
_spec5 = importlib.util.spec_from_file_location("pib_hand_config_v5", f"{_root}/config/pib_hand_config_v5.py")
_cfg5  = importlib.util.module_from_spec(_spec5)
_spec5.loader.exec_module(_cfg5)
FOLLOWER_ARMATURE_KGM2 = _cfg5.FOLLOWER_ARMATURE_KGM2
FOLLOWER_MAX_VELOCITY_DEG_S = _cfg5.FOLLOWER_MAX_VELOCITY_DEG_S


def _v5_actuator(name: str):
    """
    Parameters of a servo-driven v5 joint in prim units as a dict (servo,
    stiffness, damping, max_force, armature, max_velocity), otherwise None.
    """
    act = _cfg5.servo_actuator(name)
    if act is None:
        return None
    return {"servo": act["servo"], "stiffness": act["stiffness_deg"],
            "damping": act["damping_deg"], "max_force": act["max_force"],
            "armature": act["armature"], "max_velocity": act["max_velocity_deg"]}


# ── Mimic joints (stage 1: linear, v5 only) ───────────────────────────────────
# follower -> (reference joint, gearing, offset). PhysX formula (from
# generatedSchema.usda): q_follower + gearing * q_reference + offset = 0.
# gearing=-1, offset=0  =>  theta_follower = theta_reference. Exact at 0° and 90°;
# in the middle the real four-bar coupling deviates by up to ~10° (PIP) / ~22° (DIP)
# (tendondrive/finger_analytisch.py). The only place for gearing/offset —
# a later adaptive stage 2 only changes these values.
# v4 joints (dof_ prefix) are deliberately not included.
MIMIC_GEARING = -1.0
MIMIC_OFFSET = 0.0


def _build_mimic_joints() -> dict:
    joints = {}
    for side in ("left", "right"):
        for finger in ("index", "middle", "ring", "pinky"):
            joints[f"{finger}_{side}_distal"] = (f"{finger}_{side}_proximal", MIMIC_GEARING, MIMIC_OFFSET)  # PIP <- MCP
            joints[f"{finger}_{side}_tip"] = (f"{finger}_{side}_distal", MIMIC_GEARING, MIMIC_OFFSET)       # DIP <- PIP
        joints[f"thumb_{side}_tip"] = (f"thumb_{side}_proximal", MIMIC_GEARING, MIMIC_OFFSET)               # IP  <- MCP
    return joints


MIMIC_JOINTS = _build_mimic_joints()

# mimic instance name per physics:axis of the joint prim (multiple-apply schema)
_MIMIC_AXIS = {"X": "rotX", "Y": "rotY", "Z": "rotZ"}


# ── Setup-Funktionen ──────────────────────────────────────────────────────────

def configure_physics_scene(stg) -> None:
    path = "/World/PhysicsScene"
    if not stg.GetPrimAtPath(path):
        scene = UsdPhysics.Scene.Define(stg, path)
        scene.CreateGravityDirectionAttr(Gf.Vec3f(0.0, 0.0, -1.0))
        scene.CreateGravityMagnitudeAttr(9.81)
        PhysxSchema.PhysxSceneAPI.Apply(stg.GetPrimAtPath(path))
        print("Physics Scene erstellt")
    else:
        print("Physics Scene bereits vorhanden")


def configure_ground(stg) -> None:
    path = "/World/GroundPlane"
    if not stg.GetPrimAtPath(path):
        ground = UsdGeom.Mesh.Define(stg, path)
        ground.CreatePointsAttr([(-5, -5, 0), (5, -5, 0), (5, 5, 0), (-5, 5, 0)])
        ground.CreateFaceVertexCountsAttr([4])
        ground.CreateFaceVertexIndicesAttr([0, 1, 2, 3])
        ground.CreateNormalsAttr([(0, 0, 1)] * 4)
        UsdPhysics.CollisionAPI.Apply(stg.GetPrimAtPath(path))
        print("Boden erstellt")
    else:
        print("Boden bereits vorhanden")


def configure_lights(stg) -> None:
    dome = "/World/DomeLight"
    if not stg.GetPrimAtPath(dome):
        d = UsdLux.DomeLight.Define(stg, dome)
        d.CreateIntensityAttr(500.0)
        print("Dome Light erstellt")
    else:
        print("Dome Light bereits vorhanden")

    sun = "/World/DistantLight"
    if not stg.GetPrimAtPath(sun):
        s = UsdLux.DistantLight.Define(stg, sun)
        s.CreateIntensityAttr(1000.0)
        s.CreateAngleAttr(0.53)
        UsdGeom.XformCommonAPI(s).SetRotate(Gf.Vec3f(315.0, 0.0, 45.0))
        print("Distant Light erstellt")
    else:
        print("Distant Light bereits vorhanden")


def configure_drives(stg) -> int:
    """
    Sets the drives of all PhysicsRevoluteJoint prims:
      v4 (prefix "dof_")       → _v4_gains, maxForce=inf (reference, unchanged)
      v5 mimic followers       → passive: stiffness/damping 0, armature/velocity
                                 from FOLLOWER_* (ADR-011)
      v5 servo joints          → servo actuator model from V5_ACTUATORS (ADR-012)

    Returns: number of configured joints
    """
    count = 0
    groups = {}            # output: (servo, stiffness, damping) -> number of joints
    unknown = []
    for prim in stg.Traverse():
        is_revolute = (prim.GetTypeName() == "PhysicsRevoluteJoint" or
                       prim.HasAPI(UsdPhysics.RevoluteJoint))
        if not is_revolute:
            continue

        name = prim.GetPath().name
        drive = UsdPhysics.DriveAPI.Get(prim, "angular")
        if not drive:
            drive = UsdPhysics.DriveAPI.Apply(prim, "angular")

        if name.startswith("dof_"):
            stiffness, damping = _v4_gains(name)
            drive.GetStiffnessAttr().Set(stiffness)
            drive.GetDampingAttr().Set(damping)
            drive.GetMaxForceAttr().Set(float("inf"))
            groups[("v4", stiffness, damping)] = groups.get(("v4", stiffness, damping), 0) + 1
            count += 1
            continue

        joint_api = PhysxSchema.PhysxJointAPI.Apply(prim)
        if name in MIMIC_JOINTS:
            # Passive — an active drive would work against the constraint.
            drive.GetStiffnessAttr().Set(0.0)
            drive.GetDampingAttr().Set(0.0)
            drive.GetMaxForceAttr().Set(float("inf"))
            joint_api.CreateArmatureAttr().Set(FOLLOWER_ARMATURE_KGM2)
            joint_api.CreateMaxJointVelocityAttr().Set(FOLLOWER_MAX_VELOCITY_DEG_S)
            groups[("Mimic passiv", 0.0, 0.0)] = groups.get(("Mimic passiv", 0.0, 0.0), 0) + 1
            count += 1
            continue

        act = _v5_actuator(name)
        if act is None:
            unknown.append(name)
            continue
        drive.GetStiffnessAttr().Set(act["stiffness"])
        drive.GetDampingAttr().Set(act["damping"])
        drive.GetMaxForceAttr().Set(act["max_force"])
        joint_api.CreateArmatureAttr().Set(act["armature"])
        joint_api.CreateMaxJointVelocityAttr().Set(act["max_velocity"])
        key = (act["servo"], round(act["stiffness"], 4), round(act["damping"], 4))
        groups[key] = groups.get(key, 0) + 1
        count += 1

    print(f"configure_drives: {count} Joints konfiguriert")
    for (label, k, d), n in sorted(groups.items(), key=lambda item: str(item[0])):
        print(f"  {n:2d}x {label:<13} stiffness {k:g} Nm/°, damping {d:g} Nm·s/°")
    if unknown:
        print(f"  WARNUNG: keine Aktuator-Zuordnung für {unknown} — Antrieb unverändert")
    return count


def configure_mimic_joints(stg) -> int:
    """
    Applies PhysxMimicJointAPI to all followers from MIMIC_JOINTS
    (PIP<-MCP, DIP<-PIP, thumb IP<-MCP, both sides = 18 joints). Idempotent.
    On a stage without these joints (v4) nothing happens.

    Instance name = axis of the follower (read from physics:axis, not
    assumed). configure_drives sets the followers' drives to 0 —
    call it first, then Stop -> Play so PhysX loads the constraint.

    Returns: number of configured mimic joints
    """
    joints = {}
    for prim in stg.Traverse():
        is_revolute = (prim.GetTypeName() == "PhysicsRevoluteJoint" or
                       prim.HasAPI(UsdPhysics.RevoluteJoint))
        if is_revolute and prim.GetPath().name in MIMIC_JOINTS:
            joints[prim.GetPath().name] = prim

    def _axis(prim) -> str:
        raw = prim.GetAttribute("physics:axis").Get()
        if raw not in _MIMIC_AXIS:
            raise RuntimeError(f"{prim.GetPath()}: physics:axis = {raw!r}, erwartet X/Y/Z")
        return _MIMIC_AXIS[raw]

    count = 0
    for follower, (reference, gearing, offset) in MIMIC_JOINTS.items():
        follower_prim = joints.get(follower)
        if follower_prim is None:
            continue
        reference_prim = next((p for p in stg.Traverse()
                               if p.GetPath().name == reference and p.GetTypeName() == "PhysicsRevoluteJoint"), None)
        if reference_prim is None:
            print(f"configure_mimic_joints: Referenzgelenk {reference} für {follower} nicht gefunden — übersprungen")
            continue

        mimic = PhysxSchema.PhysxMimicJointAPI.Apply(follower_prim, _axis(follower_prim))
        mimic.CreateGearingAttr().Set(gearing)
        mimic.CreateOffsetAttr().Set(offset)
        mimic.CreateReferenceJointAxisAttr().Set(_axis(reference_prim))
        mimic.GetReferenceJointRel().SetTargets([reference_prim.GetPath()])
        count += 1

    print(f"configure_mimic_joints: {count} Mimic-Gelenke konfiguriert (gearing={MIMIC_GEARING:g}, offset={MIMIC_OFFSET:g})")
    return count


# ── Joint limits ──────────────────────────────────────────────────────────────
# Since isaac_sim/tools/flip_joint_sign.py (run once on the USD) the Onshape
# and Isaac conventions agree — no mirroring needed any more,
# these are directly the Onshape limits (positive = flexion/raise/forward).
#
# dof_upper_arm_left/dof_shoulder_horizontal_right corrected compared with the
# old (mirrored) state: the previous table had guessed a symmetric
# [-90°,90°] here, the real Onshape source is one-sided [0°,90°]
# (verified against ros2_ws/src/pib_description_v4/urdf/pib_upperbody.urdf).
# This applied explicitly to v4 only -- see the v5 block below, where
# upper_arm_left differs again (v5 IS symmetric there).
#
# v5 entries (no "dof_" prefix, see config/pib_hand_config_v5.py for the
# derivation) added in that session: _BODY_LIMITS used to contain only the
# v4 values but was shared by v4 AND v5 (set_joint_limits()
# works by name via stg.Traverse(), without distinguishing versions). As a result
# v5 was wrongly forced onto v4 limits where the real v5 URDF differs:
# upper_arm_left was wrongly restricted to [0°,90°] (real v5 limit:
# [-90°,90°], symmetric to upper_arm_right), wrist_left/wrist_right were at
# [0°,90°] instead of the real v5 limit [-90°,30°] (both sides affected
# equally, no left/right difference). shoulder_horizontal_right [0°,90°], on the
# other hand, is identical in BOTH versions (v4 AND v5 URDF) and not a deviation --
# no correction needed, see config/pib_hand_config_v5.py.
#
# wrist_left/wrist_right v5 (2026-10-04): [-60°, 0°], corrected in Onshape. The
# wrist is driven via a connecting rod that mechanically only allows a 60° swing
# (config/pib_hand_config_v5.py → WRIST_LINKAGE). Sign exception: -60° = fully
# flexed inwards, 0° = straight (docs/conventions.md).

_HAND_KEYWORDS = ("proximal", "distal", "tip", "rotator")

_BODY_LIMITS = {
    # v4 (dof_ prefix, source: pib_description_v4/urdf/pib_upperbody.urdf)
    "dof_head_horizontal":           (-90.0,  90.0),
    "dof_head_vertical":             (-45.0,  70.0),
    "dof_shoulder_vertical_left":    (-90.0,  90.0),
    "dof_shoulder_horizontal_left":  (-90.0,  90.0),
    "dof_upper_arm_left":            (  0.0,  90.0),
    "dof_elbow_left":                (-45.0,  90.0),
    "dof_forearm_left":              (-90.0,  90.0),
    "dof_wrist_left":                (  0.0,  90.0),
    "dof_shoulder_vertical_right":   (-90.0,  90.0),
    "dof_shoulder_horizontal_right": (  0.0,  90.0),
    "dof_upper_arm_right":           (-90.0,  90.0),
    "dof_elbow_right":               (-45.0,  90.0),
    "dof_forearm_right":             (-90.0,  90.0),
    "dof_wrist_right":               (  0.0,  90.0),
    # v5 (no prefix, source: pib_upperbody_urdf_v5/robot.urdf, see
    # config/pib_hand_config_v5.py)
    "head_horizontal":           (-90.0,  90.0),
    "head_vertical":             (-45.0,  70.0),
    "shoulder_vertical_left":    (-90.0,  90.0),
    "shoulder_horizontal_left":  (-90.0,  90.0),
    "upper_arm_left":            (-90.0,  90.0),
    "elbow_left":                (-45.0,  90.0),
    "forearm_left":              (-90.0,  90.0),
    "wrist_left":                (-60.0,   0.0),
    "shoulder_vertical_right":   (-90.0,  90.0),
    "shoulder_horizontal_right": (  0.0,  90.0),
    "upper_arm_right":           (-90.0,  90.0),
    "elbow_right":               (-45.0,  90.0),
    "forearm_right":             (-90.0,  90.0),
    "wrist_right":               (-60.0,   0.0),
}


def set_joint_limits(stg) -> int:
    """
    Sets the joint limits (Onshape convention, identical to the Isaac convention
    since flip_joint_sign.py). Idempotent: always sets the same target value,
    no toggle, no flag.

    Hand/finger joints (proximal/distal/tip/rotator): [0°, 90°]
    Body joints: from _BODY_LIMITS
    """
    count = 0
    for prim in stg.Traverse():
        if prim.GetTypeName() != "PhysicsRevoluteJoint":
            continue
        name = prim.GetPath().name
        lower_attr = prim.GetAttribute("physics:lowerLimit")
        upper_attr = prim.GetAttribute("physics:upperLimit")
        if not (lower_attr and upper_attr):
            continue
        if any(k in name for k in _HAND_KEYWORDS):
            lower_attr.Set(0.0)
            upper_attr.Set(90.0)
            count += 1
        elif name in _BODY_LIMITS:
            lower, upper = _BODY_LIMITS[name]
            lower_attr.Set(lower)
            upper_attr.Set(upper)
            count += 1
    print(f"set_joint_limits: {count} Gelenke konfiguriert")
    return count


def set_initial_pose(stg) -> None:
    """
    Sets all drive targets to 0° (T pose, fully extended) — Onshape
    convention since flip_joint_sign.py, positive = flexion. No special case
    for the elbow any more (it used to be 30°, which was never justified). Traverses
    all PhysicsRevoluteJoint prims generically, no name matching needed
    — works identically for v4 and v5.
    """
    count = 0
    for prim in stg.Traverse():
        is_revolute = (prim.GetTypeName() == "PhysicsRevoluteJoint" or
                       prim.HasAPI(UsdPhysics.RevoluteJoint))
        if not is_revolute:
            continue

        drive = UsdPhysics.DriveAPI.Get(prim, "angular")
        if drive:
            drive.GetTargetPositionAttr().Set(0.0)
            count += 1

    print(f"set_initial_pose: {count} Drive-Targets auf 0° gesetzt (T-Pose)")


def setup_all(stg) -> None:
    configure_physics_scene(stg)
    configure_ground(stg)
    configure_lights(stg)
    configure_drives(stg)
    configure_mimic_joints(stg)
    set_joint_limits(stg)
    set_initial_pose(stg)


# ── Script Editor block ───────────────────────────────────────────────────────
# Skipped when start.py imports this module
# (sets _SKIP_AUTO_SETUP = True before exec_module).
if not globals().get("_SKIP_AUTO_SETUP"):
    setup_all(stage)
    print("\nSetup abgeschlossen. Stage speichern (Ctrl+S), dann Play drücken.")
