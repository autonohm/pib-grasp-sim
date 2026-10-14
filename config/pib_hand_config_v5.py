"""
config/pib_hand_config_v5.py — v5 counterpart of pib_hand_config_v4.py.

All values verified directly against ros2_ws/src/pib_description_v5/urdf/pib_upperbody_v5.urdf (not copied/guessed from the
v4 config) — reason: isaac_sim/setup_stage.py:_BODY_LIMITS used to be shared by v4 AND v5,
although two body joints have different limits in v5 than in v4 (see "body DOFs" below).
This file is the record that the values were checked against the v5 source — the actual enforcement stays
in isaac_sim/setup_stage.py:_BODY_LIMITS (merged there with the v4 values,
no name collision: v4 DOF names have the "dof_" prefix, v5 does not).

v5 naming scheme: NO "dof_" prefix (unlike v4), the thumb middle joint is called "tip"
(not "distal" as for the other fingers) -- see docs/conventions.md.
"""

# ── Robot ─────────────────────────────────────────────────────────────────────
# In v5 the articulation root sits on root_joint (PhysicsFixedJoint), NOT on a
# wrapper Xform as in v4 -- a different but valid importer pattern (onshape-to-robot
# + URDF import instead of the direct Onshape importer as in v4, see docs/protokoll/current-sprint.md
# "v5-Hand-Integration"). Value taken from the Action Graph targetPrim relationships of that
# session (isaac_sim/tools/build_finger_coupling_graph.py,
# build_coupling_reflection_graph.py, isaac_sim/tools/_action_graph_inventory.txt),
# verified there against the running stage -- not guessed again here.
ROBOT_PRIM_PATH = "/World/pib_upperbody_urdf_v5/root_joint"

# ── Body DOFs (head, shoulders, arms, wrists) ─────────────────────────────────
# Limits from ros2_ws/src/pib_description_v5/urdf/pib_upperbody_v5.urdf (extracted in that session and cross-checked against
# ros2_ws/src/pib_description_v5/urdf/pib_upperbody_v5.urdf, identical).
#
# Differences from v4 (config/pib_hand_config_v4.py), do NOT simply copy:
# - upper_arm_left: v5 is symmetric [-90, 90] (v4 was [0, 90] -- see the comment
# on dof_upper_arm_left in setup_stage.py, verified there explicitly for v4, never
# valid for v5)
# - wrist_left/wrist_right: v5 is [-60, 0] (v4 is [0, 90]) -- both sides
# affected equally. Until 2026-10-04 [-90, 30]; corrected in Onshape and
# the URDFs because the linkage only allows a 60° swing (WRIST_LINKAGE below).
# Sign exception: -60 = fully flexed inwards, 0 = straight
# - shoulder_horizontal_right: [0, 90] in BOTH versions (v4 AND v5) -- this is
# NOT a bug but a real asymmetry with respect to shoulder_horizontal_left
# ([-90, 90]), verified consistently in two independent sources (v4 and v5 URDF).
# Do not "correct" it to be symmetric.
BODY_DOFS = {
    "names": [
        # Kopf
        "head_horizontal",           # [-90, 90]
        "head_vertical",             # [-45, 70]
        # Left side
        "shoulder_vertical_left",    # [-90, 90]
        "shoulder_horizontal_left",  # [-90, 90]
        "upper_arm_left",            # [-90, 90]
        "elbow_left",                # [-45, 90]
        "forearm_left",              # [-90, 90]
        "wrist_left",                # [-60, 0]  -- -60 = gebeugt (Ausnahme)
        # Right side
        "shoulder_vertical_right",   # [-90, 90]
        "shoulder_horizontal_right", # [  0, 90]  -- asymmetry verified, not a bug
        "upper_arm_right",           # [-90, 90]
        "elbow_right",               # [-45, 90]
        "forearm_right",             # [-90, 90]
        "wrist_right",               # [-60, 0]  -- -60 = gebeugt (Ausnahme)
    ],
    # TODO(param): articulation DOF indices (like BODY_DOFS["indices"] in
    # pib_hand_config_v4.py) not copied -- the v4 values come from an
    # Isaac inventory dump (inventory_output.txt) of the v4 articulation, not verified
    # for v5 and deliberately not guessed here. isaac_sim/setup_stage.py
    # does not need them at the moment (works by name traversal, no index
    # access). If needed in the future (e.g. a servo_pose_to_joints() equivalent for
    # v5): dump them from the running v5 articulation via IsaacArticulationState or similar,
    # do not copy from v4 (joint order probably differs).
}

