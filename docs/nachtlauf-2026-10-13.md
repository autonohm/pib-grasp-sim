# Nachtlauf 2026-10-12/13 — Servo-Stall und Unruhe

Stand 2026-10-12, 19:15 — **Plan steht, Vorbereitung noch offen, Start erst auf Leons Zeichen.**
Ziel (Leon): die beiden Anforderungen angehen, die die echte Hardware betreffen —
**Servo-Stall** (Überlastschutz des ST3215 nach ~2 s über 80 % Blockiermoment, Wärme) und **Unruhe** (Verschleiß,
Leitplanke). Grundsatz: volle Servoleistung, Verhalten über das Lernen steuern, nicht über Filter oder kleine Skala →
**Eltern EXP-027** (Skala 0,1 für alle, `bounds_loss`, kein Filter, keine Begrenzung). Je Experiment genau eine Änderung,
5 Seeds, 1024 Umgebungen × 300 Iterationen, eval-v2, Urteile als Entwurf (Leon).

## Warum diese Methoden

- **Unruhe → CAPS** (Mysore et al., ICRA 2021, *Regularizing Action Policies for Smooth Control*): zusätzlicher Verlust
  auf den **Mittelwert** der Policy — zeitlich ‖μ(s_t) − μ(s_{t+1})‖² (aufeinanderfolgende Zustände, nicht über
  Episodengrenzen) und räumlich ‖μ(s) − μ(s + ε)‖² (ε = σ·Std der Beobachtung). Unsere Strafe `action_rate_l2` wirkt
  auf die *verrauschte* Aktion und misst vor allem Exploration (ADR-022, Befund 2); bewertet und auf dem Chip ausgeführt
  wird aber der Mittelwert. CAPS ersetzt den Filter durch Lernen.
- **Stall → PPO-Lagrange mit PID-Regelung** (Ray, Achiam & Amodei 2019, Safety Gym; Stooke, Achiam & Abbeel, ICML 2020):
  Kosten c_t = Anteil der 7 Servos (ohne Handgelenk) mit |τ| ≥ 80 % Stall; Grenze d = 0,2 (Mittel über die Zeit;
  **von Leon bestätigt**).
  Strafe −λ·c_t, λ ≥ 0 regelt sich per PID auf J_c ≤ d. EXP-025 (feste Strafe −0,1) blieb wirkungslos — das Gewicht
  ist das Problem, und genau das stellt Lagrange selbst ein. Hängt nicht an den unbekannten Schutzwerten der echten
  Servos und hält sie auch kühl; kurze Spitzen mit vollem Moment bleiben erlaubt.
- **Servo-Last als Beobachtung**: Der ST3215 meldet seine Last („Present Load“) — realer Sensor, für die Policy bisher
  unsichtbar. Ohne sie kann sie die Last nur über Winkel und FSR erraten.

## Experimente (Reihenfolge = Kette)

| EXP | Eltern | eine Änderung | Hypothese | Dauer |
|---|---|---|---|---|
| 034 | 027 | CAPS-Verlust (zeitlich + räumlich) | Unruhe an den Servos sinkt deutlich (Ziel ≤ EXP-024 0,17), Leistung gleich | ~2 h |
| 035 | 027 | PID-Lagrange auf Stall-Anteil, d = 0,2 | Stall-Anteil und längste Stall-Dauer sinken, Leistung gleich | ~2 h |
| 036 | 034 | + PID-Lagrange wie 035 | beide Ziele zugleich (Kandidat neue Basis) | ~2 h |
| 037 | 035 | + Servo-Last als Beobachtung (8 Werte, Verlauf 5, Rauschen σ 0,05) | Policy hält die Grenze mit weniger Leistungsverlust | ~2 h |

Danach in der Kette (nur Bewertung): neue Kennzahl für EXP-014, 022, 024, 027, 033 nachholen (Hauptbedingung), Belastungstest
und beste Videos der neuen Experimente, `done`, HF-Backup. Gesamt ≈ 10 h; Start ~22 Uhr → Ende ~8 Uhr.
Fällt ein Experiment im Kurztest durch (NaN, Fehler), läuft die Kette mit dem nächsten weiter.

## Neue Kennzahlen (eval_policy, für alle neuen Bewertungen)

- **Stall-Dauer**: je Servo der längste Lauf am Stück mit |τ| ≥ 80 % Stall [s], je Episode das Maximum über die Servos;
  Median über gehaltene Episoden, dazu **Schutz-Anteil** = Anteil der Episoden mit einem Lauf > 2 s (Kriterium des
  Überlastschutzes laut STS3215-Datenblatt; Werte am echten Servo ungeprüft).
- Leaderboard v3: Spalte „Schutz > 2 s“ als Info neben Servo-Last (nicht im Index, bis wir die Zahlen kennen).

## Umsetzungsdetails (geprüft 2026-10-12)

