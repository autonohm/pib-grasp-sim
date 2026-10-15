"""
eval_policy.py — evaluate a policy with the evaluation protocol eval-v2 (experiments/README.md, ADR-021).

eval-v2 (since 2026-10-09) = eval-v1 with a reset without overlap and fall (start pose almost open, placement by
actual size and yaw rotation, YCB in its rest pose — env_cfg/mdp); eval-v1 files stay as history.

Exported actor (TorchScript, deterministic) in the grasping task; only the terminations
"object dropped" and "physics unstable" are active, the tilt angle is measured. Per episode:
end, largest tilt angle, forearm rotation, grip force/force > 15 N in the hold phase,
stall share, sinking, jitter, object path (displacement of the object centre in the table plane vs. t = 0.1 s, since
2026-10-10 — finding tools/diag_objektweg.py: the policies pull the object towards the forearm).
Output: <protokoll>.txt + <protokoll>.json (metrics, success per episode for the bootstrap in experiments.py) — one file
per protocol version, nothing is overwritten by a new version. Another condition (object from env_cfg.OBJECTS):
--objekt quader_7x7x20 --bedingung quader_seitlich → <protokoll>_<bedingung>.json/.txt; grasp type "top"
(env_cfg_oben): --greifart oben --objekt kugel_d7 --bedingung kugel_d7_oben --max_kipp_deg -1
(the default condition zylinder_seitlich stays <protokoll>.json).

  ~/IsaacLab/isaaclab.sh -p isaac_lab/eval_policy.py --policy <run>/exported/policy.pt --num_envs 16 --real_time
  ~/IsaacLab/isaaclab.sh -p isaac_lab/eval_policy.py --checkpoint <run>/model_299.pt --headless
With --checkpoint: loads like Isaac Lab's play.py and exports to <run>/exported/ (JIT + ONNX).
With --video N: records the first N steps (<out>/videos/), needs cameras. --kamera 2x2: 4 hands closer;
--kamera einzeln: one hand from two angles side by side (one run, both halves show the same episodes).
With --verlauf: additionally the time series over the episode (per time step, mean over running episodes:
object height vs. start, tilt angle, fingers on the object, grip force, fraction of running episodes) →
verlauf-v1[_<bedingung>].json. --nur-medien: write no evaluation files (video/time series only,
does not overwrite an existing evaluation).
"""
import argparse
import sys
from pathlib import Path

from isaaclab.app import AppLauncher

PROTOCOL = "eval-v2"                                        # experiments.PROTOKOLL

parser = argparse.ArgumentParser()
src = parser.add_mutually_exclusive_group(required=True)
src.add_argument("--policy", type=str, help="exported/policy.pt (TorchScript)")
src.add_argument("--checkpoint", type=str, help="model_<n>.pt eines Trainingslaufs (wird exportiert)")
src.add_argument("--onnx", type=str, help="Policy als ONNX (float oder int8 QDQ) über onnxruntime auf der CPU — M2: "
                 "int8 gegen float in der Sim (tools/quantisiere_int8.py)")
src.add_argument("--regel", type=str, choices=["alle_schliessen", "bis_kontakt"],
                 help="regelbasierter Griff statt Policy (Baseline, EXP-014/015)")
parser.add_argument("--regel-param", dest="regel_param", type=str, default="",
                    help="Parameter der Regel, z. B. schliessen=0.4,nachdruck_deg=5,rotator_deg=90")
parser.add_argument("--num_envs", type=int, default=256)
parser.add_argument("--episodes", type=int, default=1000, help="Zahl der gewerteten Episoden")
parser.add_argument("--seed", type=int, default=1000, help="Bewertungs-Seed (≠ Trainings-Seeds)")
parser.add_argument("--max_kipp_deg", type=float, default=20.0, help="Anforderung; < 0 = keine")
parser.add_argument("--greifart", choices=["seitlich", "oben"], default="seitlich",
                    help="Szene: seitlich (env_cfg) oder von oben (env_cfg_oben, Stufe 4b)")
parser.add_argument("--objekt", type=str, default=None,
                    help="Objekt aus env_cfg.OBJECTS bzw. env_cfg_oben.OBJECTS_OBEN (Standard zylinder_d6 / kugel_d7)")
parser.add_argument("--bedingung", type=str, default="zylinder_seitlich", help="Name der Bedingung (Dateiname)")
parser.add_argument("--out", type=str, default=None, help="Ausgabeordner (<protokoll>.json/.txt); "
                    "Standard: Laufordner bzw. isaac_sim/tools/")
parser.add_argument("--video", type=int, default=0, help="Schritte Video am Anfang (0 = aus)")
parser.add_argument("--kamera", choices=["raster", "2x2", "einzeln"], default="raster",
                    help="Video-Ansicht: alle Umgebungen (Standard), 2×2 Hände oder eine Hand aus zwei Winkeln "
                         "nebeneinander (setzt --num_envs auf 4 bzw. 1)")
parser.add_argument("--real_time", action="store_true", help="Auf Echtzeit bremsen (zum Zuschauen)")
parser.add_argument("--verlauf", action="store_true", help="Verlauf über die Episode messen")
parser.add_argument("--action_clip", type=float, default=0.0,
                    help="Policy-Ausgabe auf ±Wert begrenzen wie im Training (agent clip_actions, EXP-020 ff.); 0 = aus")
parser.add_argument("--action_filter", type=float, default=0.0,
                    help="Aktion wie im Training glätten (gleitender Mittelwert, α; EXP-024 ff.); 0 = aus")
parser.add_argument("--action_scale", type=float, default=0.0,
                    help="einheitliche Aktionsskala aller Servos wie im Training (Aktionsraum wie Dexsuite, EXP-027 ff.); 0 = Standard")
parser.add_argument("--servo_last", action="store_true",
                    help="Policy sieht die Servo-Last wie im Training (EXP-037: env_cfg.add_servo_load_obs, Eingang 145)")
parser.add_argument("--stoerung", action="store_true",
                    help="Störbedingung (Leaderboard v3, Robustheit): Objektlage stärker gestreut (ungenaue Vorgreifpose), "
                         "1 Policy-Schritt Verzögerung, Rauschen auf Gelenkwinkeln und FSR")
parser.add_argument("--bewegung", type=str, default="",
                    help="Belastungstest Armbewegung ART:PARAM (Scheinkräfte, mdp.apply_arm_motion): rampe:40 (a_max m/s², "
                         "bis zum Versagen), transport:5 (a_max), gieren:0.6 / nicken:0.6 (Dauer s für 45°); leer = aus")
