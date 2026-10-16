"""
audit_asset.py — step 1 "inspect the asset" (after NVIDIA's tuning series, tutorial 3):
reads the physical state of the stage and writes it to
isaac_sim/tools/_asset_audit.txt (gitignored). Changes NOTHING in the stage.

Sections:
  1. Physics Scene     — time step, solver, GPU dynamics, readback
  2. Articulation Root — self-collision, solver iterations
  3. Links             — mass/inertia in the USD (authored) and as PhysX uses them, comparison
                         with the URDF, collider type/offsets, instanceable, depenetration velocity
  4. Joints            — limits, drive (stiffness/damping/maxForce/type/target), armature,
                         maxJointVelocity, mimic configuration
  5. Joint dynamics    — effective inertia (diagonal of the mass matrix), gravity torque in the
                         current pose, from that ω_n, ζ, ω_n·Δt and saturation error, with warnings
                         after the NVIDIA Articulation Stability Guide

Units: USD angular drive stiffness = Nm/°, damping = Nm·s/°, maxJointVelocity = °/s
(see generatedSchema.usda). For ω_n/ζ they are converted to Nm/rad.
Mass matrix: PhysX does NOT include the armature (verified: MCP M_ii ≈ 6.6e-5 at armature 5e-3),
hence I_eff = M_ii + armature for ω_n/ζ.

Run in the Script Editor with the stage open (v4 or v5), after start.py, simulation on
PLAY (sections 3 "PhysX" and 5 need the running physics; otherwise they are skipped).
Pose: section 5 applies to the current pose (after start.py: T pose).
"""
import os
import io
import math
import xml.etree.ElementTree as ET
from pathlib import Path

import carb
import numpy as np
import omni.usd
from pxr import Usd, UsdPhysics

stage = omni.usd.get_context().get_stage()
out = io.StringIO()

STIFF_WN_DT_MAX = 2.0        # NVIDIA: ω_n·Δt "not much larger than 1" — warning from 2
ZETA_UNDER = 0.7
ZETA_OVER = 3.0
VEL_UNLIMITED = 1.0e5        # the schema default is 1e6 °/s


def emit(line: str = "") -> None:
    print(line)
    out.write(line + "\n")


def _find_project_root() -> Path:
    # Repo root without a fixed install path: PIB_GRASP_SIM_ROOT, else upwards from this file, the open stage or the
    # working directory until config/ is found (__file__ is not defined in the Script Editor's exec context)
    if os.environ.get("PIB_GRASP_SIM_ROOT"):
        return Path(os.environ["PIB_GRASP_SIM_ROOT"])
    starts = [Path.cwd()]
    try:
        import omni.usd  # type: ignore
        starts.insert(0, Path(omni.usd.get_context().get_stage().GetRootLayer().realPath or "."))
    except Exception:
        pass
    if "__file__" in globals():
        starts.insert(0, Path(__file__))
    for start in starts:
        for d in [start.resolve(), *start.resolve().parents]:
            if (d / "config" / "pib_hand_config_v4.py").is_file():
                return d
    raise FileNotFoundError("Repo-Wurzel nicht gefunden — Stage aus dem Repo öffnen oder PIB_GRASP_SIM_ROOT setzen")


ROOT = _find_project_root()


def _get(prim, name, default=None):
    attr = prim.GetAttribute(name)
    if not attr or not attr.HasAuthoredValue() and attr.Get() is None:
        return default
    value = attr.Get()
    return default if value is None else value


def _is_revolute(prim) -> bool:
    return prim.GetTypeName() == "PhysicsRevoluteJoint" or prim.HasAPI(UsdPhysics.RevoluteJoint)


def _fmt(v, spec=".4g"):
    return "-" if v is None else format(v, spec)


# ── URDF reference (Onshape values) ───────────────────────────────────────────

def _load_urdf() -> dict:
    stage_name = Path(stage.GetRootLayer().realPath).name
    path = ROOT / ("ros2_ws/src/pib_description_v5/urdf/pib_upperbody_v5.urdf" if "v5" in stage_name
                   else "ros2_ws/src/pib_description_v4/urdf/pib_upperbody.urdf")
    if not path.is_file():
        emit(f"URDF nicht gefunden: {path} — kein Vergleich")
        return {}
    links = {}
    for link in ET.parse(path).getroot().findall("link"):
        inert = link.find("inertial")
        if inert is None:
            continue
        a = inert.find("inertia").attrib
        tensor = np.array([[float(a["ixx"]), float(a["ixy"]), float(a["ixz"])],
                           [float(a["ixy"]), float(a["iyy"]), float(a["iyz"])],
                           [float(a["ixz"]), float(a["iyz"]), float(a["izz"])]])
        links[link.get("name")] = (float(inert.find("mass").get("value")), np.sort(np.linalg.eigvalsh(tensor)))
    emit(f"URDF-Referenz: {path.relative_to(ROOT)} ({len(links)} Links mit <inertial>)")
    return links


