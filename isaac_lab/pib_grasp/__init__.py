"""
pib_grasp — Isaac Lab grasping task of the real left pib v5 hand (proof of concept).

Registers the Gym tasks. String entry points only: this module is imported before the
Isaac Sim app starts (isaac_lab/train.py), the configs only afterwards.
"""
import gymnasium as gym

gym.register(
    id="Pib-Grasp-Hand-Left-v0",
    entry_point="isaaclab.envs:ManagerBasedRLEnv",
    disable_env_checker=True,
    kwargs={
        "env_cfg_entry_point": "pib_grasp.env_cfg:PibGraspEnvCfg",
        "rsl_rl_cfg_entry_point": "pib_grasp.agents.rsl_rl_ppo_cfg:PibGraspPPORunnerCfg",
    },
)

# Training variants for experiments (always evaluated in Pib-Grasp-Hand-Left-v0, eval-v1)
for _name, _cfg in (("FingerCount", "PibGraspEnvCfg_FingerCount"), ("Heavy", "PibGraspEnvCfg_Heavy"),
                   ("HeavyDexsuite", "PibGraspEnvCfg_HeavyDexsuite"), ("HeavyMulti", "PibGraspEnvCfg_HeavyMulti"),
                   ("HeavyMultiRand", "PibGraspEnvCfg_HeavyMultiRand"), ("HeavyMultiADR", "PibGraspEnvCfg_HeavyMultiADR")):
    gym.register(
        id=f"Pib-Grasp-Hand-Left-{_name}-v0",
        entry_point="isaaclab.envs:ManagerBasedRLEnv",
        disable_env_checker=True,
        kwargs={
            "env_cfg_entry_point": f"pib_grasp.env_cfg:{_cfg}",
            "rsl_rl_cfg_entry_point": "pib_grasp.agents.rsl_rl_ppo_cfg:PibGraspPPORunnerCfg",
        },
    )