parser.add_argument("--nur-medien", dest="nur_medien", action="store_true",
                    help="keine eval-Dateien schreiben (nur Video/Verlauf)")
AppLauncher.add_app_launcher_args(parser)
args_cli = parser.parse_args()
if args_cli.video:
    args_cli.enable_cameras = True
simulation_app = AppLauncher(args_cli).app

import json  # noqa: E402
import math  # noqa: E402
import os  # noqa: E402
import time  # noqa: E402

import gymnasium as gym  # noqa: E402
import torch  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pib_grasp  # noqa: E402,F401
from pib_grasp import mdp  # noqa: E402
from pib_grasp.env_cfg import DROP_DEPTH, DROP_SPEED, GRASP_TIME_S, PibGraspEnvCfg, apply_object  # noqa: E402
from pib_hand_left_v5_cfg import SERVO_JOINTS, WRIST_JOINT  # noqa: E402

HOLD_START_S = GRASP_TIME_S + DROP_DEPTH / DROP_SPEED     # table down → hold phase
EARLY_S = 0.1                                              # start failure (reset overlap)
FORCE_LIMIT_N = 15.0
STALL_FRACTION = 0.9
# Overload protection of the STS3215 (datasheet): > 80 % stall torque for longer than 2 s (night run 2026-10-13; values not
# checked on the real servo) — stall duration = longest continuous run per servo, protection share = episodes with a run > 2 s
PROTECT_FRACTION = 0.8
PROTECT_S = 2.0
REQ_DEG = args_cli.max_kipp_deg if args_cli.max_kipp_deg >= 0 else None
BEW_ART, BEW_PARAM = (args_cli.bewegung.split(":")[0], float(args_cli.bewegung.split(":")[1])) if args_cli.bewegung else (None, 0.0)
RUTSCH_M = 0.02          # slip = object > 2 cm relative to the hand after motion start (GenDexGrasp/GAGrasp)

# ── Environment: as in training, only the terminations "dropped" and "unstable" ─────────────
if args_cli.greifart == "oben":
    from pib_grasp.env_cfg_oben import DEFAULT_OBJECT_OBEN, PibGraspEnvCfg_Oben, apply_object_oben
    args_cli.objekt = args_cli.objekt or DEFAULT_OBJECT_OBEN
    cfg, TASK = apply_object_oben(PibGraspEnvCfg_Oben(), args_cli.objekt), "Pib-Grasp-Hand-Left-Oben-v0"
else:
    args_cli.objekt = args_cli.objekt or "zylinder_d6"
    cfg, TASK = apply_object(PibGraspEnvCfg(), args_cli.objekt), "Pib-Grasp-Hand-Left-v0"
cfg.scene.num_envs = args_cli.num_envs
cfg.seed = args_cli.seed
# Close-up video views. The env grid is centred on the world origin (1 env: env 0 at the origin), so a target in the
# env frame also works in world coordinates. "a" = viewing direction of the raster camera (env cfg), "b" = second angle
# for "einzeln" (from the palm/object side). Distances in m.
KAMERA = {
    "seitlich": {"ziel": (-0.05, -0.31, 0.52), "a": (1.75, -1.75, 1.31), "b": (-1.2, -1.6, 0.9)},
    "oben": {"ziel": (-0.02, -0.29, 0.31), "a": (1.45, -2.1, 1.1), "b": (-1.6, -1.4, 0.7)},   # oben: not checked yet
}
KAMERA_ABSTAND = {"2x2": 1.5, "einzeln": 0.34}
KAMERA_B = "/World/KameraB"


def kamera_eye(ziel, richtung, abstand):
    n = math.sqrt(sum(x * x for x in richtung))
    return tuple(z + abstand * x / n for z, x in zip(ziel, richtung))


if args_cli.kamera != "raster":
    k = KAMERA[args_cli.greifart]
    cfg.scene.num_envs = 4 if args_cli.kamera == "2x2" else 1
    cfg.viewer.lookat = k["ziel"]
    cfg.viewer.eye = kamera_eye(k["ziel"], k["a"], KAMERA_ABSTAND[args_cli.kamera])
    cfg.viewer.resolution = (1920, 1080) if args_cli.kamera == "2x2" else (960, 1080)   # einzeln: 2 halves → 1920×1080
if args_cli.action_filter > 0:                                 # as in training (env.yaml: actions.servos.alpha)
    from pib_grasp.env_cfg import filtered_servo_action
    cfg.actions.servos = filtered_servo_action(args_cli.action_filter)
if args_cli.action_scale > 0:                                  # as in training (env.yaml: actions.servos.scale)
    cfg.actions.servos.scale = args_cli.action_scale
if args_cli.servo_last:                                    # as in training (env.yaml: observations.policy.servo_load)
    from pib_grasp.env_cfg import add_servo_load_obs
    add_servo_load_obs(cfg)
if args_cli.stoerung:
    # Robustness (leaderboard v3, sim-to-real gaps docs/protokoll/pruefung-aktionsweg.md): inaccurate pre-grasp pose as an IK team
    # would deliver it (side: object up to 2 cm further away / 1 cm closer, ±3 cm along the fingers; top ±1.5 cm), sensor noise
    # (joint angles σ 0.01 rad, FSR σ 0.5 N, before the history) and 1 policy step of delay (≈ 17 ms, in the loop)
    from isaaclab.utils.noise import GaussianNoiseCfg as Gnoise
    pr = cfg.events.reset_object.params["pose_range"]
    if args_cli.greifart == "oben":
        pr.update(x=(-0.015, 0.015), y=(-0.015, 0.015))
        cfg.events.place_objects.params["height_jitter"] = 0.005           # height of the pre-grasp pose ±5 mm
    else:
        pr.update(x=(-0.02, 0.01), y=(-0.03, 0.03))
    cfg.observations.policy.joint_pos.noise = Gnoise(mean=0.0, std=0.01)
    cfg.observations.policy.fsr.noise = Gnoise(mean=0.0, std=0.5)
    cfg.observations.policy.enable_corruption = True
if getattr(cfg.terminations, "object_tilted", None) is not None:   # training-specific (EXP-001/002)
    cfg.terminations.object_tilted = None
    cfg.rewards.early_termination = None      # refers to object_tilted; reward unused here
