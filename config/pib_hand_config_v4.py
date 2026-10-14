import numpy as np

# ── Roboter ───────────────────────────────────────────────────────────────────
ROBOT_PRIM_PATH = "/World/pib_upperbody_URDF/pib_upperbody_URDF"

# ── Body DOFs (head, shoulders, arms, wrists) ─────────────────────────────────
# Since isaac_sim/tools/flip_joint_sign.py (see there) the Onshape and
# Isaac conventions agree — no JOINT_SIGN needed any more. Direct degree values,
# positive = flexion/raise/forward.
# Limits from inventory_output.txt (2026-06-18).
BODY_DOFS = {
    "names": [
        # Kopf
        "dof_head_horizontal",           # idx  0  — Drehen l/r         [-90, 90]
        "dof_head_vertical",             # idx  3  — Nicken             [-45, 70]
        # Left side
        "dof_shoulder_vertical_left",    # idx  1  — Heben/Senken       [-90, 90]
        "dof_shoulder_horizontal_left",  # idx  4  — forward/back        [-90, 90]
        "dof_upper_arm_left",            # idx  6  — Rotation           [-90, 90]
        "dof_elbow_left",                # idx  8  — Flexion (pos=biegen)[-45,90]
        "dof_forearm_left",              # idx 10  — Pronation          [-90, 90]
        "dof_wrist_left",                # idx 12  — flexion            [  0, 90]
        # Right side
        "dof_shoulder_vertical_right",   # idx  2  — Heben/Senken       [-90, 90]
        "dof_shoulder_horizontal_right", # idx  5  — forward/back        [-90, 90]
        "dof_upper_arm_right",           # idx  7  — Rotation           [-90, 90]
        "dof_elbow_right",               # idx  9  — Flexion (pos=biegen)[-45,90]
        "dof_forearm_right",             # idx 11  — Pronation          [-90, 90]
        "dof_wrist_right",               # idx 13  — flexion            [  0, 90]
    ],
    "indices": [0, 3, 1, 4, 6, 8, 10, 12, 2, 5, 7, 9, 11, 13],
}

# ── DOF data of both hands (from inventory_output.txt, 2026-06-18) ─────────────
# Sorted anatomically: thumb rotator → thumb MCP → IP →
# index MCP → PIP → DIP → middle finger ... → little finger
#
# Structure per side:
# names   — DOF names in anatomical order (15 entries)
# indices — corresponding articulation DOF indices (from the inventory DOF API)
# servos  — 6 servo groups: {servo_name: [usd_index, ...]}
#
# Servo groups:
# thumb_opp  — thumb CMC (opposition/abduction), 1 joint
# thumb      — thumb MCP + IP, 2 joints
# index/middle/ring/pinky — MCP + PIP + DIP, 3 joints each

HAND_DOFS = {
    "left": {
        "names": [
            "dof_thumb_left_rotator",    # 0  — thumb CMC
            "dof_thumb_left_proximal",   # 1  — thumb MCP
            "dof_thumb_left_distal",     # 2  — thumb IP
            "dof_index_left_proximal",   # 3  — Zeigefinger MCP
            "dof_index_left_distal",     # 4  — Zeigefinger PIP
            "dof_index_left_tip",        # 5  — Zeigefinger DIP
            "dof_middle_left_proximal",  # 6  — Mittelfinger MCP
            "dof_middle_left_distal",    # 7  — Mittelfinger PIP
            "dof_middle_left_tip",       # 8  — Mittelfinger DIP
            "dof_ring_left_proximal",    # 9  — Ringfinger MCP
            "dof_ring_left_distal",      # 10 — Ringfinger PIP
            "dof_ring_left_tip",         # 11 — Ringfinger DIP
            "dof_pinky_left_proximal",   # 12 — Kleiner Finger MCP
            "dof_pinky_left_distal",     # 13 — Kleiner Finger PIP
            "dof_pinky_left_tip",        # 14 — Kleiner Finger DIP
        ],
        "indices": [
            18,  # dof_thumb_left_rotator
            28,  # dof_thumb_left_proximal
            38,  # dof_thumb_left_distal
            14,  # dof_index_left_proximal
            24,  # dof_index_left_distal
            34,  # dof_index_left_tip
            15,  # dof_middle_left_proximal
            25,  # dof_middle_left_distal
            35,  # dof_middle_left_tip
            16,  # dof_ring_left_proximal
            26,  # dof_ring_left_distal
            36,  # dof_ring_left_tip
            17,  # dof_pinky_left_proximal
            27,  # dof_pinky_left_distal
            37,  # dof_pinky_left_tip
        ],
        "servos": {
            "thumb_opp": [18],
            "thumb":     [28, 38],
            "index":     [14, 24, 34],
            "middle":    [15, 25, 35],
            "ring":      [16, 26, 36],
            "pinky":     [17, 27, 37],
        },
    },
    "right": {
        "names": [
            "dof_thumb_right_rotator",    # 0  — thumb CMC
            "dof_thumb_right_proximal",   # 1  — thumb MCP
            "dof_thumb_right_distal",     # 2  — thumb IP
            "dof_index_right_proximal",   # 3  — Zeigefinger MCP
            "dof_index_right_distal",     # 4  — Zeigefinger PIP
            "dof_index_right_tip",        # 5  — Zeigefinger DIP
            "dof_middle_right_proximal",  # 6  — Mittelfinger MCP
            "dof_middle_right_distal",    # 7  — Mittelfinger PIP
            "dof_middle_right_tip",       # 8  — Mittelfinger DIP
            "dof_ring_right_proximal",    # 9  — Ringfinger MCP
            "dof_ring_right_distal",      # 10 — Ringfinger PIP
            "dof_ring_right_tip",         # 11 — Ringfinger DIP
            "dof_pinky_right_proximal",   # 12 — Kleiner Finger MCP
            "dof_pinky_right_distal",     # 13 — Kleiner Finger PIP
            "dof_pinky_right_tip",        # 14 — Kleiner Finger DIP
        ],
        "indices": [
            23,  # dof_thumb_right_rotator
            33,  # dof_thumb_right_proximal
            43,  # dof_thumb_right_distal
            19,  # dof_index_right_proximal
            29,  # dof_index_right_distal
            39,  # dof_index_right_tip
            20,  # dof_middle_right_proximal
            30,  # dof_middle_right_distal
            40,  # dof_middle_right_tip
            21,  # dof_ring_right_proximal
            31,  # dof_ring_right_distal
            41,  # dof_ring_right_tip
            22,  # dof_pinky_right_proximal
            32,  # dof_pinky_right_distal
            42,  # dof_pinky_right_tip
        ],
        "servos": {
            "thumb_opp": [23],
            "thumb":     [33, 43],
            "index":     [19, 29, 39],
            "middle":    [20, 30, 40],
            "ring":      [21, 31, 41],
            "pinky":     [22, 32, 42],
        },
    },
}