# ── 1. Physics Scene ──────────────────────────────────────────────────────────

def audit_scene() -> float:
    emit("\n=== 1. Physics Scene ===")
    dt = 1.0 / 60.0
    scenes = [p for p in stage.Traverse() if p.GetTypeName() == "PhysicsScene"]
    if not scenes:
        emit("  keine PhysicsScene gefunden")
    if len(scenes) > 1:
        emit(f"  WARNUNG: {len(scenes)} PhysicsScenes — sollte genau eine sein")
    for p in scenes:
        steps = _get(p, "physxScene:timeStepsPerSecond", 60)
        emit(f"  {p.GetPath()}")
        emit(f"    timeStepsPerSecond = {steps}  (Δt = {1000.0 / steps:.2f} ms)")
        emit(f"    solverType = {_get(p, 'physxScene:solverType', '-')}   "
             f"broadphaseType = {_get(p, 'physxScene:broadphaseType', '-')}   "
             f"enableGPUDynamics = {_get(p, 'physxScene:enableGPUDynamics', '-')}")
        emit(f"    gravity = {_get(p, 'physics:gravityDirection', '-')} * {_get(p, 'physics:gravityMagnitude', '-')}")
        dt = 1.0 / float(steps)
    settings = carb.settings.get_settings()
    emit(f"  carb /physics/suppressReadback = {settings.get('/physics/suppressReadback')}")
    return dt


# ── 2. Articulation Root ──────────────────────────────────────────────────────

def audit_articulation_roots() -> list:
    emit("\n=== 2. Articulation Root ===")
    roots = [p for p in stage.Traverse() if p.HasAPI(UsdPhysics.ArticulationRootAPI)]
    for p in roots:
        emit(f"  {p.GetPath()}  (Typ {p.GetTypeName()})")
        for name in ("physxArticulation:enabledSelfCollisions", "physxArticulation:solverPositionIterationCount",
                     "physxArticulation:solverVelocityIterationCount", "physxArticulation:sleepThreshold",
                     "physxArticulation:stabilizationThreshold"):
            emit(f"    {name.split(':')[1]} = {_get(p, name, '- (Default)')}")
    if not roots:
        emit("  keine ArticulationRootAPI gefunden")
    return [str(p.GetPath()) for p in roots]


# ── PhysX-Sicht (braucht Play) ────────────────────────────────────────────────

def _physx_view(root_path: str):
    try:
        from isaacsim.core.prims import Articulation
        view = Articulation(root_path, name="audit_view", reset_xform_properties=False)
        view.initialize()
        if not view.is_physics_handle_valid():
            raise RuntimeError("Physics-Handle ungültig")
        return view
    except Exception as exc:  # noqa: BLE001
        emit(f"\n  PhysX-Sicht nicht verfügbar ({exc}) — Simulation auf Play? Abschnitte mit PhysX-Werten fehlen.")
        return None


def _np(x):
    return x.cpu().numpy() if hasattr(x, "cpu") else np.asarray(x)


# ── 3. Links ──────────────────────────────────────────────────────────────────