torch.manual_seed(args_cli.seed)
env = gym.make(TASK, cfg=cfg, render_mode="rgb_array" if args_cli.video else None)
uenv = env.unwrapped
if args_cli.video and args_cli.kamera == "einzeln":
    # Second camera with the optics of the viewport camera; one render pass feeds both, render() returns them
    # side by side (RecordVideo calls render() of the unwrapped env)
    import numpy as np
    import omni.replicator.core as rep
    import omni.usd
    from pxr import Gf, UsdGeom
    stage = omni.usd.get_context().get_stage()
    cam_a = UsdGeom.Camera(stage.GetPrimAtPath(cfg.viewer.cam_prim_path))
    cam_b = UsdGeom.Camera.Define(stage, KAMERA_B)
    for get, make in ((cam_a.GetFocalLengthAttr, cam_b.CreateFocalLengthAttr),
                      (cam_a.GetHorizontalApertureAttr, cam_b.CreateHorizontalApertureAttr),
                      (cam_a.GetVerticalApertureAttr, cam_b.CreateVerticalApertureAttr),
                      (cam_a.GetClippingRangeAttr, cam_b.CreateClippingRangeAttr)):
        make().Set(get().Get())
    k = KAMERA[args_cli.greifart]
    eye_b = kamera_eye(k["ziel"], k["b"], KAMERA_ABSTAND["einzeln"])
    view = Gf.Matrix4d().SetLookAt(Gf.Vec3d(*eye_b), Gf.Vec3d(*k["ziel"]), Gf.Vec3d(0, 0, 1))
    UsdGeom.Xformable(cam_b).AddTransformOp().Set(view.GetInverse())
    rp_b = rep.create.render_product(KAMERA_B, cfg.viewer.resolution)
    rgb_b = rep.AnnotatorRegistry.get_annotator("rgb", device="cpu")
    rgb_b.attach([rp_b])
    render_a = uenv.render

    def render_beide(recompute: bool = False):
        a = render_a(recompute)
        b = np.frombuffer(rgb_b.get_data(), dtype=np.uint8)
        b = b.reshape(*rgb_b.get_data().shape)[:, :, :3] if b.size else np.zeros_like(a)
        return np.hstack([a, b])

    uenv.render = render_beide

if args_cli.checkpoint:
    # as in ~/IsaacLab/scripts/reinforcement_learning/rsl_rl/play.py: load, export the actor
    from isaaclab_rl.rsl_rl import RslRlVecEnvWrapper, export_policy_as_jit, export_policy_as_onnx
    from rsl_rl.runners import OnPolicyRunner
    from pib_grasp.agents.rsl_rl_ppo_cfg import PibGraspPPORunnerCfg
    agent_cfg = PibGraspPPORunnerCfg()
    # network size as in training (EXP-031/032: actor 512-256-128) from the run's params/agent.yaml
    agent_yaml = os.path.join(os.path.dirname(args_cli.checkpoint), "params", "agent.yaml")
    if os.path.exists(agent_yaml):
        import yaml
        with open(agent_yaml, encoding="utf-8") as f:
            trained = (yaml.unsafe_load(f) or {}).get("policy") or {}
        for key in ("actor_hidden_dims", "critic_hidden_dims", "activation"):
            if trained.get(key):
                setattr(agent_cfg.policy, key, list(trained[key]) if key != "activation" else trained[key])
    runner = OnPolicyRunner(RslRlVecEnvWrapper(env, clip_actions=agent_cfg.clip_actions), agent_cfg.to_dict(),
                            log_dir=None, device=uenv.device)
    # Only the actor is evaluated: skip critic weights with a different shape — training variants with
    # privileged extra observations (EXP-021: +6 critic inputs) would not load into the base task otherwise
    ckpt = torch.load(args_cli.checkpoint, map_location=uenv.device, weights_only=False)
    own = runner.alg.policy.state_dict()
    state = {k: v for k, v in ckpt["model_state_dict"].items() if k in own and own[k].shape == v.shape}
    skipped = sorted(set(ckpt["model_state_dict"]) - set(state))
    assert not [k for k in skipped if not k.startswith("critic")], f"Actor passt nicht: {skipped}"
    runner.alg.policy.load_state_dict(state, strict=False)
    if skipped:
        print(f"[eval] Critic-Gewichte übersprungen (andere Form, für die Bewertung unnötig): {skipped}", flush=True)
    export_dir = os.path.join(os.path.dirname(args_cli.checkpoint), "exported")
    normalizer = getattr(runner.alg.policy, "actor_obs_normalizer", None)
    export_policy_as_jit(runner.alg.policy, normalizer=normalizer, path=export_dir, filename="policy.pt")
    export_policy_as_onnx(runner.alg.policy, normalizer=normalizer, path=export_dir, filename="policy.onnx")
    args_cli.policy = os.path.join(export_dir, "policy.pt")

if args_cli.regel:
    args_cli.policy = f"regel:{args_cli.regel}:{args_cli.regel_param}"
if args_cli.onnx:
    args_cli.policy = args_cli.onnx
out_dir = Path(args_cli.out) if args_cli.out else (
    Path(args_cli.policy).resolve().parent.parent if "exported" in args_cli.policy
    else Path(__file__).resolve().parent.parent / "isaac_sim" / "tools")
out_dir.mkdir(parents=True, exist_ok=True)
STEM = PROTOCOL if args_cli.bedingung == "zylinder_seitlich" else f"{PROTOCOL}_{args_cli.bedingung}"


class StreamingRecordVideo(gym.wrappers.RecordVideo):
    """RecordVideo that pipes every frame straight into ffmpeg. gymnasium 1.2 keeps all frames in RAM until the end
    (6 episodes at 1920×1080 ≈ 10 GB → kernel OOM kill on 2026-10-15); here memory stays constant with video length.
    Same writer and codec as gymnasium (moviepy FFMPEG_VideoWriter, libx264)."""

    class _Sink:
        # stands in for the recorded_frames list: RecordVideo only appends, extends and checks len()
        def __init__(self, path: str, fps: float):
            self.path, self.fps, self.writer, self.n = path, fps, None, 0

        def append(self, frame):
            if self.writer is None:
                from moviepy.video.io.ffmpeg_writer import FFMPEG_VideoWriter
                self.writer = FFMPEG_VideoWriter(self.path, (frame.shape[1], frame.shape[0]), self.fps)
            self.writer.write_frame(frame)
            self.n += 1

        def __iadd__(self, frames):
            for f in frames:
                self.append(f)
            return self

        def __len__(self):
            return self.n

        def close(self):
            if self.writer is not None:
                self.writer.close()

    def start_recording(self, video_name: str):
        super().start_recording(video_name)
        self.recorded_frames = self._Sink(os.path.join(self.video_folder, f"{video_name}.mp4"), self.frames_per_sec)

    def stop_recording(self):
        assert self.recording, "stop_recording was called, but no recording was started"
        self.recorded_frames.close()
        self.recorded_frames, self.recording, self._video_name = [], False, None


