"""
inspect_action_graph.py — lists all OmniGraph action graphs of the open stage with their
nodes, attribute values, actual connections (exec and data pins) and relationships,
plus all ContactSensor prims of the stage and which relationships point to them.
Changes nothing.

Intended as the basis for the contact sensors (ADR-008): run once on v4 (where
index_right is verified = reference wiring), once on v5.

Writes to isaac_sim/tools/_action_graph_inventory_<stage>.txt (gitignored).
Run in the Script Editor, play state does not matter.
"""
import io
from pathlib import Path

import omni.usd

stage = omni.usd.get_context().get_stage()
out = io.StringIO()


def emit(line: str = "") -> None:
    print(line)
    out.write(line + "\n")


emit(f"Stage: {stage.GetRootLayer().realPath}\n")

graph_prims = [p for p in stage.Traverse() if p.GetTypeName() == "OmniGraph"]

if not graph_prims:
    emit("Keine Prims vom Typ 'OmniGraph' gefunden.")
else:
    for gp in graph_prims:
        emit(f"=== Action Graph: {gp.GetPath()} ===")
        for node in gp.GetChildren():
            emit(f"  {node.GetPath()}  [{node.GetTypeName()}]")
            for attr in node.GetAttributes():
                name = attr.GetName()
                if not (name.startswith("inputs:") or name.startswith("outputs:") or name.startswith("state:")):
                    continue
                conns = attr.GetConnections()
                if conns:
                    emit(f"      {name} <- {[str(c) for c in conns]}")
                    continue
                if not name.startswith("inputs:"):
                    continue
                try:
                    value = attr.Get()
                except Exception as exc:  # noqa: BLE001 — reine Diagnoseausgabe
                    value = f"<Fehler: {exc}>"
                if value in (None, "", [], 0.0):
                    continue
                emit(f"      {name} = {value!r}")
            # Relationships (e.g. targetPrim, or a possible csPrim/sensorPrim reference
            # of a contact sensor read node) — GetAttributes() above does NOT see them.
            for rel in node.GetRelationships():
                targets = rel.GetTargets()
                if targets:
                    emit(f"      {rel.GetName()} (rel) -> {[str(t) for t in targets]}")
        emit()

# ── ContactSensor prims (whole stage, not only Action Graph children) ─────────
# ADR-008: "native IsaacContactSensor prim" — type name compared deliberately as a
# string (no schema import) so as not to guess anything about the actual Isaac Sim API;
# "contactsensor" case-insensitive as a substring in case the exact
# spelling differs.
emit("=== ContactSensor-Prims (ganze Stage) ===")
sensor_prims = [p for p in stage.Traverse() if "contactsensor" in p.GetTypeName().lower()]
if not sensor_prims:
    emit("Keine Prims gefunden, deren TypeName 'contactsensor' enthält.")
else:
    for sp in sensor_prims:
        emit(f"  {sp.GetPath()}  [{sp.GetTypeName()}]  Parent: {sp.GetParent().GetPath()}")
        for attr in sp.GetAttributes():
            name = attr.GetName()
            try:
                value = attr.Get()
            except Exception as exc:  # noqa: BLE001 — reine Diagnoseausgabe
                value = f"<Fehler: {exc}>"
            if value in (None, "", [], 0.0):
                continue
            emit(f"      {name} = {value!r}")
emit()

# Which nodes/relationships point to one of the sensor prims above?
if sensor_prims:
    sensor_paths = {sp.GetPath() for sp in sensor_prims}
    emit("=== Relationships, die auf einen ContactSensor-Prim zeigen ===")
    for prim in stage.Traverse():
        for rel in prim.GetRelationships():
            targets = set(rel.GetTargets())
            hit = targets & sensor_paths
            if hit:
                emit(f"  {prim.GetPath()}.{rel.GetName()} -> {[str(t) for t in hit]}")
    emit()

emit("Fertig.")


def _find_project_root() -> Path:
    # __file__ is not defined in the Script Editor (exec context) — find the root from the
    # open stage instead, as in setup_stage.py.
    stage_file = Path(stage.GetRootLayer().realPath)
    for ancestor in [stage_file.parent, stage_file.parent.parent, stage_file.parent.parent.parent]:
        if (ancestor / "config" / "pib_hand_config_v4.py").is_file():
            return ancestor
    for candidate in [Path.home() / "repos" / "pib-hand-sim", Path.home() / "pib-hand-sim"]:
        if (candidate / "config" / "pib_hand_config_v4.py").is_file():
            return candidate
    raise FileNotFoundError("pib-hand-sim nicht gefunden.")


_out_path = (_find_project_root() / "isaac_sim" / "tools"
             / f"_action_graph_inventory_{Path(stage.GetRootLayer().realPath).stem}.txt")
_out_path.write_text(out.getvalue())
print(f"\nAusgabe geschrieben nach: {_out_path}")