# ── Grasp poses as servo values (0–90°) ──────────────────────────────────────
# Side-neutral — servo_pose_to_joints() converts them to 15 DOF angles.
# All values are guide values; adjust when testing via config/sequences.py (TENDON).
GRASP_POSES = {
    "open": {
        "thumb_opp": 0,
        "thumb":     0,
        "index":     0,
        "middle":    0,
        "ring":      0,
        "pinky":     0,
    },
    "closed_fist": {
        "thumb_opp": 30,   # CMC opposition, not a flexion joint → stays at 30°
        "thumb":     90,
        "index":     90,
        "middle":    90,
        "ring":      90,
        "pinky":     90,
    },
    "pinch": {
        "thumb_opp": 60,
        "thumb":     70,
        "index":     70,
        "middle":    0,
        "ring":      0,
        "pinky":     0,
    },
    "cylindrical": {
        "thumb_opp": 15,
        "thumb":     60,
        "index":     70,
        "middle":    70,
        "ring":      70,
        "pinky":     70,
    },
    "lateral": {
        "thumb_opp": 30,
        "thumb":     50,
        "index":     10,
        "middle":    30,
        "ring":      40,
        "pinky":     50,
    },
}

# ── Linear approximation factors per joint type ──────────────────────────────
# Simplification: all joints of a finger follow the servo 1:1 (factor=1.0).
# At full stop (90°) all joints take 90°.
# Can be calibrated later with AS5600 measurements.
_SERVO_FACTORS = {
    "thumb_opp": [1.0],
    "thumb":     [1.0, 1.0],
    "index":     [1.0, 1.0, 1.0],
    "middle":    [1.0, 1.0, 1.0],
    "ring":      [1.0, 1.0, 1.0],
    "pinky":     [1.0, 1.0, 1.0],
}


def servo_pose_to_joints(servo_pose: dict, side: str) -> dict:
    """
    Converts a servo dictionary into a complete 15-DOF dictionary.

    Linear approximation: all joints of a finger follow the servo 1:1 (factor=1.0).

    Parameters
    ----------
    servo_pose : {servo_name: angle_deg}  — missing servos are assumed to be 0°
    side       : "left" or "right"

    Returns
    -------
    {dof_name: angle_deg}  — 15 entries, all in degrees
    """
    hand = HAND_DOFS[side]
    dof_names  = hand["names"]
    servos     = hand["servos"]

    result = {name: 0.0 for name in dof_names}

    for servo_name, factors in _SERVO_FACTORS.items():
        usd_indices = servos[servo_name]
        servo_val   = float(servo_pose.get(servo_name, 0.0))

        for usd_idx, factor in zip(usd_indices, factors):
            # determine the DOF name via the USD index
            art_idx = hand["indices"].index(usd_idx)
            result[dof_names[art_idx]] = np.clip(servo_val * factor, 0.0, 90.0)

    return result


# ── Normalisation ─────────────────────────────────────────────────────────────
# 0.0 = open (0°), 1.0 = closed (90°)

def normalize_pos(pos_deg: np.ndarray) -> np.ndarray:
    return np.clip(pos_deg / 90.0, 0.0, 1.0)

def denormalize_pos(pos_norm: np.ndarray) -> np.ndarray:
    return np.clip(pos_norm * 90.0, 0.0, 90.0)

# ── Physics parameter ranges (for synthetic data generation) ─────────────────
PHYSICS_RANGES = {
    "stiffness": (50.0, 200.0),
    "damping":   (5.0,  30.0),
}