# ── Hand/finger joints ────────────────────────────────────────────────────────
# All 30 hand DOFs (thumb: rotator+proximal+tip, fingers: proximal+distal+tip,
# 5 finger/thumb groups x 2 sides) are uniformly [0, 90] -- verified against
# the v5 URDF, identical to v4. Matches the existing, version-generic
# _HAND_KEYWORDS rule in isaac_sim/setup_stage.py:set_joint_limits() (name
# substring "proximal"/"distal"/"tip"/"rotator" -> [0, 90]) -- no separate
# table is needed, only recorded here for documentation.
#
# HAND_DOFS (names, USD indices, servo grouping as in pib_hand_config_v4.py)
# NOT copied -- for the same reason as the body DOF indices above: v5 has a
# different articulation structure (44 instead of 28 joints in total, different import pattern);
# copying the indices/servo groups from v4 1:1 would be guessing, not verification.


# ── Servo actuator model (ADR-012) ────────────────────────────────────────────
# Single source for Isaac Sim (isaac_sim/setup_stage.py, units at the prim: Nm/°) and
# Isaac Lab (ArticulationCfg/ImplicitActuatorCfg, units: Nm/rad) -- servo_actuator()
# returns both. Recipe after the NVIDIA Articulation Stability Guide / tuning series
# (Robotiq example):
# max_force         = stall torque (datasheet, 12 V)
# max_velocity      = no-load speed (datasheet, 12 V)
# stiffness         = max_force / SERVO_SATURATION_ERROR_DEG  (saturation at 5° error)
# damping           = critical (ζ = 1) with I = I_nominal + armature
# Check the result with isaac_sim/tools/audit_asset.py (ω_n·Δt, ζ).
_KGCM_TO_NM = 0.0980665
_RAD_PER_DEG = 0.017453292519943295

SERVOS = {
    # ST3215 (12 V): 30 kg·cm Stall, 0.222 s/60° Leerlauf (45 RPM)
    "ST3215": {"stall_nm": 30.0 * _KGCM_TO_NM, "no_load_deg_s": 60.0 / 0.222},
    # ST3095-C002 (12 V): 95 kg·cm Stall, 31 RPM Leerlauf
    "ST3095": {"stall_nm": 95.0 * _KGCM_TO_NM, "no_load_deg_s": 31.0 * 6.0},
}
SERVO_SATURATION_ERROR_DEG = 5.0
# ASSUMPTION, not measured: reflected rotor inertia (rotor × gear ratio²) — not given in
# any of the datasheets. 5e-3 kg·m² = starting value from NVIDIA's Robotiq example.
SERVO_ARMATURE_KGM2 = 5.0e-3

# Joint groups: (keyword in the joint name, servo, I_nominal [kg·m²]).
# I_nominal = diagonal of the mass matrix in the T pose (audit_asset.py, 2026-10-03) — only
# for the damping; pose-dependent, for arm joints it dominates the armature.
# Order = matching order (the first matching keyword wins).
V5_ACTUATORS = [
    ("shoulder_vertical",   "ST3095", 0.0249),
    ("shoulder_horizontal", "ST3095", 0.116),
    ("upper_arm",           "ST3215", 0.024),
    ("elbow",               "ST3215", 0.0426),
    ("head_horizontal",     "ST3215", 0.00591),
    ("head_vertical",       "ST3215", 0.00534),
    ("forearm",             "ST3215", 0.00128),
    ("wrist",               "ST3215", 0.00281),
    ("rotator",             "ST3215", 1.58e-4),     # thumb CMC
    ("proximal",            "ST3215", 6.6e-5),      # MCP fingers (thumb 7.1e-5)
]

