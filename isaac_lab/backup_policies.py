"""
backup_policies.py — back up the experiments' trained policies to Hugging Face (new repos are created private).

Per run (logs/rsl_rl/pib_grasp_hand_left/<lauf>/) only what is needed: last checkpoint (for
continued training), exported/ (JIT + ONNX for the Nucleo), params/, meta.json, diff, evaluation,
TensorBoard log, video — no intermediate checkpoints. Plus experiments/ (plans, reports) and
a model card. Hugging Face does not re-upload unchanged files (hash comparison).

Start via isaaclab.sh -p (Python only, no simulation — provides requests for huggingface_hub):
  conda activate env_isaaclab
  ~/IsaacLab/isaaclab.sh -p isaac_lab/backup_policies.py            # dry run: what, how large
  ~/IsaacLab/isaaclab.sh -p isaac_lab/backup_policies.py --upload   # upload
Log in once beforehand yourself: hf auth login (never put the token into the repo/scripts).
"""
import argparse
import os
import shutil
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
RUNS = REPO / "logs" / "rsl_rl" / "pib_grasp_hand_left"
DEFAULT_REPO_ID = os.environ.get("PIB_HF_REPO", "churro206/pib-grasp-policies")   # repo of the 2026 project
KEEP = ["exported/*", "params/*", "meta.json", "pib_hand_sim.diff", "pib_hand_sim_untracked.tar.gz",
        "eval-v*.json", "eval-v*.txt", "verlauf-v*.json", "events.out.tfevents.*", "video_eval/videos/*.mp4"]

MODEL_CARD = """---
license: agpl-3.0
tags: [reinforcement-learning, isaac-lab, robotics, dexterous-grasping, rsl-rl, pib, humanoid]
---
# pib v5 hand — RL grasp policies

Alle in Isaac Lab trainierten Greif-Policies der realen linken **pib-v5-Hand** (8 Servos, 5 FSR an den Fingerspitzen;
Roboter [pib](https://pib.rocks) von isento) aus der Projektarbeit 2026 für RoboCup 2027 @Home. Code, Bewertung und
Anleitung: GitHub-Repo **pib-grasp-sim** ([github.com/churro206/pib-hand-sim](https://github.com/churro206/pib-hand-sim),
alter Name, leitet weiter). Ziel-Hardware: STM32N657 (Neural-ART-NPU, int8).

**Welche Policy?** Basis für den Kraftgriff seitlich ist **EXP-036** (CAPS + PID-Lagrange auf den Servo-Stall, ohne
Aktionsfilter), bester Seed `runs/2026-10-13_03-17-52_EXP-036_s42/`. Rangliste aller Policies:
`experiments/leaderboard.md`; je Experiment Hypothese, Änderung und Bericht unter `experiments/EXP-NNN_*/`.
Die fünf besten Policies als ZIP mit Startbefehl: Release `v0.1-praesentation` im GitHub-Repo.

**Inhalt**
- `runs/<zeit>_<EXP>_s<seed>/` — je Trainingslauf: letzter Checkpoint (`model_*.pt`, rsl_rl), `exported/policy.pt`
  (TorchScript) und `exported/policy.onnx` (Actor inkl. Beobachtungsnormierung), `params/` (vollständige
  Isaac-Lab-Konfiguration, maßgeblich für Aktionsskala und Varianten), `meta.json` (Commit, Versionen), `eval-v*.*`
  (Bewertung je Protokoll), TensorBoard-Log, Video
- `experiments/` — Pläne, Berichte, Übersicht (`index.md`), Leaderboard, Ablauf und Metriken (`README.md`)

**Schnittstelle** (EXP-027 ff., z. B. EXP-036): Eingang 105 = 5 Schritte × 21 — 8 Servo-Winkel [rad] (forearm, wrist,
thumb_rotator, thumb/index/middle/ring/pinky proximal), 5 FSR [N, 0–20] (Daumen … klein), 8 letzte Aktionen. Ausgang: 8
relative Gelenkziele × 0,1 rad je Schritt (60 Hz), ohne Kappung zur Laufzeit. Ältere Läufe (bis EXP-026) skalieren
Unterarm/Handgelenk mit 0,03 rad und teils mit Begrenzung oder Filter — siehe `params/env.yaml` des Laufs.

**Ansehen** (im GitHub-Repo, Isaac Lab 2.3.2):
`isaaclab.sh -p isaac_lab/eval_policy.py --policy runs/<lauf>/exported/policy.pt --action_scale 0.1 --max_kipp_deg 45 --num_envs 16 --real_time`

**Grenzen**: nur in der Simulation bewertet (Protokoll eval-v2), auf der echten Hand noch nicht getestet. Lizenz AGPL-3.0
wie das Code-Repo; die Hand-Geometrie stammt aus dem pib-Modell von isento (GPL-3.0/AGPL-3.0).
"""


def files_of(run: Path) -> list[Path]:
    ckpts = sorted(run.glob("model_*.pt"), key=lambda p: int(p.stem.split("_")[1]))
    out = ckpts[-1:]                                   # only the last checkpoint
    for pattern in KEEP:
        out += [p for p in run.glob(pattern) if p.is_file()]
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo-id", default=DEFAULT_REPO_ID)
    ap.add_argument("--upload", action="store_true", help="tatsächlich hochladen (sonst nur anzeigen)")
    a = ap.parse_args()

    runs = sorted(p for p in RUNS.glob("*") if p.is_dir() and any(p.glob("model_*.pt")))
    total = 0
    for run in runs:
        size = sum(f.stat().st_size for f in files_of(run))
        total += size
        print(f"{run.name:45s} {len(files_of(run)):3d} Dateien  {size / 1e6:7.1f} MB")
    exp_size = sum(f.stat().st_size for f in (REPO / "experiments").rglob("*") if f.is_file())
    print(f"{'experiments/':45s} {exp_size / 1e6:19.1f} MB")
    print(f"Gesamt: {len(runs)} Läufe, {(total + exp_size) / 1e6:.1f} MB → {a.repo_id}")
    if not a.upload:
        print("Probelauf — mit --upload hochladen.")
        return

    from huggingface_hub import HfApi
    api = HfApi()
    print(f"Angemeldet als: {api.whoami()['name']}")
    api.create_repo(a.repo_id, repo_type="model", private=True, exist_ok=True)
    # staging with hard links (no extra storage), then a single upload
    with tempfile.TemporaryDirectory(dir=REPO / "logs") as tmp:
        stage = Path(tmp)
        for run in runs:
            for f in files_of(run):
                dst = stage / "runs" / run.name / f.relative_to(run)
                dst.parent.mkdir(parents=True, exist_ok=True)
                os.link(f, dst)
        shutil.copytree(REPO / "experiments", stage / "experiments")
        (stage / "README.md").write_text(MODEL_CARD, encoding="utf-8")
        commit = os.popen(f"git -C {REPO} rev-parse --short HEAD").read().strip()
        api.upload_folder(repo_id=a.repo_id, repo_type="model", folder_path=str(stage),
                          commit_message=f"Sicherung der Experiment-Läufe (pib-grasp-sim {commit})")
    print(f"Fertig: https://huggingface.co/{a.repo_id}")


if __name__ == "__main__":
    main()
