"""
isaac_sim/start.py — session start routine for pib in Isaac Sim.

Run before the first Play. Configures drives, limits and the initial pose —
PhysX does not cache these values, they must be set after every session start.

Script Editor workflow:
  load the USD (contains the Action Graph) → start.py → Play
"""
import os
import sys
import importlib
import importlib.util
from pathlib import Path


def _find_root() -> Path:
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


_root = _find_root()


def _load_setup_stage():
    sys.modules.pop("_setup_stage_start", None)
    importlib.invalidate_caches()
    path = os.path.join(_root, "isaac_sim", "setup_stage.py")
    spec = importlib.util.spec_from_file_location("_setup_stage_start", path)
    mod  = importlib.util.module_from_spec(spec)
    mod._SKIP_AUTO_SETUP = True
    spec.loader.exec_module(mod)
    return mod


def run(stg=None) -> None:
    """
    Session start routine: configure_drives → configure_mimic_joints → set_joint_limits
    → set_initial_pose.

    stg: USD stage. If None, it is obtained via omni.usd.get_context() (Script Editor).
    """
    if stg is None:
        import omni.usd  # type: ignore
        stg = omni.usd.get_context().get_stage()

    _ss = _load_setup_stage()
    _ss.configure_drives(stg)
    _ss.configure_mimic_joints(stg)
    _ss.set_joint_limits(stg)
    _ss.set_initial_pose(stg)
    print("[start] Session-Setup abgeschlossen — Drives, Mimic Joints, Limits, Initialpose gesetzt.")


# ── Script-Editor-Block ───────────────────────────────────────────────────────
if not globals().get("_SKIP_AUTO_SETUP"):
    run()
