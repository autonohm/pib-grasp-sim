"""
isaac_sim/autostart.py — automatic startup for Isaac Sim.

Started via --exec (no Script Editor needed):
  ~/isaacsim/isaac-sim.sh --exec <repo>/isaac_sim/autostart.py

Sequence (fully automatic):
  1. load the USD (contains the ROS 2 Action Graph — no pib_bridge.py needed any more)
  2. run start.py (drives, limits, T pose)
  3. start the simulation (Play) — the Action Graph runs along from here on
"""
import sys
import os
import importlib
import importlib.util
import asyncio

import carb  # type: ignore

_log = carb.log_warn


def _find_root() -> str:
    if "PIB_HAND_SIM_ROOT" in os.environ:
        return os.environ["PIB_HAND_SIM_ROOT"]
    from pathlib import Path
    candidate = Path(__file__).parent.parent
    if (candidate / "config" / "pib_hand_config_v4.py").is_file():
        return str(candidate)
    for p in ["~/repos/pib-hand-sim", "~/pib-hand-sim"]:
        expanded = os.path.expanduser(p)
        if os.path.isfile(os.path.join(expanded, "config", "pib_hand_config_v4.py")):
            return expanded
    raise FileNotFoundError("Projekt nicht gefunden. PIB_HAND_SIM_ROOT setzen.")


def _load_mod(name, path, **pre_attrs):
    sys.modules.pop(name, None)
    importlib.invalidate_caches()
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    for k, v in pre_attrs.items():
        setattr(mod, k, v)
    spec.loader.exec_module(mod)
    return mod


async def _main() -> None:
    import omni.kit.app as _app_mod  # type: ignore
    import omni.usd            # type: ignore
    import omni.timeline        # type: ignore

    app      = _app_mod.get_app()
    timeline = omni.timeline.get_timeline_interface()
    root     = _find_root()

    # ── 1. USD laden ─────────────────────────────────────────────────────────
    usd_path = os.path.join(root, "isaac_sim", "usd", "pib_upperbody_v4.usd")
    if not os.path.isfile(usd_path):
        _log(f"[autostart] FEHLER: USD nicht gefunden: {usd_path}")
        return

    _log(f"[autostart] Lade USD: {usd_path}")
    success, _ = await omni.usd.get_context().open_stage_async(usd_path)
    if not success:
        _log("[autostart] FEHLER: USD konnte nicht geladen werden.")
        return
    await app.next_update_async()
    _log("[autostart] USD geladen.")

    # ── 2. run start.py (drives, limits, T pose) ─────────────────────────────
    _log("[autostart] Führe start.py aus...")
    start = _load_mod("start", os.path.join(root, "isaac_sim", "start.py"))
    # start.py is an async script → uses ensure_future internally
    # we wait a few frames so that configure_* has finished
    for _ in range(10):
        await app.next_update_async()
    _log("[autostart] start.py abgeschlossen.")

    # ── 3. Simulation starten ─────────────────────────────────────────────────
    _log("[autostart] Starte Simulation (Play)...")
    timeline.play()
    await app.next_update_async()
    _log("[autostart] Simulation läuft — Action Graph aktiv. Bereit.")


asyncio.ensure_future(_main())
