"""PPO-Konfiguration (rsl_rl) — Werte aus Dexsuite (DexsuiteKukaAllegroPPORunnerCfg),
Netze kleiner: die Policy soll int8-quantisiert auf der NPU des STM32N657 laufen."""
from isaaclab.utils import configclass

from isaaclab_rl.rsl_rl import RslRlOnPolicyRunnerCfg, RslRlPpoActorCriticCfg, RslRlPpoAlgorithmCfg


@configclass
class PibGraspPPORunnerCfg(RslRlOnPolicyRunnerCfg):
    num_steps_per_env = 32
    # Asymmetric Actor-Critic: Actor nur reale Sensoren, Critic zusätzlich privilegiert
    obs_groups = {"policy": ["policy"], "critic": ["policy", "critic"]}
    max_iterations = 3000
    save_interval = 100
    experiment_name = "pib_grasp_hand_left"
    policy = RslRlPpoActorCriticCfg(
        init_noise_std=1.0,
        actor_obs_normalization=True,
        critic_obs_normalization=True,
        actor_hidden_dims=[256, 128, 64],
        critic_hidden_dims=[512, 256, 128],
        activation="elu",
    )
    algorithm = RslRlPpoAlgorithmCfg(
        value_loss_coef=1.0,
        use_clipped_value_loss=True,
        clip_param=0.2,
        entropy_coef=0.005,
        num_learning_epochs=5,
        num_mini_batches=4,
        learning_rate=1.0e-3,
        schedule="adaptive",
        gamma=0.99,
        lam=0.95,
        desired_kl=0.01,
        max_grad_norm=1.0,
    )


@configclass
class PibGraspPPORunnerCfg_Clip(PibGraspPPORunnerCfg):
    """EXP-020/022: Aktionen auf [−1, 1] begrenzt (rsl_rl-Wrapper, Isaac Lab clip_actions). NVIDIAs Dexsuite hält den
    Mittelwert der Policy im rl_games-Setup per bounds_loss (soft bound 1,1) — rsl_rl hat das nicht, ohne Begrenzung
    überzieht die Policy weit über die Servo-Sättigung (|a| 2–3, ADR-022). 1 · Skala 0,1 rad > 5° Sättigungsfehler:
    volle Kraft bleibt erreichbar. Firmware: Netzausgabe ebenso auf [−1, 1] begrenzen."""
    clip_actions = 1.0


@configclass
class RslRlPpoActorCriticBoundsCfg(RslRlPpoActorCriticCfg):
    """Policy-Konfiguration für pib_grasp/rsl_rl_ext.ActorCriticBounds (bounds_loss wie Dexsuite rl_games)."""
    class_name: str = "ActorCriticBounds"
    bounds_loss_coef: float = 1e-4        # Dexsuite rl_games
    soft_bound: float = 1.1               # rl_games
    entropy_coef: float = 0.005           # = algorithm.entropy_coef (Umrechnung in rsl_rl_ext)


@configclass
class PibGraspPPORunnerCfg_Bounds(PibGraspPPORunnerCfg):
    """EXP-027 ff. („Aktionsraum wie Dexsuite“): keine Begrenzung zur Laufzeit, stattdessen bounds_loss wie Dexsuite in
    rl_games (pib_grasp/rsl_rl_ext.py: Koeffizient 1e-4, weiche Grenze 1,1). Netz wie PibGraspPPORunnerCfg."""

    def __post_init__(self):
        import pib_grasp.rsl_rl_ext  # noqa: F401  (registriert ActorCriticBounds beim rsl_rl-Runner)
        base = self.policy
        self.policy = RslRlPpoActorCriticBoundsCfg(
            init_noise_std=base.init_noise_std, actor_obs_normalization=base.actor_obs_normalization,
            critic_obs_normalization=base.critic_obs_normalization, actor_hidden_dims=base.actor_hidden_dims,
            critic_hidden_dims=base.critic_hidden_dims, activation=base.activation,
            entropy_coef=self.algorithm.entropy_coef)


@configclass
class PibGraspPPORunnerCfg_BoundsGross(PibGraspPPORunnerCfg_Bounds):
    """EXP-031/032: wie _Bounds, Actor 512-256-128 wie Dexsuite (DexsuiteKukaAllegroPPORunnerCfg)."""

    def __post_init__(self):
        super().__post_init__()
        self.policy.actor_hidden_dims = [512, 256, 128]


# CAPS (Nachtlauf 2026-10-13, EXP-034/036): σ je Eingang = erwartetes Messrauschen wie die Störbedingung (eval_policy
# --stoerung: Gelenkwinkel 0,01 rad, FSR 0,5 N); die letzte Aktion ist intern bekannt (σ 0). Abschnitte in der Reihenfolge
# des Beobachtungsvektors (je Größe 5 Schritte Verlauf, conventions.md → Schnittstelle Policy ↔ echte Hand).
CAPS_OBS_SIGMA = [(40, 0.01), (25, 0.5), (40, 0.0)]
CAPS_LAMBDA_T = 0.04       # per Kurztraining gewählt (2026-10-12): mit 0,1 lag der CAPS-Anteil am Actor-Gradienten in den
#                            ersten 20 Iterationen bei 20–25 % (L_T ≈ 0,1, L_S ≈ 0,013) → 0,04 für ≈ 10 % (Plan)
CAPS_LAMBDA_S = 0.04


@configclass
class RslRlPpoActorCriticCapsCfg(RslRlPpoActorCriticBoundsCfg):
    """Policy-Konfiguration für pib_grasp/rsl_rl_ext.ActorCriticCaps (bounds_loss + CAPS, Mysore et al. 2021)."""
    class_name: str = "ActorCriticCaps"
    caps_lambda_t: float = CAPS_LAMBDA_T
    caps_lambda_s: float = CAPS_LAMBDA_S
    caps_obs_sigma: list = CAPS_OBS_SIGMA
    caps_pairs: int = 4096                # zufällige Zeitpaare je Mini-Batch (Mini-Batch: 32 × 1024 / 4 = 8192)


@configclass
class PibGraspPPORunnerCfg_Caps(PibGraspPPORunnerCfg_Bounds):
    """EXP-034/036: wie _Bounds (EXP-027), zusätzlich CAPS-Verlust auf den Mittelwert der Policy (gegen Unruhe)."""

    def __post_init__(self):
        super().__post_init__()
        base = self.policy
        self.policy = RslRlPpoActorCriticCapsCfg(
            init_noise_std=base.init_noise_std, actor_obs_normalization=base.actor_obs_normalization,
            critic_obs_normalization=base.critic_obs_normalization, actor_hidden_dims=base.actor_hidden_dims,
            critic_hidden_dims=base.critic_hidden_dims, activation=base.activation,
            entropy_coef=self.algorithm.entropy_coef)
