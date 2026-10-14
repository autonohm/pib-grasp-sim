# Hardware-Annahmen der Simulation

Was die Simulation über die echte linke pib-v5-Hand annimmt, woher der Wert kommt und wie man ihn an der Hand messen kann.
Wer an der echten Hand arbeitet (M3), sollte diese Liste zuerst abarbeiten; gemessene Werte gehören nach
`config/pib_hand_config_v5.py` (gemeinsame Quelle für Isaac Sim und Isaac Lab) bzw. `isaac_lab/pib_hand_left_v5_cfg.py`.

Status: **gemessen** · **Datenblatt/CAD** (übernommen, nicht an der Hand geprüft) · **Annahme** (geschätzt) · **fehlt** (nicht
modelliert).

## Antrieb

| Größe | Sim | Status | Messvorschlag |
|---|---|---|---|
| Servo ST3215: Stall-Moment, Leerlaufdrehzahl | 2,94 Nm, 270 °/s (12 V) | Datenblatt | Moment über einen Hebel mit Kraftmesser, Drehzahl ohne Last |
| Servo-Regler (Steifigkeit, Dämpfung) | PD: Sättigung bei 5° Regelfehler (Robotiq-Rezept), kritisch gedämpft (ADR-012) | Annahme | Sprungantwort aufnehmen, Kp/Kd anpassen (Systemidentifikation, z. B. mit LeRobot-Werkzeugen für Feetech STS3215) |
| Rotorträgheit (Armature) | 5·10⁻³ kg·m² | Annahme | aus der Sprungantwort |
| **Fingerantrieb** | Gelenk direkt angetrieben, Moment in beide Richtungen | **fehlt** | real ziehen alle Hand-Servos außer Unterarm/Handgelenk über eine **Sehne**, eine **Rückstellfeder** öffnet (2026-10-13). In der Sim kann die Policy aktiv öffnen — real nur die Feder |
| Rückstellfeder | – | **fehlt** | „Present Load“ des Servos ohne Kontakt bei mehreren Fingerwinkeln |
| Übersetzung Servo ↔ Finger | 1 : 1 | Annahme | Servo-Schritte bei Finger 0°/45°/90° ablesen; bei n = 2 hätte der Finger doppeltes Moment bei halber Geschwindigkeit |
| Schlaffe Sehne | – | **fehlt** | ein Objekt kann den Finger weiter beugen, ohne dass der Servo-Winkel folgt (Servo-Winkel ≠ Fingerwinkel) |
| Fingerkopplung PIP/DIP/IP | linear, 1 : 1 zum MCP (Mimic Joints, ADR-011) | Annahme | real Viergelenk (Übersetzung 0,6–1,67): Abweichung bis ~10° (PIP), ~22° (DIP), ~8° (Daumen-IP); Spitzenkraft bei 90° etwa doppelt so hoch wie real |
| Handgelenk-Pleuel | Kurbel 6 mm, Pleuel 115 mm, Hebel 12 mm; Grenzen [−60°, 0°]; Moment = 2,94 Nm × n(θ), ≤ 12 Nm (ADR-014) | CAD | Endlagen und Moment über den Winkel prüfen; Annahme „0° = gestreckte Totlage“ |
| Überlastschutz | > 80 % Stall-Moment länger als 2 s (Kennzahl „Schutz > 2 s“) | Datenblatt | am Servo auslösen und Zeit messen; ob Moment-/Stromgrenze einstellbar ist (Feetech-Register) |
| Unterarm-Servo | wie ST3215, direkt | Datenblatt | wie oben |

## Sensoren und Regelung

| Größe | Sim | Status | Messvorschlag |
|---|---|---|---|
| FSR an den Fingerspitzen | Betrag der gesamten Kontaktkraft des Endglieds [N], bei 20 N gekappt, ohne Rauschen (Störbedingung: mit Rauschen) | Annahme | Kennlinie mit Gewichten (nichtlinear, Hysterese, Schwelle); Rauschen und Abtastrate |
| Gelenkwinkel | exakt (Störbedingung: Rauschen) | Annahme | Auflösung 4096 Schritte/360°, Rauschen im Stillstand |
| Regelrate, Latenz | Policy 60 Hz, keine Verzögerung (Störbedingung: 1 Schritt) | Annahme | Laufzeit NPU + Servo-Bus (UART) messen |
| Aktionsweg | relative Gelenkposition × Skala (0,1 rad bzw. 0,03 rad), je Rezept Begrenzung ±1 oder Filter α 0,3 | festgelegt | die **Firmware muss dasselbe tun** — Details in [conventions.md](conventions.md) → „Schnittstelle Policy ↔ echte Hand“ |
| Winkelgrenzen | Gelenkgrenzen der USD; die relative Aktion kappt das Ziel nicht | festgelegt | die Firmware sollte das Ziel auf die Grenzen kappen (kein Drücken gegen den Anschlag) |

## Mechanik und Objekte

| Größe | Sim | Status | Messvorschlag |
|---|---|---|---|
| Massen der Glieder | Vollmaterial PLA 1,30 g/cm³ ohne Servos/Infill; Unterarm 0,229 kg | CAD | Glieder wiegen |
| Kollisionsformen | konvexe Hüllen | Annahme | – (bekannt: Daumen und Zeigefinger blockieren sich bei voller Beugung ohne Rotation) |
| Reibung Finger/Handfläche (TPU) | zufällig 0,5–1,0 | Annahme | Kippwinkel-Versuch mit Probeobjekten |
| Objektmassen im Training | 0,04–0,4 kg; Testobjekte YCB bis 603 g | festgelegt | – |
| Vorgreifpose | Handfläche 3,5 cm vor der Objektoberfläche, Hand fast offen | festgelegt | mit dem IK-Team abstimmen |
| „Griff steht“ / Anheben | Tisch sinkt ab 2 s mit 0,2 m/s um 10 cm | festgelegt | Signal an den Arm (IK-Team) |

## Was davon in der Bewertung schon steckt

Die **Störbedingung** (Robust) prüft ungenaue Vorgreifpose, 1 Schritt Verzögerung und Sensorrauschen; der **Belastungstest**
prüft Beschleunigungen eines bewegten Arms; die Kennzahl **Servo-Last real** misst die Servo-Belastung so, wie der echte
Servo sie hätte (Handgelenk über das Pleuel, kein Drücken am Anschlag). Sehne, Feder und Übersetzung fehlen noch vollständig —
das ist die größte bekannte Lücke.
