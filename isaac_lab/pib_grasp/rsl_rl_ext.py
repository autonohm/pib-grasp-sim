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


class ActorCriticCaps(ActorCriticBounds):
    """bounds_loss plus CAPS (Mysore et al., ICRA 2021, *Regularizing Action Policies for Smooth Control*; Nachtlauf
    2026-10-13, EXP-034/036): Zusatzverlust auf den Mittelwert der Policy — den, den die Bewertung und der Chip ausführen —
    statt einer Strafe auf die verrauschte Aktion (ADR-022, Befund 2):
        L_T = D(μ(s_t), μ(s_{t+1}))         aufeinanderfolgende Zustände desselben Rollouts, nicht über ein Episodenende
        L_S = D(μ(s), μ(s̄)),  s̄ ~ N(s, σ)    σ je Eingang = erwartetes Messrauschen (wie die Störbedingung)
        loss' = loss + λ_T·L_T + λ_S·L_S,     D = euklidischer Abstand (wie im Paper, nicht quadriert)
    Wie bounds_loss über die Entropie in den PPO-Verlust (Modul-Docstring). L_S nutzt die Beobachtungen des Mini-Batches
    (in act() gemerkt), L_T zufällige Zeitpaare aus dem ganzen Rollout — dafür setzt der Hook um PPO.update (register())
    den Rollout-Speicher. Geloggt (Loss/…): caps_temporal, caps_spatial (Abstände) und caps_grad_share (Anteil des
    CAPS-Gradienten am Gradienten des Actors, erster Mini-Batch je Update) — danach sind λ_T/λ_S gewählt."""

    def __init__(self, *args, caps_lambda_t: float = 0.1, caps_lambda_s: float = 0.1, caps_obs_sigma=None,
                 caps_pairs: int = 4096, **kwargs):
        super().__init__(*args, **kwargs)
        self.caps_lambda_t = caps_lambda_t
        self.caps_lambda_s = caps_lambda_s
        # σ je Eingang als Abschnitte [(Anzahl, σ), …] in der Reihenfolge des Beobachtungsvektors
        self.caps_obs_sigma = [tuple(x) for x in (caps_obs_sigma or [])]
        self.caps_pairs = caps_pairs
        self._caps_obs = None              # Actor-Beobachtung (roh) des aktuellen Mini-Batches
        self._caps_seq = None              # (Actor-Beobachtungen [T, N, D] roh, gültige Paare [T-1, N])
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
        if torch.is_grad_enabled():        # nur im Update (Rollout läuft unter inference_mode)
            self._caps_obs = self.get_actor_obs(obs)
        return super().act(obs, **kwargs)

    def caps_begin(self, storage):
        with torch.no_grad():
            seq = self.get_actor_obs(storage.observations)                       # [T, N, D]
            valid = storage.dones[:-1, :, 0] == 0                                 # Paar (t, t+1) im selben Episodenlauf
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
    """PPO.update so umhüllen, dass ActorCriticCaps den Rollout-Speicher sieht (zeitlicher Term) und der Anteil des
    CAPS-Gradienten am gesamten Actor-Gradienten (vor dem Clipping, erster Mini-Batch) geloggt wird."""
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
    """Klassen für den rsl_rl-Runner auffindbar machen (eval(class_name) in rsl_rl.runners.on_policy_runner)."""
    import rsl_rl.runners.on_policy_runner as runner_module
    runner_module.ActorCriticBounds = ActorCriticBounds
    runner_module.ActorCriticCaps = ActorCriticCaps
    _wrap_ppo_update()


register()