if args_cli.video:
    env = StreamingRecordVideo(env, video_folder=str(out_dir / ("videos" if STEM == PROTOCOL else f"videos_{args_cli.bedingung}")), step_trigger=lambda s: s == 0,
                                   video_length=args_cli.video, disable_logger=True)
class RuleGrasp(torch.nn.Module):
    """Rule-based grasp in the same action space as the policy (relative servo targets, scale like ActionsCfg) and
    only with the same sensors (joint angles, FSR). Until rot_s: thumb rotator to rotator_deg, otherwise hold.
    Then thumb and fingers close with 'schliessen' (fraction of the maximum step per 1/60 s).
    alle_schliessen: keep closing until the stop (heuristic like Chen et al. 2022).
    bis_kontakt: per finger, once FSR > kontakt_n, only push on by nachdruck_deg (Hsiao et al. 2010).
    Wrist and forearm hold their start position."""

    def __init__(self, env, name: str, params: str):
        super().__init__()
        p = {"schliessen": 0.4, "rotator_deg": 90.0, "rot_s": 0.4, "nachdruck_deg": 5.0, "kontakt_n": 1.0}
        for kv in filter(None, params.split(",")):
            k, v = kv.split("=")
            p[k.strip()] = float(v)
        self.p, self.name, self.env = p, name, env
        self.robot = env.scene["robot"]
        self.ids = [self.robot.joint_names.index(n) for n in SERVO_JOINTS]
        term = env.action_manager.get_term("servos")
        s = term._scale                                      # (environments × actions) or scalar
        self.scale = s[0].clone() if torch.is_tensor(s) else torch.full((len(self.ids),), float(s), device=env.device)
        self.hold = None
        self.contact = torch.zeros(env.num_envs, 5, dtype=torch.bool, device=env.device)

    def forward(self, obs):
        import math
        env, p = self.env, self.p
        q = self.robot.data.joint_pos[:, self.ids]
        t = mdp.episode_time(env)
        new = t <= env.step_dt + 1e-6
        if self.hold is None:
            self.hold = q.clone()
        self.hold[new] = q[new]
        self.contact[new] = False
        a = torch.zeros_like(q)
        a[:, :2] = ((self.hold[:, :2] - q[:, :2]) / self.scale[:2]).clamp(-1, 1)             # forearm, wrist
        a[:, 2] = ((math.radians(p["rotator_deg"]) - q[:, 2]) / self.scale[2]).clamp(-1, 1)  # thumb rotator
        closing = (t >= p["rot_s"]).float()[:, None]
        a[:, 3:] = p["schliessen"] * closing                                                 # thumb + 4 fingers
        if self.name == "bis_kontakt":
            self.contact |= mdp.fingertip_forces(env) > p["kontakt_n"]                       # FSR: thumb … little
            squeeze = (math.radians(p["nachdruck_deg"]) / self.scale[3:]).clamp(-1, 1)
            a[:, 3:] = torch.where(self.contact, squeeze.expand_as(a[:, 3:]) * closing, a[:, 3:])
        return a


class OnnxPolicy(torch.nn.Module):
    """ONNX policy (normalisation inside the network) via onnxruntime, CPU; input rewritten to a variable batch size."""

    def __init__(self, path: str):
        super().__init__()
        import onnx
        import onnxruntime as ort
        m = onnx.load(path)
        for v in (*m.graph.input, *m.graph.output):
            v.type.tensor_type.shape.dim[0].dim_param = "N"
        self.sess = ort.InferenceSession(m.SerializeToString(), providers=["CPUExecutionProvider"])
        self.inp = self.sess.get_inputs()[0].name

    def forward(self, obs):
        out = self.sess.run(None, {self.inp: obs.detach().cpu().numpy().astype("float32")})[0]
        return torch.from_numpy(out).to(obs.device)


if args_cli.regel:
    policy = RuleGrasp(uenv, args_cli.regel, args_cli.regel_param)
elif args_cli.onnx:
    policy = OnnxPolicy(args_cli.onnx)
else:
    policy = torch.jit.load(args_cli.policy, map_location=uenv.device).eval()
obs, _ = env.reset(seed=args_cli.seed)

robot = uenv.scene["robot"]
obj = uenv.scene["object"]
forearm = robot.joint_names.index("forearm_left")
stall_ids = [robot.joint_names.index(n) for n in SERVO_JOINTS if n != WRIST_JOINT]
stall_limit = robot.data.joint_effort_limits[:, stall_ids]
term_names = uenv.termination_manager.active_terms
dt = uenv.step_dt
early_steps = round(EARLY_S / dt)
N = uenv.num_envs
dev = uenv.device


def zeros():
    return torch.zeros(N, device=dev)


