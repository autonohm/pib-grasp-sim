"""
build_fingertip_force_graph_v5.py — bundles the 10 fingertip contact forces of pib v5 into
ONE time-stamped topic, native nodes only (ADR-008 addendum):

  ReadContact_<finger> ×10   isaacsim.sensors.physics.IsaacReadContactSensor (existing, kept)
  FingertipForceArray        omni.graph.nodes.ConstructArray (arraySize 10, arrayType auto → float[])
      input0..input9 ← Reader.outputs:value   (force in N, float)
  FingertipForceToDouble     omni.graph.nodes.ToDouble  (float[] → double[], JointState expects double)
  FingertipForceTime         isaacsim.core.nodes.IsaacTimeSplitter
      time ← ReadSimTime.outputs:simulationTime
  PublisherFingertipForces   isaacsim.ros2.bridge.ROS2Publisher, sensor_msgs/JointState
      execIn ← on_physics_step, name = 10 finger names, effort ← FingertipForceToDouble.converted,
      header.stamp ← FingertipForceTime (simulation time)
      topic = /pib/fingertip_forces

The publisher's wiring and arrayType are written DIRECTLY INTO THE USD: values/connections set via
og.Controller only end up in the running graph, not in the file —
on the next rebuild from the USD (opening the file, renaming nodes) the publisher discards
its dynamic inputs ("remove dynamic attributes") and sends empty messages.
If they are in the USD, it reuses them on load ("reuse"). So after running:
save AND reopen the stage.

ConstructArray does NOT convert float to double (log: "Mismatched array element type ...
expected 'double', got 'float'"), hence the ToDouble node. If the graph already exists,
the script only repairs the wiring (idempotent).

Replaces the single publishers (PublishContact_<finger>, PublisherContactForces) and the old
index_right reader (isaac_read_contact_sensor_node) — these are deleted. Missing
ReadContact_<finger> nodes are created.

Afterwards do NOT rename/move nodes in the stage tree and do not create a compound without
having saved and reopened first: both operate on the running graph, which can differ from
the USD state — that is how a state that crashes on Play came about on 2026-10-03.

Readers and publisher hang in parallel on the trigger: the publisher may send the value of the previous
physics step (1 step of delay) — deliberately, an execOut chain would break,
because according to the node docs execOut only fires when the sensor has data.

Run in the Script Editor with pib_upperbody_v5.usd open and the simulation STOPPED.
Then SAVE and REOPEN the stage, start.py, Play, `ros2 topic echo /pib/fingertip_forces`.
Output (every step OK/FEHLER + attribute list of the publisher) to
isaac_sim/tools/_fingertip_force_graph_build.txt (gitignored).
"""
import io
from pathlib import Path

import omni.graph.core as og
import omni.usd
import usdrt
from pxr import Gf, Sdf, Vt

stage = omni.usd.get_context().get_stage()
out = io.StringIO()

ROBOT = "/World/pib_upperbody_urdf_v5"
GRAPH = "/Graph/ROS_JointStates"
TRIGGER = f"{GRAPH}/on_physics_step.outputs:step"
CONTEXT = f"{GRAPH}/Context.outputs:context"
SIM_TIME = f"{GRAPH}/ReadSimTime.outputs:simulationTime"
ARRAY = "FingertipForceArray"
TO_DOUBLE = "FingertipForceToDouble"
TIME = "FingertipForceTime"
PUB = "PublisherFingertipForces"
TOPIC = "/pib/fingertip_forces"

# order = order in JointState.name/effort
FINGERTIPS = {
    "thumb_left": "urdf_thumb_tip",
    "index_left": "urdf_finger_tip",
    "middle_left": "urdf_finger_tip_2",
    "ring_left": "urdf_finger_tip_3",
    "pinky_left": "urdf_finger_tip_4",
    "thumb_right": "urdf_thumb_tip_2",
    "index_right": "urdf_finger_tip_5",
    "middle_right": "urdf_finger_tip_6",
    "ring_right": "urdf_finger_tip_7",
    "pinky_right": "urdf_finger_tip_8",
}
# Leftovers from the copied v4 graph / the single topics — they are deleted. In the committed state the old index_right
# reader pointed with csPrim at the robot wrapper (wrong), so it is no longer
# reused: all 10 readers are uniformly named ReadContact_<finger>.
LEGACY_READERS = {"index_right": "isaac_read_contact_sensor_node"}
OLD_PUBLISHERS = ["PublisherContactForces"] + [f"PublishContact_{f}" for f in FINGERTIPS]
OLD_NODES = OLD_PUBLISHERS + list(LEGACY_READERS.values())


