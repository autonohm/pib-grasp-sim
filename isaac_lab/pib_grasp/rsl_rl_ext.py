"""
rsl_rl_ext.py — `bounds_loss` für rsl_rl (EXP-027, „Aktionsraum wie Dexsuite“; docs/pruefung-aktionsweg.md Nr. 3).

Dexsuite (rl_games-Konfiguration) hält den Mittelwert der Policy mit `bounds_loss` im sinnvollen Bereich statt die Aktion
zur Laufzeit abzuschneiden (`clip_actions: False`, `bounds_loss_coef: 1e-4`, weiche Grenze 1,1):
    L_bounds = coef · mean_Batch Σ_j [ max(μ_j − 1,1; 0)² + min(μ_j + 1,1; 0)² ]
rsl_rl kennt den Term nicht. Statt PPO.update zu kopieren, steckt er in der Entropie, die PPO ohnehin in den Verlust nimmt
(loss = … − entropy_coef · mean(entropy)): entropy' = entropy − (coef / entropy_coef) · Σ_j penalty_j ergibt genau
loss' = loss + coef · mean(Σ_j penalty_j). Nebenwirkung: die geloggte Entropie (Policy/mean_entropy) enthält den Term.
Zur Laufzeit greift nichts ein; die Firmware begrenzt nur zur Sicherheit.

Einbinden: die Agenten-Konfiguration (agents/rsl_rl_ppo_cfg.py → PibGraspPPORunnerCfg_Bounds) importiert dieses Modul
nach dem App-Start; der Import macht die Klasse für rsl_rl unter ihrem Namen auffindbar (der Runner löst `class_name` per
eval() im Modul rsl_rl.runners.on_policy_runner auf). Kein Isaac-Lab-Import hier (pxr gibt es erst nach dem App-Start).
"""
from __future__ import annotations

import torch
from rsl_rl.modules import ActorCritic


class ActorCriticBounds(ActorCritic):
    """ActorCritic mit bounds_loss wie rl_games (siehe Modul-Docstring)."""

    def __init__(self, *args, bounds_loss_coef: float = 1e-4, soft_bound: float = 1.1, entropy_coef: float = 0.005,
                 **kwargs):
        super().__init__(*args, **kwargs)
        self.bounds_loss_coef = bounds_loss_coef
        self.soft_bound = soft_bound
        self.bounds_entropy_coef = entropy_coef            # muss algorithm.entropy_coef entsprechen

    def bounds_penalty(self) -> torch.Tensor:
        mu = self.action_mean
        return (torch.clamp(mu - self.soft_bound, min=0.0) ** 2
                + torch.clamp(mu + self.soft_bound, max=0.0) ** 2).sum(dim=-1)

    @property
    def entropy(self) -> torch.Tensor:
        return ActorCritic.entropy.fget(self) - (self.bounds_loss_coef / self.bounds_entropy_coef) * self.bounds_penalty()


def register():
    """Klasse für den rsl_rl-Runner auffindbar machen (eval(class_name) in rsl_rl.runners.on_policy_runner)."""
    import rsl_rl.runners.on_policy_runner as runner_module
    runner_module.ActorCriticBounds = ActorCriticBounds


register()