# Passive mimic followers (PIP/DIP/IP, no servo): small armature against the extreme
# inertia ratio to the MCP (fingertip M_ii ≈ 1e-6 vs. MCP 5e-3; NVIDIA: avoid large
# inertia ratios) and a velocity limit (real coupling up to 1.67×
# MCP velocity ≈ 450 °/s). ASSUMPTIONS, not measured. Which joints are followers
# is defined in isaac_sim/setup_stage.py → MIMIC_JOINTS (ADR-011).
FOLLOWER_ARMATURE_KGM2 = 5.0e-4
FOLLOWER_MAX_VELOCITY_DEG_S = 500.0


# ── Wrist linkage (2026-10-04) ────────────────────────────────────────────────
# The wrist servo (ST3215) drives the wrist via a connecting rod (four-bar linkage:
# crank at the servo → connecting rod → lever at the palm). Dimensions from Onshape at 0°.
# The crank can rotate fully (Grashof), the lever swings exactly 60° between the dead
# points for 180° of crank angle → wrist [-60°, 0°]. Transmission ≈ 2:1 in the middle,
# towards ∞ at the dead points (torque ↑, speed ↓).
# ASSUMPTION: 0° (straight) lies at the dead point "crank and rod stretched", -60° at
# the folded one. The transmission is almost symmetric (5 % from the edge: 0.228 and 0.241),
# swapping them barely changes the table.
WRIST_LINKAGE = {"crank_mm": 6.0, "rod_mm": 115.0, "lever_mm": 12.0, "frame_mm": 115.43}
WRIST_RANGE_DEG = (-60.0, 0.0)
WRIST_TORQUE_CAP_NM = 12.0      # cap near the dead points (2026-10-04)


def _wrist_rocker_limits():
    """Lever angle β [rad] at the wrist in the two dead points (stretched, folded)."""
    import math
    a, b, c, d = (WRIST_LINKAGE[k] for k in ("crank_mm", "rod_mm", "lever_mm", "frame_mm"))
    beta = lambda r: math.acos((d * d + c * c - r * r) / (2 * d * c))  # noqa: E731
    return beta(b + a), beta(b - a)


def wrist_transmission(theta_deg: float) -> float:
    """
    Transmission of the wrist linkage n = dφ_servo / dθ_wrist (≥ 1, "in/out")
    at wrist angle theta_deg ∈ [-60, 0]. Analytically from the velocity of the
    two joint pins along the rigid connecting rod (as in tendondrive/ for the fingers, commit 1d0cd9c).
    """
    import math
    a, b, c, d = (WRIST_LINKAGE[k] for k in ("crank_mm", "rod_mm", "lever_mm", "frame_mm"))
    beta_ext, beta_fold = _wrist_rocker_limits()
    frac = min(max(-theta_deg / (WRIST_RANGE_DEG[1] - WRIST_RANGE_DEG[0]), 0.0), 1.0)
    beta = beta_ext + frac * (beta_fold - beta_ext)
    # servo axis (0,0), wrist axis (d,0); lever pin B, crank pin A with |A|=a, |A-B|=b
    bx, by = d - c * math.cos(beta), c * math.sin(beta)
    r = math.hypot(bx, by)
    gamma = math.acos(max(-1.0, min(1.0, (a * a + r * r - b * b) / (2 * a * r))))
    phi = math.atan2(by, bx) - gamma                      # one assembly branch, continuous over the range
    ax, ay = a * math.cos(phi), a * math.sin(phi)
    ux, uy = bx - ax, by - ay                             # direction of the connecting rod
    t_a = (-math.sin(phi), math.cos(phi))                 # Tangente Kurbelzapfen
    t_b = (-math.sin(beta), -math.cos(beta))              # Tangente Hebelzapfen (dB/dβ / c)
    out_per_in = (a * (t_a[0] * ux + t_a[1] * uy)) / (c * (t_b[0] * ux + t_b[1] * uy))
    return 1.0 / max(abs(out_per_in), 1e-6)


