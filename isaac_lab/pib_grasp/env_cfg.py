"""
env_cfg.py — grasping task of the real left pib v5 hand (proof of concept).

Template: Isaac Lab Dexsuite (manipulation/dexsuite, Kuka-Allegro lift) — structure,
reward weights, contact-force clip (20 N), action type (relative joint position)
and randomisation taken from there, reduced to what is needed.

Course of an episode (4.5 s, policy 60 Hz):
  0.0–2.0 s  can stands on the table in front of the palm, the policy grasps
  2.0–2.5 s  table lowers by 10 cm (≙ the arm lifts the hand)
  2.5–4.5 s  can must stay in the hand
Hand fixed (forearm base), side grasp: palm towards the can, thumb up.

Asymmetric actor-critic: the policy only sees what the real hand measures (8 servo
joint angles, 5 FSR, last action; 5 steps of history). The critic additionally sees
object position/orientation/velocity, follower joints, object contact forces and the phase.
"""
import math
from pathlib import Path

import isaaclab.sim as sim_utils
from isaaclab.assets import ArticulationCfg, AssetBaseCfg, RigidObjectCfg
from isaaclab.envs import ManagerBasedRLEnvCfg
from isaaclab.envs import mdp as base_mdp
from isaaclab.managers import EventTermCfg as EventTerm
from isaaclab.managers import ObservationGroupCfg as ObsGroup
from isaaclab.managers import ObservationTermCfg as ObsTerm
from isaaclab.managers import RewardTermCfg as RewTerm
from isaaclab.managers import SceneEntityCfg
from isaaclab.managers import TerminationTermCfg as DoneTerm
from isaaclab.managers import CurriculumTermCfg as CurrTerm
from isaaclab.utils.noise import AdditiveUniformNoiseCfg as Unoise
from isaaclab.scene import InteractiveSceneCfg
from isaaclab.sensors import ContactSensorCfg
from isaaclab.utils import configclass
from isaaclab.utils.assets import ISAAC_NUCLEUS_DIR

from pib_hand_left_v5_cfg import PIB_HAND_LEFT_V5_CFG, SERVO_JOINTS

from isaaclab_tasks.manager_based.manipulation.dexsuite.mdp import rewards as dexsuite_rewards
from isaaclab_tasks.manager_based.manipulation.dexsuite.mdp import curriculums as dexsuite_curriculums

from . import mdp

# ── Geometry (hand root frame from isaac_lab/tools/probe_geometry.py, 2026-10-04) ───
# Without rotation the fingers point to −y, the palm to −z, the thumb lies on
# −x. Rotation +90° about y: palm → −x, thumb → +z, fingers stay at −y.
HAND_POS = (0.0, 0.0, 0.5)
HAND_ROT = (math.cos(math.pi / 4), 0.0, math.sin(math.pi / 4), 0.0)   # (w, x, y, z)

OBJECT_RADIUS = 0.03          # Dose Ø 6 cm
OBJECT_HEIGHT = 0.15
PALM_GAP = 0.035              # palm ↔ object surface (pre-grasp pose, the same for all objects)
# Table top 8.5 cm below the hand root: the tip of the little finger is at
# −6.3 cm (tools/debug_scene.py); at −6 cm it hit the table
TABLE_TOP_Z = HAND_POS[2] - 0.085
# Can centre: 6.5 cm in front of the palm (−x), at the height of the proximal phalanges between MCP
# (y ≈ −0.31) and PIP (y ≈ −0.35), standing on the table. Until 2026-10-04 y = −0.32: the
# fingers pulled the can towards the wrist until it slid off the back of the table.
OBJECT_POS = (HAND_POS[0] - PALM_GAP - OBJECT_RADIUS, HAND_POS[1] - 0.34, TABLE_TOP_Z + OBJECT_HEIGHT / 2)
OBJECT_POS_RANGE = {"x": (-0.01, 0.01), "y": (-0.02, 0.02)}
# Table: ends 4 cm in front of the hand root (x) so the hand never touches it; in y from
# 16 cm in front of to 29 cm behind the can, so a shifted can does not fall immediately
TABLE_SIZE = (0.20, 0.45, 0.04)
TABLE_POS = (HAND_POS[0] - 0.04 - TABLE_SIZE[0] / 2, OBJECT_POS[1] + 0.065, TABLE_TOP_Z - TABLE_SIZE[2] / 2)

GRASP_TIME_S = 2.0
DROP_SPEED = 0.2              # m/s
DROP_DEPTH = 0.10             # m
EPISODE_S = 4.5

FSR_CLIP_N = 20.0             # Dexsuite: "contact force in finger tips is under 20N normally"
# The can should stay upright (test run 2026-10-04: the forearm tipped it onto the palm).
# Since EXP-003 only via the reward (Dexsuite: orientation rewarded, not terminated);
# rot_std 0.5 rad like Dexsuite's success_reward. EXP-001/002: termination at 20° → the policy
# stopped grasping at all (experiments/).
UPRIGHT_ROT_STD = 0.5
HOLD_STD_M = 0.02            # sinking [m] for 1 − tanh(s/std)
CONTACT_N = 1.0              # Kontaktschwelle Gegengriff (Dexsuite: threshold 1.0)