def emit(line: str = "") -> None:
    print(line)
    out.write(line + "\n")


def _find_project_root() -> Path:
    stage_file = Path(stage.GetRootLayer().realPath)
    for ancestor in [stage_file.parent, stage_file.parent.parent, stage_file.parent.parent.parent]:
        if (ancestor / "config" / "pib_hand_config_v4.py").is_file():
            return ancestor
    for candidate in [Path.home() / "repos" / "pib-hand-sim", Path.home() / "pib-hand-sim"]:
        if (candidate / "config" / "pib_hand_config_v4.py").is_file():
            return candidate
    raise FileNotFoundError("pib-hand-sim nicht gefunden.")


def _exists(node: str) -> bool:
    return bool(stage.GetPrimAtPath(f"{GRAPH}/{node}"))


def _step(label: str, fn) -> bool:
    try:
        fn()
        emit(f"  OK      {label}")
        return True
    except Exception as exc:  # noqa: BLE001
        emit(f"  FEHLER  {label}: {exc}")
        return False


def _set_pos(node: str, x: float, y: float) -> None:
    prim = stage.GetPrimAtPath(f"{GRAPH}/{node}")
    if prim:
        prim.CreateAttribute("ui:nodegraph:node:pos", Sdf.ValueTypeNames.Float2).Set(Gf.Vec2f(x, y))


def _inputs(node: str) -> list:
    return [a for a in og.Controller.node(f"{GRAPH}/{node}").get_attributes() if a.get_name().startswith("inputs:")]


def _connected(src: str, dst: str) -> bool:
    ups = og.Controller.attribute(dst).get_upstream_connections()
    return any(u.get_path() == src for u in ups)


def _connect_once(src: str, dst: str) -> None:
    if not _connected(src, dst):
        og.Controller.connect(og.Controller.attribute(src), og.Controller.attribute(dst))


def _reader_for(finger: str) -> str:
    return f"ReadContact_{finger}"


def _usd_attr(prim, name: str, vtype):
    attr = prim.GetAttribute(name)
    return attr if attr else prim.CreateAttribute(name, vtype, custom=True)