# ADR-022 (EXP-019–022): per variant env configuration × agent configuration (Clip = actions clipped to [−1, 1])
for _name, _cfg, _agent in (("HeavyMultiProgress", "PibGraspEnvCfg_HeavyMultiProgress", "PibGraspPPORunnerCfg"),
                            ("HeavyMultiClip", "PibGraspEnvCfg_HeavyMulti", "PibGraspPPORunnerCfg_Clip"),
                            ("HeavyMultiPriv", "PibGraspEnvCfg_HeavyMultiPriv", "PibGraspPPORunnerCfg"),
                            ("HeavyMultiProgressClip", "PibGraspEnvCfg_HeavyMultiProgress", "PibGraspPPORunnerCfg_Clip"),
                            ("HeavyMultiProgressClipXY", "PibGraspEnvCfg_HeavyMultiProgressXY", "PibGraspPPORunnerCfg_Clip"),
                            # Night run 2026-10-11 (EXP-024–026): one change each vs. EXP-022
                            ("HeavyMultiProgressClipFilter", "PibGraspEnvCfg_HeavyMultiProgressFilter", "PibGraspPPORunnerCfg_Clip"),
                            ("HeavyMultiProgressClipTorque", "PibGraspEnvCfg_HeavyMultiProgressTorque", "PibGraspPPORunnerCfg_Clip"),
                            ("HeavyMultiProgressClipFingers", "PibGraspEnvCfg_HeavyMultiProgressFingers", "PibGraspPPORunnerCfg_Clip"),
                            # Night run 2026-10-12: action space like Dexsuite (scale 0.1 for all, bounds_loss instead of clipping)
                            ("HeavyMultiProgressDex", "PibGraspEnvCfg_HeavyMultiProgressDex", "PibGraspPPORunnerCfg_Bounds"),
                            ("HeavyMultiProgressDexGross", "PibGraspEnvCfg_HeavyMultiProgressDex", "PibGraspPPORunnerCfg_BoundsGross"),
                            # EXP-033: bounds_loss with the old scale (0.03 forearm/wrist) — cause of the tipping in EXP-027?
                            ("HeavyMultiProgressBounds", "PibGraspEnvCfg_HeavyMultiProgress", "PibGraspPPORunnerCfg_Bounds"),
                            # Night run 2026-10-13 (EXP-034–037): jitter (CAPS) and servo stall (PID Lagrangian), parent EXP-027
                            ("HeavyMultiProgressDexCaps", "PibGraspEnvCfg_HeavyMultiProgressDex", "PibGraspPPORunnerCfg_Caps"),
                            ("HeavyMultiProgressDexLagrange", "PibGraspEnvCfg_HeavyMultiProgressDexLagrange", "PibGraspPPORunnerCfg_Bounds"),
                            ("HeavyMultiProgressDexCapsLagrange", "PibGraspEnvCfg_HeavyMultiProgressDexLagrange", "PibGraspPPORunnerCfg_Caps"),
                            ("HeavyMultiProgressDexLagrangeLoad", "PibGraspEnvCfg_HeavyMultiProgressDexLagrangeLoad", "PibGraspPPORunnerCfg_Bounds"),
                            # Night run 2026-10-14 (EXP-038–041): stall as on the real servo, limit per servo, finger count; parent EXP-036
                            ("HeavyMultiProgressDexCapsLagrangeReal", "PibGraspEnvCfg_LagrangeReal", "PibGraspPPORunnerCfg_Caps"),
                            ("HeavyMultiProgressDexCapsLagrangeJeServo", "PibGraspEnvCfg_LagrangeJeServo", "PibGraspPPORunnerCfg_Caps"),
                            ("HeavyMultiProgressDexCapsLagrangeJeServoFinger", "PibGraspEnvCfg_LagrangeJeServoFinger", "PibGraspPPORunnerCfg_Caps"),
                            ("HeavyMultiProgressDexCapsLagrangeRealFinger", "PibGraspEnvCfg_LagrangeRealFinger", "PibGraspPPORunnerCfg_Caps")):
    gym.register(
        id=f"Pib-Grasp-Hand-Left-{_name}-v0",
        entry_point="isaaclab.envs:ManagerBasedRLEnv",
        disable_env_checker=True,
        kwargs={
            "env_cfg_entry_point": f"pib_grasp.env_cfg:{_cfg}",
            "rsl_rl_cfg_entry_point": f"pib_grasp.agents.rsl_rl_ppo_cfg:{_agent}",
        },
    )

# Grasp type "top" (stage 4b, docs/protokoll/plan-griff-von-oben.md): base task for the evaluation, training variants with
# the EXP-022 recipe (progress, actions clipped to ±1)
for _name, _cfg, _agent in (("Oben", "PibGraspEnvCfg_Oben", "PibGraspPPORunnerCfg_Clip"),
                            ("ObenMulti", "PibGraspEnvCfg_ObenMulti", "PibGraspPPORunnerCfg_Clip"),
                            ("ObenMultiXY", "PibGraspEnvCfg_ObenMultiXY", "PibGraspPPORunnerCfg_Clip"),
                            ("ObenMultiDex", "PibGraspEnvCfg_ObenMultiDex", "PibGraspPPORunnerCfg_Bounds")):
    gym.register(
        id=f"Pib-Grasp-Hand-Left-{_name}-v0",
        entry_point="isaaclab.envs:ManagerBasedRLEnv",
        disable_env_checker=True,
        kwargs={
            "env_cfg_entry_point": f"pib_grasp.env_cfg_oben:{_cfg}",
            "rsl_rl_cfg_entry_point": f"pib_grasp.agents.rsl_rl_ppo_cfg:{_agent}",
        },
    )

gym.register(
    id="Pib-Grasp-Hand-Left-Play-v0",
    entry_point="isaaclab.envs:ManagerBasedRLEnv",
    disable_env_checker=True,
    kwargs={
        "env_cfg_entry_point": "pib_grasp.env_cfg:PibGraspEnvCfg_PLAY",
        "rsl_rl_cfg_entry_point": "pib_grasp.agents.rsl_rl_ppo_cfg:PibGraspPPORunnerCfg",
    },
)
