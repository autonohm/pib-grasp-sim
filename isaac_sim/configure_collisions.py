"""
isaac_sim/configure_collisions.py — Collision-Group-Setup für pib-Hände.

Gruppen-Struktur:
  body          — alle Körper-Links (Torso, Kopf, Schultern, Arme, Unterarme)
  palm_left/right
  thumb/index/middle/ring/pinky _left/right

Filtered Pairs (kollidieren NICHT):
  body ↔ body        — keine Körper-Links gegeneinander
  body ↔ palm        — Arm/Schulter nicht gegen eigene Hand
  body ↔ finger      — Körper nicht gegen eigene Finger
  palm ↔ finger      — Palm überlappt geometrisch mit Fingerwurzeln

Aktive Kollisionen (erwünscht):
  finger ↔ finger    — Finger blockieren sich beim Schließen (Greifphysik)
  links ↔ rechts     — beidhändiges Greifen

Diagnostic: Viewport → 👁 → Physics → Contact Points zeigt live welche Links
sich berühren. Tools → Robot Self-Collision Detector für interaktive Analyse.

Workflow: setup_stage.py → configure_collisions.py → Ctrl+S → Play
Beide Skripte einmalig ausführen; das Ergebnis wird im USD gespeichert.
"""
import importlib.util
from pathlib import Path

import omni.usd  # type: ignore
from pxr import UsdPhysics, PhysxSchema, Usd, Sdf  # type: ignore

stage = omni.usd.get_context().get_stage()

# ── Config laden ──────────────────────────────────────────────────────────────
def _find_root() -> str:
    stage_file = Path(stage.GetRootLayer().realPath)
    for ancestor in [stage_file.parent, stage_file.parent.parent]:
        if (ancestor / "config" / "pib_hand_config.py").is_file():
            return str(ancestor)
    for candidate in [Path.home() / "repos" / "pib-hand-sim", Path.home() / "pib-hand-sim"]:
        if (candidate / "config" / "pib_hand_config.py").is_file():
            return str(candidate)
    raise FileNotFoundError("pib-hand-sim nicht gefunden.")

_root = _find_root()
_spec = importlib.util.spec_from_file_location("pib_hand_config", f"{_root}/config/pib_hand_config.py")
_cfg  = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_cfg)

ROBOT_PRIM_PATH  = _cfg.ROBOT_PRIM_PATH
GROUPS_BASE_PATH = "/World/CollisionGroups"

# ── Körper-DOFs (ohne Handgelenk — Palme gehört zur Palm-Gruppe) ─────────────
_BODY_DOFS = [
    "dof_head_horizontal", "dof_head_vertical",
    "dof_shoulder_vertical_left",  "dof_shoulder_horizontal_left",
    "dof_upper_arm_left",          "dof_elbow_left",  "dof_forearm_left",
    "dof_shoulder_vertical_right", "dof_shoulder_horizontal_right",
    "dof_upper_arm_right",         "dof_elbow_right", "dof_forearm_right",
]

# ── Hilfsfunktionen ───────────────────────────────────────────────────────────

def _resolve_link(dof_name: str, rel: str = "physics:body1"):
    """Gibt den Link-Pfad über eine Joint-Relation zurück (body0 oder body1)."""
    joint = stage.GetPrimAtPath(f"{ROBOT_PRIM_PATH}/{dof_name}")
    if not joint.IsValid():
        print(f"  WARN: Joint nicht gefunden: {dof_name}")
        return None
    relationship = joint.GetRelationship(rel)
    targets = relationship.GetTargets() if relationship else []
    if not targets:
        print(f"  WARN: {rel} leer: {dof_name}")
        return None
    return targets[0]


def _child_link(dof_name: str):
    return _resolve_link(dof_name, "physics:body1")


def _parent_link(dof_name: str):
    return _resolve_link(dof_name, "physics:body0")


def _make_group(name: str) -> UsdPhysics.CollisionGroup:
    """Erstellt eine CollisionGroup (idempotent via Define)."""
    return UsdPhysics.CollisionGroup.Define(stage, Sdf.Path(f"{GROUPS_BASE_PATH}/{name}"))


def _add_link(group: UsdPhysics.CollisionGroup, link_path) -> bool:
    """Fügt einen Link-Pfad zur 'colliders'-Collection der Gruppe hinzu."""
    if link_path is None:
        return False
    collection = Usd.CollectionAPI.Apply(group.GetPrim(), "colliders")
    collection.GetIncludesRel().AddTarget(link_path)
    return True


