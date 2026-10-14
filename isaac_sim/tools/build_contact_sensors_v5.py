"""
build_contact_sensors_v5.py — phase 1: creates the IsaacContactSensor prims on all 10
fingertips of pib v5 (ADR-008 pattern), following the GUI template index_right:

  <fingertip link>/Contact_Sensor   IsaacContactSensor, radius -1 (whole link),
                                    threshold 0..100000, PhysxContactReportAPI on the link

ONLY the sensor prims — no graph nodes (those are wired in phase 2,
build_fingertip_force_graph_v5.py). Separated to narrow down whether Isaac crashes because of the sensors
or because of the graph nodes. Idempotent: existing sensors stay unchanged.

Run in the Script Editor with pib_upperbody_v5.usd open and the simulation STOPPED.
Then save the stage (Ctrl+S). Output additionally to
isaac_sim/tools/_contact_sensors_build.txt (gitignored).
"""
import io
from pathlib import Path

import omni.kit.commands
import omni.usd
from pxr import Gf

stage = omni.usd.get_context().get_stage()
out = io.StringIO()

ROBOT = "/World/pib_upperbody_urdf_v5"

# fingertips → child link of the *_tip joint (from ros2_ws/src/pib_description_v5/urdf/pib_upperbody_v5.urdf).
# Order = order in the bundled topic (phase 2).
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


def _ensure_sensor(link_path: str) -> str:
    sensor_path = f"{link_path}/Contact_Sensor"
    if stage.GetPrimAtPath(sensor_path):
        emit(f"    vorhanden: {sensor_path}")
        return sensor_path
    link = stage.GetPrimAtPath(link_path)
    if not link:
        raise RuntimeError(f"Link nicht gefunden: {link_path}")
    if link.IsInstanceProxy() or link.IsInstance():
        raise RuntimeError(f"{link_path} ist instanceable — erst Instanceable ausschalten (ADR-008)")
    # same command and same parameters as the GUI template (index_right)
    omni.kit.commands.execute(
        "IsaacSensorCreateContactSensor",
        path="/Contact_Sensor",
        parent=link_path,
        min_threshold=0.0,
        max_threshold=100000.0,
        color=Gf.Vec4f(1.0, 0.0, 0.0, 1.0),
        radius=-1.0,
        sensor_period=-1.0,
    )
    if not stage.GetPrimAtPath(sensor_path):
        raise RuntimeError(f"Sensor wurde nicht unter {sensor_path} angelegt")
    emit(f"    angelegt:  {sensor_path}")
    return sensor_path


def main() -> None:
    failed = []
    for finger, link in FINGERTIPS.items():
        emit(f"{finger} ({link})")
        try:
            _ensure_sensor(f"{ROBOT}/{link}")
        except Exception as exc:  # noqa: BLE001
            emit(f"    FEHLER: {exc}")
            failed.append(finger)
    emit(f"\nFertig: {len(FINGERTIPS) - len(failed)} von {len(FINGERTIPS)} Sensoren vorhanden"
         f"{f', Fehler: {failed}' if failed else ''}")
    emit("Jetzt Stage speichern (Ctrl+S). Bleibt Isaac stabil, Phase 2: "
         "build_fingertip_force_graph_v5.py")


main()

_out_path = _find_project_root() / "isaac_sim" / "tools" / "_contact_sensors_build.txt"
_out_path.write_text(out.getvalue())
print(f"\nAusgabe geschrieben nach: {_out_path}")