def audit_links(robot_root: str, urdf: dict, view) -> None:
    emit("\n=== 3. Links (USD authored | PhysX effektiv | URDF) ===")
    physx = {}
    if view is not None:
        masses = _np(view.get_body_masses())[0]
        inertias = _np(view.get_body_inertias())[0]
        for i, name in enumerate(view.body_names):
            physx[name] = (float(masses[i]), np.sort(np.linalg.eigvalsh(inertias[i].reshape(3, 3))))

    robot_prim = stage.GetPrimAtPath(robot_root)
    search_root = robot_prim.GetParent() if robot_prim and robot_prim.GetTypeName() == "PhysicsFixedJoint" else robot_prim
    bodies = [p for p in Usd.PrimRange(search_root, Usd.TraverseInstanceProxies()) if p.HasAPI(UsdPhysics.RigidBodyAPI)]
    emit(f"  {len(bodies)} Rigid Bodies unter {search_root.GetPath()}")
    emit(f"  {'Link':<28}{'m USD':>9}{'m PhysX':>9}{'m URDF':>9}  {'I PhysX (Haupt, kg·m²)':<32}{'I URDF':<32}"
         f"{'Collider':<22}{'cOff/rOff':<16}{'maxDepen':>9}  Hinweise")
    for body in bodies:
        name = body.GetName()
        notes = []
        m_usd = _get(body, "physics:mass")
        m_px, i_px = physx.get(name, (None, None))
        m_ur, i_ur = urdf.get(name, (None, None))
        if m_usd in (None, 0.0):
            notes.append("keine Masse authored → PhysX rechnet aus Collider-Volumen")
        if m_px is not None and m_ur is not None and abs(m_px - m_ur) > 0.02 * m_ur:
            notes.append(f"Masse ≠ URDF ({(m_px / m_ur - 1) * 100:+.0f} %)")
        if i_px is not None and i_ur is not None and np.max(np.abs(i_px - i_ur) / np.maximum(i_ur, 1e-12)) > 0.05:
            notes.append("Trägheit ≠ URDF")
        if name in urdf and name not in physx and physx:
            notes.append("nicht in PhysX-Bodies")

        colliders = [p for p in Usd.PrimRange(body, Usd.TraverseInstanceProxies()) if p.HasAPI(UsdPhysics.CollisionAPI)]
        approx = sorted({str(_get(c, "physics:approximation", "none")) for c in colliders})
        offsets = sorted({(_get(c, "physxCollision:contactOffset"), _get(c, "physxCollision:restOffset")) for c in colliders})
        off_txt = ",".join(f"{_fmt(a, '.3g')}/{_fmt(b, '.3g')}" for a, b in offsets) or "-"
        if body.IsInstance() or body.IsInstanceProxy():
            notes.append("Link selbst instanceable/Proxy (Sensor-Prims nicht anlegbar, ADR-008)")
        elif any(p.IsInstanceProxy() for p in Usd.PrimRange(body, Usd.TraverseInstanceProxies())):
            notes.append("Mesh-Kinder instanced (Link selbst editierbar)")
        if not colliders:
            notes.append("kein Collider")
        i_px_txt = "/".join(f"{v:.3g}" for v in i_px) if i_px is not None else "-"
        i_ur_txt = "/".join(f"{v:.3g}" for v in i_ur) if i_ur is not None else "-"
        emit(f"  {name:<28}{_fmt(m_usd):>9}{_fmt(m_px):>9}{_fmt(m_ur):>9}  {i_px_txt:<32}{i_ur_txt:<32}"
             f"{f'{len(colliders)}x ' + ','.join(approx):<22}{off_txt:<16}"
             f"{_fmt(_get(body, 'physxRigidBody:maxDepenetrationVelocity'), '.3g'):>9}  {'; '.join(notes)}")


# ── 4./5. Joints ──────────────────────────────────────────────────────────────

def _mimic(prim):
    for schema in prim.GetAppliedSchemas():
        if schema.startswith("PhysxMimicJointAPI:"):
            inst = schema.split(":", 1)[1]
            rel = prim.GetRelationship(f"physxMimicJoint:{inst}:referenceJoint")
            targets = [t.name for t in rel.GetTargets()] if rel else []
            return (f"{inst} ← {targets[0] if targets else '?'} "
                    f"G={_fmt(_get(prim, f'physxMimicJoint:{inst}:gearing'), 'g')} "
                    f"off={_fmt(_get(prim, f'physxMimicJoint:{inst}:offset'), 'g')}")
    return ""


