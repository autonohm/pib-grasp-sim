"""
flip_joint_sign.py — flips the sign convention of all PhysicsRevoluteJoint
prims in the currently open stage without changing the physical pose.

Background: Onshape and Isaac's imported joint axes have inverted signs
(JOINT_SIGN=-1). Previously compensated by a script node in the Action Graph +
mirrored limits in setup_stage.py. This script fixes the cause directly at the
joint prim, independent of the import path (Onshape importer, not URDF import).

Mechanics: a revolute joint measures its angle from the relative orientation
of localRot0 (body0 side) to localRot1 (body1 side) about the common axis.
Rotating BOTH sides by the same 180° rotation about an axis perpendicular to the
joint axis leaves the world orientation of the axis unchanged (no snap), but
the measured angle flips its sign (rotation conjugation F⁻¹MF preserves
the angle and only mirrors the axis — the same angle about the mirrored axis
is exactly the opposite sign about the original axis).

Limits are flipped accordingly: new_lower = -old_upper, new_upper = -old_lower.

IMPORTANT:
  - Before running: stop the simulation (do not run during Play).
  - Afterwards do NOT simply run start.py again before setup_stage.py/
    config/pib_hand_config_v4.py have been adapted (see accompanying changes) —
    otherwise set_joint_limits() overwrites the new limits with the
    old mirrored values.
  - Save with Ctrl+S only after visual confirmation (Play, move one joint to a
    positive value, check the direction).

Run in the Script Editor.
"""
import omni.usd
from pxr import Gf

stage = omni.usd.get_context().get_stage()

_AXIS_VEC = {
    "X": Gf.Vec3d(1, 0, 0),
    "Y": Gf.Vec3d(0, 1, 0),
    "Z": Gf.Vec3d(0, 0, 1),
}


def _perpendicular(axis_vec: Gf.Vec3d) -> Gf.Vec3d:
    """Any unit vector perpendicular to axis_vec."""
    ref = Gf.Vec3d(0, 0, 1) if abs(axis_vec[2]) < 0.9 else Gf.Vec3d(0, 1, 0)
    return (axis_vec ^ ref).GetNormalized()  # Kreuzprodukt-Operator (pxr.Gf.Vec3d)


def flip_joint_sign(prim) -> bool:
    axis_attr = prim.GetAttribute("physics:axis")
    lower_attr = prim.GetAttribute("physics:lowerLimit")
    upper_attr = prim.GetAttribute("physics:upperLimit")
    rot0_attr = prim.GetAttribute("physics:localRot0")
    rot1_attr = prim.GetAttribute("physics:localRot1")
    if not all([axis_attr, lower_attr, upper_attr, rot0_attr, rot1_attr]):
        return False

    axis_vec = _AXIS_VEC.get(str(axis_attr.Get()))
    if axis_vec is None:
        return False

    perp = _perpendicular(axis_vec)
    flip = Gf.Quatf(Gf.Rotation(perp, 180.0).GetQuat())

    rot0_attr.Set(rot0_attr.Get() * flip)
    rot1_attr.Set(rot1_attr.Get() * flip)

    lower, upper = lower_attr.Get(), upper_attr.Get()
    lower_attr.Set(-upper)
    upper_attr.Set(-lower)
    return True


count = 0
for prim in stage.Traverse():
    if prim.GetTypeName() != "PhysicsRevoluteJoint":
        continue
    name = prim.GetPath().name
    lo0 = prim.GetAttribute("physics:lowerLimit").Get()
    up0 = prim.GetAttribute("physics:upperLimit").Get()
    if flip_joint_sign(prim):
        count += 1
        lo1 = prim.GetAttribute("physics:lowerLimit").Get()
        up1 = prim.GetAttribute("physics:upperLimit").Get()
        print(f"{name}: [{lo0:.1f},{up0:.1f}] -> [{lo1:.1f},{up1:.1f}]")
    else:
        print(f"ÜBERSPRUNGEN (fehlende Attribute): {name}")

print(f"\n{count} Gelenke umgedreht. NICHT speichern vor visueller Prüfung:")
print("  1. Play drücken, z.B. dof_elbow_right per Drive-Target auf +90 setzen")
print("  2. Erwartung: Ellbogen beugt sich (Onshape-Konvention direkt)")
print("  3. Erst wenn das stimmt: Stop, dann Ctrl+S")