# ── Object catalogue (conditions, experiments/README.md) ─────────────────────────────────
# A side grasp needs ≥ ~15 cm of height: the fingertips lie 2.5–16.5 cm above the
# table top (little finger … thumb, tools/debug_scene.py, 2026-10-07); the hand cannot go lower,
# otherwise the little finger hits the table.
# shape, dimensions [m] (cylinder: radius, height; box: x, y, z), rotation on reset [rad]
OBJECTS = {
    "zylinder_d6": {"form": "zylinder", "masse": (0.03, 0.15), "gier": (-math.pi, math.pi)},      # Dose (Training)
    "zylinder_d8": {"form": "zylinder", "masse": (0.04, 0.15), "gier": (-math.pi, math.pi)},      # dicke Dose/Becher
    # Milk carton: one face towards the hand ±15° (as a grasp planner would approach)
    "quader_7x7x20": {"form": "quader", "masse": (0.07, 0.07, 0.20), "gier": (-math.radians(15), math.radians(15))},
    # Test objects (never in training, EXP-013 ff.): bottle — Ø as in training but 25 cm tall; juice carton —
    # narrow side (6 cm) towards the hand; in training the wide or a square side always faces the hand
    "flasche_d7x25": {"form": "zylinder", "masse": (0.035, 0.25), "gier": (-math.pi, math.pi)},
    "saftpackung_9x6x19": {"form": "quader", "masse": (0.09, 0.06, 0.19), "gier": (-math.radians(15), math.radians(15))},
    # YCB test objects (Isaac Sim 5.1 Props/YCB/Axis_Aligned_Physics, tools/inspect_ycb.py, 2026-10-09): real mass and
    # size from the asset (random mass/scale off); the assets lie down (height along y) → upright via a wrapper USD
    # that only rotates the mesh (drehung = rotateXYZ [°]); the rigid body stays z-up like all objects (tilt angle,
    # yaw). masse = bounding box upright (depth towards the hand, width, height); friction like all objects (random 0.5–1.0).
    # The top of the asset points to −y → −90° about x (+90° put it upside down, window test 2026-10-09).
    # ruhelage = measured rest pose on the table (tools/ruhelage_objekt.py, typical of 64 environments): height of the
    # origin above the table top [m], tilt (body frame, w x y z) — the scanned bottoms are uneven,
    # the colliders reach below the visible box; this way the object stands still at t = 0 instead of falling/tipping.
    "ycb_003_cracker": {"form": "usd", "ycb": "003_cracker_box", "drehung": (-90, 0, 0),          # 411 g, schmale
                        "masse": (0.164, 0.072, 0.213), "gier": (-math.radians(15), math.radians(15)),   # face towards the hand
                        "ruhelage": {"hoehe": 0.10635, "quat": (0.99965, 0.02641, -0.00166, 0.00023)}},  # 3,1°
    "ycb_004_zucker": {"form": "usd", "ycb": "004_sugar_box", "drehung": (-90, 0, 0),             # 514 g, schmale
                       "masse": (0.093, 0.045, 0.176), "gier": (-math.radians(15), math.radians(15)),    # face towards the hand
                       "ruhelage": {"hoehe": 0.08735, "quat": (0.99979, 0.01307, -0.01552, 0.00069)}},   # 2,3°
    "ycb_006_senf": {"form": "usd", "ycb": "006_mustard_bottle", "drehung": (-90, 0, 0),           # 603 g, schmale
                     "masse": (0.096, 0.058, 0.191), "gier": (-math.radians(15), math.radians(15)),      # face towards the hand
                     "ruhelage": {"hoehe": 0.09736, "quat": (1.0, 0.0, 0.0, 0.0)}},                      # upright
}
# Start pose of the hand on reset almost open (default since 2026-10-09, eval-v2): finger flexion 0–15° and wrist
# −10–0° (up to eval-v1) left the hand inside the object at reset (tools/analyse_reset.py: cylinder Ø6 34 %, Ø8 44 %,
# box 81 %, YCB cracker 63 % of starts, mainly middle phalanges/tips and wrist flexion); now 0 %. Thumb uncritical,
# keeps 0–90° rotator / 0–15° flexion. The hand arrives almost open, as in the pre-grasp pose.
FINGER_START_MAX_DEG = 4.0
WRIST_START_MAX_DEG = 1.0


# Colliders of the scanned YCB meshes (convex decomposition) reach up to ~2 mm below the visible bounding box → spawned
# flush, the object starts inside the table and is pushed out (mustard: +2 mm, up to 1 cm sideways, tools/check_objekt.py);
# 3 mm higher it drops briefly onto the table instead.
YCB_SPAWN_LIFT = 0.003
YCB_WRAPPER_DIR = Path(__file__).resolve().parents[2] / "logs" / "ycb_aufrecht"     # erzeugt, gitignored


def ycb_upright_usd(name: str, rot_deg: tuple[float, float, float]) -> str:
    """Wrapper USD for a YCB asset: references it and only rotates the mesh child (rotateXYZ, scale unchanged);
    rigid body, mass and colliders come unchanged from the asset."""
    src = f"{ISAAC_NUCLEUS_DIR}/Props/YCB/Axis_Aligned_Physics/{name}.usd"
    child = "_" + name[1:]                                     # 003_cracker_box → _03_cracker_box (prim in the asset)
    YCB_WRAPPER_DIR.mkdir(parents=True, exist_ok=True)
    path = YCB_WRAPPER_DIR / f"{name}_aufrecht.usda"
    path.write_text(f"""#usda 1.0
(
    defaultPrim = "Object"
    metersPerUnit = 1
    upAxis = "Z"
)

def Xform "Object" (
    prepend references = @{src}@
)
{{
    over "{child}"
    {{
        float3 xformOp:rotateXYZ = ({rot_deg[0]}, {rot_deg[1]}, {rot_deg[2]})
        uniform token[] xformOpOrder = ["xformOp:rotateXYZ", "xformOp:scale"]
    }}
}}
""", encoding="utf-8")
    return str(path)
DEFAULT_OBJECT = "zylinder_d6"