- **rsl_rl 3.1.2** (conda `env_isaaclab`). Muster `pib_grasp/rsl_rl_ext.py`: `ActorCriticBounds` steckt den Zusatzverlust in
  die `entropy`-Property (loss = … − entropy_coef·entropy → entropy' = entropy − (coef/entropy_coef)·Term); `register()`
  macht die Klasse für `eval(class_name)` im Runner auffindbar; Agenten-Cfg `PibGraspPPORunnerCfg_Bounds` in
  `agents/rsl_rl_ppo_cfg.py`, Task `HeavyMultiProgressDex` (EXP-027) in `pib_grasp/__init__.py`.
- **CAPS**: `ActorCriticCaps(ActorCriticBounds)`. Räumlich: Beobachtung des Mini-Batches in `act()` merken, μ(s + σ·Std·ε)
  über `act_inference` (Normalisierer wird dort nicht aktualisiert). Zeitlich: der Mini-Batch kennt s_{t+1} nicht →
  `PPO.update` per Hook so umhüllen, dass die Policy Zugriff auf `storage.observations`/`storage.dones` des Rollouts hat;
  je Mini-Batch K zufällige Paare (t, t+1) ohne Episodenende, ‖μ(s_t) − μ(s_{t+1})‖² als Skalar in den Verlust.
  Gewichte λ_T, λ_S und σ so wählen, dass der Term zu Beginn ≈ 10 % des PPO-Verlusts ausmacht (offline am Kurztest messen).
- **PID-Lagrange**: als Belohnungsklasse (`ManagerTermBase`) in `mdp.py`, keine rsl_rl-Änderung: liefert c_t je Umgebung,
  Gewicht im Term = −λ; J_c = gleitender Mittelwert von c_t, λ ← max(0, K_P·e + K_I·Σe + K_D·Δe) mit e = J_c − d einmal je
  Rollout (32 Schritte, `num_steps_per_env`). Isaac Lab multipliziert Belohnungen mit dt → λ in „je s“. Startwerte K_P/K_I/K_D
  per `reward_diag` so, dass λ in ~20 Iterationen Größenordnung der Haltebelohnung (~10/s) erreichen kann; λ und J_c
  zusätzlich loggen (Kurve am Morgen). Vereinfachung ggü. Safety Gym: kein eigener Kosten-Critic (Strafe in der Belohnung).
- **Servo-Last-Beobachtung** (EXP-037): `|applied_torque| / effort_limit` je Servo (8), Verlauf 5 wie die übrigen
  Größen, Rauschen σ 0,05; Policy-Eingang 105 → 145 (NPU unkritisch). Firmware müsste „Present Load“ mitlesen.
- **Neue Kennzahlen** in `eval_policy.py` neben `stall_anteil` (90 %): Lauf am Stück ≥ 80 % je Servo, Max je Episode
  (`stall_dauer_max_s`, Median gehaltene Episoden) und `schutz_anteil` (Episoden mit Lauf > 2 s).
- **Kette** wie `scratchpad/nacht2/kette3.sh`: `experiments.py run EXP-…` nacheinander, Log mit START/ENDE je Experiment,
  am Ende „KETTE ENDE“; danach `experiments.py eval` für die Nachbewertung (holt nur Fehlendes),
  `experiments.py belastung EXP-034 … EXP-037`, `medien <EXP> --beste`, `done`. Während `run` nichts unter `isaac_lab/` ändern.

## Vorbereitung (vor dem Start, ~2,5 h)

1. `eval_policy.py`: Stall-Dauer und Schutz-Anteil (80 %-Schwelle getrennt von der bisherigen 90 %-Kennzahl).
2. `pib_grasp/rsl_rl_ext.py`: `ActorCriticCaps` (wie `ActorCriticBounds` über die Entropie in den Verlust; zeitlicher Term
   aus zufälligen Zeitpaaren der Rollout-Daten ohne Episodenende, Zugriff über einen Hook auf `PPO.update`).
3. `pib_grasp/mdp.py`: Belohnungsklasse `StallLagrange` (Kosten, PID auf λ einmal je Rollout, λ und J_c ins Log);
   Beobachtung `servo_load` (|τ|/Stall je Servo, wie „Present Load“).
4. `env_cfg.py`, `agents/rsl_rl_ppo_cfg.py`, `__init__.py`: Task-IDs für 034–037; `experiments.py new` für die YAMLs
   (Hypothese, Änderung, Bedingungen wie EXP-027).
5. Prüfen: CAPS-Term offline an einem Batch (Größe ≈ 10 % des PPO-Verlusts zu Beginn → Gewicht), `reward_diag` für die
   Lagrange-Strafe (λ-Verlauf plausibel, Kosten anfangs über d), Kurztraining je Task mit allen Codepfaden.

## Bewertung am Morgen

- Hauptfrage je Experiment: Unruhe wirksam bzw. Stall-Anteil, Stall-Dauer, Schutz-Anteil gegenüber EXP-027 und EXP-024,
  bei gleicher Leistung (nur erfolgreiche Seeds). Index v3 zur Info.
- **Mindestanforderung Transport** (Belastungstest, 0,3 m mit 5 m/s², realistisch für pib): mindestens EXP-024-Niveau
  (97 %; Regel 96 %, EXP-027 87 %) — ein ruhigeres/kühleres Rezept, das bei Armbewegung mehr verliert, ist kein Fortschritt.
- Kurven: λ und Kostenanteil (EXP-035/036/037), CAPS-Verlust (EXP-034/036).
- Risiken: EXP-027 hat nur 2/5 erfolgreiche Seeds (Vergleich wenig trennscharf); Lagrange kann anfangs schwingen
  (PID-D-Anteil dämpft, Stooke 2020); CAPS zu stark → Policy träge, greift schlechter.

## Quellen

Mysore et al. 2021 (CAPS, arXiv 2012.06644) · Ray, Achiam & Amodei 2019 (Safety Gym) · Stooke, Achiam & Abbeel 2020
(PID Lagrangian, ICML) · STS3215-Datenblatt (Überlastschutz 80 %/2 s) · ADR-022 (Befund 2: Aktionsstrafen messen Rauschen)
