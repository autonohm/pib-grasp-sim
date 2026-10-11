"""
env_cfg_oben.py — Greifart „von oben“ (Stufe 4b, ADR-018, Plan: docs/plan-griff-von-oben.md).

Startpose aus der parallelen Suche (tools/suche_startpose_oben.py, docs/startpose-oben/ergebnis.md, 2026-10-11; Vorbild
Greifplaner „vorschlagen → schließen → bewerten“): Hand von oben, **20° um x gekippt** (Finger leicht nach unten), nicht
gerollt, **Daumen-Rotator beim Start 75°**, Objekt in der Greifmitte zwischen Daumen- und Fingerspitzen. Die Höhe der
tiefsten Fingerspitze (der Daumen) über dem Tisch hängt vom Objekt ab (mdp.tip_height_for_object; Regel „alle schließen“
damit 90–100 % auf Kugel Ø 5/7/9, Dose, Schachtel und YCB-Suppe, 48 Episoden je Höhe). Im Training wird die Höhe je
Umgebung ±5 mm gestreut und die Lage ±1 cm (ungenaue Vorgreifpose des Arms).
Ablauf wie seitlich: 0–2 s greifen, 2–2,5 s senkt sich der Tisch um 10 cm (≙ Arm hebt an), danach halten.

Verworfen: waagrecht mit 3,5 cm Abstand (Daumen stieß gegen den Tisch, Kugel Ø 5/Schachtel ≤ 3/24) und 36,5° gekippt mit
gleich hohen Spitzen (Finger streiften beim Schließen den Tisch, 3–5/24) — Plan, Abschnitte „Gemessen“ und „Stand 2026-10-11“.

Belohnung = seitliches Rezept ohne Orientierungsterme, wie Dexsuite Lift (orientation_tracking = None, success ohne
rot_std): beim Heben zählt nur, dass das Objekt in der Hand bleibt. Bewertung ohne Kippanforderung (--max_kipp_deg -1).
"""
import math

import isaaclab.sim as sim_utils
from isaaclab.managers import EventTermCfg as EventTerm
from isaaclab.managers import RewardTermCfg as RewTerm
from isaaclab.utils import configclass

from . import mdp
from .env_cfg import (GRASP_TIME_S, HAND_POS, HOLD_STD_M, START_REF_S, XY_PENALTY_WEIGHT, YCB_SPAWN_LIFT,
                      PibGraspEnvCfg, RewardsProgressCfg, dexsuite_action_space, ycb_upright_usd)

# Pose und Geometrie (Mesh-Punkte der Fingerspitzen bei Rotator 75°, übrige Gelenke 0, logs/startpose_oben/geometrie.npz aus
# tools/probe_neigung_oben.py --dump), relativ zum Hand-Root nach der Drehung, in Weltachsen:
HAND_ROT_OBEN = (0.98481, 0.17365, 0.0, 0.0)                 # (w, x, y, z) = 20° um x
ROTATOR_START_DEG = 75.0
TIP_LOW_Z = HAND_POS[2] - 0.1914                             # tiefster Punkt aller fünf Spitzen (Daumen; Finger ≈ −0,150)
GRASP_XY = (HAND_POS[0] - 0.0203, HAND_POS[1] - 0.2870)      # Greifmitte: zwischen Daumenspitze und Mitte der Fingerspitzen
# Höhe der tiefsten Spitze über dem Tisch (Suche): Kugeln max(10 mm, Ø − 60 mm), sonst max(10 mm, Höhe − 40 mm)
SPHERE_OFFSET, BLOCK_OFFSET, MIN_TIP_HEIGHT = 0.060, 0.040, 0.010
TRAIN_HEIGHT_JITTER = 0.005          # Training: Höhe je Umgebung ±5 mm (Bewertung: 0; Störbedingung ±5 mm)
OBJECT_XY_RANGE = {"x": (-0.01, 0.01), "y": (-0.01, 0.01)}
# Tisch um die Greifmitte, je Umgebung in der Höhe an die Objektunterseite gesetzt (mdp.place_objects_from_above)
TABLE_SIZE_OBEN = (0.30, 0.30, 0.04)

