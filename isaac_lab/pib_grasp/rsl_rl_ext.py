"""
rsl_rl_ext.py — `bounds_loss` for rsl_rl (EXP-027, "action space like Dexsuite"; docs/protokoll/pruefung-aktionsweg.md no. 3).

Dexsuite (rl_games configuration) keeps the policy mean within a sensible range with `bounds_loss` instead of cutting
off the action at runtime (`clip_actions: False`, `bounds_loss_coef: 1e-4`, soft bound 1.1):
    L_bounds = coef · mean_batch Σ_j [ max(μ_j − 1.1; 0)² + min(μ_j + 1.1; 0)² ]
rsl_rl does not have this term. Instead of copying PPO.update, it is put into the entropy, which PPO adds to the loss anyway
(loss = … − entropy_coef · mean(entropy)): entropy' = entropy − (coef / entropy_coef) · Σ_j penalty_j gives exactly
loss' = loss + coef · mean(Σ_j penalty_j). Side effect: the logged entropy (Policy/mean_entropy) contains the term.
Nothing intervenes at runtime; the firmware clips only for safety.

Usage: the agent configuration (agents/rsl_rl_ppo_cfg.py → PibGraspPPORunnerCfg_Bounds) imports this module
after the app has started; the import makes the class findable for rsl_rl by its name (the runner resolves `class_name` via
eval() in the module rsl_rl.runners.on_policy_runner). No Isaac Lab import here (pxr only exists after the app start).
"""
from __future__ import annotations

import torch
from rsl_rl.modules import ActorCritic


class ActorCriticBounds(ActorCritic):
    """ActorCritic with bounds_loss like rl_games (see module docstring)."""

    def __init__(self, *args, bounds_loss_coef: float = 1e-4, soft_bound: float = 1.1, entropy_coef: float = 0.005,
                 **kwargs):
        super().__init__(*args, **kwargs)
        self.bounds_loss_coef = bounds_loss_coef
        self.soft_bound = soft_bound
        self.bounds_entropy_coef = entropy_coef            # must match algorithm.entropy_coef

    def bounds_penalty(self) -> torch.Tensor:
        mu = self.action_mean
        return (torch.clamp(mu - self.soft_bound, min=0.0) ** 2
                + torch.clamp(mu + self.soft_bound, max=0.0) ** 2).sum(dim=-1)

    @property
    def entropy(self) -> torch.Tensor:
        return ActorCritic.entropy.fget(self) - (self.bounds_loss_coef / self.bounds_entropy_coef) * self.bounds_penalty()