def _wire_output() -> None:
    """Array (auto) → ToDouble → effort, reader → array, time stamp, names — directly in the USD.
    Idempotent (rebuild and repair). Takes effect only after saving + reopening the stage."""
    keys = og.Controller.Keys
    if not _exists(TO_DOUBLE):
        _step("ToDouble anlegen", lambda: og.Controller.edit(GRAPH, {
            keys.CREATE_NODES: [(TO_DOUBLE, "omni.graph.nodes.ToDouble")]}))
    arr = stage.GetPrimAtPath(f"{GRAPH}/{ARRAY}")
    conv = stage.GetPrimAtPath(f"{GRAPH}/{TO_DOUBLE}")
    pub = stage.GetPrimAtPath(f"{GRAPH}/{PUB}")
    emit("5. Verdrahtung in die USD schreiben")
    _step("ConstructArray.arrayType = auto", lambda: arr.GetAttribute("inputs:arrayType").Set("auto"))
    for i, finger in enumerate(FINGERTIPS):
        reader = _reader_for(finger)
        _step(f"input{i} ← {reader}.value", lambda i=i, reader=reader: arr.GetAttribute(f"inputs:input{i}")
              .SetConnections([Sdf.Path(f"{GRAPH}/{reader}.outputs:value")]))
    _step("ToDouble.value ← array", lambda: conv.GetAttribute("inputs:value")
          .SetConnections([Sdf.Path(f"{GRAPH}/{ARRAY}.outputs:array")]))
    # All fields of sensor_msgs/JointState as dynamic inputs (names/types according to the log of
    # OgnROS2Publisher "create dynamic attributes") — complete, so that the publisher recognises them
    # as matching on load and reuses them
    fields = {
        "inputs:header:stamp:sec": Sdf.ValueTypeNames.Int,
        "inputs:header:stamp:nanosec": Sdf.ValueTypeNames.UInt,
        "inputs:header:frame_id": Sdf.ValueTypeNames.Token,
        "inputs:name": Sdf.ValueTypeNames.TokenArray,
        "inputs:position": Sdf.ValueTypeNames.DoubleArray,
        "inputs:velocity": Sdf.ValueTypeNames.DoubleArray,
        "inputs:effort": Sdf.ValueTypeNames.DoubleArray,
    }
    attrs = {}
    for name, vtype in fields.items():
        if _step(f"Publisher-Eingang {name}", lambda name=name, vtype=vtype: attrs.__setitem__(name, _usd_attr(pub, name, vtype))):
            pass
    _step("effort ← ToDouble.converted", lambda: attrs["inputs:effort"]
          .SetConnections([Sdf.Path(f"{GRAPH}/{TO_DOUBLE}.outputs:converted")]))
    _step("header:stamp:sec ← seconds", lambda: attrs["inputs:header:stamp:sec"]
          .SetConnections([Sdf.Path(f"{GRAPH}/{TIME}.outputs:seconds")]))
    _step("header:stamp:nanosec ← nanoseconds", lambda: attrs["inputs:header:stamp:nanosec"]
          .SetConnections([Sdf.Path(f"{GRAPH}/{TIME}.outputs:nanoseconds")]))
    _step("name = Fingernamen", lambda: attrs["inputs:name"].Set(Vt.TokenArray(list(FINGERTIPS))))
    _set_pos(TO_DOUBLE, 1100.0, 800.0)


def _diagnose() -> None:
    """Reads from the USD — that is the state that is saved and loaded on opening."""
    emit("\nDiagnose (USD):")
    for node in (ARRAY, TO_DOUBLE, PUB):
        prim = stage.GetPrimAtPath(f"{GRAPH}/{node}")
        emit(f"  {node}")
        for attr in prim.GetAttributes():
            name = attr.GetName()
            if not name.startswith("inputs:") or name in ("inputs:execIn", "inputs:context"):
                continue
            conns = [str(c) for c in attr.GetConnections()]
            value = attr.Get() if not conns else None
            if conns or value not in (None, "", [], 0, 0.0):
                emit(f"    {name}  [{attr.GetTypeName()}]  " + (f"<- {conns[0]}" if conns else f"= {value}"))