# ── Objektkatalog von oben: rund, klein oder flach (ADR-018; seitlich braucht ≥ 15 cm Höhe) ─────────────────────────
# form, Maße [m] (Kugel: Radius; Zylinder: Radius, Höhe; Quader: x quer zu den Fingern, y längs, z), Gier beim Reset
OBJECTS_OBEN = {
    "kugel_d7": {"form": "kugel", "masse": (0.035,), "gier": (-math.pi, math.pi)},          # Apfel-Ersatz (Benchmark)
    "kugel_d5": {"form": "kugel", "masse": (0.025,), "gier": (-math.pi, math.pi)},          # Mandarine/Pflaume
    "kugel_d9": {"form": "kugel", "masse": (0.045,), "gier": (-math.pi, math.pi)},          # Orange/großer Apfel
    "dose_d68x10": {"form": "zylinder", "masse": (0.034, 0.10), "gier": (-math.pi, math.pi)},   # kurze Dose aufrecht
    "quader_9x6x4": {"form": "quader", "masse": (0.09, 0.06, 0.04),                          # flache Schachtel
                     "gier": (-math.radians(15), math.radians(15))},
    # Testobjekt (nie trainiert): YCB 005 Tomatensuppendose, 349 g, 6,8 × 10,2 cm, aufrecht (wie 003/004/006 über eine
    # Wrapper-USD; Oberseite des Assets zeigt nach −y → −90° um x). Ruhelage noch nicht gemessen → 3 mm Fallhöhe.
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
    """EXP-022-Rezept ohne Orientierung (Dexsuite Lift): kein upright, Erfolg = gehalten (ohne Kippfaktor)."""
    upright = None
    success = RewTerm(func=mdp.object_held, weight=10.0, params={"drop_start_s": GRASP_TIME_S, "std": HOLD_STD_M})


@configclass
class PibGraspEnvCfg_Oben(PibGraspEnvCfg):
    """Basisaufgabe „von oben“ (Bewertung je Objekt über apply_object_oben, Standard Kugel Ø 7 cm)."""
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
        # Startlage je Umgebung aus Bounding Box und Form (inkl. Zufallsgröße): Objekt in der Greifmitte, Tisch so hoch,
        # wie die Suche je Objekt ergab — ersetzt place_objects_by_size
        self.events.place_objects = EventTerm(
            func=mdp.place_objects_from_above, mode="startup",
            params={"center_xy": GRASP_XY, "tip_low_z": TIP_LOW_Z, "sphere_offset": SPHERE_OFFSET,
                    "block_offset": BLOCK_OFFSET, "min_tip_height": MIN_TIP_HEIGHT, "height_jitter": 0.0,
                    "table_thickness": TABLE_SIZE_OBEN[2], "lift": 0.0})
        # Vorgreifpose: Daumen-Rotator fest auf 75° (wie in der Suche), übrige Servos wie seitlich fast offen
        self.events.reset_hand.params["ranges_deg"]["thumb_left_rotator"] = (ROTATOR_START_DEG, ROTATOR_START_DEG)
        self.events.reset_object.params["pose_range"] = {**OBJECT_XY_RANGE, "yaw": (-math.pi, math.pi)}
        # von schräg vorn/oben auf Fingerspitzen und Daumen (Hand liegt waagrecht)
        self.viewer.eye = (1.6, -2.6, 1.5)
        self.viewer.lookat = (0.15, -0.5, 0.4)


def apply_object_oben(cfg: PibGraspEnvCfg_Oben, key: str) -> PibGraspEnvCfg_Oben:
    """Objekt aus OBJECTS_OBEN einsetzen (wie env_cfg.apply_object; Startlage setzt das Startup-Event place_objects
    aus der tatsächlichen Bounding Box). YCB: echte Masse/Größe aus dem Asset, keine Zufallsmasse/-größe."""
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


# ── Training: Objektvielfalt wie EXP-013 (prozedural, MultiAssetSpawnerCfg), Masse wie Heavy ──────────────────────
TRAIN_SPHERES_OBEN = [0.025, 0.03, 0.035, 0.04, 0.045]                                 # Radius: Ø 5–9 cm
TRAIN_CYLINDERS_OBEN = [(r, h) for r in (0.025, 0.03, 0.035, 0.04) for h in (0.06, 0.10)]
TRAIN_CUBOIDS_OBEN = [(0.06, 0.06, 0.04), (0.08, 0.08, 0.05), (0.09, 0.06, 0.04), (0.06, 0.09, 0.05)]


@configclass
class PibGraspEnvCfg_ObenMulti(PibGraspEnvCfg_Oben):
    """Spezialist „von oben“ (voraussichtlich EXP-024): 17 Formen (5 Kugeln, 8 kurze Zylinder, 4 flache Quader),
    Masse 0,04–0,4 kg (wie EXP-006 ff.), Gier ±15° (bei Kugeln/Zylindern ohne Wirkung). Agent PibGraspPPORunnerCfg_Clip."""

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
    """EXP-029: Spezialist „von oben“ mit dem Rezept von EXP-027 (Aktionsraum wie Dexsuite, Agent mit bounds_loss)."""

    def __post_init__(self):
        super().__post_init__()
        dexsuite_action_space(self)


@configclass
class RewardsObenXYCfg(RewardsObenCfg):
    """Nur falls EXP-023 die Strafe auf die Verschiebung in der Tischebene stützt."""
    object_xy = RewTerm(func=mdp.object_xy_displacement, weight=XY_PENALTY_WEIGHT,
                        params={"ref_s": START_REF_S, "max_dist": 0.2})


@configclass
class PibGraspEnvCfg_ObenMultiXY(PibGraspEnvCfg_ObenMulti):
    rewards: RewardsObenXYCfg = RewardsObenXYCfg()