@configclass
class SceneCfg(InteractiveSceneCfg):
    robot: ArticulationCfg = PIB_HAND_LEFT_V5_CFG.replace(
        prim_path="{ENV_REGEX_NS}/Robot",
        init_state=PIB_HAND_LEFT_V5_CFG.init_state.replace(pos=HAND_POS, rot=HAND_ROT),
    )

    object: RigidObjectCfg = RigidObjectCfg(
        prim_path="{ENV_REGEX_NS}/Object",
        spawn=sim_utils.CylinderCfg(
            radius=OBJECT_RADIUS,
            height=OBJECT_HEIGHT,
            rigid_props=sim_utils.RigidBodyPropertiesCfg(
                solver_position_iteration_count=16,
                solver_velocity_iteration_count=0,
            ),
            collision_props=sim_utils.CollisionPropertiesCfg(),
            mass_props=sim_utils.MassPropertiesCfg(mass=0.1),
            physics_material=sim_utils.RigidBodyMaterialCfg(static_friction=0.8, dynamic_friction=0.8),
            visual_material=sim_utils.PreviewSurfaceCfg(diffuse_color=(0.8, 0.2, 0.2)),
        ),
        init_state=RigidObjectCfg.InitialStateCfg(pos=OBJECT_POS),
    )

    table: RigidObjectCfg = RigidObjectCfg(
        prim_path="{ENV_REGEX_NS}/Table",
        spawn=sim_utils.CuboidCfg(
            size=TABLE_SIZE,
            rigid_props=sim_utils.RigidBodyPropertiesCfg(kinematic_enabled=True),
            collision_props=sim_utils.CollisionPropertiesCfg(),
            visual_material=sim_utils.PreviewSurfaceCfg(diffuse_color=(0.18, 0.18, 0.2)),   # dunkel: Hand hebt sich ab
        ),
        init_state=RigidObjectCfg.InitialStateCfg(pos=TABLE_POS),
    )

    # One sensor per fingertip (= per FSR), like Dexsuite: the object filter (privileged
    # force) only works in Isaac Lab if a sensor covers exactly one prim.
    # Link names: mdp.FINGERTIP_LINKS (thumb, index, middle, ring, little).
    fsr_thumb = ContactSensorCfg(prim_path="{ENV_REGEX_NS}/Robot/urdf_thumb_tip",
                                 filter_prim_paths_expr=["{ENV_REGEX_NS}/Object"])
    fsr_index = ContactSensorCfg(prim_path="{ENV_REGEX_NS}/Robot/urdf_finger_tip",
                                 filter_prim_paths_expr=["{ENV_REGEX_NS}/Object"])
    fsr_middle = ContactSensorCfg(prim_path="{ENV_REGEX_NS}/Robot/urdf_finger_tip_2",
                                  filter_prim_paths_expr=["{ENV_REGEX_NS}/Object"])
    fsr_ring = ContactSensorCfg(prim_path="{ENV_REGEX_NS}/Robot/urdf_finger_tip_3",
                                filter_prim_paths_expr=["{ENV_REGEX_NS}/Object"])
    fsr_pinky = ContactSensorCfg(prim_path="{ENV_REGEX_NS}/Robot/urdf_finger_tip_4",
                                 filter_prim_paths_expr=["{ENV_REGEX_NS}/Object"])

    # Visuals only (2026-10-08): dome light weak as fill light and invisible (black background),
    # directional key light obliquely from above on the camera side → shadows and contrast on fingers/object
    light = AssetBaseCfg(prim_path="/World/light",
                         spawn=sim_utils.DomeLightCfg(intensity=350.0, visible_in_primary_ray=False))
    sun = AssetBaseCfg(prim_path="/World/sun", spawn=sim_utils.DistantLightCfg(intensity=1600.0, angle=1.0),
                       init_state=AssetBaseCfg.InitialStateCfg(rot=(0.9666, 0.1573, 0.2022, 0.0)))


@configclass
class ActionsCfg:
    # Dexsuite: relative joint position, scale 0.1 rad per step. Wrist/forearm
    # smaller (original prompt: no "whipping" of the arm). 0.1 rad ≈ 5.7° ≥ servo
    # saturation error (5°) — full stall torque is reachable.
    servos = base_mdp.RelativeJointPositionActionCfg(
        asset_name="robot",
        joint_names=SERVO_JOINTS,
        preserve_order=True,
        scale={"forearm_left": 0.03, "wrist_left": 0.03, ".*_left_(proximal|rotator)": 0.1},
    )


@configclass
class ObservationsCfg:
    @configclass
    class PolicyCfg(ObsGroup):
        """Only what the real hand measures — order = interface to the firmware."""
        joint_pos = ObsTerm(
            func=base_mdp.joint_pos,
            params={"asset_cfg": SceneEntityCfg("robot", joint_names=SERVO_JOINTS, preserve_order=True)},
        )
        fsr = ObsTerm(func=mdp.fingertip_forces, clip=(0.0, FSR_CLIP_N))
        last_action = ObsTerm(func=base_mdp.last_action)

        def __post_init__(self):
            self.enable_corruption = False
            self.concatenate_terms = True
            self.history_length = 5

    @configclass
    class CriticCfg(ObsGroup):
        """Privileged (simulation only)."""
        all_joint_pos = ObsTerm(func=base_mdp.joint_pos)
        all_joint_vel = ObsTerm(func=base_mdp.joint_vel)
        object_pos = ObsTerm(func=mdp.object_pos_in_root)
        object_quat = ObsTerm(func=mdp.object_quat_in_root)
        object_vel = ObsTerm(func=mdp.object_lin_vel)
        object_forces = ObsTerm(func=mdp.fingertip_object_forces, clip=(0.0, 50.0))
        phase = ObsTerm(func=mdp.phase, params={"drop_start_s": GRASP_TIME_S})

        def __post_init__(self):
            self.enable_corruption = False
            self.concatenate_terms = True

    policy: PolicyCfg = PolicyCfg()
    critic: CriticCfg = CriticCfg()


