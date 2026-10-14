# Nachtlauf 2026-10-12/13 — Servo-Stall und Unruhe

Stand 2026-10-13 mittags — **gelaufen** (23:13–10:23, alle Schritte rc = 0, HF-Backup fertig). Ergebnis unten (Entwurf, Urteil offen).
Ziel: die beiden Anforderungen angehen, die die echte Hardware betreffen —
**Servo-Stall** (Überlastschutz des ST3215 nach ~2 s über 80 % Blockiermoment, Wärme) und **Unruhe** (Verschleiß,
Leitplanke). Grundsatz: volle Servoleistung, Verhalten über das Lernen steuern, nicht über Filter oder kleine Skala →
**Eltern EXP-027** (Skala 0,1 für alle, `bounds_loss`, kein Filter, keine Begrenzung). Je Experiment genau eine Änderung,
5 Seeds, 1024 Umgebungen × 300 Iterationen, eval-v2, Urteile als Entwurf.

## Warum diese Methoden

- **Unruhe → CAPS** (Mysore et al., ICRA 2021, *Regularizing Action Policies for Smooth Control*): zusätzlicher Verlust
  auf den **Mittelwert** der Policy — zeitlich ‖μ(s_t) − μ(s_{t+1})‖² (aufeinanderfolgende Zustände, nicht über
  Episodengrenzen) und räumlich ‖μ(s) − μ(s + ε)‖² (ε = σ·Std der Beobachtung). Unsere Strafe `action_rate_l2` wirkt
  auf die *verrauschte* Aktion und misst vor allem Exploration (ADR-022, Befund 2); bewertet und auf dem Chip ausgeführt
  wird aber der Mittelwert. CAPS ersetzt den Filter durch Lernen.
- **Stall → PPO-Lagrange mit PID-Regelung** (Ray, Achiam & Amodei 2019, Safety Gym; Stooke, Achiam & Abbeel, ICML 2020):
  Kosten c_t = Anteil der 7 Servos (ohne Handgelenk) mit |τ| ≥ 80 % Stall; Grenze d = 0,2 (Mittel über die Zeit;
  **bestätigt**).
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

## Vorbereitung — Ergebnis (2026-10-12 abends)

- Code: `rsl_rl_ext.ActorCriticCaps` + Hook auf `PPO.update` (loggt `Loss/caps_temporal`, `caps_spatial`, `caps_grad_share`),
  `mdp.StallLagrange` (loggt `Lagrange/lambda`, `J_c`, `integral`), `mdp.servo_load` + `env_cfg.add_servo_load_obs`,
  Task-IDs `HeavyMultiProgressDex{Caps,Lagrange,CapsLagrange,LagrangeLoad}-v0`, `eval_policy --servo_last` (automatisch über
  `experiments.clip_args`), Kennzahlen `servo_schutz` (Stall-Dauer, Schutz-Anteil, Servos ≥ 80 %), Leaderboard-Info-Spalte
  „Schutz > 2 s“, `experiments.py eval --bedingung haupt` (neue Kennzahl nur für die Hauptbedingung nachholen).
- CAPS: σ = Messrauschen der Störbedingung (Gelenkwinkel 0,01 rad, FSR 0,5 N, letzte Aktion 0). Abstände euklidisch, nicht
  quadriert (wie im Paper). Kurztraining (40 It., CAPS + Lagrange): mit λ = 0,1 lag der CAPS-Anteil am Actor-Gradienten in den
  ersten 20 Iterationen bei 20–25 % (L_T ≈ 0,1, L_S ≈ 0,013) → **λ_T = λ_S = 0,04** (≈ 10 %).
- Lagrange im Kurztraining: J_c schon vor dem Greifen ≈ 0,2 (Zufallsaktionen drücken gegen Anschläge), steigt mit dem Greifen
  auf 0,28; λ wächst ab Iteration 11 und liegt nach 40 Iterationen bei 2,1/s — noch klein gegen die Haltebelohnung, wächst
  weiter, solange J_c > 0,2. Statt `reward_diag` (λ startet bei 0) diente der λ-Verlauf des Kurztrainings als Prüfung.
- Prüfungen: Kurztraining CAPS + Lagrange (40 It.) und Servo-Last (15 It., Eingang 145) ohne Fehler; Bewertung eines
  Servo-Last-Checkpoints mit `--servo_last` läuft; neue Kennzahl an EXP-027 s44 (128 Episoden): längster Stall-Lauf Median
  4,4 s, Schutz-Anteil 100 %, Servos ≥ 80 % im Mittel 50 % — die Policy liegt praktisch die ganze Episode im Stall.
- Die Nachbewertung der Hauptbedingung (EXP-014/022/024/027/033) rechnet diese Bedingung neu (gleicher Seed; GPU-PhysX nicht
  bitgenau → Zahlen statistisch gleich, nicht identisch).

