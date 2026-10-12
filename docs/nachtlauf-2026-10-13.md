# Nachtlauf 2026-10-12/13 — Servo-Stall und Unruhe

Entwurf 2026-10-12 abends. Ziel (Leon): die beiden Anforderungen angehen, die die echte Hardware betreffen —
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
  Kosten c_t = Anteil der 7 Servos (ohne Handgelenk) mit |τ| ≥ 80 % Stall; Grenze d = 0,2 (Mittel über die Zeit).
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
  bei gleicher Leistung (nur erfolgreiche Seeds). Index v3 und Belastungstest zur Info.
- Kurven: λ und Kostenanteil (EXP-035/036/037), CAPS-Verlust (EXP-034/036).
- Risiken: EXP-027 hat nur 2/5 erfolgreiche Seeds (Vergleich wenig trennscharf); Lagrange kann anfangs schwingen
  (PID-D-Anteil dämpft, Stooke 2020); CAPS zu stark → Policy träge, greift schlechter.

## Quellen

Mysore et al. 2021 (CAPS, arXiv 2012.06644) · Ray, Achiam & Amodei 2019 (Safety Gym) · Stooke, Achiam & Abbeel 2020
(PID Lagrangian, ICML) · STS3215-Datenblatt (Überlastschutz 80 %/2 s) · ADR-022 (Befund 2: Aktionsstrafen messen Rauschen)
