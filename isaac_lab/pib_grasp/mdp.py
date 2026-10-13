"""
mdp.py — Eigene MDP-Terme der pib-Greifaufgabe (zusätzlich zu isaaclab.envs.mdp).

Aufbau nach Isaac Labs Dexsuite (manipulation/dexsuite/mdp), angepasst an die pib-Hand:
Fingerspitzen-Kräfte in fester Reihenfolge (wie die echten FSR), "Tisch absenken" als
Erfolgstest statt Zielpose-Kommando.
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

# Feste FSR-Reihenfolge (auch für die Firmware): Daumen, Zeige, Mittel, Ring, klein.
# Link-Namen aus pib_hand_left_urdf_v5/robot.urdf (finger_tip = Zeige, _2 = Mittel,
# _3 = Ring, _4 = klein). Der ContactSensor liefert sie in anderer Reihenfolge.
FINGERTIP_LINKS = ["urdf_thumb_tip", "urdf_finger_tip", "urdf_finger_tip_2", "urdf_finger_tip_3", "urdf_finger_tip_4"]
# Ein ContactSensor je Fingerspitze (wie Dexsuite): Isaac Labs Objekt-Filter funktioniert
# nur, wenn ein Sensor genau einen Prim abdeckt (ContactSensorCfg.filter_prim_paths_expr).
FINGERTIP_SENSORS = ["fsr_thumb", "fsr_index", "fsr_middle", "fsr_ring", "fsr_pinky"]


def _sensors(env: ManagerBasedRLEnv) -> list[ContactSensor]:
    return [env.scene.sensors[name] for name in FINGERTIP_SENSORS]


def episode_time(env: ManagerBasedRLEnv) -> torch.Tensor:
    return env.episode_length_buf * env.step_dt


# ── Aktion ────────────────────────────────────────────────────────────────────

class FilteredRelativeJointPositionAction(RelativeJointPositionAction):
    """Relative Gelenkposition wie Dexsuite, die Aktion vorher mit einem gleitenden Mittelwert geglättet (EXP-024):
    a_f ← α·a + (1 − α)·a_f, Sollwert = q + Skala·a_f. Vorbild Isaac Lab ShadowHand-OpenAI (act_moving_average = 0.3,
    DeXtreme-Linie) — dort auf den Gelenk-Sollwerten, hier auf der relativen Aktion, weil der Sollwert jeden Schritt aus
    der aktuellen Stellung neu entsteht. Die Firmware muss denselben Filter (gleiches α, 60 Hz) vor die Servos setzen.
    filtered_actions = das, was die Servos tatsächlich bekommen (Kennzahl „Unruhe wirksam“)."""

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


# ── Beobachtungen ─────────────────────────────────────────────────────────────

def fingertip_forces(env: ManagerBasedRLEnv) -> torch.Tensor:
    """Betrag der Gesamtkontaktkraft je Fingerspitze [N], FSR-Reihenfolge. Alle Kontakte
    (auch Finger-Finger), wie ein echter FSR. Clip über ObsTerm(clip=...)."""
    return torch.stack([s.data.net_forces_w[:, 0].norm(dim=-1) for s in _sensors(env)], dim=-1)


def fingertip_object_forces(env: ManagerBasedRLEnv) -> torch.Tensor:
    """Kontaktkraft je Fingerspitze nur mit dem Objekt [N] (privilegiert, Critic/Reward)."""
    # force_matrix_w: (N, Körper=1, Filter=1, 3)
    return torch.stack([s.data.force_matrix_w[:, 0, 0].norm(dim=-1) for s in _sensors(env)], dim=-1)


def object_pos_in_root(env: ManagerBasedRLEnv, robot_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
                       object_cfg: SceneEntityCfg = SceneEntityCfg("object")) -> torch.Tensor:
    from isaaclab.utils.math import quat_apply_inverse
    robot: Articulation = env.scene[robot_cfg.name]
    obj: RigidObject = env.scene[object_cfg.name]
    return quat_apply_inverse(robot.data.root_quat_w, obj.data.root_pos_w - robot.data.root_pos_w)


def object_quat_in_root(env: ManagerBasedRLEnv, robot_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
                        object_cfg: SceneEntityCfg = SceneEntityCfg("object")) -> torch.Tensor:
    """Objektorientierung (w, x, y, z) im Hand-Root-Frame (Dexsuite: object_quat_b), privilegiert."""
    from isaaclab.utils.math import quat_inv, quat_mul
    robot: Articulation = env.scene[robot_cfg.name]
    obj: RigidObject = env.scene[object_cfg.name]
    return quat_mul(quat_inv(robot.data.root_quat_w), obj.data.root_quat_w)


def object_tilt(env: ManagerBasedRLEnv, object_cfg: SceneEntityCfg = SceneEntityCfg("object")) -> torch.Tensor:
    """Kippwinkel [rad] zwischen Objekt-z-Achse (Zylinderachse) und Welt-z."""
    from isaaclab.utils.math import quat_apply
    obj: RigidObject = env.scene[object_cfg.name]
    z = torch.zeros_like(obj.data.root_pos_w)
    z[:, 2] = 1.0
    return torch.acos(quat_apply(obj.data.root_quat_w, z)[:, 2].clamp(-1.0, 1.0))


def object_lin_vel(env: ManagerBasedRLEnv, object_cfg: SceneEntityCfg = SceneEntityCfg("object")) -> torch.Tensor:
    obj: RigidObject = env.scene[object_cfg.name]
    return obj.data.root_lin_vel_w


def object_properties(env: ManagerBasedRLEnv, object_cfg: SceneEntityCfg = SceneEntityCfg("object")) -> torch.Tensor:
    """Privilegiert (nur Critic, EXP-021; wie HORA und Dexsuite, deren Critic Masse/Reibung/Form kennt): halbe Tiefe,
    halbe Breite, Höhe [m] (Bounding Box inkl. Zufallsgröße), Masse [kg], Haft- und Gleitreibung. Beim ersten Aufruf
    nach den Startup-Events gelesen (ändern sich danach nicht); davor Nullen (Formbestimmung des Observation-Managers)."""
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
    """Episodenzeit relativ zum Tisch-Absenken (privilegiert, nur Critic)."""
    return (episode_time(env) - drop_start_s).unsqueeze(-1)


# ── Events ────────────────────────────────────────────────────────────────────

def lower_table(env: ManagerBasedRLEnv, env_ids: torch.Tensor, drop_start_s: float, drop_speed: float,
                drop_depth: float, table_cfg: SceneEntityCfg = SceneEntityCfg("table")) -> None:
    """Kinematischen Tisch ab drop_start_s mit drop_speed [m/s] um drop_depth [m] absenken.
    Physikalisch gleichwertig zum Anheben der Hand (später: der Arm hebt), ohne die
    feste Basis der Artikulation zu bewegen."""
    table: RigidObject = env.scene[table_cfg.name]
    t = episode_time(env)[env_ids]
    dz = ((t - drop_start_s) * drop_speed).clamp(0.0, drop_depth)
    pose = table.data.default_root_state[env_ids, :7].clone()
    pose[:, :3] += env.scene.env_origins[env_ids]
    pose[:, 2] -= dz
    table.write_root_pose_to_sim(pose, env_ids=env_ids)


# Mimic-Kopplung der linken Hand (ADR-011, isaac_sim/setup_stage.py → MIMIC_JOINTS):
# Folgegelenk -> Referenz, gearing -1 = gleicher Winkel. Reihenfolge: PIP vor DIP.
MIMIC_LEFT = [(f"{f}_left_distal", f"{f}_left_proximal") for f in ("index", "middle", "ring", "pinky")] + \
             [(f"{f}_left_tip", f"{f}_left_distal") for f in ("index", "middle", "ring", "pinky")] + \
             [("thumb_left_tip", "thumb_left_proximal")]


def reset_hand_joints(env: ManagerBasedRLEnv, env_ids: torch.Tensor, ranges_deg: dict[str, tuple[float, float]],
                      asset_cfg: SceneEntityCfg = SceneEntityCfg("robot")) -> None:
    """Servo-Gelenke beim Reset gleichverteilt in ranges_deg setzen (Dexsuite: reset_joints_by_offset),
    Folgegelenke passend zur Mimic-Kopplung — sonst startet die Zwangsbedingung mit einem Sprung.
    Sollwerte = Startstellung, damit die Antriebe nicht zurückziehen."""
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
    """Startup: Startlage je Umgebung aus der Bounding Box des gespawnten Objekts (USD, inkl. zufälliger Größe) —
    Oberfläche palm_gap vor der Handfläche, Boden lift über der Tischplatte. root_height: gemessene Ruhelage
    (Höhe des Ursprungs über der Tischplatte, tools/ruhelage_objekt.py) statt Bounding Box + lift."""
    import re
    import isaaclab.sim as sim_utils
    from pxr import Usd, UsdGeom
    obj: RigidObject = env.scene[object_cfg.name]
    cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(), [UsdGeom.Tokens.default_])
    stage = env.scene.stage
    # Grundriss je Umgebung für reset_object_gap_aware (halbe Tiefe/Breite, eckig 1 / rund 0) und Höhe [m]
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
    """Höhe der tiefsten Fingerspitze über dem Tisch [m] für ein Objekt unter der Hand „von oben“ — Regel aus der
    Startpose-Suche (docs/startpose-oben/ergebnis.md, 48 Episoden je Höhe nachgeprüft: Kugel Ø 5/7/9 → 10/15/30 mm, Dose
    10 cm → 60 mm, Schachtel 4 cm → 10–15 mm): Kugeln max(min, Ø − sphere_offset), sonst max(min, Höhe − block_offset).
    kind: kugel, zylinder oder quader; size = Bounding Box (x, y, z)."""
    if kind == "kugel":
        return max(min_tip_height, size[2] - sphere_offset)
    return max(min_tip_height, size[2] - block_offset)


def place_objects_from_above(env: ManagerBasedRLEnv, env_ids: torch.Tensor | None, center_xy: tuple[float, float],
                             tip_low_z: float, sphere_offset: float, block_offset: float, min_tip_height: float,
                             height_jitter: float, table_thickness: float, lift: float = 0.0,
                             object_cfg: SceneEntityCfg = SceneEntityCfg("object"),
                             table_cfg: SceneEntityCfg = SceneEntityCfg("table")) -> None:
    """Startup, Greifart „von oben“ (env_cfg_oben, Pose aus der Startpose-Suche): je Umgebung aus Bounding Box und Form des
    gespawnten Objekts (inkl. Zufallsgröße) die Höhe der tiefsten Fingerspitze über dem Tisch (tip_height_for_object), dazu
    eine feste Streuung je Umgebung ±height_jitter (ungenaue Vorgreifpose); Objekt in der Greifmitte center_xy auf dem
    Tisch, Tischplatte = tip_low_z − Höhe (− lift: YCB fällt kurz auf den Tisch). Die Hand ist fest — Objekt und Tisch
    werden gesetzt; lower_table und reset_scene_to_default nutzen die geänderte Standardlage. Höhe je Umgebung in
    env.pib_tip_height (Diagnose). Grundriss für reset_object_gap_aware ohne Eckkorrektur (eckig = 0)."""
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
        obj.data.default_root_state[idx, 2] = top + lift + size[2] / 2  # Ursprung = Boxmitte (auch YCB)
        table.data.default_root_state[idx, 0] = center_xy[0]
        table.data.default_root_state[idx, 1] = center_xy[1]
        table.data.default_root_state[idx, 2] = top - table_thickness / 2


def reset_object_gap_aware(env: ManagerBasedRLEnv, env_ids: torch.Tensor, pose_range: dict[str, tuple[float, float]],
                           velocity_range: dict[str, tuple[float, float]],
                           asset_cfg: SceneEntityCfg = SceneEntityCfg("object")) -> None:
    """Wie Isaac Labs reset_root_state_uniform, aber der Abstand zur Handfläche gilt nach der Gierdrehung: ein eckiges
    Objekt wird um a·|cos θ| + b·|sin θ| − a von der Hand weggerückt (a, b = halbe Tiefe/Breite), damit seine nächste
    Ecke so weit vor der Handfläche liegt wie die Vorderfläche ohne Drehung — wie ein Greifplaner die Vorgreifpose
    setzen würde. Runde Objekte unverändert. Ohne Grundriss (place_objects_by_size) wie das Original.
    Vorher berührte die Ecke eines um 10–15° gedrehten Quaders beim Reset die Finger (tools/analyse_reset.py)."""
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
        positions[:, 0] -= square * (a * yaw.cos().abs() + b * yaw.sin().abs() - a)   # Objekt liegt bei −x der Hand
    orientations = math_utils.quat_mul(root_states[:, 3:7],
                                       math_utils.quat_from_euler_xyz(rand[:, 3], rand[:, 4], rand[:, 5]))
    vranges = torch.tensor([velocity_range.get(k, (0.0, 0.0)) for k in ("x", "y", "z", "roll", "pitch", "yaw")],
                           device=asset.device)
    velocities = root_states[:, 7:13] + math_utils.sample_uniform(vranges[:, 0], vranges[:, 1], (len(env_ids), 6),
                                                                  device=asset.device)
    asset.write_root_pose_to_sim(torch.cat([positions, orientations], dim=-1), env_ids=env_ids)
    asset.write_root_velocity_to_sim(velocities, env_ids=env_ids)


class GraspDifficultyScheduler(ManagerTermBase):
    """Curriculum wie Dexsuites DifficultyScheduler (adr_curriculum.py), mit unserem Erfolgskriterium statt des
    Zielkommandos: je Umgebung Schwierigkeit +1 nach einer erfolgreichen Episode (bis zum Zeitende gehalten,
    Kippwinkel ≤ max_kipp_deg), sonst −1; difficulty_frac = Mittel / max_difficulty steuert über
    initial_final_interpolate_fn Schwerkraft und Beobachtungsrauschen (EXP-017)."""

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
        # Tensor wie bei Dexsuite: initial_final_interpolate_fn ruft .item() auf den interpolierten Werten auf
        self.difficulty_frac = self.current.mean() / max(max_difficulty, 1)
        return self.difficulty_frac


# ── Belohnungen ───────────────────────────────────────────────────────────────

def fingertips_to_object(env: ManagerBasedRLEnv, std: float,
                         robot_cfg: SceneEntityCfg = SceneEntityCfg("robot", body_names=FINGERTIP_LINKS),
                         object_cfg: SceneEntityCfg = SceneEntityCfg("object")) -> torch.Tensor:
    """Annäherung: 1 − tanh(größter Abstand Fingerspitze↔Objekt / std) (Dexsuite: object_ee_distance)."""
    robot: Articulation = env.scene[robot_cfg.name]
    obj: RigidObject = env.scene[object_cfg.name]
    tips = robot.data.body_pos_w[:, robot_cfg.body_ids]
    dist = torch.norm(tips - obj.data.root_pos_w[:, None, :], dim=-1).max(dim=-1).values
    return 1.0 - torch.tanh(dist / std)


class FingertipProgress(ManagerTermBase):
    """Annäherung wie NVIDIA AllegroKuka/DexPBT (IsaacGymEnvs allegro_kuka_base.py; Petrenko et al. 2023): je
    Fingerspitze nur der Fortschritt zur Objektmitte, Σ max(kleinster bisheriger Abstand − aktueller, 0) — bloßes
    Nahesein bringt nichts (nicht ausnutzbar), dass die Spitzen die Mitte hoher Objekte nie erreichen, stört nicht.
    Nur in der Greifphase (vor dem Absenken; AllegroKuka: bis das Objekt angehoben ist). EXP-019, ersetzt
    fingertips_to_object (maß alle Handkörper, für 3–4 cm Fingerweg ohnehin zu flach — ADR-022)."""

    def __init__(self, cfg, env: ManagerBasedRLEnv):
        super().__init__(cfg, env)
        self.robot: Articulation = env.scene["robot"]
        self.obj: RigidObject = env.scene["object"]
        self.tip_ids = [self.robot.body_names.index(n) for n in FINGERTIP_LINKS]
        self.closest = torch.full((env.num_envs, len(self.tip_ids)), -1.0, device=env.device)   # −1: neu setzen

    def reset(self, env_ids=None):
        self.closest[slice(None) if env_ids is None else env_ids] = -1.0

    def __call__(self, env: ManagerBasedRLEnv, drop_start_s: float, max_delta: float = 0.05) -> torch.Tensor:
        d = torch.norm(self.robot.data.body_pos_w[:, self.tip_ids] - self.obj.data.root_pos_w[:, None, :], dim=-1)
        self.closest = torch.where(self.closest < 0, d, self.closest)
        delta = (self.closest - d).clamp(0.0, max_delta)          # AllegroKuka: clip(…, 0, 10)
        self.closest = torch.minimum(self.closest, d)
        return delta.sum(dim=-1) * (episode_time(env) < drop_start_s).float()


def thumb_opposition_contact(env: ManagerBasedRLEnv, threshold: float) -> torch.Tensor:
    """1, wenn Daumen und mindestens ein Finger das Objekt berühren (Dexsuite: contacts)."""
    f = fingertip_object_forces(env)
    return ((f[:, 0] > threshold) & (f[:, 1:] > threshold).any(dim=-1)).float()


def object_sink(env: ManagerBasedRLEnv, drop_start_s: float,
                object_cfg: SceneEntityCfg = SceneEntityCfg("object")) -> torch.Tensor:
    """Absinken [m] gegenüber der Höhe beim Beginn des Absenkens (bis dahin mitgeführt, danach
    eingefroren). Nicht gegen die Standardhöhe: mit ±10 % Größe steht die Dose bis 7,5 mm tiefer."""
    obj: RigidObject = env.scene[object_cfg.name]
    z = obj.data.root_pos_w[:, 2]
    if getattr(env, "_pib_z_ref", None) is None or env._pib_z_ref.shape != z.shape:
        env._pib_z_ref = z.clone()
    before = episode_time(env) < drop_start_s
    env._pib_z_ref[before] = z[before]
    return (env._pib_z_ref - z).clamp(min=0.0)


def fingers_in_contact(env: ManagerBasedRLEnv, threshold: float) -> torch.Tensor:
    """Anteil der vier Finger mit Objektkontakt, nur bei Daumenkontakt: (Finger > threshold) / 4 ·
    𝟙[Daumen > threshold] ∈ [0, 1]. Belohnt Kraftgriff statt Pinzettengriff (EXP-005)."""
    f = fingertip_object_forces(env)
    return (f[:, 1:] > threshold).float().mean(dim=-1) * (f[:, 0] > threshold).float()


def object_held(env: ManagerBasedRLEnv, drop_start_s: float, std: float,
                object_cfg: SceneEntityCfg = SceneEntityCfg("object")) -> torch.Tensor:
    """Ab dem Tisch-Absenken: 1 − tanh(Absinken des Objekts / std). Vorher 0 — solange das
    Objekt auf dem Tisch steht, gibt es nichts zu verdienen."""
    active = (episode_time(env) >= drop_start_s).float()
    return active * (1.0 - torch.tanh(object_sink(env, drop_start_s, object_cfg) / std))


def held_in_grasp(env: ManagerBasedRLEnv, drop_start_s: float, std: float, threshold: float) -> torch.Tensor:
    """Dicht, ab dem Absenken: Halten × Gegengriff (Dexsuite position_command_error_tanh, × contacts)."""
    return object_held(env, drop_start_s, std) * thumb_opposition_contact(env, threshold)


def upright_in_grasp(env: ManagerBasedRLEnv, drop_start_s: float, rot_std: float, threshold: float) -> torch.Tensor:
    """Dicht, ab dem Absenken: (1 − tanh(Kippwinkel/rot_std)) × Gegengriff (Dexsuite
    orientation_command_error_tanh, × contacts). Erst ab dem Absenken — auf dem Tisch steht die
    Dose von selbst aufrecht, sonst gäbe es die Belohnung fürs bloße Antippen."""
    active = (episode_time(env) >= drop_start_s).float()
    return active * (1.0 - torch.tanh(object_tilt(env) / rot_std)) * thumb_opposition_contact(env, threshold)


def object_held_upright(env: ManagerBasedRLEnv, drop_start_s: float, std: float, rot_std: float,
                        object_cfg: SceneEntityCfg = SceneEntityCfg("object")) -> torch.Tensor:
    """Halten × aufrecht (Dexsuite success_reward: (1 − tanh(Fehler/pos_std))·(1 − tanh(Winkel/rot_std))).
    Gekippt halten bringt fast nichts, ohne die Episode abzubrechen — das Greifen bleibt erkundbar."""
    return object_held(env, drop_start_s, std, object_cfg) * (1.0 - torch.tanh(object_tilt(env, object_cfg) / rot_std))


def object_upright(env: ManagerBasedRLEnv, drop_start_s: float, std: float) -> torch.Tensor:
    """Ab dem Tisch-Absenken: 1 − tanh(Kippwinkel / std). Vorher 0 — auf dem Tisch steht die
    Dose ohnehin aufrecht, die Belohnung gäbe es dort ohne Zutun."""
    active = (episode_time(env) >= drop_start_s).float()
    return active * (1.0 - torch.tanh(object_tilt(env) / std))


# ── Positionsterme wie Dexsuite (EXP-012): Ziel = Startposition des Objekts ────────────────

def object_start_distance(env: ManagerBasedRLEnv, ref_s: float,
                          object_cfg: SceneEntityCfg = SceneEntityCfg("object")) -> torch.Tensor:
    """3D-Abstand [m] des Objekts zu seiner Startposition (bis ref_s mitgeführt, dann eingefroren: Objekt
    abgesetzt, Größe eingeschwungen). Gegenstück zu Dexsuites Zielposition (Kommando relativ zur
    Roboterbasis): die Hand ist fest, das Objekt soll bleiben, wo der Arm es gegriffen hat."""
    obj: RigidObject = env.scene[object_cfg.name]
    pos = obj.data.root_pos_w
    if getattr(env, "_pib_start_pos", None) is None or env._pib_start_pos.shape != pos.shape:
        env._pib_start_pos = pos.clone()
    before = episode_time(env) < ref_s
    env._pib_start_pos[before] = pos[before]
    return torch.norm(pos - env._pib_start_pos, dim=-1)


def position_tracking_start(env: ManagerBasedRLEnv, drop_start_s: float, std: float, threshold: float,
                            ref_s: float) -> torch.Tensor:
    """Dexsuite position_command_error_tanh: (1 − tanh(‖p − p_Ziel‖/std)) × Gegengriff, ab dem Absenken."""
    active = (episode_time(env) >= drop_start_s).float()
    return active * (1.0 - torch.tanh(object_start_distance(env, ref_s) / std)) * thumb_opposition_contact(env, threshold)


def success_start(env: ManagerBasedRLEnv, drop_start_s: float, pos_std: float, rot_std: float,
                  ref_s: float) -> torch.Tensor:
    """Dexsuite success_reward: (1 − tanh(‖p − p_Ziel‖/pos_std)) · (1 − tanh(Kippwinkel/rot_std)), ab dem
    Absenken. Orientierung als Kippwinkel (Anforderung aufrecht, kein Gierziel)."""
    active = (episode_time(env) >= drop_start_s).float()
    return (active * (1.0 - torch.tanh(object_start_distance(env, ref_s) / pos_std))
            * (1.0 - torch.tanh(object_tilt(env) / rot_std)))


def object_xy_displacement(env: ManagerBasedRLEnv, ref_s: float, max_dist: float = 0.2,
                           object_cfg: SceneEntityCfg = SceneEntityCfg("object")) -> torch.Tensor:
    """Verschiebung [m] der Objektmitte in der Tischebene ggü. der Startlage (bis ref_s mitgeführt, dann
    eingefroren), gekappt bei max_dist. Als Strafe über die ganze Episode wie Cross-Embodiment Dexterous Grasping
    (Yuan et al. 2024: r = −0,3·‖xy − xy_Start‖); z bleibt beim Halteterm. EXP-023: die Policies zogen das Objekt
    ~13 cm Richtung Unterarm (tools/diag_objektweg.py), nichts in der Belohnung hielt die Lage in der Tischebene."""
    obj: RigidObject = env.scene[object_cfg.name]
    xy = obj.data.root_pos_w[:, :2]
    if getattr(env, "_pib_start_xy", None) is None or env._pib_start_xy.shape != xy.shape:
        env._pib_start_xy = xy.clone()
    before = episode_time(env) < ref_s
    env._pib_start_xy[before] = xy[before]
    return torch.norm(xy - env._pib_start_xy, dim=-1).clamp(max=max_dist)


def servo_torque_l2(env: ManagerBasedRLEnv, asset_cfg: SceneEntityCfg) -> torch.Tensor:
    """Σ (Moment / Stall-Moment)² der Servos in asset_cfg (EXP-025): 0 = kraftlos, ≈ Zahl der Servos bei Dauer-Stall.
    Wie die Moment-Strafe von HORA (Qi et al. 2022) und Isaac Labs joint_torques_l2, aber je Gelenk auf das Stall-Moment
    normiert (Servos verschieden stark). applied_torque = PD-Moment nach Begrenzung — dieselbe Größe wie die Leitplanke
    Stall-Anteil (eval_policy). Gelenke nur über params (SceneEntityCfg wird nur dort aufgelöst, ADR-017)."""
    robot: Articulation = env.scene[asset_cfg.name]
    tau = robot.data.applied_torque[:, asset_cfg.joint_ids] / robot.data.joint_effort_limits[:, asset_cfg.joint_ids]
    return torch.sum(torch.square(tau), dim=1)


def servo_effort_limit(robot: Articulation, ids: list) -> torch.Tensor:
    """Stall-Moment je Gelenk in `ids` (N, len(ids)) am Gelenk. Gestängegetriebene Gelenke (Handgelenk-Pleuel,
    RemotizedPDActuator, ADR-014): winkelabhängig 2,94 Nm × Übersetzung n(θ) aus der Tabelle des Aktuators — dort steht
    joint_effort_limits auf Isaac Labs Standard 1e9 (explizite Aktuatoren), |τ|/Grenze wäre immer ≈ 0. So ist |τ|/Grenze
    für alle Servos dieselbe Größe: Moment am Servo / Stall-Moment."""
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
    """Stall je Servo (N, len(ids)) als bool: |τ| ≥ fraction · Stall-Moment (PD-Schätzung applied_torque, Grenze aus
    servo_effort_limit). Wie am echten Servo (Nachtlauf 2026-10-14): `firmware_limits` = kein Stall ≤ limit_tol_deg vor
    der Gelenkgrenze in Momentrichtung (die Firmware kappt das Ziel, der Servo drückt nicht gegen den Anschlag).
    `tendon` (bool je Servo, optional) = nur τ > 0 zählt (Sehne zieht nur) — im Training bewusst nicht genutzt: die Sim
    kann Finger aktiv öffnen, real nur die Feder; ohne Kosten würde die Policy diese Kraft frei nutzen.
    Gemeinsam für StallLagrange (Training) und eval_policy (Kennzahl „Servo-Last real“)."""
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
    """Grenze auf den Servo-Stall per PID-Lagrange (Nachtlauf 2026-10-13, EXP-035 ff.; Ray, Achiam & Amodei 2019, Safety
    Gym; Stooke, Achiam & Abbeel 2020, PID Lagrangian). Kosten c_t = Anteil der Servos in `joint_names` mit
    |τ| ≥ `fraction` · Stall-Moment (dieselbe Größe wie applied_torque in eval_policy). Ziel J_c = Mittel von c_t ≤ `limit`.
    Der Term liefert λ · c_t (Gewicht im RewTerm −1 → Strafe −λ · c_t je s); λ ≥ 0 regelt sich einmal je Rollout
    (`steps_per_update` Aufrufe = num_steps_per_env) nach Stooke 2020, Algorithmus 2:
        e = J_c − d,  I ← max(0, I + K_I·e),  λ = max(0, K_P·e + I + K_D·max(0, J_c − J_c,vorher))
    J_c = Mittel von c_t über den Rollout (alle Umgebungen), für P- und D-Anteil zusätzlich geglättet (EMA α).
    Vereinfachung ggü. Safety Gym: kein eigener Kosten-Critic, die Strafe steht in der Belohnung (wie Lagrange-PPO
    mit gemeinsamem Vorteil). λ, J_c und I gehen über extras["log"] ins TensorBoard (Lagrange/…).

    Nachtlauf 2026-10-14 (EXP-038 ff., docs/nachtlauf-2026-10-14.md), Stall wie am echten Servo (servo_stall):
    - Handgelenk mit winkelabhängigem Stall-Moment (Pleuel) — `joint_names` dann alle 8 Servos.
    - `firmware_limits`: kein Stall ≤ `limit_tol_deg` vor der Gelenkgrenze in Momentrichtung (die Firmware kappt das Ziel
      auf die Grenze, der Servo drückt nicht gegen den Anschlag).
    - `tendon_joints` (optional): nur Zug zählt — siehe servo_stall, warum nicht genutzt.
    - `per_joint`: ein λ je Servo (CaT, Chane-Sane et al. 2024: Grenze je Gelenk), jeder Servo J_c,i ≤ `limit`;
      Strafe (1/n)·Σ λ_i·c_i (gleiche Größenordnung wie mit einem λ)."""

    def __init__(self, cfg, env: ManagerBasedRLEnv):
        super().__init__(cfg, env)
        p = cfg.params
        self.robot: Articulation = env.scene["robot"]
        self.names = list(p["joint_names"])
        self.ids, _ = self.robot.find_joints(self.names, preserve_order=True)
        tendon = set(p.get("tendon_joints") or [])
        self.tendon = torch.tensor([n in tendon for n in self.names], dtype=torch.bool, device=env.device)
        n = len(self.ids) if p.get("per_joint", False) else 1
        # Reglerzustand auf der CPU (Logging in reset() ohne GPU-Synchronisierung), λ zusätzlich auf dem Gerät
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
    """Servo-Last wie der „Present Load“ des ST3215 (EXP-037): |τ| / Stall-Moment je Servo in `joint_names`
    (Reihenfolge = Aktionsraum), auf [0; 1,5] begrenzt. Reale Größe — die Firmware müsste sie mitlesen."""
    robot: Articulation = env.scene["robot"]
    key = tuple(joint_names)
    if key not in _SERVO_LOAD_IDS:
        _SERVO_LOAD_IDS[key] = robot.find_joints(joint_names, preserve_order=True)[0]
    ids = _SERVO_LOAD_IDS[key]
    return (robot.data.applied_torque[:, ids].abs() / robot.data.joint_effort_limits[:, ids]).clamp(0.0, 1.5)


def excess_fingertip_force(env: ManagerBasedRLEnv, limit: float) -> torch.Tensor:
    """Summe der Kraft über `limit` [N] an allen Fingerspitzen (gegen Zerquetschen und
    unrealistisch hohe Kräfte, ADR-011: lineare Kopplung überschätzt die Spitzenkraft)."""
    return (fingertip_forces(env) - limit).clamp(min=0.0).sum(dim=-1)


# ── Abbruch ───────────────────────────────────────────────────────────────────

def object_dropped(env: ManagerBasedRLEnv, max_sink: float,
                   object_cfg: SceneEntityCfg = SceneEntityCfg("object")) -> torch.Tensor:
    obj: RigidObject = env.scene[object_cfg.name]
    z0 = obj.data.default_root_state[:, 2] + env.scene.env_origins[:, 2]
    return (z0 - obj.data.root_pos_w[:, 2]) > max_sink


def object_tilted(env: ManagerBasedRLEnv, max_tilt_deg: float) -> torch.Tensor:
    """Abbruch, wenn das Objekt mehr als max_tilt_deg kippt (Muster: Isaac Lab
    deploy/gear_assembly, reset_when_gear_orientation_exceeds_threshold)."""
    import math
    return object_tilt(env) > math.radians(max_tilt_deg)


def abnormal_robot_state(env: ManagerBasedRLEnv, asset_cfg: SceneEntityCfg = SceneEntityCfg("robot")) -> torch.Tensor:
    """Gelenkgeschwindigkeit > 2× Limit — instabile Physik (Dexsuite: abnormal_robot_state)."""
    robot: Articulation = env.scene[asset_cfg.name]
    return (robot.data.joint_vel.abs() > (robot.data.joint_vel_limits * 2)).any(dim=1)


# ── Armbewegung (Belastungstest, 2026-10-12) ──────────────────────────────────
# Die Hand ist fest montiert. Eine Bewegung des ganzen Arms ist im Bezugssystem der Hand gleichwertig zu Scheinkräften
# auf jeden Körper (Objekt und Handglieder, im Schwerpunkt):
#   F = m·[−a_P + (Rᵀg − g) − α×r − ω×(ω×r) − 2·ω×v]
# a_P = Beschleunigung des Drehpunkts, R = Drehung der Hand seit Bewegungsbeginn (Schwerkraft dreht relativ zur Hand),
# ω/α um eine feste Achse n, r = Schwerpunkt − Drehpunkt, v = Geschwindigkeit im Handrahmen (Coriolis). Für reine
# Translation exakt −m·a (Äquivalenzprinzip; DexGraspNet prüft Griffe genauso mit gedrehter Schwerkraft). Momente aus dem
# ungleichmäßigen Feld vernachlässigt. Profile: Minimum-Jerk (Flash & Hogan 1985), Rampe bis zum Versagen (Grasp to Act
# 2026, SoGraB), Drehen ±45° wie GRASPA. Drehpunkt = Hand-Root (Ellbogen, `elbow_lower`); Gieren um die senkrechte Achse
# (Oberarm hängt senkrecht), Nicken um die waagrechte Achse quer zum Unterarm (Unterarm/Hand zeigen nach −y).

BEWEGUNG_START_S = 2.6          # Haltephase ab 2,5 s (Tisch unten), Episode 4,5 s
RAMPE_S = 1.8                   # Rampe 0 → a_max bis kurz vor Episodenende
TRANSPORT_M = 0.3               # Strecke der Transportbewegung
DREH_RAD = 0.7853981633974483   # 45° (GRASPA)
_ACHSEN6 = ((1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1))
BEWEGUNG_RICHTUNGEN = {"rampe": ("+x", "−x", "+y", "−y", "+z", "−z"), "transport": ("+x", "−x", "+y", "−y", "+z", "−z"),
                       "gieren": ("+", "−"), "nicken": ("+", "−")}


def min_jerk(t: torch.Tensor, T: float):
    """Minimum-Jerk-Profil auf Strecke 1: Weg s, Geschwindigkeit ṡ, Beschleunigung s̈ (0 vor dem Start, konstant 1 danach).
    Spitzenbeschleunigung 10/√3/T² ≈ 5,77/T²."""
    x = (t / T).clamp(0.0, 1.0)
    s = x ** 3 * (10 - 15 * x + 6 * x ** 2)
    sd = 30 * x ** 2 * (1 - x) ** 2 / T
    sdd = 60 * x * (1 - x) * (1 - 2 * x) / T ** 2
    return s, sd, sdd


def transport_dauer(a_max: float, strecke: float = TRANSPORT_M) -> float:
    """Dauer T der Minimum-Jerk-Bewegung über `strecke` mit Spitzenbeschleunigung a_max."""
    return (10 / 3 ** 0.5 * strecke / a_max) ** 0.5


def _rotate(v: torch.Tensor, n: torch.Tensor, phi: torch.Tensor) -> torch.Tensor:
    """Rodrigues: v (…, 3) um die Einheitsachse n (3,) um phi (…, 1) drehen."""
    c, s = torch.cos(phi), torch.sin(phi)
    n = n.expand_as(v)
    return v * c + torch.cross(n, v, dim=-1) * s + n * (n * v).sum(-1, keepdim=True) * (1 - c)


def apply_arm_motion(env: ManagerBasedRLEnv, art: str, param: float, t: torch.Tensor,
                     start_s: float = BEWEGUNG_START_S) -> torch.Tensor:
    """Scheinkräfte einer Armbewegung auf Objekt und Hand setzen (bleiben bis zum nächsten Aufruf gesetzt).
    art: rampe (param = a_max [m/s²], linear in RAMPE_S), transport (param = a_max, Minimum-Jerk über TRANSPORT_M),
    gieren/nicken (param = Dauer T [s] für 45°). Richtung je Umgebung `env_id % len(Richtungen)`, t = Episodenzeit zu
    Beginn des Schritts.
    Gibt den Betrag der Beschleunigung des Drehpunkts bzw. ω²·r am Objekt [m/s²] je Umgebung zurück (Grenzwert)."""
    robot: Articulation = env.scene["robot"]
    obj: RigidObject = env.scene["object"]
    dev, N = env.device, env.num_envs
    k = torch.arange(N, device=dev) % len(BEWEGUNG_RICHTUNGEN[art])
    tau = t + env.step_dt / 2 - start_s           # in der Mitte des Policy-Schritts (Kraft je Schritt konstant)
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
        amag = torch.sqrt((al * r_perp) ** 2 + (w ** 2 * r_perp) ** 2)                  # Bahnbeschleunigung am Objekt
    else:
        raise ValueError(f"unbekannte Bewegung {art}")
    for asset, pos, vel in bodies:
        m = asset.root_physx_view.get_masses().to(dev)[..., None]                        # (N, B, 1)
        f = (m * per_body(pos, vel)).contiguous()
        asset.permanent_wrench_composer.set_forces_and_torques(forces=f, torques=torch.zeros_like(f), is_global=True)
    return amag
