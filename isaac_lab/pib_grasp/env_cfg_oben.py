"""
env_cfg_oben.py — grasp type "top" (stage 4b, ADR-018, plan: docs/protokoll/plan-griff-von-oben.md).

Start pose from the parallel search (tools/suche_startpose_oben.py, docs/protokoll/startpose-oben/ergebnis.md, 2026-10-11;
modelled on grasp planners "propose → close → evaluate"): hand from above, **tilted 20° about x** (fingers slightly
down), not rolled, **thumb rotator at 75° at the start**, object in the grasp centre between thumb and fingertips. The
height of the lowest fingertip (the thumb) above the table depends on the object (mdp.tip_height_for_object; with it the
rule "close all" reaches 90–100 % on spheres Ø 5/7/9, can, small box and YCB soup, 48 episodes per height). In training
the height is spread ±5 mm per environment and the position ±1 cm (inaccurate pre-grasp pose of the arm).
Sequence as for the side grasp: 0–2 s grasp, 2–2.5 s the table lowers by 10 cm (≙ the arm lifts), then hold.

Rejected: horizontal with 3.5 cm distance (thumb hit the table, sphere Ø 5/small box ≤ 3/24) and tilted 36.5° with
fingertips at equal height (fingers brushed the table while closing, 3–5/24) — plan, sections "Gemessen" and "Stand 2026-10-11".

Reward = side-grasp recipe without orientation terms, like Dexsuite Lift (orientation_tracking = None, success without
rot_std): when lifting, all that counts is that the object stays in the hand. Evaluation without tilt requirement (--max_kipp_deg -1).
"""
import math

import isaaclab.sim as sim_utils
from isaaclab.managers import EventTermCfg as EventTerm
from isaaclab.managers import RewardTermCfg as RewTerm
from isaaclab.utils import configclass

from . import mdp
from .env_cfg import (GRASP_TIME_S, HAND_POS, HOLD_STD_M, START_REF_S, XY_PENALTY_WEIGHT, YCB_SPAWN_LIFT,
                      PibGraspEnvCfg, RewardsProgressCfg, dexsuite_action_space, ycb_upright_usd)

# Pose and geometry (mesh points of the fingertips at rotator 75°, other joints 0, logs/startpose_oben/geometrie.npz from
# tools/probe_neigung_oben.py --dump), relative to the hand root after the rotation, in world axes:
HAND_ROT_OBEN = (0.98481, 0.17365, 0.0, 0.0)                 # (w, x, y, z) = 20° um x
ROTATOR_START_DEG = 75.0
TIP_LOW_Z = HAND_POS[2] - 0.1914                             # lowest point of all five tips (thumb; fingers ≈ −0.150)
GRASP_XY = (HAND_POS[0] - 0.0203, HAND_POS[1] - 0.2870)      # grasp centre: between the thumb tip and the middle of the fingertips
# height of the lowest tip above the table (search): spheres max(10 mm, Ø − 60 mm), otherwise max(10 mm, height − 40 mm)
SPHERE_OFFSET, BLOCK_OFFSET, MIN_TIP_HEIGHT = 0.060, 0.040, 0.010
TRAIN_HEIGHT_JITTER = 0.005          # training: height per environment ±5 mm (evaluation: 0; perturbed condition ±5 mm)
OBJECT_XY_RANGE = {"x": (-0.01, 0.01), "y": (-0.01, 0.01)}
# table around the grasp centre, its height set per environment to the object's bottom (mdp.place_objects_from_above)
TABLE_SIZE_OBEN = (0.30, 0.30, 0.04)