def audit_joints(robot_root: str, view, dt: float) -> None:
    emit("\n=== 4. Gelenke (USD authored) ===")
    joints = {}
    root_prim = stage.GetPrimAtPath(robot_root)
    search_root = root_prim.GetParent() if root_prim.GetTypeName() == "PhysicsFixedJoint" else root_prim
    for p in Usd.PrimRange(search_root, Usd.TraverseInstanceProxies()):
        if _is_revolute(p):
            joints[p.GetName()] = p
    emit(f"  {'Gelenk':<26}{'Limit [°]':<16}{'k [Nm/°]':>10}{'d [Nm·s/°]':>11}{'maxF [Nm]':>10}{'Typ':>6}"
         f"{'Target°':>8}{'Armature':>10}{'maxVel°/s':>11}  Mimic")
    for name, p in joints.items():
        lo, hi = _get(p, "physics:lowerLimit"), _get(p, "physics:upperLimit")
        vel = _get(p, "physxJoint:maxJointVelocity")
        limit_txt = "[" + _fmt(lo, ".1f") + ", " + _fmt(hi, ".1f") + "]"
        emit(f"  {name:<26}{limit_txt:<16}"
             f"{_fmt(_get(p, 'drive:angular:physics:stiffness'), '.4g'):>10}"
             f"{_fmt(_get(p, 'drive:angular:physics:damping'), '.4g'):>11}"
             f"{_fmt(_get(p, 'drive:angular:physics:maxForce'), '.4g'):>10}"
             f"{str(_get(p, 'drive:angular:physics:type', '-'))[:5]:>6}"
             f"{_fmt(_get(p, 'drive:angular:physics:targetPosition'), '.1f'):>8}"
             f"{_fmt(_get(p, 'physxJoint:armature'), '.3g'):>10}"
             f"{('Default' if vel is None or vel >= VEL_UNLIMITED else format(vel, '.0f')):>11}  {_mimic(p)}")

    emit("\n=== 5. Gelenk-Dynamik (PhysX, aktuelle Pose) ===")
    if view is None:
        emit("  übersprungen — PhysX-Sicht fehlt (Play?)")
        return
    dof_names = list(view.dof_names)
    M = _np(view.get_mass_matrices())[0]
    if M.ndim == 1:
        n = int(round(math.sqrt(M.size)))
        M = M.reshape(n, n)
    grav = _np(view.get_generalized_gravity_forces())[0]
    q = _np(view.get_joint_positions())[0]
    try:
        arm = _np(view.get_armatures())[0]
    except Exception:  # noqa: BLE001
        arm = np.full(len(dof_names), np.nan)
    emit(f"  Massenmatrix {M.shape}, Δt = {dt * 1000:.2f} ms. ω_n = √(k/I), ζ = d/(2√(k·I)), I = M_ii + Armature.")
    emit(f"  {'Gelenk':<26}{'q°':>7}{'Target°':>8}{'M_ii':>10}{'Armature':>10}{'τ_grav':>8}{'maxF':>7}"
         f"{'ω_n':>9}{'ζ':>8}{'ω_n·Δt':>8}{'Sätt.°':>8}  Warnungen")
    counts = {"steif": 0, "unter": 0, "grav": 0, "vel": 0}
    for i, name in enumerate(dof_names):
        p = joints.get(name)
        I = (float(M[i, i]) if i < M.shape[0] else float("nan")) + (0.0 if np.isnan(arm[i]) else float(arm[i]))
        k_deg = _get(p, "drive:angular:physics:stiffness", 0.0) if p else 0.0
        d_deg = _get(p, "drive:angular:physics:damping", 0.0) if p else 0.0
        max_f = _get(p, "drive:angular:physics:maxForce", float("inf")) if p else float("inf")
        target = _get(p, "drive:angular:physics:targetPosition") if p else None
        vel = _get(p, "physxJoint:maxJointVelocity") if p else None
        k_rad, d_rad = k_deg * 180.0 / math.pi, d_deg * 180.0 / math.pi
        warn = []
        if k_rad > 0 and I > 0:
            wn = math.sqrt(k_rad / I)
            zeta = d_rad / (2.0 * math.sqrt(k_rad * I))
            wn_dt = wn * dt
            if wn_dt > STIFF_WN_DT_MAX:
                warn.append(f"zu steif (ω_n·Δt>{STIFF_WN_DT_MAX:g})")
                counts["steif"] += 1
            if zeta < ZETA_UNDER:
                warn.append("unterdämpft")
                counts["unter"] += 1
            elif zeta > ZETA_OVER:
                warn.append("stark überdämpft")
        else:
            wn = zeta = wn_dt = float("nan")
            if p is not None and k_deg == 0:
                warn.append("passiv (k=0)")
        sat = max_f / k_deg if (k_deg > 0 and math.isfinite(max_f)) else float("inf")
        if math.isfinite(max_f) and abs(grav[i]) > max_f:
            warn.append("Schwerkraft > maxForce")
            counts["grav"] += 1
        if p is not None and k_deg > 0 and (vel is None or vel >= VEL_UNLIMITED):
            warn.append("kein Vel-Limit")
            counts["vel"] += 1
        if target is not None and abs(math.degrees(q[i]) - target) > 2.0 and k_deg > 0:
            warn.append("Target ≠ Ist")
        emit(f"  {name:<26}{math.degrees(q[i]):7.1f}{_fmt(target, '.1f'):>8}{I:10.3g}{arm[i]:10.3g}{grav[i]:8.3f}"
             f"{('inf' if not math.isfinite(max_f) else format(max_f, '.2f')):>7}{wn:9.3g}{zeta:8.3g}{wn_dt:8.3g}"
             f"{('inf' if not math.isfinite(sat) else format(sat, '.3g')):>8}  {'; '.join(warn)}")
    emit(f"\n  Zusammenfassung: {counts['steif']} zu steif, {counts['unter']} unterdämpft, "
         f"{counts['grav']} mit Schwerkraft > maxForce, {counts['vel']} angetriebene ohne Vel-Limit "
         f"(von {len(dof_names)} DOFs)")


def main() -> None:
    emit(f"Stage: {stage.GetRootLayer().realPath}")
    urdf = _load_urdf()
    dt = audit_scene()
    roots = audit_articulation_roots()
    if not roots:
        return
    robot_root = roots[0]
    view = _physx_view(robot_root)
    audit_links(robot_root, urdf, view)
    audit_joints(robot_root, view, dt)
    emit("\nFertig.")


main()

_out_path = ROOT / "isaac_sim" / "tools" / "_asset_audit.txt"
_out_path.write_text(out.getvalue())
print(f"\nAusgabe geschrieben nach: {_out_path}")