def wrist_lookup_table(points: int = 25) -> list:
    """
    Table for Isaac Lab's RemotizedPDActuatorCfg.joint_parameter_lookup (NVIDIA pattern
    for linkage-driven joints, Spot knee): [joint angle rad, transmission in/out,
    output torque Nm], torque = stall torque × transmission, clipped at WRIST_TORQUE_CAP_NM
    (transmission clipped accordingly; Isaac Lab only uses the torque for the limit).
    """
    lo, hi = WRIST_RANGE_DEG
    stall = SERVOS["ST3215"]["stall_nm"]
    n_cap = WRIST_TORQUE_CAP_NM / stall
    table = []
    for i in range(points):
        theta = lo + (hi - lo) * i / (points - 1)
        n = min(wrist_transmission(theta), n_cap)
        table.append([theta * _RAD_PER_DEG, n, stall * n])
    return table


# Constant transmission for PhysX drives (Isaac Sim cannot do angle-dependent
# torque): middle of the range.
WRIST_TRANSMISSION_NOMINAL = wrist_transmission(sum(WRIST_RANGE_DEG) / 2)

# Transmission between servo and joint per joint group (keyword → n = dφ/dθ).
# Torque × n, velocity ÷ n, armature (rotor inertia on the servo side) × n².
TRANSMISSIONS = {"wrist": WRIST_TRANSMISSION_NOMINAL}


def servo_actuator(name: str):
    """
    Parameters of a servo-driven v5 joint, otherwise None. Both unit systems:
      *_deg: USD prim (stiffness Nm/°, damping Nm·s/°, max_velocity °/s)
      *_rad: Isaac Lab / ROS (stiffness Nm/rad, damping Nm·s/rad, max_velocity rad/s)
    max_force [Nm] and armature [kg·m²] are the same in both. Joints behind a
    linkage (TRANSMISSIONS) get the servo values converted to the joint.
    """
    n = name.lower()
    for key, servo, inertia in V5_ACTUATORS:
        if key in n:
            spec = SERVOS[servo]
            ratio = next((r for k, r in TRANSMISSIONS.items() if k in n), 1.0)
            max_force = spec["stall_nm"] * ratio
            max_velocity_deg = spec["no_load_deg_s"] / ratio
            armature = SERVO_ARMATURE_KGM2 * ratio ** 2
            k_deg = max_force / SERVO_SATURATION_ERROR_DEG
            k_rad = k_deg / _RAD_PER_DEG
            d_rad = 2.0 * (k_rad * (inertia + armature)) ** 0.5    # ζ = 1
            return {
                "servo": servo,
                "transmission": ratio,
                "max_force": max_force,
                "armature": armature,
                "stiffness_deg": k_deg,
                "damping_deg": d_rad * _RAD_PER_DEG,
                "max_velocity_deg": max_velocity_deg,
                "stiffness_rad": k_rad,
                "damping_rad": d_rad,
                "max_velocity_rad": max_velocity_deg * _RAD_PER_DEG,
            }
    return None


# ── Real left hand (prototype, STM32 Nucleo) ──────────────────────────────────
# The 8 servo joints = action space of the RL policy (feature/rl-grasping). Names from
# ros2_ws/src/pib_description_v5/urdf/pib_upperbody_v5.urdf. All other joints of the left hand
# (*_distal, *_tip) are passive mimic followers (ADR-011).
LEFT_HAND_SERVO_JOINTS = [
    "forearm_left",          # forearm rotation
    "wrist_left",
    "thumb_left_rotator",
    "thumb_left_proximal",
    "index_left_proximal",
    "middle_left_proximal",
    "ring_left_proximal",
    "pinky_left_proximal",
]