class ActorCriticCaps(ActorCriticBounds):
    """bounds_loss plus CAPS (Mysore et al., ICRA 2021, *Regularizing Action Policies for Smooth Control*; night run
    2026-10-13, EXP-034/036): an extra loss on the policy mean — the one the evaluation and the chip execute —
    instead of a penalty on the noisy action (ADR-022, finding 2):
        L_T = D(μ(s_t), μ(s_{t+1}))         consecutive states of the same rollout, not across an episode end
        L_S = D(μ(s), μ(s̄)),  s̄ ~ N(s, σ)    σ per input = expected measurement noise (like the perturbed condition)
        loss' = loss + λ_T·L_T + λ_S·L_S,     D = Euclidean distance (as in the paper, not squared)
    Like bounds_loss, added to the PPO loss via the entropy (module docstring). L_S uses the observations of the mini-batch
    (remembered in act()), L_T random time pairs from the whole rollout — for that the hook around PPO.update (register())
    sets the rollout storage. Logged (Loss/…): caps_temporal, caps_spatial (distances) and caps_grad_share (share of the
    CAPS gradient in the actor's gradient, first mini-batch per update) — λ_T/λ_S were chosen from these."""

    def __init__(self, *args, caps_lambda_t: float = 0.1, caps_lambda_s: float = 0.1, caps_obs_sigma=None,
                 caps_pairs: int = 4096, **kwargs):
        super().__init__(*args, **kwargs)
        self.caps_lambda_t = caps_lambda_t
        self.caps_lambda_s = caps_lambda_s
        # σ per input as segments [(count, σ), …] in the order of the observation vector
        self.caps_obs_sigma = [tuple(x) for x in (caps_obs_sigma or [])]
        self.caps_pairs = caps_pairs
        self._caps_obs = None              # actor observation (raw) of the current mini-batch
        self._caps_seq = None              # (actor observations [T, N, D] raw, valid pairs [T-1, N])
        self._caps_log = None

    def _sigma_vector(self, dim: int, device) -> torch.Tensor:
        sig = torch.cat([torch.full((n,), float(s), device=device) for n, s in self.caps_obs_sigma]) \
            if self.caps_obs_sigma else torch.zeros(0, device=device)
        assert sig.numel() == dim, f"caps_obs_sigma deckt {sig.numel()} von {dim} Eingängen ab"
        return sig

    def _mu(self, raw: torch.Tensor) -> torch.Tensor:
        out = self.actor(self.actor_obs_normalizer(raw))
        return out[..., 0, :] if self.state_dependent_std else out

    def act(self, obs, **kwargs):
        if torch.is_grad_enabled():        # only in the update (the rollout runs under inference_mode)
            self._caps_obs = self.get_actor_obs(obs)
        return super().act(obs, **kwargs)

    def caps_begin(self, storage):
        with torch.no_grad():
            seq = self.get_actor_obs(storage.observations)                       # [T, N, D]
            valid = storage.dones[:-1, :, 0] == 0                                 # pair (t, t+1) within the same episode
        self._caps_seq = (seq, valid.nonzero())
        self._caps_log = {"caps_temporal": 0.0, "caps_spatial": 0.0, "n": 0, "caps_grad_share": None}

    def caps_end(self) -> dict:
        lg, self._caps_seq, self._caps_obs = self._caps_log, None, None
        n = max(lg.pop("n"), 1)
        out = {"caps_temporal": lg["caps_temporal"] / n, "caps_spatial": lg["caps_spatial"] / n}
        if lg["caps_grad_share"] is not None:
            out["caps_grad_share"] = lg["caps_grad_share"]
        return out

    def caps_loss(self) -> torch.Tensor:
        mu = self.action_mean
        zero = mu.new_zeros(())
        l_s = zero
        if self._caps_obs is not None and self.caps_lambda_s > 0:
            raw = self._caps_obs
            noisy = raw + self._sigma_vector(raw.shape[-1], raw.device) * torch.randn_like(raw)
            l_s = (mu - self._mu(noisy)).norm(dim=-1).mean()
        l_t = zero
        if self._caps_seq is not None and self.caps_lambda_t > 0 and len(self._caps_seq[1]) > 0:
            seq, pairs = self._caps_seq
            pick = pairs[torch.randint(len(pairs), (min(self.caps_pairs, len(pairs)),), device=pairs.device)]
            t, n = pick[:, 0], pick[:, 1]
            l_t = (self._mu(seq[t, n]) - self._mu(seq[t + 1, n])).norm(dim=-1).mean()
        term = self.caps_lambda_t * l_t + self.caps_lambda_s * l_s
        if self._caps_log is not None:
            lg = self._caps_log
            lg["caps_temporal"] += float(l_t.detach())
            lg["caps_spatial"] += float(l_s.detach())
            lg["n"] += 1
            if lg["n"] == 1 and term.requires_grad:
                params = [p for p in self.actor.parameters() if p.requires_grad]
                g = torch.autograd.grad(term, params, retain_graph=True, allow_unused=True)
                lg["_caps_grad"] = torch.sqrt(sum((x ** 2).sum() for x in g if x is not None))
        return term

    @property
    def entropy(self) -> torch.Tensor:
        return super().entropy - self.caps_loss() / self.bounds_entropy_coef


def _wrap_ppo_update():
    """Wrap PPO.update so that ActorCriticCaps sees the rollout storage (temporal term) and the share of the
    CAPS gradient in the total actor gradient (before clipping, first mini-batch) is logged."""
    from rsl_rl.algorithms import PPO
    if getattr(PPO.update, "_caps_wrapped", False):
        return
    orig = PPO.update

    def update(self):
        pol = self.policy
        if not isinstance(pol, ActorCriticCaps):
            return orig(self)
        pol.caps_begin(self.storage)
        clip = torch.nn.utils.clip_grad_norm_

        def clip_logged(params, *a, **k):
            lg = pol._caps_log
            if lg is not None and "_caps_grad" in lg:          # erster Mini-Batch: gesamten Actor-Gradienten messen
                total = torch.sqrt(sum((p.grad ** 2).sum() for p in pol.actor.parameters() if p.grad is not None))
                lg["caps_grad_share"] = float(lg.pop("_caps_grad") / (total + 1e-12))
            return clip(params, *a, **k)

        torch.nn.utils.clip_grad_norm_ = clip_logged
        try:
            out = orig(self)
        finally:
            torch.nn.utils.clip_grad_norm_ = clip
        out.update(pol.caps_end())
        return out

    update._caps_wrapped = True
    PPO.update = update


def register():
    """Make the classes findable for the rsl_rl runner (eval(class_name) in rsl_rl.runners.on_policy_runner)."""
    import rsl_rl.runners.on_policy_runner as runner_module
    runner_module.ActorCriticBounds = ActorCriticBounds
    runner_module.ActorCriticCaps = ActorCriticCaps
    _wrap_ppo_update()


register()