@configclass
class EventCfg:
    # -- startup (Dexsuite pattern, narrower ranges for the PoC)
    object_scale = EventTerm(
        func=base_mdp.randomize_rigid_body_scale,
        mode="prestartup",
        params={"scale_range": (0.9, 1.1), "asset_cfg": SceneEntityCfg("object")},
    )
    robot_material = EventTerm(
        func=base_mdp.randomize_rigid_body_material,
        mode="startup",
        params={
            "asset_cfg": SceneEntityCfg("robot", body_names=".*"),
            "static_friction_range": (0.5, 1.0),
            "dynamic_friction_range": (0.5, 1.0),
            "restitution_range": (0.0, 0.0),
            "num_buckets": 250,
        },
    )
    object_material = EventTerm(
        func=base_mdp.randomize_rigid_body_material,
        mode="startup",
        params={
            "asset_cfg": SceneEntityCfg("object"),
            "static_friction_range": (0.5, 1.0),
            "dynamic_friction_range": (0.5, 1.0),
            "restitution_range": (0.0, 0.0),
            "num_buckets": 250,
        },
    )
    object_mass = EventTerm(
        func=base_mdp.randomize_rigid_body_mass,
        mode="startup",
        params={"asset_cfg": SceneEntityCfg("object"), "mass_distribution_params": (0.05, 0.2), "operation": "abs"},
    )
    # Start pose per environment from the bounding box of the spawned object incl. random scale (default since 2026-10-09,
    # eval-v2; up to eval-v1 only EXP-013 ff.): surface PALM_GAP in front of the palm, bottom on the table top (+ lift).
    # Before that from the nominal size → with ±10 % the object fell up to 7.5 mm or started inside the table (tools/analyse_reset.py).
    place_objects = EventTerm(
        func=mdp.place_objects_by_size, mode="startup",
        params={"hand_x": HAND_POS[0], "palm_gap": PALM_GAP, "table_top_z": TABLE_TOP_Z, "lift": 0.0,
                "root_height": None})
    servo_gains = EventTerm(
        func=base_mdp.randomize_actuator_gains,
        mode="startup",
        params={
            "asset_cfg": SceneEntityCfg("robot", joint_names=SERVO_JOINTS),
            "stiffness_distribution_params": (0.8, 1.25),
            "damping_distribution_params": (0.8, 1.25),
            "operation": "scale",
        },
    )

    # -- reset
    reset_robot = EventTerm(func=base_mdp.reset_scene_to_default, mode="reset",
                            params={"reset_joint_targets": True})
    # Random start position of the servo joints (Dexsuite: reset_joints_by_offset ±0.5 rad;
    # narrower here, joints only 0–90°). Rotator over the full range so the policy also
    # experiences starts with the thumb in opposition (feasibility test: rotator 90° → 14–15/16 held).
    reset_hand = EventTerm(
        func=mdp.reset_hand_joints,
        mode="reset",
        params={"ranges_deg": {
            "thumb_left_rotator": (0.0, 90.0),
            "thumb_left_proximal": (0.0, FINGER_START_MAX_DEG),
            "index_left_proximal": (0.0, FINGER_START_MAX_DEG),
            "middle_left_proximal": (0.0, FINGER_START_MAX_DEG),
            "ring_left_proximal": (0.0, FINGER_START_MAX_DEG),
            "pinky_left_proximal": (0.0, FINGER_START_MAX_DEG),
            "wrist_left": (-WRIST_START_MAX_DEG, 0.0),
        }},
    )
    reset_object = EventTerm(
        func=mdp.reset_object_gap_aware,            # distance to the palm after the yaw rotation (eval-v2)
        mode="reset",
        params={
            "pose_range": {**OBJECT_POS_RANGE, "yaw": (-math.pi, math.pi)},
            "velocity_range": {},
            "asset_cfg": SceneEntityCfg("object"),
        },
    )

    # -- every step: lower the table
    lower_table = EventTerm(
        func=mdp.lower_table,
        mode="interval",
        interval_range_s=(0.0, 0.0),
        params={"drop_start_s": GRASP_TIME_S, "drop_speed": DROP_SPEED, "drop_depth": DROP_DEPTH},
    )


@configclass
class RewardsCfg:
    """Reward set like Isaac Lab Dexsuite (dexsuite_env_cfg.RewardsCfg + KukaAllegroReorientRewardCfg),
    goal pose replaced by "held at the start height after the lowering, upright" (EXP-004).
    All terms bounded; contribution per second = weight × term (Isaac Lab multiplies by dt)."""
    # Action: Dexsuite functions directly (clipped at 1000 as protection against outliers)
    action_l2 = RewTerm(func=dexsuite_rewards.action_l2_clamped, weight=-0.005)
    action_rate_l2 = RewTerm(func=dexsuite_rewards.action_rate_l2_clamped, weight=-0.005)
    # Approach (Dexsuite object_ee_distance, std 0.4) and opposition (Dexsuite contacts, 0.5)
    fingertips_to_object = RewTerm(func=mdp.fingertips_to_object, weight=1.0, params={"std": 0.4})
    good_contact = RewTerm(func=mdp.thumb_opposition_contact, weight=0.5, params={"threshold": CONTACT_N})
    # Dense, from the lowering on, only with opposition (Dexsuite position/orientation_command_error_tanh)
    held = RewTerm(func=mdp.held_in_grasp, weight=2.0,
                   params={"drop_start_s": GRASP_TIME_S, "std": HOLD_STD_M, "threshold": CONTACT_N})
    upright = RewTerm(func=mdp.upright_in_grasp, weight=4.0,
                      params={"drop_start_s": GRASP_TIME_S, "rot_std": 1.5, "threshold": CONTACT_N})
    # Sharp: held × upright (Dexsuite success_reward, pos_std/rot_std → sinking/tilt)
    success = RewTerm(func=mdp.object_held_upright, weight=10.0,
                      params={"drop_start_s": GRASP_TIME_S, "std": HOLD_STD_M, "rot_std": UPRIGHT_ROT_STD})
    early_termination = RewTerm(func=base_mdp.is_terminated_term, weight=-1.0,
                                params={"term_keys": ["abnormal_robot"]})


@configclass
class TerminationsCfg:
    time_out = DoneTerm(func=base_mdp.time_out, time_out=True)
    object_dropped = DoneTerm(func=mdp.object_dropped, params={"max_sink": 0.05})
    abnormal_robot = DoneTerm(func=mdp.abnormal_robot_state)