# ── Object catalogue for the top grasp: round, small or flat (ADR-018; the side grasp needs ≥ 15 cm height) ─────────
# shape, dimensions [m] (sphere: radius; cylinder: radius, height; box: x across the fingers, y along, z), yaw on reset
OBJECTS_OBEN = {
    "kugel_d7": {"form": "kugel", "masse": (0.035,), "gier": (-math.pi, math.pi)},          # Apfel-Ersatz (Benchmark)
    "kugel_d5": {"form": "kugel", "masse": (0.025,), "gier": (-math.pi, math.pi)},          # Mandarine/Pflaume
    "kugel_d9": {"form": "kugel", "masse": (0.045,), "gier": (-math.pi, math.pi)},          # orange/large apple
    "dose_d68x10": {"form": "zylinder", "masse": (0.034, 0.10), "gier": (-math.pi, math.pi)},   # kurze Dose aufrecht
    "quader_9x6x4": {"form": "quader", "masse": (0.09, 0.06, 0.04),                          # flache Schachtel
                     "gier": (-math.radians(15), math.radians(15))},
    # Test object (never trained): YCB 005 tomato soup can, 349 g, 6.8 × 10.2 cm, upright (like 003/004/006 via a
    # wrapper USD; the top of the asset points to −y → −90° about x). Rest pose not measured yet → 3 mm drop height.
    "ycb_005_suppe": {"form": "usd", "ycb": "005_tomato_soup_can", "drehung": (-90, 0, 0),
                      "masse": (0.0677, 0.0677, 0.1019), "gier": (-math.pi, math.pi)},
}
DEFAULT_OBJECT_OBEN = "kugel_d7"


def _spawn(spec: dict, common: dict):
    if spec["form"] == "kugel":
        return sim_utils.SphereCfg(radius=spec["masse"][0], **common)
    if spec["form"] == "zylinder":
        return sim_utils.CylinderCfg(radius=spec["masse"][0], height=spec["masse"][1], **common)
    return sim_utils.CuboidCfg(size=spec["masse"], **common)


def _height(spec: dict) -> float:
    return {"kugel": 2 * spec["masse"][0], "zylinder": spec["masse"][-1]}.get(spec["form"], spec["masse"][-1])


@configclass
class RewardsObenCfg(RewardsProgressCfg):
    """EXP-022 recipe without orientation (Dexsuite Lift): no upright term, success = held (without tilt factor)."""
    upright = None
    success = RewTerm(func=mdp.object_held, weight=10.0, params={"drop_start_s": GRASP_TIME_S, "std": HOLD_STD_M})


@configclass
class PibGraspEnvCfg_Oben(PibGraspEnvCfg):
    """Base task "top" (evaluation per object via apply_object_oben, default sphere Ø 7 cm)."""
    rewards: RewardsObenCfg = RewardsObenCfg()

    def __post_init__(self):
        super().__post_init__()
        self.scene.robot.init_state.rot = HAND_ROT_OBEN
        old = self.scene.object.spawn
        self.scene.object.spawn = sim_utils.SphereCfg(
            radius=OBJECTS_OBEN[DEFAULT_OBJECT_OBEN]["masse"][0],
            **{k: getattr(old, k) for k in ("rigid_props", "collision_props", "mass_props", "physics_material",
                                             "visual_material")})
        h = _height(OBJECTS_OBEN[DEFAULT_OBJECT_OBEN])
        self.scene.object.init_state.pos = (*GRASP_XY, TIP_LOW_Z - 0.03 + h / 2)       # Ausgangswert, s. u.
        self.scene.table.spawn.size = TABLE_SIZE_OBEN
        self.scene.table.init_state.pos = (*GRASP_XY, TIP_LOW_Z - 0.03 - TABLE_SIZE_OBEN[2] / 2)
        # Start pose per environment from bounding box and shape (incl. random scale): object in the grasp centre, table as
        # high as the search found per object — replaces place_objects_by_size
        self.events.place_objects = EventTerm(
            func=mdp.place_objects_from_above, mode="startup",
            params={"center_xy": GRASP_XY, "tip_low_z": TIP_LOW_Z, "sphere_offset": SPHERE_OFFSET,
                    "block_offset": BLOCK_OFFSET, "min_tip_height": MIN_TIP_HEIGHT, "height_jitter": 0.0,
                    "table_thickness": TABLE_SIZE_OBEN[2], "lift": 0.0})
        # pre-grasp pose: thumb rotator fixed at 75° (as in the search), other servos almost open as for the side grasp
        self.events.reset_hand.params["ranges_deg"]["thumb_left_rotator"] = (ROTATOR_START_DEG, ROTATOR_START_DEG)
        self.events.reset_object.params["pose_range"] = {**OBJECT_XY_RANGE, "yaw": (-math.pi, math.pi)}
        # obliquely from the front/above onto fingertips and thumb (the hand lies horizontally)
        self.viewer.eye = (1.6, -2.6, 1.5)
        self.viewer.lookat = (0.15, -0.5, 0.4)


