"""PPO configuration (rsl_rl) — values from Dexsuite (DexsuiteKukaAllegroPPORunnerCfg),
smaller networks: the policy is to run int8-quantised on the NPU of the STM32N657."""
from isaaclab.utils import configclass

from isaaclab_rl.rsl_rl import RslRlOnPolicyRunnerCfg, RslRlPpoActorCriticCfg, RslRlPpoAlgorithmCfg


@configclass
class PibGraspPPORunnerCfg(RslRlOnPolicyRunnerCfg):
    num_steps_per_env = 32
    # Asymmetric actor-critic: actor only real sensors, critic additionally privileged
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
    """EXP-020/022: actions clipped to [−1, 1] (rsl_rl wrapper, Isaac Lab clip_actions). NVIDIA's Dexsuite keeps the
    policy mean in its rl_games setup via bounds_loss (soft bound 1.1) — rsl_rl lacks this; without clipping
    the policy overshoots far beyond the servo saturation (|a| 2–3, ADR-022). 1 · scale 0.1 rad > 5° saturation error:
    full force stays reachable. Firmware: clip the network output to [−1, 1] as well."""
    clip_actions = 1.0


@configclass
class RslRlPpoActorCriticBoundsCfg(RslRlPpoActorCriticCfg):
    """Policy configuration for pib_grasp/rsl_rl_ext.ActorCriticBounds (bounds_loss like Dexsuite rl_games)."""
    class_name: str = "ActorCriticBounds"
    bounds_loss_coef: float = 1e-4        # Dexsuite rl_games
    soft_bound: float = 1.1               # rl_games
    entropy_coef: float = 0.005           # = algorithm.entropy_coef (conversion in rsl_rl_ext)


@configclass
class PibGraspPPORunnerCfg_Bounds(PibGraspPPORunnerCfg):
    """EXP-027 ff. ("action space like Dexsuite"): no clipping at runtime, instead bounds_loss like Dexsuite in
    rl_games (pib_grasp/rsl_rl_ext.py: coefficient 1e-4, soft bound 1.1). Network like PibGraspPPORunnerCfg."""

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
    """EXP-031/032: like _Bounds, actor 512-256-128 like Dexsuite (DexsuiteKukaAllegroPPORunnerCfg)."""

    def __post_init__(self):
        super().__post_init__()
        self.policy.actor_hidden_dims = [512, 256, 128]


# CAPS (night run 2026-10-13, EXP-034/036): σ per input = expected measurement noise like the perturbed condition
# (eval_policy --stoerung: joint angles 0.01 rad, FSR 0.5 N); the last action is known internally (σ 0). Segments in the
# order of the observation vector (5 steps of history per quantity, conventions.md → Schnittstelle Policy ↔ echte Hand).
CAPS_OBS_SIGMA = [(40, 0.01), (25, 0.5), (40, 0.0)]
CAPS_LAMBDA_T = 0.04       # chosen via a short training (2026-10-12): with 0.1 the CAPS share of the actor gradient in the
# first 20 iterations was 20–25 % (L_T ≈ 0.1, L_S ≈ 0.013) → 0.04 for ≈ 10 % (plan)
CAPS_LAMBDA_S = 0.04


@configclass
class RslRlPpoActorCriticCapsCfg(RslRlPpoActorCriticBoundsCfg):
    """Policy configuration for pib_grasp/rsl_rl_ext.ActorCriticCaps (bounds_loss + CAPS, Mysore et al. 2021)."""
    class_name: str = "ActorCriticCaps"
    caps_lambda_t: float = CAPS_LAMBDA_T
    caps_lambda_s: float = CAPS_LAMBDA_S
    caps_obs_sigma: list = CAPS_OBS_SIGMA
    caps_pairs: int = 4096                # random time pairs per mini-batch (mini-batch: 32 × 1024 / 4 = 8192)


@configclass
class PibGraspPPORunnerCfg_Caps(PibGraspPPORunnerCfg_Bounds):
    """EXP-034/036: like _Bounds (EXP-027), plus a CAPS loss on the policy mean (against jitter)."""

    def __post_init__(self):
        super().__post_init__()
        base = self.policy
        self.policy = RslRlPpoActorCriticCapsCfg(
            init_noise_std=base.init_noise_std, actor_obs_normalization=base.actor_obs_normalization,
            critic_obs_normalization=base.critic_obs_normalization, actor_hidden_dims=base.actor_hidden_dims,
            critic_hidden_dims=base.critic_hidden_dims, activation=base.activation,
            entropy_coef=self.algorithm.entropy_coef)
