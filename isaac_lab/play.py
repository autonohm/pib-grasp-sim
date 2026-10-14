"""play.py — like train.py, runs Isaac Lab's rsl_rl/play.py (loads the last checkpoint,
exports the policy as ONNX/JIT to <log>/exported/)."""
import os
import runpy
from pathlib import Path

os.environ["PIB_RSL_RL_SCRIPT"] = "play"

runpy.run_path(str(Path(__file__).resolve().parent / "train.py"), run_name="__main__")