def _filter(group_a: UsdPhysics.CollisionGroup,
            group_b: UsdPhysics.CollisionGroup) -> None:
    """Gegenseitiger Ausschluss: a und b kollidieren nicht."""
    group_a.GetFilteredGroupsRel().AddTarget(group_b.GetPrim().GetPath())
    group_b.GetFilteredGroupsRel().AddTarget(group_a.GetPrim().GetPath())


# ── Haupt-Funktion ────────────────────────────────────────────────────────────

def configure_collision_groups() -> None:
    """Konfiguriert Self-Collision und alle Collision Groups."""

    robot_prim = stage.GetPrimAtPath(ROBOT_PRIM_PATH)
    if not robot_prim.IsValid():
        print(f"ERROR: Roboter-Prim nicht gefunden: {ROBOT_PRIM_PATH}")
        return

    # enabledSelfCollisions = True notwendig damit Collision Groups
    # innerhalb der Artikulation greifen
    art = PhysxSchema.PhysxArticulationAPI.Apply(robot_prim)
    art.GetEnabledSelfCollisionsAttr().Set(True)
    print(f"Self-Collision aktiviert: {ROBOT_PRIM_PATH}")

    if not stage.GetPrimAtPath(GROUPS_BASE_PATH).IsValid():
        stage.DefinePrim(GROUPS_BASE_PATH, "Scope")

    link_count   = 0
    filter_count = 0
    all_hand_groups = []   # alle Palm- und Finger-Gruppen beider Seiten

    # ── Hand-Gruppen (Palm + 5 Finger × 2 Seiten) ────────────────────────────
    _FINGER_DOFS = {
        "thumb":  ["{}_thumb_{}_rotator",  "{}_thumb_{}_proximal",  "{}_thumb_{}_distal"],
        "index":  ["{}_index_{}_proximal", "{}_index_{}_distal",    "{}_index_{}_tip"],
        "middle": ["{}_middle_{}_proximal","{}_middle_{}_distal",   "{}_middle_{}_tip"],
        "ring":   ["{}_ring_{}_proximal",  "{}_ring_{}_distal",     "{}_ring_{}_tip"],
        "pinky":  ["{}_pinky_{}_proximal", "{}_pinky_{}_distal",    "{}_pinky_{}_tip"],
    }

    for side in ("left", "right"):
        # Palm = child-Link des Handgelenk-Joints
        g_palm = _make_group(f"palm_{side}")
        if _add_link(g_palm, _child_link(f"dof_wrist_{side}")):
            link_count += 1
        all_hand_groups.append(g_palm)

        for finger_name, dof_templates in _FINGER_DOFS.items():
            g_finger = _make_group(f"{finger_name}_{side}")
            for tmpl in dof_templates:
                dof = tmpl.format("dof", side)
                if _add_link(g_finger, _child_link(dof)):
                    link_count += 1
            all_hand_groups.append(g_finger)

            # Palm ↔ Finger: Palm-Geometrie überlappt mit Fingerwurzeln
            _filter(g_palm, g_finger)
            filter_count += 1

    # ── Body-Gruppe (Torso, Kopf, Schultern, Arme, Unterarme) ────────────────
    g_body = _make_group("body")

    # Torso = parent-Link des Kopf-Joints (Wurzel der kinematischen Kette)
    torso_path = _parent_link("dof_head_horizontal")
    if torso_path and _add_link(g_body, torso_path):
        link_count += 1

    # Alle Körper-Links über body1-Relation der Body-DOFs
    for dof in _BODY_DOFS:
        if _add_link(g_body, _child_link(dof)):
            link_count += 1

    # Body ↔ Body: Körper-Links kollidieren nicht untereinander
    g_body.GetFilteredGroupsRel().AddTarget(g_body.GetPrim().GetPath())
    filter_count += 1

    # Body ↔ alle Hand-Gruppen: Körper kollidiert nicht mit eigenen Händen
    for g_hand in all_hand_groups:
        _filter(g_body, g_hand)
        filter_count += 1

    print(
        f"\nconfigure_collision_groups abgeschlossen:\n"
        f"  {link_count} Links zugewiesen\n"
        f"  {filter_count} Filtered-Group-Paare\n"
        f"  Gruppen unter {GROUPS_BASE_PATH}\n"
        f"  Aktiv: finger ↔ finger (gleiche/verschiedene Hand)"
    )


# ── Script-Editor-Block ───────────────────────────────────────────────────────
if not globals().get("_SKIP_COLLISION_SETUP"):
    configure_collision_groups()
    print("Stage speichern (Ctrl+S), dann Play drücken.")