# running quantities per environment (current episode)
steps, max_tilt, early_tilt, max_forearm = zeros(), zeros(), zeros(), zeros()
hold_steps, hold_force, hold_over, stall, act_rate, sink = zeros(), zeros(), zeros(), zeros(), zeros(), zeros()
act_rate_eff = zeros()      # effective jitter: change of the action the servos receive (clipped to ±1, possibly smoothed)
eff_prev = torch.zeros(N, len(SERVO_JOINTS), device=dev)
stall_joint = torch.zeros(N, len(stall_ids), device=dev)       # stall share per servo (descriptive, since 2026-10-11)
prot_run = torch.zeros(N, len(stall_ids), device=dev)          # current run ≥ 80 % per servo [steps]
prot_max, prot_frac = zeros(), zeros()                         # longest run per episode; Σ fraction of servos ≥ 80 % (= cost c_t)
# Servo load as on the real servo (night run 2026-10-14): all 8 servos incl. the wrist (stall torque via the linkage),
# no stall at the joint stop (the firmware clips) — same function as the training cost (mdp.servo_stall), threshold 80 %
# like the overload protection
real_names = list(SERVO_JOINTS)
real_ids = [robot.joint_names.index(n) for n in real_names]
s80_joint = torch.zeros(N, len(stall_ids), device=dev)         # ≥ 80 % per servo (7, without wrist), measured as before
s80r_joint = torch.zeros(N, len(real_ids), device=dev)         # ≥ 80 % per servo (8), as on the real servo
s80r_hold = torch.zeros(N, len(real_ids), device=dev)          # … hold phase only
prot_run_r = torch.zeros(N, len(real_ids), device=dev)
prot_max_r = zeros()
xy_path, xy_path_max = zeros(), zeros()     # object path in the table plane vs. t = EARLY_S (settled, scale settled)
xy0 = obj.data.root_pos_w[:, :2].clone()
# Oscillation (leaderboard v3): object motion in the hold phase (hand fixed → any motion is wobbling/slipping) and
# frequency of the servo commands (amplitude-weighted mean frequency of the spectrum, inspired by CAPS, Mysore et al. 2021)
hold_v2, hold_w2 = zeros(), zeros()
T_EP = int(uenv.max_episode_length) + 2
ep_act = torch.zeros(N, T_EP, len(SERVO_JOINTS), device=dev)
hold_touch = torch.zeros(N, 5, device=dev)       # finger use: steps with object contact > 1 N per finger
hold_fobj = torch.zeros(N, 5, device=dev)        # … and object force per finger (order thumb … little)
forearm0 = robot.data.joint_pos[:, forearm].clone()
z0 = obj.data.root_pos_w[:, 2].clone()           # can height at episode start (scale randomised)
episodes = []                                   # completed episodes
# Load test (--bewegung): pose at motion start, largest slip afterwards, acceleration at the first slip
p_bew0 = obj.data.root_pos_w.clone()
rutsch_max = zeros()
a_grenz = torch.full((N,), float("nan"), device=dev)
a_last = zeros()
# Time series per time step since episode start (sums over running episodes, only completed ones count)
T = int(uenv.max_episode_length) + 2
trace_keys = ("hoehe_mm", "kipp_deg", "finger", "kraft_n")
trace_sum = {k: torch.zeros(T, device=dev) for k in trace_keys}
trace_n = torch.zeros(T, device=dev)
ep_trace = {k: torch.zeros(N, T, device=dev) for k in trace_keys}   # running episode per environment


def action_frequency(i) -> float | None:
    """Amplitude-weighted mean frequency [Hz] of the servo commands of an episode, averaged over the servos."""
    n_i = int(steps[i].item())
    if n_i < 16:
        return None
    seq = ep_act[i, :n_i]
    amp = torch.fft.rfft(seq - seq.mean(0), dim=0).abs()[1:]                  # without DC component
    freq = torch.fft.rfftfreq(n_i, d=dt, device=dev)[1:, None]
    tot = amp.sum(0)
    ok = tot > 1e-6                                                           # servos that move at all
    return float(((amp * freq).sum(0)[ok] / tot[ok]).mean()) if ok.any() else 0.0


def finish(i, reason):
    if args_cli.verlauf:
        n_i = int(steps[i].item())
        trace_n[:n_i] += 1
        for k in trace_keys:
            trace_sum[k][:n_i] += ep_trace[k][i, :n_i]
    held = reason == "time_out"
    req_ok = REQ_DEG is None or math.degrees(max_tilt[i].item()) <= REQ_DEG
    bewegt = BEW_ART is not None and steps[i].item() * dt > mdp.BEWEGUNG_START_S
    if bewegt and reason == "object_dropped" and math.isnan(a_grenz[i].item()):
        a_grenz[i] = a_last[i]                     # dropped before 2 cm of slip was measured
    if BEW_ART is not None:
        req_ok = req_ok and rutsch_max[i].item() < RUTSCH_M
    n = max(steps[i].item(), 1.0)
    early = (not held and steps[i].item() <= early_steps) or (
        REQ_DEG is not None and math.degrees(early_tilt[i].item()) > REQ_DEG)
    episodes.append({
        "ende": reason, "gehalten": held, "erfolg": held and req_ok, "startfehler": early,
        "kipp_max_deg": math.degrees(max_tilt[i].item()),
        "unterarm_max_deg": math.degrees(max_forearm[i].item()),
        "kraft_mittel_n": hold_force[i].item() / hold_steps[i].item() if hold_steps[i] > 0 else None,
        "kraft_ueber_anteil": hold_over[i].item() / hold_steps[i].item() if hold_steps[i] > 0 else None,
        "stall_anteil": stall[i].item() / n,
        "absinken_mm": 1000 * sink[i].item(),
        "unruhe": act_rate[i].item() / n,
        "unruhe_wirksam": act_rate_eff[i].item() / n,
        "objektweg_mm": 1000 * xy_path[i].item(),
        "objektweg_max_mm": 1000 * xy_path_max[i].item(),
        "finger_kontakt": (hold_touch[i] / hold_steps[i]).tolist() if hold_steps[i] > 0 else None,
        "finger_kraft_n": (hold_fobj[i] / hold_steps[i]).tolist() if hold_steps[i] > 0 else None,
        "stall_je_servo": (stall_joint[i] / n).tolist(),
        "stall_dauer_max_s": prot_max[i].item() * dt,
        "stall80_servo_anteil": prot_frac[i].item() / n,
        "stall80_je_servo": (s80_joint[i] / n).tolist(),
        "stall80_real_je_servo": (s80r_joint[i] / n).tolist(),
        "stall80_real_halten_je_servo": (s80r_hold[i] / hold_steps[i]).tolist() if hold_steps[i] > 0 else None,
        "stall_dauer_real_max_s": prot_max_r[i].item() * dt,
        "schwingen_mm_s": 1000 * (hold_v2[i] / hold_steps[i]).sqrt().item() if hold_steps[i] > 0 else None,
        "drehschwingen_deg_s": math.degrees((hold_w2[i] / hold_steps[i]).sqrt().item()) if hold_steps[i] > 0 else None,
        "aktion_frequenz_hz": action_frequency(i),
        "rutsch_max_mm": 1000 * rutsch_max[i].item() if bewegt else None,
        "a_grenz": None if not bewegt or math.isnan(a_grenz[i].item()) else a_grenz[i].item(),   # None = holds until the end
        "richtung": i % len(mdp.BEWEGUNG_RICHTUNGEN[BEW_ART]) if BEW_ART else None,
    })


