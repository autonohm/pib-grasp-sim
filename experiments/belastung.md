# Belastungstest „Arm bewegt sich“

Automatisch erzeugt (`experiments.py belastung`). Die Hand bleibt fest, die Armbewegung wirkt als Scheinkraft auf Objekt und Handglieder (`mdp.apply_arm_motion`; geprüft mit `tools/pruef_bewegung.py`: 1–3 % Abweichung, schnellste Drehung 9 %). Erfolg = gehalten, Anforderung erfüllt **und** < 2 cm Rutschen relativ zur Hand ab Bewegungsbeginn (GenDexGrasp/GAGrasp); Werte bedingt auf Episoden, die die Bewegung erreichen (ab 2,6 s).

- **Rampe** (Grasp to Act 2026, SoGraB): Beschleunigung in ±x, ±y, ±z linear 0 → 200 m/s² in 1,8 s; **Grenze** = Beschleunigung beim ersten Rutschen > 2 cm, Median über Episoden (hält bis zum Ende → 200). Top-Seed.
- **Gieren / Nicken** (GRASPA): Hand dreht 45° (beide Richtungen) um den Ellbogen, senkrechte bzw. waagrechte Achse, Minimum-Jerk (Flash & Hogan 1985) in T = 0.8 / 0.45 / 0.25 s (härter nach rechts; Abbruch unter 20 %). Top-Seed.
- **Transport** (Dex-Net „transportieren“): 0,3 m Minimum-Jerk mit 5 m/s² in 6 Richtungen — realistisch für pib. Mittel über alle erfolgreichen Seeds.
- Richtungen im Weltrahmen: x quer zur Handfläche, y längs des Unterarms (−y = zu den Fingern), z senkrecht. Kraft auf das Objekt = −m·a (Hand beschleunigt in +z → Objekt wird nach unten gedrückt).

## Greifart „seitlich“

| Experiment | Top | Rampe Ø 6: Grenze [schwächste] | Rampe Senf (YCB, 603 g): Grenze [schwächste] | Gieren 0.8 / 0.45 / 0.25 s | Nicken 0.8 / 0.45 / 0.25 s | Transport 5 m/s² |
|---|---|---|---|---|---|---|
| EXP-014 (Regel) | EXP-014 | 116 m/s² [+x 66] | 31 m/s² [+x 18] | 97 % / 96 % / 86 % | 97 % / 97 % / 95 % | 96 % (1 Seeds) |
| EXP-022  | s42 | 101 m/s² [+z 51] | 25 m/s² [+z 21] | 97 % / 97 % / 97 % | 96 % / 97 % / 96 % | 85 % (5 Seeds) |
| EXP-024  | s44 | 106 m/s² [+x 53] | 47 m/s² [+z 32] | 94 % / 92 % / 84 % | 92 % / 94 % / 92 % | 97 % (5 Seeds) |
| EXP-027  | s44 | 151 m/s² [+x 97] | 47 m/s² [+z 38] | 90 % / 90 % / 90 % | 91 % / 89 % / 90 % | 87 % (2 Seeds) |
| EXP-033  | s42 | 88 m/s² [−z 40] | 60 m/s² [+z 23] | 79 % / 81 % / 79 % | 53 % / 41 % / 37 % | 88 % (4 Seeds) |
| EXP-034  | s42 | 114 m/s² [+x 86] | 45 m/s² [+z 34] | 97 % / 97 % / 95 % | 97 % / 97 % / 95 % | 88 % (4 Seeds) |
| EXP-035  | s44 | 81 m/s² [+x 23] | 38 m/s² [+y 34] | 97 % / 89 % / 15 % | 97 % / 97 % / 97 % | 95 % (2 Seeds) |
| EXP-036  | s42 | 108 m/s² [+x 77] | 40 m/s² [−z 31] | 99 % / 100 % / 99 % | 99 % / 100 % / 99 % | 95 % (4 Seeds) |
| EXP-037  | s45 | 121 m/s² [−z 53] | 32 m/s² [+z 27] | 61 % / 60 % / 60 % | 60 % / 60 % / 60 % | 60 % (1 Seeds) |

## Greifart „oben“

| Experiment | Top | Rampe Kugel Ø 7: Grenze [schwächste] | Rampe Suppendose (YCB): Grenze [schwächste] | Gieren 0.8 / 0.45 / 0.25 s | Nicken 0.8 / 0.45 / 0.25 s | Transport 5 m/s² |
|---|---|---|---|---|---|---|
| EXP-028 (Regel) | EXP-028 | 132 m/s² [+x 103] | 56 m/s² [−y 44] | 99 % / 99 % / 99 % | 99 % / 98 % / 98 % | 99 % (1 Seeds) |
| EXP-030  | s42 | 112 m/s² [−x 75] | 19 m/s² [+x 16] | 83 % / 84 % / 84 % | 84 % / 84 % / 83 % | 67 % (5 Seeds) |