@configclass
class PibGraspEnvCfg(ManagerBasedRLEnvCfg):
    scene: SceneCfg = SceneCfg(num_envs=1024, env_spacing=0.6, replicate_physics=False)
    observations: ObservationsCfg = ObservationsCfg()
    actions: ActionsCfg = ActionsCfg()
    events: EventCfg = EventCfg()
    rewards: RewardsCfg = RewardsCfg()
    terminations: TerminationsCfg = TerminationsCfg()

    def __post_init__(self):
        self.decimation = 2               # physics 120 Hz, policy 60 Hz (like Dexsuite)
        self.episode_length_s = EPISODE_S
        self.is_finite_horizon = True
        self.sim.dt = 1 / 120
        self.sim.render_interval = self.decimation
        self.sim.physx.bounce_threshold_velocity = 0.01
        # Oblique from the back of the hand/fingertips, ~28° from above, 2.8 m (2026-10-08): all 16 hands
        # and the fingers on the object visible
        self.viewer.eye = (1.9, -2.25, 1.76)
        self.viewer.lookat = (0.15, -0.5, 0.45)


# ── Variants for experiments (own task IDs, same evaluation environment) ─────────────────

@configclass
class RewardsFingerCountCfg(RewardsCfg):
    # EXP-005: reward increases with the number of fingers on the can (EXP-004: only thumb + 1 finger)
    finger_count = RewTerm(func=mdp.fingers_in_contact, weight=1.0, params={"threshold": CONTACT_N})


@configclass
class PibGraspEnvCfg_FingerCount(PibGraspEnvCfg):
    rewards: RewardsFingerCountCfg = RewardsFingerCountCfg()


@configclass
class PibGraspEnvCfg_Heavy(PibGraspEnvCfg):
    """EXP-006: object mass like Dexsuite (0.2 kg × 0.2–2 = 0.04–0.4 kg) instead of 0.05–0.2 kg."""

    def __post_init__(self):
        super().__post_init__()
        self.events.object_mass.params["mass_distribution_params"] = (0.04, 0.4)


def apply_object(cfg: PibGraspEnvCfg, key: str) -> PibGraspEnvCfg:
    """Insert an object from OBJECTS: shape/dimensions, start pose (surface PALM_GAP in front of the palm,
    standing on the table) and rotation on reset. Physics, mass, material stay as configured — except for
    YCB (form usd): real mass and size from the asset, no random mass/scale. The start pose is then set by
    the startup event place_objects from the actual bounding box (init_state is only the initial value)."""
    spec = OBJECTS[key]
    old = cfg.scene.object.spawn
    common = {k: getattr(old, k) for k in ("rigid_props", "collision_props", "mass_props", "physics_material",
                                           "visual_material")}
    if spec["form"] == "zylinder":
        radius, height = spec["masse"]
        cfg.scene.object.spawn = sim_utils.CylinderCfg(radius=radius, height=height, **common)
        depth = radius
    elif spec["form"] == "usd":                 # YCB: real mass/size from the asset, appearance from the asset
        cfg.scene.object.spawn = sim_utils.UsdFileCfg(usd_path=ycb_upright_usd(spec["ycb"], spec["drehung"]),
                                                      rigid_props=old.rigid_props, collision_props=old.collision_props)
        cfg.events.object_mass = None
        cfg.events.object_scale = None
        if "ruhelage" in spec:                  # measured rest pose: stands at t = 0 the way it stands by itself
            cfg.events.place_objects.params["root_height"] = spec["ruhelage"]["hoehe"]
            cfg.scene.object.init_state.rot = spec["ruhelage"]["quat"]
        else:
            cfg.events.place_objects.params["lift"] = YCB_SPAWN_LIFT
        depth, height = spec["masse"][0] / 2, spec["masse"][2] + 2 * YCB_SPAWN_LIFT
    else:
        size = spec["masse"]
        cfg.scene.object.spawn = sim_utils.CuboidCfg(size=size, **common)
        depth, height = size[0] / 2, size[2]
    cfg.scene.object.init_state.pos = (HAND_POS[0] - PALM_GAP - depth, OBJECT_POS[1], TABLE_TOP_Z + height / 2)
    cfg.events.reset_object.params["pose_range"]["yaw"] = spec["gier"]
    return cfg


# ── Object variety (EXP-013): procedural shapes like Dexsuite (16 basic shapes, MultiAssetSpawnerCfg), but only
# within the category "side grasp" (upright, ≥ 15 cm tall). Dimensions [m]: cylinder (radius, height),
# box (depth towards the hand, width, height). Start pose per environment from the bounding box (mdp.place_objects_by_size).
TRAIN_CYLINDERS = [(r, h) for r in (0.025, 0.03, 0.035, 0.04, 0.045) for h in (0.15, 0.20)]
TRAIN_CUBOIDS = [(x, y, z) for x, y in ((0.06, 0.06), (0.07, 0.07), (0.08, 0.08), (0.06, 0.09)) for z in (0.16, 0.20)]


@configclass
class PibGraspEnvCfg_HeavyMulti(PibGraspEnvCfg_Heavy):
    """EXP-013: like EXP-006 (mass 0.04–0.4 kg), but per environment one of 18 shapes of the category (10 cylinders
    Ø 5–9 cm × 15/20 cm, 8 boxes 6–8 cm × 16/20 cm) instead of always the Ø 6 cm cylinder; rotation on reset
    ±15° for all (no effect on cylinders). Evaluation unchanged per object (eval_policy, base task)."""

    def __post_init__(self):
        super().__post_init__()
        old = self.scene.object.spawn
        common = {k: getattr(old, k) for k in ("rigid_props", "collision_props", "mass_props")}
        mat = {k: getattr(old, k) for k in ("physics_material", "visual_material")}    # per shape, like Dexsuite
        shapes = [sim_utils.CylinderCfg(radius=r, height=h, **mat) for r, h in TRAIN_CYLINDERS] + \
                 [sim_utils.CuboidCfg(size=s, **mat) for s in TRAIN_CUBOIDS]
        self.scene.object.spawn = sim_utils.MultiAssetSpawnerCfg(assets_cfg=shapes, random_choice=False, **common)
        self.events.reset_object.params["pose_range"]["yaw"] = (-math.radians(15), math.radians(15))