t_start = time.time()
total_steps = 0
with torch.inference_mode():
    # with video at least until the full video length (otherwise e.g. the table lowering is missing)
    while (len(episodes) < args_cli.episodes or total_steps < args_cli.video) and simulation_app.is_running():
        t0 = time.time()
        total_steps += 1
        act = policy(obs["policy"])
        if args_cli.action_clip > 0 and not args_cli.regel:       # like rsl_rl clip_actions in training
            act = act.clamp(-args_cli.action_clip, args_cli.action_clip)
        if args_cli.stoerung:                                      # 1-step delay: the previous action is executed
            act, act_queued = (act_queued if total_steps > 1 else torch.zeros_like(act)), act
        if BEW_ART:                                                # fictitious forces for this step (episode time)
            a_now = mdp.apply_arm_motion(uenv, BEW_ART, BEW_PARAM, mdp.episode_time(uenv))
            a_last = torch.where(steps * dt > mdp.BEWEGUNG_START_S - dt, a_now, a_last)
            pos_now = obj.data.root_pos_w
            started = steps * dt > mdp.BEWEGUNG_START_S
            slip = torch.norm(pos_now - p_bew0, dim=-1)
            rutsch_max = torch.where(started, torch.maximum(rutsch_max, slip), rutsch_max)
            first = started & (slip > RUTSCH_M) & torch.isnan(a_grenz)
            a_grenz = torch.where(first, a_last, a_grenz)
            p_bew0 = torch.where((~started)[:, None], pos_now, p_bew0)
        obs, _, terminated, truncated, _ = env.step(act)
        done = terminated | truncated
        for i in done.nonzero().flatten().tolist():
            if len(episodes) < args_cli.episodes:
                finish(i, next((n for n in term_names if uenv.termination_manager.get_term(n)[i]), "?"))
        # reset new episodes, update running ones (values after the step)
        for buf in (steps, max_tilt, early_tilt, max_forearm, hold_steps, hold_force, hold_over, stall, act_rate, act_rate_eff, sink,
                    hold_touch, hold_fobj, xy_path, xy_path_max, stall_joint, hold_v2, hold_w2, ep_act, prot_run, prot_max,
                    prot_frac, s80_joint, s80r_joint, s80r_hold, prot_run_r, prot_max_r):
            buf[done] = 0.0
        forearm0[done] = robot.data.joint_pos[done, forearm]
        rutsch_max[done], a_last[done] = 0.0, 0.0
        a_grenz[done] = float("nan")
        z0[done] = obj.data.root_pos_w[done, 2]
        live = ~done
        steps[live] += 1
        tilt = mdp.object_tilt(uenv)
        max_tilt[live] = torch.maximum(max_tilt[live], tilt[live])
        early = live & (steps <= early_steps)
        early_tilt[early] = torch.maximum(early_tilt[early], tilt[early])
        max_forearm[live] = torch.maximum(max_forearm[live], (robot.data.joint_pos[live, forearm] - forearm0[live]).abs())
        in_hold = live & (steps * dt >= HOLD_START_S)
        f = mdp.fingertip_forces(uenv)
        hold_steps[in_hold] += 1
        hold_force[in_hold] += f[in_hold].sum(-1)
        hold_over[in_hold] += (f[in_hold] > FORCE_LIMIT_N).any(-1).float()
        fo = mdp.fingertip_object_forces(uenv)
        hold_touch[in_hold] += (fo[in_hold] > 1.0).float()
        hold_fobj[in_hold] += fo[in_hold]
        at_limit = (robot.data.applied_torque[:, stall_ids].abs() >= STALL_FRACTION * stall_limit).float()
        stall[live] += at_limit[live].max(-1).values
        stall_joint[live] += at_limit[live]
        prot = robot.data.applied_torque[:, stall_ids].abs() >= PROTECT_FRACTION * stall_limit
        prot_run = torch.where(prot & live[:, None], prot_run + 1, torch.zeros_like(prot_run))
        prot_max[live] = torch.maximum(prot_max[live], prot_run[live].max(-1).values)
        prot_frac[live] += prot[live].float().mean(-1)
        s80r = mdp.servo_stall(robot, real_ids, PROTECT_FRACTION, firmware_limits=True)
        s80_joint[live] += prot[live].float()
        s80r_joint[live] += s80r[live].float()
        s80r_hold[in_hold] += s80r[in_hold].float()
        prot_run_r = torch.where(s80r & live[:, None], prot_run_r + 1, torch.zeros_like(prot_run_r))
        prot_max_r[live] = torch.maximum(prot_max_r[live], prot_run_r[live].max(-1).values)
        am = uenv.action_manager
        act_rate[live] += ((am.action - am.prev_action) ** 2).sum(-1)[live]
        servo_term = am.get_term("servos")
        eff = (servo_term.filtered_actions if hasattr(servo_term, "filtered_actions") else am.action).clamp(-1, 1)
        act_rate_eff[live] += ((eff - eff_prev) ** 2).sum(-1)[live]
        eff_prev = torch.where(done[:, None], torch.zeros_like(eff), eff)
        rows_live = live.nonzero().flatten()
        ep_act[rows_live, (steps[rows_live] - 1).long().clamp(0, T_EP - 1)] = eff[rows_live]
        hold_v2[in_hold] += (obj.data.root_lin_vel_w[in_hold] ** 2).sum(-1)
        hold_w2[in_hold] += (obj.data.root_ang_vel_w[in_hold] ** 2).sum(-1)
        sink[live] = (z0 - obj.data.root_pos_w[:, 2]).clamp(min=0.0)[live]   # hand fixed → relative to the start pose
        ref = live & (steps <= early_steps)                                   # track until 0.1 s, then fixed
        xy0[ref] = obj.data.root_pos_w[ref, :2]
        xy_path[live] = torch.norm(obj.data.root_pos_w[:, :2] - xy0, dim=-1)[live]
        xy_path_max[live] = torch.maximum(xy_path_max[live], xy_path[live])
        if args_cli.verlauf:
            idx = (steps - 1).long().clamp(0, T - 1)
            rows = live.nonzero().flatten()
            vals = {"hoehe_mm": 1000 * (obj.data.root_pos_w[:, 2] - z0), "kipp_deg": torch.rad2deg(tilt),
                    "finger": (fo > 1.0).float().sum(-1), "kraft_n": f.sum(-1)}
            for k in trace_keys:
                ep_trace[k][rows, idx[rows]] = vals[k][rows]
        if args_cli.real_time:
            time.sleep(max(0.0, dt - (time.time() - t0)))