def apply_object_oben(cfg: PibGraspEnvCfg_Oben, key: str) -> PibGraspEnvCfg_Oben:
    """Insert an object from OBJECTS_OBEN (like env_cfg.apply_object; the start pose is set by the startup event
    place_objects from the actual bounding box). YCB: real mass/size from the asset, no random mass/scale."""
    spec = OBJECTS_OBEN[key]
    old = cfg.scene.object.spawn
    common = {k: getattr(old, k) for k in ("rigid_props", "collision_props", "mass_props", "physics_material",
                                           "visual_material")}
    if spec["form"] == "usd":
        cfg.scene.object.spawn = sim_utils.UsdFileCfg(usd_path=ycb_upright_usd(spec["ycb"], spec["drehung"]),
                                                      rigid_props=old.rigid_props, collision_props=old.collision_props)
        cfg.events.object_mass = None
        cfg.events.object_scale = None
        cfg.events.place_objects.params["lift"] = YCB_SPAWN_LIFT
    else:
        cfg.scene.object.spawn = _spawn(spec, common)
    h = _height(spec)
    cfg.scene.object.init_state.pos = (*GRASP_XY, TIP_LOW_Z - 0.03 + h / 2)
    cfg.events.reset_object.params["pose_range"]["yaw"] = spec["gier"]
    return cfg


# ── Training: object variety like EXP-013 (procedural, MultiAssetSpawnerCfg), mass like Heavy ──────────────────────
TRAIN_SPHERES_OBEN = [0.025, 0.03, 0.035, 0.04, 0.045]                                 # Radius: Ø 5–9 cm
TRAIN_CYLINDERS_OBEN = [(r, h) for r in (0.025, 0.03, 0.035, 0.04) for h in (0.06, 0.10)]
TRAIN_CUBOIDS_OBEN = [(0.06, 0.06, 0.04), (0.08, 0.08, 0.05), (0.09, 0.06, 0.04), (0.06, 0.09, 0.05)]


@configclass
class PibGraspEnvCfg_ObenMulti(PibGraspEnvCfg_Oben):
    """Specialist "top" (planned as EXP-024 at the time): 17 shapes (5 spheres, 8 short cylinders, 4 flat boxes),
    mass 0.04–0.4 kg (like EXP-006 ff.), yaw ±15° (no effect on spheres/cylinders). Agent PibGraspPPORunnerCfg_Clip."""

    def __post_init__(self):
        super().__post_init__()
        self.events.object_mass.params["mass_distribution_params"] = (0.04, 0.4)
        old = self.scene.object.spawn
        common = {k: getattr(old, k) for k in ("rigid_props", "collision_props", "mass_props")}
        mat = {k: getattr(old, k) for k in ("physics_material", "visual_material")}
        shapes = ([sim_utils.SphereCfg(radius=r, **mat) for r in TRAIN_SPHERES_OBEN]
                  + [sim_utils.CylinderCfg(radius=r, height=h, **mat) for r, h in TRAIN_CYLINDERS_OBEN]
                  + [sim_utils.CuboidCfg(size=s, **mat) for s in TRAIN_CUBOIDS_OBEN])
        self.scene.object.spawn = sim_utils.MultiAssetSpawnerCfg(assets_cfg=shapes, random_choice=False, **common)
        self.events.reset_object.params["pose_range"]["yaw"] = (-math.radians(15), math.radians(15))
        self.events.place_objects.params["height_jitter"] = TRAIN_HEIGHT_JITTER     # ungenaue Vorgreifpose


@configclass
class PibGraspEnvCfg_ObenMultiDex(PibGraspEnvCfg_ObenMulti):
    """EXP-029: specialist "top" with the recipe of EXP-027 (action space like Dexsuite, agent with bounds_loss)."""

    def __post_init__(self):
        super().__post_init__()
        dexsuite_action_space(self)


@configclass
class RewardsObenXYCfg(RewardsObenCfg):
    """Only if EXP-023 supports the penalty on the displacement in the table plane."""
    object_xy = RewTerm(func=mdp.object_xy_displacement, weight=XY_PENALTY_WEIGHT,
                        params={"ref_s": START_REF_S, "max_dist": 0.2})


@configclass
class PibGraspEnvCfg_ObenMultiXY(PibGraspEnvCfg_ObenMulti):
    rewards: RewardsObenXYCfg = RewardsObenXYCfg()
