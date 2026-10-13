# Handoff

_Wird durch `/handoff` am Session-Ende aktualisiert._

---

## Stand 2026-10-13 mittags (Nachtlauf 2026-10-12/13 ausgewertet)

### Zuletzt gearbeitet an

1. **Nachtlauf 2026-10-12/13** (23:13–10:23, alle Schritte rc = 0, HF-Backup fertig): EXP-034–037 trainiert, bewertet,
   Belastungstest, beste Videos; Hauptbedingung EXP-014/022/024/027/033 mit neuer Kennzahl „Schutz > 2 s“ nachbewertet.
2. **Auswertung** (`docs/nachtlauf-2026-10-13.md` → „Ergebnis“, Entwürfe in `ergebnis`/`schluss` der YAMLs, `urteil` leer):
   **EXP-036 CAPS + Lagrange Index 0,66 = Platz 1** seitlich (EXP-024 0,64): Unruhe 0,04, Servo-Last 11 %, 4/5, Leistung 83 %,
   Transport 95 % (Kriterium 97 % knapp verfehlt, ein Seed 84 %), Kippen 28°. EXP-034 CAPS: Unruhe 0,06, Transport 88 %.
   EXP-035 Lagrange: Servo-Last 13 %, 2/5. EXP-037 Servo-Last als Beobachtung: gesichert schlechter → verworfen.
3. **Befund Überlastschutz**: Lagrange auf den *Anteil* der Servos sammelt die Last auf einem Servo (Zeigefinger 95–97 % oder
   Daumen 35–65 % der Zeit), 1/7 = 14 % < 20 % → Schutz > 2 s bleibt 85–87 %, längster Lauf 3–4 s.

### Offene Punkte

- **Entscheidung Leon**: EXP-036 als neue Basis? (Videos `experiments/EXP-036_caps_lagrange/beste_videos/`, Top-Seed s42)
- Urteile EXP-027–037 sind Entwürfe (Feld `urteil` leer).
- Überlastschutz: Grenze je Servo (7 Multiplikatoren) oder Kosten auf die Stall-Lauflänge > 2 s — Literatur vorher prüfen.
  Werte des echten Servo-Schutzes ungeprüft (Leon kommt vorerst nicht an Hand/Motor-Kollegen).
- Index „oben“ misst die Objektlage nicht — Lage-Anforderung je Objekt offen.
- **Abgabe/Veröffentlichung** (`docs/current-sprint.md`): englisch, Leon nur als Autor; Empfänger, Frist, Lizenz offen.

### Nächste Schritte (in Reihenfolge)

1. Präsentation Do 2026-10-15 (Folien-Zahlen unten, EXP-036 als neuester Stand ergänzen).
2. Nach Leons Urteil: Überlastschutz je Servo planen (Eltern EXP-036), danach Pause.

### Wichtige Kontextdetails

- **Folien-Zahlen**: seitlich bestes Rezept EXP-024 (87 %, 5/5, Robust 72 %, Transport 97 %), neu EXP-036 (Index 0,66, 83 %, 4/5,
  Unruhe 0,04, Servo-Last 11 %, Transport 95 %), Regel 69 % (Transport 96 %);
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
- TensorBoard-Werte lesen: in `env_isaaclab` mit gesetztem PYTHONPATH (`python scratchpad/tbscan.py EXP-…`; mit `env -u PYTHONPATH`
  fehlt numpy). λ/J_c unter `Lagrange/*`, CAPS unter `Loss/caps_*`.