## Bewertung am Morgen

- Hauptfrage je Experiment: Unruhe wirksam bzw. Stall-Anteil, Stall-Dauer, Schutz-Anteil gegenüber EXP-027 und EXP-024,
  bei gleicher Leistung (nur erfolgreiche Seeds). Index v3 zur Info.
- **Mindestanforderung Transport** (Belastungstest, 0,3 m mit 5 m/s², realistisch für pib): mindestens EXP-024-Niveau
  (97 %; Regel 96 %, EXP-027 87 %) — ein ruhigeres/kühleres Rezept, das bei Armbewegung mehr verliert, ist kein Fortschritt.
- Kurven: λ und Kostenanteil (EXP-035/036/037), CAPS-Verlust (EXP-034/036).
- Risiken: EXP-027 hat nur 2/5 erfolgreiche Seeds (Vergleich wenig trennscharf); Lagrange kann anfangs schwingen
  (PID-D-Anteil dämpft, Stooke 2020); CAPS zu stark → Policy träge, greift schlechter.

## Ergebnis (Entwurf, 2026-10-13; Urteil offen)

Nur erfolgreiche Seeds (wie Leistung und Index v3); Transport = Belastungstest 0,3 m mit 5 m/s², Mittel der erfolgreichen Seeds.

| EXP | Index | Leistung | Unruhe | Servo-Last | Schutz > 2 s |
|---|---|---|---|---|---|
| 024 Filter (Referenz) | 0,64 | 87 %, 5/5 | 0,17 | 43 % | 100 % |
| 027 Eltern | 0,45 | 80 %, 2/5 | 0,31 | 40 % | 100 % |
| 034 CAPS | 0,39 | 78 %, 4/5 | 0,06 | 45 % | 100 % |
| 035 Lagrange | 0,60 | 84 %, 2/5 | 0,16 | 13 % | 87 % |
| **036 CAPS + Lagrange** | **0,66** | 83 %, 4/5 | 0,04 | 11 % | 85 % |
| 037 + Servo-Last | 0,28 | 60 %, 1/5 | 0,20 | 16 % | 93 % |

- **Leistung**: nirgends gesichert verschieden außer EXP-037 (gesichert schlechter, Leitplanken verletzt → verworfen).
- **Unruhe (CAPS)**: Ziel erreicht — ohne Filter ruhiger als EXP-024 (0,06 bzw. 0,04 gegen 0,17). Der CAPS-Anteil am
  Actor-Gradienten liegt anfangs bei 14–17 % und fällt bis zum Ende auf 2–7 %; das Explorationsrauschen σ bleibt bei CAPS
  allein so hoch wie bei EXP-027 (≈ 0,8), CAPS glättet nur den Mittelwert.
- **Stall (Lagrange)**: Die Grenze im Mittel hält (J_c im Training am Ende 0,16–0,18; λ Spitze 4–8 um It. 100–200, Ende 0–5),
  Servo-Last 11–13 % statt 40 %, Griffkraft 57–63 N statt 97 N. Nebenwirkung: σ sinkt auf ≈ 0,4 (Rauschen drückt Servos in den
  Stall). **Aber der Überlastschutz bleibt**: Die Policy sammelt die Last auf **einem** Servo (Zeigefinger 95–97 % oder Daumen
  35–65 % der Zeit, die übrigen ≤ 5 %); Kosten = Anteil der Servos erlauben das (1/7 = 14 % < 20 %). Schutz > 2 s nur 85–87 %
  statt 100 %, längster Stall-Lauf im Median weiter 3–4 s.
- **Transport** (Kriterium ≥ 97 %): EXP-036 95 % (s42 99, s43 84, s44 99, s45 97) — knapp verfehlt durch einen Seed; der
  Top-Seed s42 liegt mit 99 % über EXP-024s Top-Seed (94 %). EXP-034 88 %, EXP-035 95 %.
- **Kippen**: EXP-036 28°, EXP-024 13° — die kleine Skala/der Filter regularisieren weiter stärker gegen das Kippen (ADR-022).
- **Vorschlag**: EXP-036 als Kandidat neue Basis neben EXP-024 (Videos `EXP-036_*/beste_videos/`). Nächster Schritt
  Überlastschutz: Grenze **je Servo** (7 Multiplikatoren, CMDP mit mehreren Nebenbedingungen) oder Kosten auf die Lauflänge
  > 2 s statt auf den Anteil — vorher prüfen, wie die Literatur das macht.

## Quellen

Mysore et al. 2021 (CAPS, arXiv 2012.06644) · Ray, Achiam & Amodei 2019 (Safety Gym) · Stooke, Achiam & Abbeel 2020
(PID Lagrangian, ICML) · STS3215-Datenblatt (Überlastschutz 80 %/2 s) · ADR-022 (Befund 2: Aktionsstrafen messen Rauschen)