def median(v):
    v = sorted(x for x in v if x is not None)
    return v[len(v) // 2] if v else None


def mean(v):
    v = [x for x in v if x is not None]
    return sum(v) / len(v) if v else None


E = len(episodes)
held = [e for e in episodes if e["gehalten"]]
rate = lambda key: sum(1 for e in episodes if e[key]) / max(E, 1)  # noqa: E731
summary = {
    "aufgabenerfolg": rate("erfolg"),
    "haltequote": rate("gehalten"),
    "fehler": {
        "startfehler": sum(1 for e in episodes if e["startfehler"]) / max(E, 1),
        "gefallen": sum(1 for e in episodes if e["ende"] == "object_dropped" and not e["startfehler"]) / max(E, 1),
        "instabil": sum(1 for e in episodes if e["ende"] == "abnormal_robot" and not e["startfehler"]) / max(E, 1),
        "anforderung_verletzt": sum(1 for e in episodes if e["gehalten"] and not e["erfolg"] and not e["startfehler"]) / max(E, 1),
    },
    "leitplanken": {
        "kipp_median_deg": median([e["kipp_max_deg"] for e in held]),
        "unterarm_median_deg": median([e["unterarm_max_deg"] for e in held]),
        "kraft_mittel_n": mean([e["kraft_mittel_n"] for e in held]),
        "kraft_ueber_15n_anteil": mean([e["kraft_ueber_anteil"] for e in held]),
        "stall_anteil": mean([e["stall_anteil"] for e in held]),
        "absinken_mm": mean([e["absinken_mm"] for e in held]),
        "unruhe": mean([e["unruhe"] for e in held]),
        "unruhe_wirksam": mean([e["unruhe_wirksam"] for e in held]),
        "objektweg_mm": mean([e["objektweg_mm"] for e in held]),
        "objektweg_max_mm": mean([e["objektweg_max_mm"] for e in held]),
        "schwingen_mm_s": mean([e["schwingen_mm_s"] for e in held]),
        "drehschwingen_deg_s": mean([e["drehschwingen_deg_s"] for e in held]),
        "aktion_frequenz_hz": mean([e["aktion_frequenz_hz"] for e in held]),
    },
    # descriptive (not a guardrail): contact share/force per finger in the hold phase, held episodes
    "fingernutzung": {
        "finger": ["daumen", "zeige", "mittel", "ring", "klein"],
        "kontakt_anteil": [mean([e["finger_kontakt"][k] for e in held if e["finger_kontakt"]]) for k in range(5)],
        "kraft_n": [mean([e["finger_kraft_n"][k] for e in held if e["finger_kraft_n"]]) for k in range(5)],
        "finger_mit_kontakt": mean([sum(e["finger_kontakt"]) for e in held if e["finger_kontakt"]]),
    },
    # descriptive: fraction of steps per servo (except the wrist) with ≥ 90 % of the stall torque, held episodes
    "stall_je_servo": {"servo": [n for n in SERVO_JOINTS if n != WRIST_JOINT],
                       "anteil": [mean([e["stall_je_servo"][k] for e in held]) for k in range(len(stall_ids))]},
    # Overload protection (night run 2026-10-13), held episodes: longest continuous run ≥ 80 % stall (median),
    # fraction of episodes with a run > 2 s, mean fraction of the 7 servos ≥ 80 % (= cost of the Lagrangian limit)
    "servo_schutz": {
        "stall_dauer_median_s": median([e["stall_dauer_max_s"] for e in held]),
        "schutz_anteil": sum(1 for e in held if e["stall_dauer_max_s"] > PROTECT_S) / max(len(held), 1) if held else None,
        "stall80_servo_anteil": mean([e["stall80_servo_anteil"] for e in held]),
        # as on the real servo (8 servos incl. wrist, firmware limits; night run 2026-10-14)
        "stall_dauer_real_median_s": median([e["stall_dauer_real_max_s"] for e in held]),
        "schutz_anteil_real": sum(1 for e in held if e["stall_dauer_real_max_s"] > PROTECT_S) / max(len(held), 1) if held else None,
    },
    # Servo load as on the real servo (night run 2026-10-14), held episodes: fraction of steps per servo with ≥ 80 %
    # stall torque, all 8 servos (wrist via the linkage), without pushing against the stop; "mittel" = mean over the 8
    # (leaderboard v3: Servo-Last real); "bisher_80" = 7 servos without wrist, with stop (like the Lagrangian cost up to EXP-037)
    "servo_last_real": {
        "servo": real_names,
        "anteil": [mean([e["stall80_real_je_servo"][k] for e in held]) for k in range(len(real_ids))],
        "anteil_halten": [mean([e["stall80_real_halten_je_servo"][k] for e in held if e["stall80_real_halten_je_servo"]])
                          for k in range(len(real_ids))],
        "mittel": mean([sum(e["stall80_real_je_servo"]) / len(real_ids) for e in held]),
        "mittel_halten": mean([sum(e["stall80_real_halten_je_servo"]) / len(real_ids) for e in held
                               if e["stall80_real_halten_je_servo"]]),
        "servo_bisher_80": [n for n in SERVO_JOINTS if n != WRIST_JOINT],
        "anteil_bisher_80": [mean([e["stall80_je_servo"][k] for e in held]) for k in range(len(stall_ids))],
    },
}
if BEW_ART:
    # Load test: episodes that reached the motion (no start failure, not dropped before)
    bew = [e for e in episodes if e["rutsch_max_mm"] is not None]
    richt = mdp.BEWEGUNG_RICHTUNGEN[BEW_ART]
    grenz = lambda es: median([BEW_PARAM if e["a_grenz"] is None else e["a_grenz"] for e in es])  # noqa: E731
    summary["bewegung"] = {
        "art": BEW_ART, "param": BEW_PARAM, "episoden_bewegt": len(bew),
        "erfolg_bewegt": sum(1 for e in bew if e["erfolg"]) / max(len(bew), 1),
        "rutsch_median_mm": median([e["rutsch_max_mm"] for e in bew]),
        # Ramp: acceleration at the first slip > 2 cm; holds until the end → a_max (censored)
        "a_grenz_median": grenz(bew) if BEW_ART == "rampe" else None,
        "je_richtung": {r: {"episoden": len(es), "erfolg": sum(1 for e in es if e["erfolg"]) / max(len(es), 1),
                            "a_grenz_median": grenz(es) if BEW_ART == "rampe" else None,
                            "rutsch_median_mm": median([e["rutsch_max_mm"] for e in es])}
                        for j, r in enumerate(richt) for es in [[e for e in bew if e["richtung"] == j]]},
    }
result = {
    "protokoll": PROTOCOL, "bedingung": args_cli.bedingung, "objekt": args_cli.objekt, "greifart": args_cli.greifart,
    "stoerung": args_cli.stoerung, "bewegung": args_cli.bewegung or None,
    "policy": args_cli.policy if args_cli.regel else str(Path(args_cli.policy).resolve()), "seed": args_cli.seed,
    "episoden": E, "umgebungen": N, "anforderung": {"max_kipp_deg": REQ_DEG},
    "dauer_s": round(time.time() - t_start, 1), "zusammenfassung": summary,
    "netz": {"eingaenge": int(obs["policy"].shape[-1]), "ausgaenge": int(uenv.action_manager.total_action_dim),
             "actor_parameter": int(sum(p.numel() for p in policy.parameters()))},
    "erfolg_je_episode": [int(e["erfolg"]) for e in episodes],
    "gehalten_je_episode": [int(e["gehalten"]) for e in episodes],
    "kipp_je_episode": [round(e["kipp_max_deg"], 2) for e in episodes],
}
if BEW_ART:
    result["rutsch_je_episode"] = [None if e["rutsch_max_mm"] is None else round(e["rutsch_max_mm"], 1) for e in episodes]
    result["a_grenz_je_episode"] = [None if e["a_grenz"] is None else round(e["a_grenz"], 2) for e in episodes]


def pct(x):
    return "–" if x is None else f"{100 * x:5.1f} %"


def num(x, unit="", digits=1):
    return "–" if x is None else f"{x:.{digits}f}{unit}"


L = summary["leitplanken"]
lines = [
    f"Bewertung {PROTOCOL}, Bedingung {args_cli.bedingung} (Objekt {args_cli.objekt}): {args_cli.policy}",
    f"{E} Episoden, {N} Umgebungen, Seed {args_cli.seed}, Anforderung Kippwinkel ≤ {REQ_DEG}°",
    "",
    f"Aufgabenerfolg      {pct(summary['aufgabenerfolg'])}",
    f"Haltequote          {pct(summary['haltequote'])}",
    "Fehlerarten:  " + "  ".join(f"{k} {pct(v)}" for k, v in summary["fehler"].items()),
    "Leitplanken (gehaltene Episoden):",
    f"  Kippwinkel Median    {num(L['kipp_median_deg'], '°')}",
    f"  Unterarm Median      {num(L['unterarm_median_deg'], '°')}",
    f"  Griffkraft Mittel    {num(L['kraft_mittel_n'], ' N')}",
    f"  Kraft > 15 N         {pct(L['kraft_ueber_15n_anteil'])}",
    f"  Stall-Anteil         {pct(L['stall_anteil'])}",
    f"  Absinken             {num(L['absinken_mm'], ' mm')}",
    f"  Unruhe               {num(L['unruhe'], digits=3)}",
    f"  Unruhe wirksam       {num(L['unruhe_wirksam'], digits=3)}",
    f"  Objektweg Ende/max   {num(L['objektweg_mm'], ' mm')} / {num(L['objektweg_max_mm'], ' mm')}",
    f"  Schwingen Objekt     {num(L['schwingen_mm_s'], ' mm/s')}, Drehung {num(L['drehschwingen_deg_s'], ' °/s')}",
    f"  Aktionsfrequenz      {num(L['aktion_frequenz_hz'], ' Hz', 2)}",
    "Fingernutzung (Haltephase, Kontakt > 1 N / Kraft an der Dose), Daumen … klein:",
    "  Kontakt  " + "  ".join(pct(x) for x in summary["fingernutzung"]["kontakt_anteil"]),
    "  Kraft    " + "  ".join(num(x, " N") for x in summary["fingernutzung"]["kraft_n"]),
    f"  Finger mit Kontakt im Mittel: {num(summary['fingernutzung']['finger_mit_kontakt'], digits=2)}",
    "Stall je Servo (Anteil der Schritte ≥ 90 % des Stall-Moments): " + "  ".join(
        f"{n.replace('_left', '')} {pct(x)}" for n, x in zip(summary["stall_je_servo"]["servo"], summary["stall_je_servo"]["anteil"])),
    f"Überlastschutz (≥ 80 % Stall): längster Lauf Median {num(summary['servo_schutz']['stall_dauer_median_s'], ' s', 2)}, "
    f"Episoden mit Lauf > {PROTECT_S:.0f} s {pct(summary['servo_schutz']['schutz_anteil'])}, "
    f"Servos ≥ 80 % im Mittel {pct(summary['servo_schutz']['stall80_servo_anteil'])}",
    f"Servo-Last real (≥ 80 %, 8 Servos inkl. Handgelenk, ohne Anschlag): Mittel {pct(summary['servo_last_real']['mittel'])}, "
    f"Haltephase {pct(summary['servo_last_real']['mittel_halten'])}, Schutz > {PROTECT_S:.0f} s "
    f"{pct(summary['servo_schutz']['schutz_anteil_real'])}; je Servo " + "  ".join(
        f"{n.replace('_left', '')} {pct(x)}" for n, x in zip(summary["servo_last_real"]["servo"], summary["servo_last_real"]["anteil"])),
]
if args_cli.video and getattr(env, "recording", False):
    env.stop_recording()                        # write the video even if shorter than --video
if args_cli.verlauf:
    n = trace_n.clamp(min=1)
    last = int((trace_n > 0).nonzero().max().item()) + 1 if (trace_n > 0).any() else 0
    verlauf = {"protokoll": PROTOCOL, "bedingung": args_cli.bedingung, "objekt": args_cli.objekt,
               "policy": args_cli.policy if args_cli.regel else str(Path(args_cli.policy).resolve()), "episoden": E, "dt_s": dt,
               "absenken_s": [GRASP_TIME_S, HOLD_START_S],
               "t_s": [round((k + 1) * dt, 4) for k in range(last)],
               "laufend_anteil": (trace_n[:last] / max(E, 1)).tolist(),
               **{k: (trace_sum[k][:last] / n[:last]).tolist() for k in trace_keys}}
    vstem = STEM.replace(PROTOCOL, "verlauf-v1", 1)
    (out_dir / f"{vstem}.json").write_text(json.dumps(verlauf), encoding="utf-8")
    print(f"Verlauf: {out_dir / (vstem + '.json')}", flush=True)
if not args_cli.nur_medien:
    (out_dir / f"{STEM}.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
    (out_dir / f"{STEM}.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
print("\n".join(lines), flush=True)
print(f"Bericht: {out_dir / (STEM + '.txt')}", flush=True)
os._exit(0)
