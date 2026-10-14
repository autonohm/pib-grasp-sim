# Prüfung Aktions- und Aktuatorweg (2026-10-11)

Anlass: der Aktionsfilter (EXP-024) und die Begrenzung auf ±1 (EXP-020/022) greifen zur Laufzeit ein, und die kleine
Aktionsskala von Unterarm/Handgelenk war nie gegen die Servo-Physik geprüft. Grundsatz: **die Servos behalten ihr
volles Potential, das Netz lernt es vernünftig zu nutzen** — echte Hardware-Grenzen in die Sim, alles andere über Kosten im
Training statt Eingriffe zur Laufzeit. Geprüft gegen Code, Datenblatt-Modell (`config/pib_hand_config_v5.py`) und Vorbild
(Isaac Lab Dexsuite, `~/IsaacLab/source`). Zahlen mit „Modell“ sind aus dem Servomodell gerechnet, nicht gemessen.

## Aktionsraum

| # | Ist | Hardware / Vorbild | Folge | Sollte |
|---|---|---|---|---|
| 1 | Skala Unterarm, Handgelenk **0,03 rad** je Schritt | ST3215 270 °/s (Handgelenk über Pleuel 135 °/s), volles Moment ab 5° Fehler; Dexsuite: Skala 0,1 für **alle** Gelenke inkl. Arm | max. Sollabstand 1,7° → nur **~34 % Moment**; Dauer-Geschwindigkeit bei voller Aktion ≈ 63 °/s (Unterarm) bzw. 47 °/s (Handgelenk) statt 270/135 (Modell: Dämpfung bremst bei Sollgeschwindigkeit 0) | 0,1 wie Finger und Dexsuite |
| 2 | Skala Finger/Daumen/Rotator 0,1 rad | 5,7° > 5° Sättigung | volle Aktion = volles Moment; Dauer-Geschwindigkeit ≈ 204 °/s (Modell) — nahe am Servo | lassen (volles Potential); Stall über Kosten lernen |
| 3 | Begrenzung auf ±1 (`clip_actions`, EXP-020 ff.) zur Laufzeit | Dexsuite/rl_games: `bounds_loss` (Strafe im PPO-Verlust auf den Mittelwert außerhalb ±1,1); rsl_rl hat das nicht | wirkt nicht auf die Dynamik (±1 deckt die volle Servo-Leistung ab), aber PPO lernt eine unbegrenzte Verteilung, die Umgebung schneidet ab | `bounds_loss` in rsl_rl nachbauen; Begrenzung in der Firmware nur als Sicherung |
| 4 | Aktionsfilter α 0,3 (EXP-024) | Isaac Lab ShadowHand-OpenAI; Dexsuite nicht | ~50 ms Verzögerung, beschneidet schnelle Reaktionen, Firmware muss ihn exakt nachbauen | raus; Glätte über Kosten (Strafen-Curriculum wie Lift, CAPS) |
| 5 | Sollwert relativ zur **gemessenen** Stellung | wie Dexsuite | Messrauschen/-verzögerung fließen real direkt ein | lassen; Rauschen in der Sim (Nr. 12) |

## Aktuatormodell

| # | Ist | Hardware / Vorbild | Folge | Sollte |
|---|---|---|---|---|
| 6 | Moment und Geschwindigkeit je getrennt begrenzt (implizite PD-Antriebe) | Elektromotor: Moment fällt mit der Drehzahl (Kennlinie); Isaac Lab hat dafür `DCMotorCfg` | Sim kann volles Moment bei voller Drehzahl → **mehr Leistung als real** | Kennlinie (`DCMotorCfg`, explizit) — Stabilität bei kleinen Fingerträgheiten erst prüfen |
| 7 | Sättigung bei 5°, Armature 5e-3, Dämpfung kritisch | nicht gemessen (Datenblatt nennt sie nicht) | Gains/Trägheit geschätzt | Servo-Messung (M3, LeRobot-Werkzeuge); bis dahin Gains ±25 % randomisiert (vorhanden) |
| 8 | keine Verzögerung (`min/max_delay = 0`) | real: Bus lesen/schreiben + Servo-Regler, unbekannt (geschätzt einige ms bis > 16 ms) | Policy reagiert in der Sim schneller als real | zufällige Verzögerung 0–2 Physikschritte (Isaac-Lab-Spot-Muster), mindestens in der Bewertung prüfen |
| 9 | Handgelenk: Momentgrenze winkelabhängig bis 12 Nm, Stiffness aus Nennmoment 5,87 Nm | Pleuel | Sättigung erst bei ~10° Fehler; mit Skala 0,03 nie erreicht (max. ~2 Nm), mit 0,1 bis ~6,7 Nm | mit Nr. 1 zusammen |

## Kopplung und Kraft

| # | Ist | Folge |
|---|---|---|
| 10 | lineare Mimic-Kopplung (ADR-011) | Fingerspitzenkraft bei 90° etwa 2× zu hoch, Winkel bis 22° ab — Griffkraft-Zahlen der Sim sind überschätzt; Servo-Last (Stall je Servo) ist das bessere Maß |

## Beobachtung (Schnittstelle zur Firmware)

| # | Ist | Folge / Sollte |
|---|---|---|
| 11 | Verlauf **je Größe**, älteste zuerst: 5 × 8 Gelenkwinkel, dann 5 × 5 FSR, dann 5 × 8 letzte Aktionen (Isaac Lab `CircularBuffer` + `torch.cat` der Terme); nach einem Reset wird der erste Wert in alle 5 Plätze kopiert | `conventions.md` („je Schritt 21 Werte“) ist missverständlich → korrigieren; Firmware genau so aufbauen; Replay-Test mit Sim-Daten |
| 12 | kein Rauschen auf Gelenkwinkeln und FSR (`enable_corruption = False`) | Policy verlässt sich auf perfekte Sensoren; Rauschen wie Isaac Lab inhand (Gelenk std 0,005) bzw. Dexsuite-Curriculum (EXP-017) |
| 13 | FSR = Betrag der Gesamtkontaktkraft der Spitze, ideal | echte FSR: Normalkraft, Kennlinie, Sättigung, Rauschen (M3) |

## Training

| # | Ist | Vorbild | Folge |
|---|---|---|---|
| 14 | 1024 Umgebungen × 32 × 300 It. ≈ 9,8 Mio. Schritte | Dexsuite 4096 × 32 × 15 000 ≈ 2 Mrd. | ~0,5 % Budget (ADR-022) |
| 15 | Actor 256-128-64 | Dexsuite 512-256-128 | 3× kleiner |
| 16 | Policy 60 Hz, Physik 120 Hz | Dexsuite gleich | ok |

## Vorschlag: sauberes Basis-Rezept („Aktionsraum wie Dexsuite“)

Aus EXP-022: **Skala 0,1 für alle Servos** (Nr. 1), **`bounds_loss` statt Begrenzung** (Nr. 3), **kein Filter** (Nr. 4) —
eine Änderung „Aktionsraum wie das Vorbild als Ganzes“ (ADR-022-Regel). Darauf Netz × Budget (2×2). Sim-to-Real-Treue
(Nr. 6–8, 12–13) als eigene Schritte danach, vor der echten Hand; Nr. 11 vor der Firmware.