@configclass
class PibGraspEnvCfg_HeavyMultiRand(PibGraspEnvCfg_HeavyMulti):
    """EXP-016: like EXP-013, randomisation of the hand like Dexsuite: servo gains 0.5–2 (instead of 0.8–1.25) and
    joint friction × 0–5 (new, dexsuite_env_cfg.EventCfg.joint_friction). Scale stays ±10 % (Dexsuite 0.75–1.5
    would create objects below 15 cm height — outside the side-grasp category)."""

    def __post_init__(self):
        super().__post_init__()
        self.events.servo_gains.params["stiffness_distribution_params"] = (0.5, 2.0)
        self.events.servo_gains.params["damping_distribution_params"] = (0.5, 2.0)
        self.events.joint_friction = EventTerm(
            func=base_mdp.randomize_joint_parameters, mode="startup",
            params={"asset_cfg": SceneEntityCfg("robot", joint_names=".*"),
                    "friction_distribution_params": (0.0, 5.0), "operation": "scale"})


@configclass
class CurriculumADRCfg:
    """Like Dexsuite (adr_curriculum.CurriculumCfg): difficulty 0–10 per environment by success; gravity
    0 → 9.81 m/s² and noise of the joint-angle observation 0 → ±0.1 rad (Dexsuite final values). FSR without
    noise (Dexsuite has no force sensors)."""
    adr = CurrTerm(func=mdp.GraspDifficultyScheduler,
                   params={"max_kipp_deg": 45.0, "init_difficulty": 0, "min_difficulty": 0, "max_difficulty": 10})
    gravity_adr = CurrTerm(func=base_mdp.modify_term_cfg, params={
        "address": "events.variable_gravity.params.gravity_distribution_params",
        "modify_fn": dexsuite_curriculums.initial_final_interpolate_fn,
        "modify_params": {"initial_value": ((0.0, 0.0, 0.0), (0.0, 0.0, 0.0)),
                          "final_value": ((0.0, 0.0, -9.81), (0.0, 0.0, -9.81)), "difficulty_term_str": "adr"}})
    joint_pos_noise_min_adr = CurrTerm(func=base_mdp.modify_term_cfg, params={
        "address": "observations.policy.joint_pos.noise.n_min",
        "modify_fn": dexsuite_curriculums.initial_final_interpolate_fn,
        "modify_params": {"initial_value": 0.0, "final_value": -0.1, "difficulty_term_str": "adr"}})
    joint_pos_noise_max_adr = CurrTerm(func=base_mdp.modify_term_cfg, params={
        "address": "observations.policy.joint_pos.noise.n_max",
        "modify_fn": dexsuite_curriculums.initial_final_interpolate_fn,
        "modify_params": {"initial_value": 0.0, "final_value": 0.1, "difficulty_term_str": "adr"}})


@configclass
class PibGraspEnvCfg_HeavyMultiADR(PibGraspEnvCfg_HeavyMulti):
    """EXP-017: like EXP-013, plus a curriculum like Dexsuite (gravity and observation noise grow with
    success). Dexsuite: 'deliberate trick … starting with no gravity (easy) … the agent learns more smoothly'."""
    curriculum: CurriculumADRCfg = CurriculumADRCfg()

    def __post_init__(self):
        super().__post_init__()
        self.events.variable_gravity = EventTerm(func=base_mdp.randomize_physics_scene_gravity, mode="reset",
                                                 params={"gravity_distribution_params": ([0.0, 0.0, 0.0], [0.0, 0.0, 0.0]),
                                                         "operation": "abs"})
        self.observations.policy.joint_pos.noise = Unoise(n_min=0.0, n_max=0.0)
        self.observations.policy.enable_corruption = True
START_REF_S = 0.1     # start position = object pose at 0.1 s (settled, scale settled)


@configclass
class RewardsDexsuiteCfg(RewardsCfg):
    """EXP-012: custom parts not required by the task, back to Dexsuite
    (dexsuite_env_cfg.RewardsCfg, Kuka-Allegro configuration):
    - approach: Dexsuite object_ee_distance over palm + fingertips (instead of tips only)
    - position tracking (held): 3D distance to the target position, std 0.2 (instead of one-sided z sinking, 0.02)
    - success: 3D distance pos_std 0.1 × tilt rot_std 0.5 (instead of sinking 0.02 × tilt 0.5)
    Target = start position of the object (Dexsuite: commanded pose). Deliberately kept custom: opposition with
    the little finger, orientation as tilt angle, held/upright/success only from the lowering on (ADR-017)."""
    fingertips_to_object = RewTerm(func=dexsuite_rewards.object_ee_distance, weight=1.0, params={
        "std": 0.4, "asset_cfg": SceneEntityCfg("robot", body_names=["urdf_palm_left", *mdp.FINGERTIP_LINKS])})
    held = RewTerm(func=mdp.position_tracking_start, weight=2.0, params={
        "drop_start_s": GRASP_TIME_S, "std": 0.2, "threshold": CONTACT_N, "ref_s": START_REF_S})
    success = RewTerm(func=mdp.success_start, weight=10.0, params={
        "drop_start_s": GRASP_TIME_S, "pos_std": 0.1, "rot_std": UPRIGHT_ROT_STD, "ref_s": START_REF_S})


@configclass
class PibGraspEnvCfg_HeavyDexsuite(PibGraspEnvCfg_Heavy):
    """EXP-012: like EXP-006 (mass 0.04–0.4 kg), reward as close to Dexsuite as the task allows."""
    rewards: RewardsDexsuiteCfg = RewardsDexsuiteCfg()


# ── ADR-022 (2026-10-09): approach per fingertip, critic knows the object — one change each vs. HeavyMulti ──
PROGRESS_WEIGHT = 500.0     # Σ progress [m] per step × dt × weight; magnitude via tools/reward_diag.py


