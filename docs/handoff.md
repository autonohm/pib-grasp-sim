# Handoff

_Wird durch `/handoff` am Session-Ende aktualisiert._

---

## Stand 2026-10-12, 19:15 (vor dem Nachtlauf 2026-10-12/13)

### Zuletzt gearbeitet an

1. **Nachtlauf 2026-10-11/12 ausgewertet** (EXP-027–033, Commit `4d7a099`): Aktionsraum wie Dexsuite kippt mehr; die kleine
   Skala 0,03 an Unterarm/Handgelenk wirkte als Regularisierer (ADR-022, Nachtrag); von oben genügt die Regel.
2. **Leaderboard v3 überarbeitet** (Leon, `c4378d6`): alle Größen nur über erfolgreiche Seeds, Kippen inakzeptabel bei 45°,
   Objektweg 150 mm, Unterarm nur Info, Untergrenze 0,1, Spalte **Top** (Index des besten Seeds). Seitlich EXP-024 0,64
   (Top 0,79) vor Regel 0,55, EXP-022 0,49, EXP-027 0,45. Fehlende beste Videos (EXP-029/031/032/033) ergänzt.
3. **Belastungstest „Arm bewegt sich“** (`4c96023`, `experiments/belastung.md`): Armbewegung als Scheinkraft
   (`mdp.apply_arm_motion`, geprüft mit `tools/pruef_bewegung.py`), `eval_policy --bewegung`, `experiments.py belastung`,
   Info-Spalte „Bewegt“. Transport 5 m/s²: seitlich Regel 96 %, **EXP-024 97 %**, übrige RL 85–88 %; von oben Regel 99 %,
   EXP-030 67 %. Rampe: leichte Objekte rutschen erst bei 9–15 g, Senf (603 g) bei 25–60 m/s² (schwächste Richtung 18–38).
   Drehen: Tempo egal, die 45°-Neigung zählt; EXP-033 beim Nicken nur 37–53 %.
4. **Nachtlauf-Plan** `docs/nachtlauf-2026-10-13.md` (Servo-Stall und Unruhe): EXP-034 CAPS, EXP-035 PID-Lagrange
   (Stall-Anteil ≤ 20 %, Leon bestätigt), EXP-036 = 034 + Lagrange, EXP-037 = 035 + Servo-Last als Beobachtung; Eltern EXP-027.

### Offene Punkte

- **Nachtlauf noch nicht vorbereitet und nicht gestartet** — Start erst, wenn Leon sich meldet. Vorbereitung (~2,5 h) laut
  Plan: Kennzahlen Stall-Dauer/Schutz-Anteil, `ActorCriticCaps`, `StallLagrange`, `servo_load`, Task-IDs, YAMLs
  (`experiments.py new`), Prüfungen (CAPS-Größe offline, `reward_diag`, Kurztraining je Task), Kette.
- Überlastschutz des echten Servos (STS3215-Datenblatt: > 80 % Blockiermoment für 2 s) — ob er bei 60-Hz-Neubefehlen greift
  und welche Werte eingestellt sind, ist ungeprüft (Leon kommt vorerst nicht an Hand/Motor-Kollegen).
- Urteile EXP-027–033 sind Entwürfe (Feld `urteil` leer).
- Index „oben“ misst die Objektlage nicht (Kipp raus, Unterarm nur Info) — Lage-Anforderung je Objekt offen.
- **Abgabe/Veröffentlichung** als Sprint-Abschnitt (`docs/current-sprint.md`): englisch, Leon nur als Autor; Empfänger,
  Frist, Lizenz noch offen (eilt nicht).

### Nächste Schritte (in Reihenfolge)

1. Auf Leons Zeichen: Vorbereitung laut `docs/nachtlauf-2026-10-13.md` → Kette starten (≈ 10 h).
2. Am Morgen: Auswertung (Unruhe, Stall-Anteil/-Dauer/Schutz-Anteil, Transport ≥ EXP-024), Entwürfe in die YAMLs, Commit,
   Push, HF-Backup.
3. Präsentation Do 2026-10-15.

### Wichtige Kontextdetails

- **Folien-Zahlen**: seitlich bestes Rezept EXP-024 (87 %, 5/5, Robust 72 %, Transport 97 %), Regel 69 % (Transport 96 %);
  von oben Regel 100 %/Robust 99 %/Transport 99 %; int8 EXP-023 s43: alle Schichten NPU, 71 kB, −1,4 PP.
- Leons Grundsatz: volle Servoleistung, Verhalten über Lernen/Kosten steuern — kein Filter, keine ±1-Begrenzung, keine kleine
  Skala (darum Eltern EXP-027, nicht EXP-024/033).
- Fehlerarten EXP-024: fast nur „gefallen“ (3–20 %, Quader/Ø 8), Kippen < 2 % → Kippen ist nicht der Engpass.
- Fingerspitzenkraft der Sim: lineare Mimic-Kopplung (Übersetzung 1) vs. real 0,6–1,667 → Kraft je nach Fingerwinkel zu hoch
  oder zu niedrig (Schätzung „2×“ nur bei 90°); Laufzeit-Gearing gibt es in der Tensor-API nicht (nur USD).
- PhysX integriert semi-implizit: freier Fall läuft um ½·g·h·t vor (h = 1/120 s) — bei Bahnvergleichen berücksichtigen.
- Isaac Lab 2.3.2: externe Kräfte über `asset.permanent_wrench_composer.set_forces_and_torques(..., is_global=True)`
  (`set_external_force_and_torque` ist veraltet und warnt je Aufruf).
- Während `experiments.py run` nichts unter `isaac_lab/` ändern; Prozesse nie per `pkill -f`; nur ein Isaac-Prozess.
- TensorBoard-Werte lesen: `~/IsaacLab/isaaclab.sh -p <skript>` (Hilfsskripte `scratchpad/tb_rewards.py`, `tb_std.py`).
