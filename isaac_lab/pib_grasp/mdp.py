"""
mdp.py — custom MDP terms of the pib grasping task (in addition to isaaclab.envs.mdp).

Structured after Isaac Lab's Dexsuite (manipulation/dexsuite/mdp), adapted to the pib hand:
fingertip forces in a fixed order (like the real FSRs), "lower the table" as the
success test instead of a goal-pose command.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

import math

import torch

from isaaclab.assets import Articulation, RigidObject
from isaaclab.envs.mdp.actions import RelativeJointPositionActionCfg
from isaaclab.envs.mdp.actions.joint_actions import RelativeJointPositionAction
from isaaclab.managers import ManagerTermBase, SceneEntityCfg
from isaaclab.sensors import ContactSensor
from isaaclab.utils import configclass

if TYPE_CHECKING:
    from isaaclab.envs import ManagerBasedRLEnv

# Fixed FSR order (also for the firmware): thumb, index, middle, ring, little.
# Link names from pib_hand_left_urdf_v5/robot.urdf (finger_tip = index, _2 = middle,
# _3 = ring, _4 = little). The ContactSensor returns them in a different order.
FINGERTIP_LINKS = ["urdf_thumb_tip", "urdf_finger_tip", "urdf_finger_tip_2", "urdf_finger_tip_3", "urdf_finger_tip_4"]
# One ContactSensor per fingertip (like Dexsuite): Isaac Lab's object filter only works
# if a sensor covers exactly one prim (ContactSensorCfg.filter_prim_paths_expr).
FINGERTIP_SENSORS = ["fsr_thumb", "fsr_index", "fsr_middle", "fsr_ring", "fsr_pinky"]


def _sensors(env: ManagerBasedRLEnv) -> list[ContactSensor]:
    return [env.scene.sensors[name] for name in FINGERTIP_SENSORS]


def episode_time(env: ManagerBasedRLEnv) -> torch.Tensor:
    return env.episode_length_buf * env.step_dt


# ── Aktion ────────────────────────────────────────────────────────────────────

class FilteredRelativeJointPositionAction(RelativeJointPositionAction):
    """Relative joint position like Dexsuite, with the action smoothed by a moving average first (EXP-024):
    a_f ← α·a + (1 − α)·a_f, target = q + scale·a_f. Reference: Isaac Lab ShadowHand-OpenAI (act_moving_average = 0.3,
    DeXtreme line) — there on the joint targets, here on the relative action, because the target is recomputed from the
    current position every step. The firmware must apply the same filter (same α, 60 Hz) in front of the servos.
    filtered_actions = what the servos actually receive (metric "Unruhe wirksam")."""

    cfg: FilteredRelativeJointPositionActionCfg

    def __init__(self, cfg: FilteredRelativeJointPositionActionCfg, env):
        super().__init__(cfg, env)
        self._filtered = torch.zeros_like(self._raw_actions)

    @property
    def filtered_actions(self) -> torch.Tensor:
        return self._filtered

    def process_actions(self, actions: torch.Tensor):
        self._raw_actions[:] = actions
        self._filtered[:] = self.cfg.alpha * actions + (1.0 - self.cfg.alpha) * self._filtered
        self._processed_actions = self._filtered * self._scale + self._offset
        if self.cfg.clip is not None:
            self._processed_actions = torch.clamp(self._processed_actions, min=self._clip[:, :, 0], max=self._clip[:, :, 1])

    def reset(self, env_ids=None) -> None:
        super().reset(env_ids)
        self._filtered[env_ids] = 0.0


@configclass
class FilteredRelativeJointPositionActionCfg(RelativeJointPositionActionCfg):
    class_type: type = FilteredRelativeJointPositionAction
    alpha: float = 0.3
    """Gewicht der neuen Aktion (1 = kein Filter)."""


# ── Observations ──────────────────────────────────────────────────────────────

def fingertip_forces(env: ManagerBasedRLEnv) -> torch.Tensor:
    """Magnitude of the total contact force per fingertip [N], FSR order. All contacts
    (including finger-finger), like a real FSR. Clipping via ObsTerm(clip=...)."""
    return torch.stack([s.data.net_forces_w[:, 0].norm(dim=-1) for s in _sensors(env)], dim=-1)


def fingertip_object_forces(env: ManagerBasedRLEnv) -> torch.Tensor:
    """Contact force per fingertip with the object only [N] (privileged, critic/reward)."""
    # force_matrix_w: (N, bodies=1, filters=1, 3)
    return torch.stack([s.data.force_matrix_w[:, 0, 0].norm(dim=-1) for s in _sensors(env)], dim=-1)


def object_pos_in_root(env: ManagerBasedRLEnv, robot_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
                       object_cfg: SceneEntityCfg = SceneEntityCfg("object")) -> torch.Tensor:
    from isaaclab.utils.math import quat_apply_inverse
    robot: Articulation = env.scene[robot_cfg.name]
    obj: RigidObject = env.scene[object_cfg.name]
    return quat_apply_inverse(robot.data.root_quat_w, obj.data.root_pos_w - robot.data.root_pos_w)


def object_quat_in_root(env: ManagerBasedRLEnv, robot_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
                        object_cfg: SceneEntityCfg = SceneEntityCfg("object")) -> torch.Tensor:
    """Object orientation (w, x, y, z) in the hand root frame (Dexsuite: object_quat_b), privileged."""
    from isaaclab.utils.math import quat_inv, quat_mul
    robot: Articulation = env.scene[robot_cfg.name]
    obj: RigidObject = env.scene[object_cfg.name]
    return quat_mul(quat_inv(robot.data.root_quat_w), obj.data.root_quat_w)


def object_tilt(env: ManagerBasedRLEnv, object_cfg: SceneEntityCfg = SceneEntityCfg("object")) -> torch.Tensor:
    """Tilt angle [rad] between the object z axis (cylinder axis) and world z."""
    from isaaclab.utils.math import quat_apply
    obj: RigidObject = env.scene[object_cfg.name]
    z = torch.zeros_like(obj.data.root_pos_w)
    z[:, 2] = 1.0
    return torch.acos(quat_apply(obj.data.root_quat_w, z)[:, 2].clamp(-1.0, 1.0))


def object_lin_vel(env: ManagerBasedRLEnv, object_cfg: SceneEntityCfg = SceneEntityCfg("object")) -> torch.Tensor:
    obj: RigidObject = env.scene[object_cfg.name]
    return obj.data.root_lin_vel_w


def object_properties(env: ManagerBasedRLEnv, object_cfg: SceneEntityCfg = SceneEntityCfg("object")) -> torch.Tensor:
    """Privileged (critic only, EXP-021; like HORA and Dexsuite, whose critic knows mass/friction/shape): half depth,
    half width, height [m] (bounding box incl. random scale), mass [kg], static and dynamic friction. Read on the first
    call after the startup events (they do not change afterwards); zeros before (shape inference of the observation manager)."""
    props = getattr(env, "_pib_object_props", None)
    if props is not None:
        return props
    footprint = getattr(env, "pib_object_footprint", None)
    if footprint is None:
        return torch.zeros(env.num_envs, 6, device=env.device)
    obj: RigidObject = env.scene[object_cfg.name]
    mass = obj.root_physx_view.get_masses().reshape(env.num_envs, -1).sum(-1).to(env.device)
    material = obj.root_physx_view.get_material_properties().reshape(env.num_envs, -1, 3)[:, 0, :2].to(env.device)
    env._pib_object_props = torch.cat([footprint[:, [0, 1, 3]], mass[:, None], material], dim=-1)
    return env._pib_object_props


def phase(env: ManagerBasedRLEnv, drop_start_s: float) -> torch.Tensor:
    """Episode time relative to the table lowering (privileged, critic only)."""
    return (episode_time(env) - drop_start_s).unsqueeze(-1)


# ── Events ────────────────────────────────────────────────────────────────────

def lower_table(env: ManagerBasedRLEnv, env_ids: torch.Tensor, drop_start_s: float, drop_speed: float,
                drop_depth: float, table_cfg: SceneEntityCfg = SceneEntityCfg("table")) -> None:
    """Lower the kinematic table from drop_start_s at drop_speed [m/s] by drop_depth [m].
    Physically equivalent to lifting the hand (later: the arm lifts), without moving the
    fixed base of the articulation."""
    table: RigidObject = env.scene[table_cfg.name]
    t = episode_time(env)[env_ids]
    dz = ((t - drop_start_s) * drop_speed).clamp(0.0, drop_depth)
    pose = table.data.default_root_state[env_ids, :7].clone()
    pose[:, :3] += env.scene.env_origins[env_ids]
    pose[:, 2] -= dz
    table.write_root_pose_to_sim(pose, env_ids=env_ids)


# Mimic coupling of the left hand (ADR-011, isaac_sim/setup_stage.py → MIMIC_JOINTS):
# follower -> reference, gearing -1 = same angle. Order: PIP before DIP.
MIMIC_LEFT = [(f"{f}_left_distal", f"{f}_left_proximal") for f in ("index", "middle", "ring", "pinky")] + \
             [(f"{f}_left_tip", f"{f}_left_distal") for f in ("index", "middle", "ring", "pinky")] + \
             [("thumb_left_tip", "thumb_left_proximal")]


def reset_hand_joints(env: ManagerBasedRLEnv, env_ids: torch.Tensor, ranges_deg: dict[str, tuple[float, float]],
                      asset_cfg: SceneEntityCfg = SceneEntityCfg("robot")) -> None:
    """Set the servo joints uniformly within ranges_deg on reset (Dexsuite: reset_joints_by_offset),
    followers consistent with the mimic coupling — otherwise the constraint starts with a jump.
    Targets = start position, so the drives do not pull back."""
    import math
    robot: Articulation = env.scene[asset_cfg.name]
    q = robot.data.default_joint_pos[env_ids].clone()
    for name, (lo, hi) in ranges_deg.items():
        u = torch.rand(len(env_ids), device=q.device)
        q[:, robot.joint_names.index(name)] = math.radians(lo) + u * math.radians(hi - lo)
    for follower, reference in MIMIC_LEFT:
        q[:, robot.joint_names.index(follower)] = q[:, robot.joint_names.index(reference)]
    robot.write_joint_state_to_sim(q, torch.zeros_like(q), env_ids=env_ids)
    robot.set_joint_position_target(q, env_ids=env_ids)


def place_objects_by_size(env: ManagerBasedRLEnv, env_ids: torch.Tensor | None, hand_x: float, palm_gap: float,
                          table_top_z: float, lift: float = 0.0, root_height: float | None = None,
                          object_cfg: SceneEntityCfg = SceneEntityCfg("object")) -> None:
    """Startup: start pose per environment from the bounding box of the spawned object (USD, incl. random scale) —
    surface palm_gap in front of the palm, bottom lift above the table top. root_height: measured rest pose
    (height of the origin above the table top, tools/ruhelage_objekt.py) instead of bounding box + lift."""
    import re
    import isaaclab.sim as sim_utils
    from pxr import Usd, UsdGeom
    obj: RigidObject = env.scene[object_cfg.name]
    cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(), [UsdGeom.Tokens.default_])
    stage = env.scene.stage
    # Footprint per environment for reset_object_gap_aware (half depth/width, angular 1 / round 0) and height [m]
    env.pib_object_footprint = torch.zeros(env.num_envs, 4, device=env.device)
    for path in sim_utils.find_matching_prim_paths(obj.cfg.prim_path):
        idx = int(re.search(r"env_(\d+)", path).group(1))
        prim = stage.GetPrimAtPath(path)
        size = cache.ComputeWorldBound(prim).ComputeAlignedRange().GetSize()
        round_ = any(p.GetTypeName() == "Cylinder" for p in Usd.PrimRange(prim))
        env.pib_object_footprint[idx] = torch.tensor([size[0] / 2, size[1] / 2, 0.0 if round_ else 1.0, size[2]])
        obj.data.default_root_state[idx, 0] = hand_x - palm_gap - size[0] / 2
        obj.data.default_root_state[idx, 2] = table_top_z + (root_height if root_height is not None
                                                             else lift + size[2] / 2)


def tip_height_for_object(kind: str, size: tuple[float, float, float], sphere_offset: float, block_offset: float,
                          min_tip_height: float) -> float:
    """Height of the lowest fingertip above the table [m] for an object below the hand ("top grasp") — rule from the
    start-pose search (docs/protokoll/startpose-oben/ergebnis.md, re-checked with 48 episodes per height: sphere Ø 5/7/9 →
    10/15/30 mm, can 10 cm → 60 mm, small box 4 cm → 10–15 mm): spheres max(min, Ø − sphere_offset), otherwise
    max(min, height − block_offset). kind: kugel, zylinder or quader; size = bounding box (x, y, z)."""
    if kind == "kugel":
        return max(min_tip_height, size[2] - sphere_offset)
    return max(min_tip_height, size[2] - block_offset)


def place_objects_from_above(env: ManagerBasedRLEnv, env_ids: torch.Tensor | None, center_xy: tuple[float, float],
                             tip_low_z: float, sphere_offset: float, block_offset: float, min_tip_height: float,
                             height_jitter: float, table_thickness: float, lift: float = 0.0,
                             object_cfg: SceneEntityCfg = SceneEntityCfg("object"),
                             table_cfg: SceneEntityCfg = SceneEntityCfg("table")) -> None:
    """Startup, grasp type "top" (env_cfg_oben, pose from the start-pose search): per environment, from bounding box and
    shape of the spawned object (incl. random scale), the height of the lowest fingertip above the table
    (tip_height_for_object), plus a fixed spread per environment ±height_jitter (inaccurate pre-grasp pose); object at the
    grasp centre center_xy on the table, table top = tip_low_z − height (− lift: YCB drops briefly onto the table). The
    hand is fixed — object and table are placed; lower_table and reset_scene_to_default use the changed default pose.
    Height per environment in env.pib_tip_height (diagnostics). Footprint for reset_object_gap_aware without corner
    correction (angular = 0)."""
    import re
    import isaaclab.sim as sim_utils
    from pxr import Usd, UsdGeom
    obj: RigidObject = env.scene[object_cfg.name]
    table: RigidObject = env.scene[table_cfg.name]
    cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(), [UsdGeom.Tokens.default_])
    stage = env.scene.stage
    env.pib_object_footprint = torch.zeros(env.num_envs, 4, device=env.device)
    env.pib_tip_height = torch.zeros(env.num_envs, device=env.device)
    jitter = (torch.rand(env.num_envs) * 2 - 1) * height_jitter
    for path in sim_utils.find_matching_prim_paths(obj.cfg.prim_path):
        idx = int(re.search(r"env_(\d+)", path).group(1))
        prim = stage.GetPrimAtPath(path)
        size = cache.ComputeWorldBound(prim).ComputeAlignedRange().GetSize()
        types = {q.GetTypeName() for q in Usd.PrimRange(prim)}
        kind = "kugel" if "Sphere" in types else ("zylinder" if "Cylinder" in types else "quader")
        h = tip_height_for_object(kind, (size[0], size[1], size[2]), sphere_offset, block_offset, min_tip_height)
        h = max(min_tip_height * 0.5, h + float(jitter[idx]))
        env.pib_tip_height[idx] = h
        env.pib_object_footprint[idx] = torch.tensor([size[0] / 2, size[1] / 2, 0.0, size[2]])
        top = tip_low_z - h                                           # Tischplatte
        obj.data.default_root_state[idx, 0] = center_xy[0]
        obj.data.default_root_state[idx, 1] = center_xy[1]
        obj.data.default_root_state[idx, 2] = top + lift + size[2] / 2  # origin = box centre (also YCB)
        table.data.default_root_state[idx, 0] = center_xy[0]
        table.data.default_root_state[idx, 1] = center_xy[1]
        table.data.default_root_state[idx, 2] = top - table_thickness / 2


def reset_object_gap_aware(env: ManagerBasedRLEnv, env_ids: torch.Tensor, pose_range: dict[str, tuple[float, float]],
                           velocity_range: dict[str, tuple[float, float]],
                           asset_cfg: SceneEntityCfg = SceneEntityCfg("object")) -> None:
    """Like Isaac Lab's reset_root_state_uniform, but the distance to the palm holds after the yaw rotation: an angular
    object is moved away from the hand by a·|cos θ| + b·|sin θ| − a (a, b = half depth/width), so that its nearest
    corner lies as far in front of the palm as the front face without rotation — as a grasp planner would set the
    pre-grasp pose. Round objects unchanged. Without a footprint (place_objects_by_size) like the original.
    Before this, the corner of a box rotated by 10–15° touched the fingers at reset (tools/analyse_reset.py)."""
    from isaaclab.utils import math as math_utils
    asset: RigidObject = env.scene[asset_cfg.name]
    root_states = asset.data.default_root_state[env_ids].clone()
    ranges = torch.tensor([pose_range.get(k, (0.0, 0.0)) for k in ("x", "y", "z", "roll", "pitch", "yaw")],
                          device=asset.device)
    rand = math_utils.sample_uniform(ranges[:, 0], ranges[:, 1], (len(env_ids), 6), device=asset.device)
    positions = root_states[:, 0:3] + env.scene.env_origins[env_ids] + rand[:, 0:3]
    footprint = getattr(env, "pib_object_footprint", None)
    if footprint is not None:
        a, b, square = footprint[env_ids, :3].unbind(-1)
        yaw = rand[:, 5]
        positions[:, 0] -= square * (a * yaw.cos().abs() + b * yaw.sin().abs() - a)   # object lies at −x of the hand
    orientations = math_utils.quat_mul(root_states[:, 3:7],
                                       math_utils.quat_from_euler_xyz(rand[:, 3], rand[:, 4], rand[:, 5]))
    vranges = torch.tensor([velocity_range.get(k, (0.0, 0.0)) for k in ("x", "y", "z", "roll", "pitch", "yaw")],
                           device=asset.device)
    velocities = root_states[:, 7:13] + math_utils.sample_uniform(vranges[:, 0], vranges[:, 1], (len(env_ids), 6),
                                                                  device=asset.device)
    asset.write_root_pose_to_sim(torch.cat([positions, orientations], dim=-1), env_ids=env_ids)
    asset.write_root_velocity_to_sim(velocities, env_ids=env_ids)


class GraspDifficultyScheduler(ManagerTermBase):
    """Curriculum like Dexsuite's DifficultyScheduler (adr_curriculum.py), with our success criterion instead of the
    goal command: per environment difficulty +1 after a successful episode (held until timeout,
    tilt ≤ max_kipp_deg), otherwise −1; difficulty_frac = mean / max_difficulty drives gravity and observation
    noise via initial_final_interpolate_fn (EXP-017)."""

    def __init__(self, cfg, env):
        super().__init__(cfg, env)
        self.current = torch.ones(env.num_envs, device=env.device) * self.cfg.params.get("init_difficulty", 0)
        self.difficulty_frac = torch.zeros((), device=env.device)

    def __call__(self, env: ManagerBasedRLEnv, env_ids, max_kipp_deg: float = 45.0, init_difficulty: int = 0,
                 min_difficulty: int = 0, max_difficulty: int = 10):
        import math
        ok = env.termination_manager.time_outs[env_ids] & (object_tilt(env)[env_ids] <= math.radians(max_kipp_deg))
        self.current[env_ids] = torch.where(ok, self.current[env_ids] + 1, self.current[env_ids] - 1).clamp(
            min=min_difficulty, max=max_difficulty)
        # tensor as in Dexsuite: initial_final_interpolate_fn calls .item() on the interpolated values
        self.difficulty_frac = self.current.mean() / max(max_difficulty, 1)
        return self.difficulty_frac


# ── Rewards ───────────────────────────────────────────────────────────────────

def fingertips_to_object(env: ManagerBasedRLEnv, std: float,
                         robot_cfg: SceneEntityCfg = SceneEntityCfg("robot", body_names=FINGERTIP_LINKS),
                         object_cfg: SceneEntityCfg = SceneEntityCfg("object")) -> torch.Tensor:
    """Approach: 1 − tanh(largest fingertip↔object distance / std) (Dexsuite: object_ee_distance)."""
    robot: Articulation = env.scene[robot_cfg.name]
    obj: RigidObject = env.scene[object_cfg.name]
    tips = robot.data.body_pos_w[:, robot_cfg.body_ids]
    dist = torch.norm(tips - obj.data.root_pos_w[:, None, :], dim=-1).max(dim=-1).values
    return 1.0 - torch.tanh(dist / std)


class FingertipProgress(ManagerTermBase):
    """Approach like NVIDIA AllegroKuka/DexPBT (IsaacGymEnvs allegro_kuka_base.py; Petrenko et al. 2023): per
    fingertip only the progress towards the object centre, Σ max(smallest distance so far − current, 0) — merely
    being close earns nothing (not exploitable), and that the tips never reach the centre of tall objects does not
    matter. Only in the grasp phase (before the table lowering; AllegroKuka: until the object is lifted). EXP-019,
    replaces fingertips_to_object (measured all hand bodies, and too flat for 3–4 cm of finger travel anyway — ADR-022)."""

    def __init__(self, cfg, env: ManagerBasedRLEnv):
        super().__init__(cfg, env)
        self.robot: Articulation = env.scene["robot"]
        self.obj: RigidObject = env.scene["object"]
        self.tip_ids = [self.robot.body_names.index(n) for n in FINGERTIP_LINKS]
        self.closest = torch.full((env.num_envs, len(self.tip_ids)), -1.0, device=env.device)   # −1: set anew

    def reset(self, env_ids=None):
        self.closest[slice(None) if env_ids is None else env_ids] = -1.0

    def __call__(self, env: ManagerBasedRLEnv, drop_start_s: float, max_delta: float = 0.05) -> torch.Tensor:
        d = torch.norm(self.robot.data.body_pos_w[:, self.tip_ids] - self.obj.data.root_pos_w[:, None, :], dim=-1)
        self.closest = torch.where(self.closest < 0, d, self.closest)
        delta = (self.closest - d).clamp(0.0, max_delta)          # AllegroKuka: clip(…, 0, 10)
        self.closest = torch.minimum(self.closest, d)
        return delta.sum(dim=-1) * (episode_time(env) < drop_start_s).float()


def thumb_opposition_contact(env: ManagerBasedRLEnv, threshold: float) -> torch.Tensor:
    """1 if the thumb and at least one finger touch the object (Dexsuite: contacts)."""
    f = fingertip_object_forces(env)
    return ((f[:, 0] > threshold) & (f[:, 1:] > threshold).any(dim=-1)).float()


def object_sink(env: ManagerBasedRLEnv, drop_start_s: float,
                object_cfg: SceneEntityCfg = SceneEntityCfg("object")) -> torch.Tensor:
    """Sinking [m] relative to the height at the start of the table lowering (tracked until then, frozen
    afterwards). Not against the default height: with ±10 % scale the can stands up to 7.5 mm lower."""
    obj: RigidObject = env.scene[object_cfg.name]
    z = obj.data.root_pos_w[:, 2]
    if getattr(env, "_pib_z_ref", None) is None or env._pib_z_ref.shape != z.shape:
        env._pib_z_ref = z.clone()
    before = episode_time(env) < drop_start_s
    env._pib_z_ref[before] = z[before]
    return (env._pib_z_ref - z).clamp(min=0.0)


def fingers_in_contact(env: ManagerBasedRLEnv, threshold: float) -> torch.Tensor:
    """Fraction of the four fingers in contact with the object, only with thumb contact: (finger > threshold) / 4 ·
    𝟙[thumb > threshold] ∈ [0, 1]. Rewards a power grasp instead of a pinch grasp (EXP-005)."""
    f = fingertip_object_forces(env)
    return (f[:, 1:] > threshold).float().mean(dim=-1) * (f[:, 0] > threshold).float()


def object_held(env: ManagerBasedRLEnv, drop_start_s: float, std: float,
                object_cfg: SceneEntityCfg = SceneEntityCfg("object")) -> torch.Tensor:
    """From the table lowering on: 1 − tanh(object sinking / std). Before that 0 — while the
    object stands on the table there is nothing to earn."""
    active = (episode_time(env) >= drop_start_s).float()
    return active * (1.0 - torch.tanh(object_sink(env, drop_start_s, object_cfg) / std))


def held_in_grasp(env: ManagerBasedRLEnv, drop_start_s: float, std: float, threshold: float) -> torch.Tensor:
    """Dense, from the lowering on: held × opposition (Dexsuite position_command_error_tanh, × contacts)."""
    return object_held(env, drop_start_s, std) * thumb_opposition_contact(env, threshold)


def upright_in_grasp(env: ManagerBasedRLEnv, drop_start_s: float, rot_std: float, threshold: float) -> torch.Tensor:
    """Dense, from the table lowering on: (1 − tanh(tilt/rot_std)) × opposition (Dexsuite
    orientation_command_error_tanh, × contacts). Only from the lowering on — on the table the
    can stands upright by itself, otherwise merely touching it would be rewarded."""
    active = (episode_time(env) >= drop_start_s).float()
    return active * (1.0 - torch.tanh(object_tilt(env) / rot_std)) * thumb_opposition_contact(env, threshold)


def object_held_upright(env: ManagerBasedRLEnv, drop_start_s: float, std: float, rot_std: float,
                        object_cfg: SceneEntityCfg = SceneEntityCfg("object")) -> torch.Tensor:
    """Held × upright (Dexsuite success_reward: (1 − tanh(error/pos_std))·(1 − tanh(angle/rot_std))).
    Holding it tilted earns almost nothing without terminating the episode — grasping stays explorable."""
    return object_held(env, drop_start_s, std, object_cfg) * (1.0 - torch.tanh(object_tilt(env, object_cfg) / rot_std))


def object_upright(env: ManagerBasedRLEnv, drop_start_s: float, std: float) -> torch.Tensor:
    """From the table lowering on: 1 − tanh(tilt / std). Before that 0 — on the table the
    can stands upright anyway, the reward would come for free there."""
    active = (episode_time(env) >= drop_start_s).float()
    return active * (1.0 - torch.tanh(object_tilt(env) / std))


# ── Position terms like Dexsuite (EXP-012): target = start position of the object ────────────────

def object_start_distance(env: ManagerBasedRLEnv, ref_s: float,
                          object_cfg: SceneEntityCfg = SceneEntityCfg("object")) -> torch.Tensor:
    """3D distance [m] of the object to its start position (tracked until ref_s, then frozen: object
    settled, scale settled). Counterpart of Dexsuite's target position (command relative to the
    robot base): the hand is fixed, the object should stay where the arm grasped it."""
    obj: RigidObject = env.scene[object_cfg.name]
    pos = obj.data.root_pos_w
    if getattr(env, "_pib_start_pos", None) is None or env._pib_start_pos.shape != pos.shape:
        env._pib_start_pos = pos.clone()
    before = episode_time(env) < ref_s
    env._pib_start_pos[before] = pos[before]
    return torch.norm(pos - env._pib_start_pos, dim=-1)


def position_tracking_start(env: ManagerBasedRLEnv, drop_start_s: float, std: float, threshold: float,
                            ref_s: float) -> torch.Tensor:
    """Dexsuite position_command_error_tanh: (1 − tanh(‖p − p_target‖/std)) × opposition, from the lowering on."""
    active = (episode_time(env) >= drop_start_s).float()
    return active * (1.0 - torch.tanh(object_start_distance(env, ref_s) / std)) * thumb_opposition_contact(env, threshold)


def success_start(env: ManagerBasedRLEnv, drop_start_s: float, pos_std: float, rot_std: float,
                  ref_s: float) -> torch.Tensor:
    """Dexsuite success_reward: (1 − tanh(‖p − p_target‖/pos_std)) · (1 − tanh(tilt/rot_std)), from the
    lowering on. Orientation as tilt angle (requirement upright, no yaw target)."""
    active = (episode_time(env) >= drop_start_s).float()
    return (active * (1.0 - torch.tanh(object_start_distance(env, ref_s) / pos_std))
            * (1.0 - torch.tanh(object_tilt(env) / rot_std)))


def object_xy_displacement(env: ManagerBasedRLEnv, ref_s: float, max_dist: float = 0.2,
                           object_cfg: SceneEntityCfg = SceneEntityCfg("object")) -> torch.Tensor:
    """Displacement [m] of the object centre in the table plane relative to the start pose (tracked until ref_s, then
    frozen), clipped at max_dist. As a penalty over the whole episode like Cross-Embodiment Dexterous Grasping
    (Yuan et al. 2024: r = −0.3·‖xy − xy_start‖); z stays with the hold term. EXP-023: the policies pulled the object
    ~13 cm towards the forearm (tools/diag_objektweg.py); nothing in the reward kept the pose in the table plane."""
    obj: RigidObject = env.scene[object_cfg.name]
    xy = obj.data.root_pos_w[:, :2]
    if getattr(env, "_pib_start_xy", None) is None or env._pib_start_xy.shape != xy.shape:
        env._pib_start_xy = xy.clone()
    before = episode_time(env) < ref_s
    env._pib_start_xy[before] = xy[before]
    return torch.norm(xy - env._pib_start_xy, dim=-1).clamp(max=max_dist)


def servo_torque_l2(env: ManagerBasedRLEnv, asset_cfg: SceneEntityCfg) -> torch.Tensor:
    """Σ (torque / stall torque)² of the servos in asset_cfg (EXP-025): 0 = no force, ≈ number of servos at permanent stall.
    Like HORA's torque penalty (Qi et al. 2022) and Isaac Lab's joint_torques_l2, but normalised per joint by the stall
    torque (servos differ in strength). applied_torque = PD torque after clipping — the same quantity as the stall-share
    guardrail (eval_policy). Joints only via params (SceneEntityCfg is only resolved there, ADR-017)."""
    robot: Articulation = env.scene[asset_cfg.name]
    tau = robot.data.applied_torque[:, asset_cfg.joint_ids] / robot.data.joint_effort_limits[:, asset_cfg.joint_ids]
    return torch.sum(torch.square(tau), dim=1)


def servo_effort_limit(robot: Articulation, ids: list) -> torch.Tensor:
    """Stall torque per joint in `ids` (N, len(ids)) at the joint. Linkage-driven joints (wrist linkage,
    RemotizedPDActuator, ADR-014): angle-dependent 2.94 Nm × transmission n(θ) from the actuator's table — there
    joint_effort_limits holds Isaac Lab's default 1e9 (explicit actuators), so |τ|/limit would always be ≈ 0. This way
    |τ|/limit is the same quantity for all servos: torque at the servo / stall torque."""
    lim = robot.data.joint_effort_limits[:, ids].clone()
    for act in robot.actuators.values():
        if not hasattr(act, "_torque_limit"):
            continue
        jids = act.joint_indices if not isinstance(act.joint_indices, slice) else list(range(robot.num_joints))
        jids = [int(j) for j in (jids.tolist() if torch.is_tensor(jids) else jids)]
        for col, jid in enumerate(ids):
            if jid in jids:
                lim[:, col] = act._torque_limit.compute(robot.data.joint_pos[:, [jid]])[:, 0]
    return lim


def servo_stall(robot: Articulation, ids: list, fraction: float, tendon: torch.Tensor | None = None,
                firmware_limits: bool = False, limit_tol_deg: float = 1.0) -> torch.Tensor:
    """Stall per servo (N, len(ids)) as bool: |τ| ≥ fraction · stall torque (PD estimate applied_torque, limit from
    servo_effort_limit). As on the real servo (night run 2026-10-14): `firmware_limits` = no stall within limit_tol_deg
    of the joint limit in the torque direction (the firmware clips the target, the servo does not push against the stop).
    `tendon` (bool per servo, optional) = only τ > 0 counts (tendon can only pull) — deliberately not used in training:
    the sim can actively open fingers, the real hand only via the spring; without a cost the policy would use this force freely.
    Shared by StallLagrange (training) and eval_policy (metric "Servo-Last real")."""
    tau = robot.data.applied_torque[:, ids]
    stall = tau.abs() >= fraction * servo_effort_limit(robot, ids)
    if tendon is not None:
        stall = torch.where(tendon[None, :], stall & (tau > 0), stall)
    if firmware_limits:
        q = robot.data.joint_pos[:, ids]
        lim = robot.data.joint_pos_limits[:, ids]
        tol = math.radians(limit_tol_deg)
        stall = stall & ~torch.where(tau > 0, q >= lim[..., 1] - tol, q <= lim[..., 0] + tol)
    return stall


class StallLagrange(ManagerTermBase):
    """Limit on servo stall via PID Lagrangian (night run 2026-10-13, EXP-035 ff.; Ray, Achiam & Amodei 2019, Safety
    Gym; Stooke, Achiam & Abbeel 2020, PID Lagrangian). Cost c_t = fraction of the servos in `joint_names` with
    |τ| ≥ `fraction` · stall torque (the same quantity as applied_torque in eval_policy). Target J_c = mean of c_t ≤ `limit`.
    The term returns λ · c_t (weight −1 in the RewTerm → penalty −λ · c_t per s); λ ≥ 0 is updated once per rollout
    (`steps_per_update` calls = num_steps_per_env) after Stooke 2020, Algorithm 2:
        e = J_c − d,  I ← max(0, I + K_I·e),  λ = max(0, K_P·e + I + K_D·max(0, J_c − J_c,prev))
    J_c = mean of c_t over the rollout (all environments), additionally smoothed (EMA α) for the P and D parts.
    Simplification compared with Safety Gym: no separate cost critic, the penalty is part of the reward (like Lagrangian
    PPO with a shared advantage). λ, J_c and I go to TensorBoard via extras["log"] (Lagrange/…).

    Night run 2026-10-14 (EXP-038 ff., docs/protokoll/nachtlauf-2026-10-14.md), stall as on the real servo (servo_stall):
    - wrist with angle-dependent stall torque (linkage) — `joint_names` then holds all 8 servos.
    - `firmware_limits`: no stall within `limit_tol_deg` of the joint limit in the torque direction (the firmware clips
      the target to the limit, the servo does not push against the stop).
    - `tendon_joints` (optional): only pulling counts — see servo_stall for why it is not used.
    - `per_joint`: one λ per servo (CaT, Chane-Sane et al. 2024: limit per joint), every servo J_c,i ≤ `limit`;
      penalty (1/n)·Σ λ_i·c_i (same order of magnitude as with a single λ)."""

    def __init__(self, cfg, env: ManagerBasedRLEnv):
        super().__init__(cfg, env)
        p = cfg.params
        self.robot: Articulation = env.scene["robot"]
        self.names = list(p["joint_names"])
        self.ids, _ = self.robot.find_joints(self.names, preserve_order=True)
        tendon = set(p.get("tendon_joints") or [])
        self.tendon = torch.tensor([n in tendon for n in self.names], dtype=torch.bool, device=env.device)
        n = len(self.ids) if p.get("per_joint", False) else 1
        # Controller state on the CPU (logging in reset() without GPU synchronisation), λ additionally on the device
        self.lam = torch.full((n,), float(p.get("lambda_init", 0.0)))
        self.lam_dev = self.lam.to(env.device)
        self.integral = self.lam.clone()
        self.jc_ema = None
        self.jc_prev = None
        self.jc_last = torch.zeros(n)
        self.cost_sum = torch.zeros(n, device=env.device)
        self.calls = 0

    def reset(self, env_ids=None):
        log = self._env.extras.get("log")
        if isinstance(log, dict):
            log["Lagrange/lambda"] = float(self.lam.mean())
            log["Lagrange/J_c"] = float(self.jc_last.mean())
            log["Lagrange/integral"] = float(self.integral.mean())
            if self.lam.numel() > 1:
                log["Lagrange/lambda_max"] = float(self.lam.max())
                log["Lagrange/J_c_max"] = float(self.jc_last.max())
                for k, name in enumerate(self.names):
                    short = name.replace("_left", "").replace("_proximal", "")
                    log[f"Lagrange/lambda_{short}"] = float(self.lam[k])
                    log[f"Lagrange/J_c_{short}"] = float(self.jc_last[k])

    def __call__(self, env: ManagerBasedRLEnv, joint_names: list, fraction: float = 0.8, limit: float = 0.2,
                 k_p: float = 10.0, k_i: float = 1.0, k_d: float = 5.0, ema: float = 0.5, lambda_max: float = 100.0,
                 steps_per_update: int = 32, lambda_init: float = 0.0, tendon_joints: list | None = None,
                 firmware_limits: bool = False, limit_tol_deg: float = 1.0, per_joint: bool = False) -> torch.Tensor:
        c = servo_stall(self.robot, self.ids, fraction, self.tendon, firmware_limits, limit_tol_deg).float()  # (N, n)
        cost = c if per_joint else c.mean(dim=-1, keepdim=True)                    # (N, n_λ)
        self.cost_sum = self.cost_sum + cost.mean(dim=0)
        self.calls += 1
        if self.calls >= steps_per_update:
            jc = (self.cost_sum / self.calls).cpu()
            self.cost_sum, self.calls, self.jc_last = torch.zeros_like(self.cost_sum), 0, jc
            self.jc_ema = jc if self.jc_ema is None else ema * jc + (1.0 - ema) * self.jc_ema
            e = self.jc_ema - limit
            self.integral = (self.integral + k_i * (jc - limit)).clamp(min=0.0)
            deriv = torch.zeros_like(jc) if self.jc_prev is None else (self.jc_ema - self.jc_prev).clamp(min=0.0)
            self.jc_prev = self.jc_ema
            self.lam = (k_p * e + self.integral + k_d * deriv).clamp(0.0, lambda_max)
            self.lam_dev = self.lam.to(self.cost_sum.device)
        return (self.lam_dev[None, :] * cost).mean(dim=-1)


_SERVO_LOAD_IDS: dict = {}


def servo_load(env: ManagerBasedRLEnv, joint_names: list) -> torch.Tensor:
    """Servo load like the "Present Load" of the ST3215 (EXP-037): |τ| / stall torque per servo in `joint_names`
    (order = action space), clipped to [0, 1.5]. A real quantity — the firmware would have to read it."""
    robot: Articulation = env.scene["robot"]
    key = tuple(joint_names)
    if key not in _SERVO_LOAD_IDS:
        _SERVO_LOAD_IDS[key] = robot.find_joints(joint_names, preserve_order=True)[0]
    ids = _SERVO_LOAD_IDS[key]
    return (robot.data.applied_torque[:, ids].abs() / robot.data.joint_effort_limits[:, ids]).clamp(0.0, 1.5)


def excess_fingertip_force(env: ManagerBasedRLEnv, limit: float) -> torch.Tensor:
    """Sum of the force above `limit` [N] over all fingertips (against crushing and
    unrealistically high forces, ADR-011: the linear coupling overestimates the tip force)."""
    return (fingertip_forces(env) - limit).clamp(min=0.0).sum(dim=-1)


# ── Abbruch ───────────────────────────────────────────────────────────────────

def object_dropped(env: ManagerBasedRLEnv, max_sink: float,
                   object_cfg: SceneEntityCfg = SceneEntityCfg("object")) -> torch.Tensor:
    obj: RigidObject = env.scene[object_cfg.name]
    z0 = obj.data.default_root_state[:, 2] + env.scene.env_origins[:, 2]
    return (z0 - obj.data.root_pos_w[:, 2]) > max_sink


def object_tilted(env: ManagerBasedRLEnv, max_tilt_deg: float) -> torch.Tensor:
    """Terminate when the object tilts by more than max_tilt_deg (pattern: Isaac Lab
    deploy/gear_assembly, reset_when_gear_orientation_exceeds_threshold)."""
    import math
    return object_tilt(env) > math.radians(max_tilt_deg)


def abnormal_robot_state(env: ManagerBasedRLEnv, asset_cfg: SceneEntityCfg = SceneEntityCfg("robot")) -> torch.Tensor:
    """Joint velocity > 2× limit — unstable physics (Dexsuite: abnormal_robot_state)."""
    robot: Articulation = env.scene[asset_cfg.name]
    return (robot.data.joint_vel.abs() > (robot.data.joint_vel_limits * 2)).any(dim=1)


# ── Arm motion (load test, 2026-10-12) ──────────────────────────────────────
# The hand is mounted fixed. A motion of the whole arm is equivalent, in the hand's frame, to fictitious forces
# on every body (object and hand links, at the centre of mass):
# F = m·[−a_P + (Rᵀg − g) − α×r − ω×(ω×r) − 2·ω×v]
# a_P = acceleration of the pivot, R = rotation of the hand since the motion started (gravity rotates relative to the hand),
# ω/α about a fixed axis n, r = centre of mass − pivot, v = velocity in the hand frame (Coriolis). For pure
# translation exactly −m·a (equivalence principle; DexGraspNet tests grasps the same way with rotated gravity). Torques
# from the non-uniform field neglected. Profiles: minimum jerk (Flash & Hogan 1985), ramp until failure (Grasp to Act
# 2026, SoGraB), rotation ±45° like GRASPA. Pivot = hand root (elbow, `elbow_lower`); yaw about the vertical axis
# (upper arm hangs vertically), pitch about the horizontal axis across the forearm (forearm/hand point to −y).

BEWEGUNG_START_S = 2.6          # hold phase from 2.5 s (table down), episode 4.5 s
RAMPE_S = 1.8                   # ramp 0 → a_max until shortly before the end of the episode
TRANSPORT_M = 0.3               # distance of the transport motion
DREH_RAD = 0.7853981633974483   # 45° (GRASPA)
_ACHSEN6 = ((1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1))
BEWEGUNG_RICHTUNGEN = {"rampe": ("+x", "−x", "+y", "−y", "+z", "−z"), "transport": ("+x", "−x", "+y", "−y", "+z", "−z"),
                       "gieren": ("+", "−"), "nicken": ("+", "−")}


def min_jerk(t: torch.Tensor, T: float):
    """Minimum-jerk profile over distance 1: position s, velocity ṡ, acceleration s̈ (0 before the start, constant 1 after).
    Peak acceleration 10/√3/T² ≈ 5.77/T²."""
    x = (t / T).clamp(0.0, 1.0)
    s = x ** 3 * (10 - 15 * x + 6 * x ** 2)
    sd = 30 * x ** 2 * (1 - x) ** 2 / T
    sdd = 60 * x * (1 - x) * (1 - 2 * x) / T ** 2
    return s, sd, sdd


def transport_dauer(a_max: float, strecke: float = TRANSPORT_M) -> float:
    """Duration T of the minimum-jerk motion over `strecke` with peak acceleration a_max."""
    return (10 / 3 ** 0.5 * strecke / a_max) ** 0.5


def _rotate(v: torch.Tensor, n: torch.Tensor, phi: torch.Tensor) -> torch.Tensor:
    """Rodrigues: rotate v (…, 3) about the unit axis n (3,) by phi (…, 1)."""
    c, s = torch.cos(phi), torch.sin(phi)
    n = n.expand_as(v)
    return v * c + torch.cross(n, v, dim=-1) * s + n * (n * v).sum(-1, keepdim=True) * (1 - c)


def apply_arm_motion(env: ManagerBasedRLEnv, art: str, param: float, t: torch.Tensor,
                     start_s: float = BEWEGUNG_START_S) -> torch.Tensor:
    """Set the fictitious forces of an arm motion on object and hand (they stay set until the next call).
    art: rampe (param = a_max [m/s²], linear over RAMPE_S), transport (param = a_max, minimum jerk over TRANSPORT_M),
    gieren/nicken (param = duration T [s] for 45°). Direction per environment `env_id % len(directions)`, t = episode
    time at the start of the step.
    Returns the magnitude of the pivot acceleration or ω²·r at the object [m/s²] per environment (limit value)."""
    robot: Articulation = env.scene["robot"]
    obj: RigidObject = env.scene["object"]
    dev, N = env.device, env.num_envs
    k = torch.arange(N, device=dev) % len(BEWEGUNG_RICHTUNGEN[art])
    tau = t + env.step_dt / 2 - start_s           # in the middle of the policy step (force constant per step)
    g = torch.tensor((0.0, 0.0, -9.81), device=dev)
    bodies = [(obj, obj.data.body_com_pos_w, obj.data.body_com_lin_vel_w),
              (robot, robot.data.body_com_pos_w, robot.data.body_com_lin_vel_w)]
    if art in ("rampe", "transport"):
        d = torch.tensor(_ACHSEN6, dtype=torch.float32, device=dev)[k]                  # (N, 3)
        if art == "rampe":
            amag = param * (tau / RAMPE_S).clamp(0.0, 1.0) * (tau >= 0)
            acc = amag[:, None] * d
        else:
            _, _, sdd = min_jerk(tau, transport_dauer(param))
            acc = (TRANSPORT_M * sdd)[:, None] * d
            amag = acc.norm(dim=-1)
        per_body = lambda p, v: (-acc)[:, None, :].expand_as(p)                          # noqa: E731
    elif art in ("gieren", "nicken"):
        n = torch.tensor((0.0, 0.0, 1.0) if art == "gieren" else (1.0, 0.0, 0.0), device=dev)
        sign = torch.tensor((1.0, -1.0), device=dev)[k]
        s, sd, sdd = min_jerk(tau, param)
        theta, w, al = (sign * DREH_RAD * x for x in (s, sd, sdd))
        pivot = robot.data.root_pos_w                                                    # Ellbogen
        g_rel = _rotate(g.expand(N, 3), n, -theta[:, None]) - g                          # Rᵀg − g

        def per_body(p, v):
            r = p - pivot[:, None, :]
            nn = n.expand_as(r)
            nxr = torch.cross(nn, r, dim=-1)
            return (g_rel[:, None, :] - al[:, None, None] * nxr - w[:, None, None] ** 2 * torch.cross(nn, nxr, dim=-1)
                    - 2 * w[:, None, None] * torch.cross(nn, v, dim=-1))
        r_obj = obj.data.root_pos_w - pivot
        r_perp = (r_obj - n * (r_obj @ n)[:, None]).norm(dim=-1)
        amag = torch.sqrt((al * r_perp) ** 2 + (w ** 2 * r_perp) ** 2)                  # path acceleration at the object
    else:
        raise ValueError(f"unbekannte Bewegung {art}")
    for asset, pos, vel in bodies:
        m = asset.root_physx_view.get_masses().to(dev)[..., None]                        # (N, B, 1)
        f = (m * per_body(pos, vel)).contiguous()
        asset.permanent_wrench_composer.set_forces_and_torques(forces=f, torques=torch.zeros_like(f), is_global=True)
    return amag