def main() -> None:
    if not stage.GetPrimAtPath(GRAPH):
        emit(f"Graph {GRAPH} nicht gefunden — falsche Stage offen?")
        return
    if _exists(PUB):
        emit(f"{PUB} existiert schon — Reparatur-Modus")
        old = [n for n in OLD_PUBLISHERS if _exists(n)]
        if old:
            _step(f"{len(old)} alte Einzel-Publisher löschen", lambda: og.Controller.edit(
                GRAPH, {og.Controller.Keys.DELETE_NODES: [og.Controller.node(f"{GRAPH}/{n}") for n in old]}))
        _wire_output()
        _diagnose()
        return
    missing = [f for f, link in FINGERTIPS.items() if not stage.GetPrimAtPath(f"{ROBOT}/{link}/Contact_Sensor")]
    if missing:
        emit(f"ABBRUCH: Sensor-Prims fehlen für {missing} — erst build_contact_sensors_v5.py.")
        return
    keys = og.Controller.Keys

    emit("1. Altlasten entfernen (Einzel-Publisher, alter index_right-Reader)")
    old = [n for n in OLD_NODES if _exists(n)]
    if old:
        # node objects instead of path strings: edit(GRAPH, ...) prefixes strings with the graph path
        # ("/Graph/X//Graph/X/Node" → not found)
        _step(f"{len(old)} Knoten löschen", lambda: og.Controller.edit(
            GRAPH, {keys.DELETE_NODES: [og.Controller.node(f"{GRAPH}/{n}") for n in old]}))
    else:
        emit("  keine vorhanden")

    emit("2. Reader zuordnen (vorhandene weiterverwenden)")
    readers = {}
    for finger, link in FINGERTIPS.items():
        name = f"ReadContact_{finger}"
        if _exists(name):
            readers[finger] = name
        else:
            sensor = f"{ROBOT}/{link}/Contact_Sensor"
            if _step(f"{name} anlegen", lambda name=name, sensor=sensor: og.Controller.edit(GRAPH, {
                keys.CREATE_NODES: [(name, "isaacsim.sensors.physics.IsaacReadContactSensor")],
                keys.SET_VALUES: [(f"{name}.inputs:csPrim", [usdrt.Sdf.Path(sensor)])],
                keys.CONNECT: [(TRIGGER, f"{name}.inputs:execIn")],
            })):
                readers[finger] = name
        emit(f"  {finger:<13} → {readers.get(finger, 'FEHLT')}")
    if len(readers) != len(FINGERTIPS):
        emit("ABBRUCH: nicht alle Reader vorhanden.")
        return

    emit("3. Array, Zeit, Publisher anlegen")
    if not _step("Knoten + Grundverbindungen", lambda: og.Controller.edit(GRAPH, {
        keys.CREATE_NODES: [(ARRAY, "omni.graph.nodes.ConstructArray"),
                            (TIME, "isaacsim.core.nodes.IsaacTimeSplitter"),
                            (PUB, "isaacsim.ros2.bridge.ROS2Publisher")],
        keys.SET_VALUES: [(f"{ARRAY}.inputs:arraySize", len(FINGERTIPS)),
                          (f"{ARRAY}.inputs:arrayType", "auto"),
                          (f"{PUB}.inputs:messagePackage", "sensor_msgs"),
                          (f"{PUB}.inputs:messageSubfolder", "msg"),
                          (f"{PUB}.inputs:messageName", "JointState"),
                          (f"{PUB}.inputs:topicName", TOPIC)],
        # existing nodes with full path (relative names only for newly created ones)
        keys.CONNECT: [(TRIGGER, f"{PUB}.inputs:execIn"),
                       (CONTEXT, f"{PUB}.inputs:context"),
                       (SIM_TIME, f"{TIME}.inputs:time")],
    })):
        return

    emit("4. ConstructArray: Eingänge input1..input9 + Reader verbinden")
    _step("dynamische Eingänge", lambda: og.Controller.edit(GRAPH, {
        keys.CREATE_ATTRIBUTES: [(f"{GRAPH}/{ARRAY}.inputs:input{i}", "any") for i in range(1, len(FINGERTIPS))]}))
    for i, (finger, reader) in enumerate(readers.items()):
        _step(f"{reader}.value → input{i} ({finger})", lambda reader=reader, i=i: og.Controller.connect(
            og.Controller.attribute(f"{GRAPH}/{reader}.outputs:value"),
            og.Controller.attribute(f"{GRAPH}/{ARRAY}.inputs:input{i}")))

    _wire_output()

    for i, reader in enumerate(readers.values()):
        _set_pos(reader, 600.0, 400.0 + 110.0 * i)
    _set_pos(ARRAY, 950.0, 800.0)
    _set_pos(TIME, 950.0, 600.0)
    _set_pos(PUB, 1250.0, 700.0)

    _diagnose()
    emit(f"\nFertig. Stage SPEICHERN, Stage NEU ÖFFNEN (File → Open), start.py, Play, "
         f"dann `ros2 topic echo {TOPIC}`.")
    emit("Optional im GUI: Reader, Array, Zeit, Publisher markieren → Rechtsklick → Make Compound.")


main()

_out_path = _find_project_root() / "isaac_sim" / "tools" / "_fingertip_force_graph_build.txt"
_out_path.write_text(out.getvalue())
print(f"\nAusgabe geschrieben nach: {_out_path}")