@configclass
class RewardsProgressCfg(RewardsCfg):
    """EXP-019: approach like NVIDIA AllegroKuka/DexPBT (mdp.FingertipProgress) instead of fingertips_to_object."""
    fingertips_to_object = None
    fingertip_progress = RewTerm(func=mdp.FingertipProgress, weight=PROGRESS_WEIGHT,
                                 params={"drop_start_s": GRASP_TIME_S, "max_delta": 0.05})


@configclass
class PibGraspEnvCfg_HeavyMultiProgress(PibGraspEnvCfg_HeavyMulti):
    """EXP-019 (and EXP-022 with clipped actions): like EXP-018, approach per fingertip as progress only."""
    rewards: RewardsProgressCfg = RewardsProgressCfg()


# EXP-023: pulling 13 cm (finding 2026-10-10) costs as much as the opposition earns (0.5/s): 0.5 / 0.13 ≈ 4
XY_PENALTY_WEIGHT = -4.0


@configclass
class RewardsProgressXYCfg(RewardsProgressCfg):
    """EXP-023: like EXP-022, plus a penalty on the object's displacement in the table plane (mdp.object_xy_displacement)."""
    object_xy = RewTerm(func=mdp.object_xy_displacement, weight=XY_PENALTY_WEIGHT,
                        params={"ref_s": START_REF_S, "max_dist": 0.2})


@configclass
class PibGraspEnvCfg_HeavyMultiProgressXY(PibGraspEnvCfg_HeavyMulti):
    """EXP-023: like EXP-022 (with agent PibGraspPPORunnerCfg_Clip), the object should stay in place in the table plane."""
    rewards: RewardsProgressXYCfg = RewardsProgressXYCfg()


# ── Night run 2026-10-11: one change each vs. EXP-022 (HeavyMultiProgress + actions clipped to ±1) ──────────────────
ACTION_FILTER_ALPHA = 0.3       # Isaac Lab ShadowHand-OpenAI act_moving_average (DeXtreme-Linie)
TORQUE_PENALTY_WEIGHT = -0.1    # Σ(τ/τ_stall)² of the 7 servos except the wrist; magnitude via tools/reward_diag.py
STALL_JOINTS = [j for j in SERVO_JOINTS if j != "wrist_left"]     # like the stall-share guardrail (eval_policy)


def filtered_servo_action(alpha: float = ACTION_FILTER_ALPHA) -> mdp.FilteredRelativeJointPositionActionCfg:
    """Servo action like ActionsCfg.servos, with a moving average (also for eval_policy --action_filter)."""
    base = ActionsCfg().servos
    return mdp.FilteredRelativeJointPositionActionCfg(asset_name=base.asset_name, joint_names=base.joint_names,
                                                      preserve_order=base.preserve_order, scale=base.scale, alpha=alpha)


@configclass
class PibGraspEnvCfg_HeavyMultiProgressFilter(PibGraspEnvCfg_HeavyMultiProgress):
    """EXP-024 (against jitter): like EXP-022, action smoothed before the servos (moving average, α = 0.3)."""

    def __post_init__(self):
        super().__post_init__()
        self.actions.servos = filtered_servo_action()


@configclass
class RewardsProgressTorqueCfg(RewardsProgressCfg):
    """EXP-025 (against servo stall): penalty on the normalised servo torque like HORA (torque penalty)."""
    servo_torque = RewTerm(func=mdp.servo_torque_l2, weight=TORQUE_PENALTY_WEIGHT,
                           params={"asset_cfg": SceneEntityCfg("robot", joint_names=STALL_JOINTS, preserve_order=True)})


@configclass
class PibGraspEnvCfg_HeavyMultiProgressTorque(PibGraspEnvCfg_HeavyMulti):
    rewards: RewardsProgressTorqueCfg = RewardsProgressTorqueCfg()


@configclass
class RewardsProgressFingersCfg(RewardsProgressCfg):
    """EXP-026 (more fingers): reward by the number of fingers on the object with thumb contact (term from EXP-005)."""
    finger_count = RewTerm(func=mdp.fingers_in_contact, weight=1.0, params={"threshold": CONTACT_N})


@configclass
class PibGraspEnvCfg_HeavyMultiProgressFingers(PibGraspEnvCfg_HeavyMulti):
    rewards: RewardsProgressFingersCfg = RewardsProgressFingersCfg()


# ── Action space like Dexsuite (EXP-027 ff., docs/protokoll/pruefung-aktionsweg.md): scale 0.1 rad for ALL servos (Dexsuite:
# RelativeJointPositionActionCfg(scale=0.1) for all joints incl. the arm) — before, forearm/wrist 0.03 rad (≈ 34 %
# torque, ~63/47 °/s instead of 270/135 °/s). No clipping at runtime (agent PibGraspPPORunnerCfg_Bounds: bounds_loss).
DEXSUITE_ACTION_SCALE = 0.1


def dexsuite_action_space(cfg):
    """Same scale for all 8 servos (Dexsuite). Evaluation: eval_policy --action_scale 0.1 (experiments.clip_args)."""
    cfg.actions.servos.scale = DEXSUITE_ACTION_SCALE
    return cfg


@configclass
class PibGraspEnvCfg_HeavyMultiProgressDex(PibGraspEnvCfg_HeavyMultiProgress):
    """EXP-027: base recipe (EXP-019/022: progress per fingertip) with an action space like Dexsuite."""

    def __post_init__(self):
        super().__post_init__()
        dexsuite_action_space(self)


# ── Night run 2026-10-13 (docs/protokoll/nachtlauf-2026-10-13.md): servo stall and jitter, parent EXP-027 ─────────────────────
# PID Lagrangian (Stooke et al. 2020): cost c_t = fraction of the 7 servos (without wrist) with |τ| ≥ 80 % stall, limit
# J_c ≤ 0.2. λ in "per s" (Isaac Lab × dt); hold reward ~10/s → λ should be able to reach this magnitude within
# ~20 iterations (K_I · e per rollout, e ≈ 0.3 for EXP-027).
STALL_LAGRANGE = {"fraction": 0.8, "limit": 0.2, "k_p": 10.0, "k_i": 1.0, "k_d": 5.0, "ema": 0.5, "lambda_max": 100.0,
                  "steps_per_update": 32}
SERVO_LOAD_NOISE = 0.05         # noise of the servo-load observation ("Present Load", fraction of the stall torque)


@configclass
class RewardsProgressLagrangeCfg(RewardsProgressCfg):
    """EXP-035 ff.: like EXP-027, plus a penalty −λ·c_t with λ via PID Lagrangian (mdp.StallLagrange)."""
    stall_lagrange = RewTerm(func=mdp.StallLagrange, weight=-1.0,
                             params={"joint_names": STALL_JOINTS, **STALL_LAGRANGE})


@configclass
class PibGraspEnvCfg_HeavyMultiProgressDexLagrange(PibGraspEnvCfg_HeavyMultiProgressDex):
    """EXP-035 (agent _Bounds) and EXP-036 (agent _Caps): stall limit via PID Lagrangian."""
    rewards: RewardsProgressLagrangeCfg = RewardsProgressLagrangeCfg()


def add_servo_load_obs(cfg):
    """Servo load as an observation (EXP-037, also eval_policy --servo_last): |τ|/stall per servo like the "Present Load" of
    the ST3215, history 5 like the other quantities, as the last quantity in the vector (input 105 → 145), noise σ 0.05."""
    from isaaclab.utils.noise import GaussianNoiseCfg as Gnoise
    cfg.observations.policy.servo_load = ObsTerm(func=mdp.servo_load, params={"joint_names": SERVO_JOINTS},
                                                 noise=Gnoise(mean=0.0, std=SERVO_LOAD_NOISE))
    cfg.observations.policy.enable_corruption = True       # only terms with noise (here: servo_load) are corrupted
    return cfg


@configclass
class PibGraspEnvCfg_HeavyMultiProgressDexLagrangeLoad(PibGraspEnvCfg_HeavyMultiProgressDexLagrange):
    """EXP-037: like EXP-035, the policy additionally sees the servo load."""

    def __post_init__(self):
        super().__post_init__()
        add_servo_load_obs(self)


# ── Night run 2026-10-14 (docs/protokoll/nachtlauf-2026-10-14.md): stall as on the real servo, limit per servo, finger count ─────
# Parent EXP-036 (agent _Caps). Stall as on the real servo (mdp.servo_stall): all 8 servos incl. the wrist (stall torque
# angle-dependent via the linkage; it was missing before because its limit in the sim is 1e9), no stall at the joint stop
# (the firmware clips the target). Opening against something still counts: in reality only the spring opens, the sim can push actively.
STALL_JOINTS_REAL = list(SERVO_JOINTS)
STALL_REAL = {"firmware_limits": True, "limit_tol_deg": 1.0}


@configclass
class RewardsLagrangeRealCfg(RewardsProgressLagrangeCfg):
    """EXP-038: stall cost as on the real servo (8 servos incl. wrist, no pushing against the stop)."""
    stall_lagrange = RewTerm(func=mdp.StallLagrange, weight=-1.0,
                             params={"joint_names": STALL_JOINTS_REAL, **STALL_LAGRANGE, **STALL_REAL})


@configclass
class RewardsLagrangeJeServoCfg(RewardsProgressLagrangeCfg):
    """EXP-039: like EXP-038, one λ per servo (8; CaT: limit per joint), every servo ≤ 20 %."""
    stall_lagrange = RewTerm(func=mdp.StallLagrange, weight=-1.0,
                             params={"joint_names": STALL_JOINTS_REAL, **STALL_LAGRANGE, **STALL_REAL, "per_joint": True})


@configclass
class RewardsLagrangeJeServoFingerCfg(RewardsLagrangeJeServoCfg):
    """EXP-040: like EXP-039, plus a reward by finger count (term from EXP-005/026)."""
    finger_count = RewTerm(func=mdp.fingers_in_contact, weight=1.0, params={"threshold": CONTACT_N})


@configclass
class RewardsLagrangeRealFingerCfg(RewardsLagrangeRealCfg):
    """EXP-041: like EXP-038, plus a reward by finger count (control for EXP-040 without the per-servo limit)."""
    finger_count = RewTerm(func=mdp.fingers_in_contact, weight=1.0, params={"threshold": CONTACT_N})


@configclass
class PibGraspEnvCfg_LagrangeReal(PibGraspEnvCfg_HeavyMultiProgressDex):
    rewards: RewardsLagrangeRealCfg = RewardsLagrangeRealCfg()


@configclass
class PibGraspEnvCfg_LagrangeJeServo(PibGraspEnvCfg_HeavyMultiProgressDex):
    rewards: RewardsLagrangeJeServoCfg = RewardsLagrangeJeServoCfg()


@configclass
class PibGraspEnvCfg_LagrangeJeServoFinger(PibGraspEnvCfg_HeavyMultiProgressDex):
    rewards: RewardsLagrangeJeServoFingerCfg = RewardsLagrangeJeServoFingerCfg()


@configclass
class PibGraspEnvCfg_LagrangeRealFinger(PibGraspEnvCfg_HeavyMultiProgressDex):
    rewards: RewardsLagrangeRealFingerCfg = RewardsLagrangeRealFingerCfg()


@configclass
class PibGraspEnvCfg_HeavyMultiPriv(PibGraspEnvCfg_HeavyMulti):
    """EXP-021: like EXP-018, critic additionally with object size, mass and friction (privileged, like HORA/Dexsuite)."""

    def __post_init__(self):
        super().__post_init__()
        self.observations.critic.object_props = ObsTerm(func=mdp.object_properties)


@configclass
class PibGraspEnvCfg_PLAY(PibGraspEnvCfg):
    def __post_init__(self):
        super().__post_init__()
        self.scene.num_envs = 16
