# Plan: Repo abgabebereit — damit andere pib-Studierende hier weiterarbeiten können

Stand 2026-10-13 nachts — **Entwurf**, Entscheidungen offen (unten). Grundlage: Checkliste `docs/current-sprint.md` →
„Abgabe / Veröffentlichung“ (Leon, 2026-10-12: englisch, Leon nur als Autor, Präsentationsstand vorher taggen). Neu gewichtet
(Leon, 2026-10-13): **Zielgruppe sind Studierende, die später am pib weiterarbeiten** — sie brauchen zuerst einen Einstieg,
der funktioniert, und eine ehrliche Karte, was fertig, was Altlast und was offen ist. Veröffentlichung (Lizenz, DOI) folgt daraus.

## Leitlinien

1. **Nichts Belegtes zerstören.** Vor jedem Umbau Tag `v0.1-praesentation`; keine Umbenennung von Dateien, Task-IDs,
   CLI-Optionen oder Bezeichnern, auf die Experimente, Berichte und Logs verweisen. Git-Historie nicht umschreiben.
2. **Einstieg vor Vollständigkeit.** Wer neu ist, liest README → Getting Started → Repo-Karte → „Weitermachen“. Tiefe Doku
   (ADRs, Experimentberichte) bleibt, wird aber verlinkt statt umgeschrieben.
3. **Jeder Einstiegsschritt ist geprüft.** Was im README steht, wurde auf einem frischen Klon ausgeführt (Selbsttest).
4. Wie bisher: nur Bewährtes; Vorbild für den Aufbau sind Isaac Lab (README + docs, Extension-Template), LeRobot
   (Quickstart mit vortrainierter Policy) und die NeurIPS-Reproduzierbarkeits-Checkliste.

## Bestandsaufnahme (2026-10-13, nur lesend)

| Bereich | Befund | Folge für Studierende |
|---|---|---|
| Branches | `main` steht auf 2026-06-21 (virtual servo layer), der Stand liegt auf `feature/rl-grasping` (+125 Commits); dazu `experiment/omnigraph-lightweight`, `feature/ros2-control`, `sandbox`, `session-collision-dev` | Wer klont, bekommt den Juni-Stand. Höchste Priorität |
| README | deutsch, Onboarding nur für den Zwilling (ROS2/Isaac Sim), RL-Teil verweist auf `conventions.md`; Stand-Tabelle zeigt EXP-017 als beste Policy (veraltet) | kein Weg „klonen → Policy greift“ |
| Umgebung | Isaac Sim 5.1.0, Isaac Lab 2.3.2, Python 3.11, torch 2.7.0+cu128, rsl-rl-lib 3.1.2, numpy 1.26.0 (eingefroren), onnxruntime 1.30; RTX 3060 Ti 8 GB, Treiber 580 — nirgends gesammelt festgeschrieben | Versionen raten |
| Absolute Pfade | `/home/leon` in `isaac_sim/autostart.py`, `.claude/settings.json`, je 1× in `pib_upperbody_v4.usd`, `pib_upperbody_v5.usd`, `configuration/pib_upperbody_v5_physics.usd`; Doku-Beispiele mit `~/repos/pib-hand-sim` | Start bricht auf anderem Rechner ggf. ab (USD prüfen) |
| Policies | nur im privaten HF-Repo `churro206/pib-grasp-policies`; im Git nur Videos | ohne Training nichts vorzuführen |
| Doku | 3,2k Zeilen: `decisions.md` (22 ADRs, 890 Z.), `current-sprint.md` (478 Z., Sprint-Tagebuch), `handoff.md` (Session-Übergabe), `nachtlauf-*.md`, `plan-*.md`; alles deutsch | reich, aber ohne Leseweg; Sprint/Handoff sind Arbeitsnotizen |
| Experimente | 434 Dateien in `experiments/` (Berichte, SVG, 99 MP4 ≈ 107 MB), Framework `experiments.py` | stark — fehlt nur ein „Dein erstes Experiment“ |
| Werkzeuge | `isaac_lab/tools/` 20 Skripte: dauerhafte Werkzeuge (`reward_diag`, `analyse_reset`, `check_objekt`, `check_multi`, `quantisiere_int8`, `kalibrierdaten_int8`, `ruhelage_objekt`) neben einmaligen Diagnosen (`diag_*`, `probe_*`, `suche_/auswertung_startpose_oben`, `machbarkeit_oben`) | unklar, was man braucht |
| Sprache im Code | Kommentare, Docstrings, CLI (`--objekt`, `--bedingung`, `new --eltern --kurz`), Bericht-/JSON-Schlüssel deutsch | Übersetzen der Bezeichner würde Berichte/Logs entwerten |
| Lizenzen | keine `LICENSE` für den eigenen Code; nur `ros2_ws/src/topic_based_ros2_control/LICENSE` (Fremdpaket). pib-CAD/Meshes (Onshape, isento) im Repo — Lizenz online nicht gefunden. YCB nur referenziert (Isaac-Nucleus), nicht im Repo (YCB selbst CC BY 4.0). Teile von `mdp.py` aus Isaac Lab Dexsuite abgeleitet (BSD-3) | Weitergabe rechtlich ungeklärt |
| Geheimnisse | Suche über die ganze Historie nach HF-/GitHub-/OpenAI-/AWS-Token: nichts gefunden (`gitleaks` nicht installiert — vor Veröffentlichung nachholen) | — |
| Größe | `.git` 288 MB; größte Dateien: USD 34 MB (2×), STL bis 21 MB (v4-Meshes), Hand-USD 17 MB | Klon dauert, ok |
| Assistent | `CLAUDE.md`, `.claude/commands/` (handoff/resume/checkpoint) — auf Leon zugeschnitten | für Studierende mit KI-Assistent eigentlich nützlich, wenn verallgemeinert |
| Tests | kein Test-Framework; Prüfskripte und Kurztest in `experiments.py run` | kein „funktioniert mein Setup?“ |

## Plan in Phasen

### Phase 0 — jetzt, während die GPU rechnet (nur Doku, nichts unter `isaac_lab/` oder `experiments/`)
- [x] Bestandsaufnahme (oben), Versionen gesammelt (`pip freeze` liegt im Scratchpad, 414 Pakete)
- [x] Entwürfe unter `docs/abgabe/` (ersetzen noch nichts, englisch): `repo-map.md` (jede Datei mit Status), `glossar.md` (DE → EN)
- [ ] Gliederung README/Getting Started (nach der Sprachentscheidung)
- [ ] Entscheidungen mit Leon (unten)

### Phase 1 — Einstieg (nach dem Nachtlauf, nach Tag `v0.1-praesentation`; ~1 Tag)
1. **Branch**: `feature/rl-grasping` nach `main` (Merge, kein Force-Push), GitHub-Standardbranch `main`; übrige Branches als
   Tags archivieren oder im README erklären (`feature/ros2-control` = Team-Integration/LSTM).
2. **README neu** (kurz, ~150 Zeilen): Was ist das (Bild/Video), was funktioniert (Tabelle mit Stand), drei Wege:
   (a) Digitaler Zwilling mit ROS2, (b) vortrainierte Greif-Policy ansehen, (c) eigenes Training/Experiment; Hardware-
   Anforderung; Links in die Doku.
3. **`docs/getting-started.md`**: Installation Schritt für Schritt (Isaac Sim 5.1, Isaac Lab 2.3.2 in conda nach NVIDIA-Doku,
   ROS2 Jazzy, `ros2_ws`), bekannte Fallstricke aus ADR-015 (setuptools, PYTHONPATH, `simulation_app.close()` hängt).
4. **„Erste 30 Minuten“**: beste Policy (EXP-036 s42 bzw. die neue Basis) als GitHub-Release-Asset (ONNX + JIT, ~1 MB) →
   `eval_policy.py --real_time --num_envs 16` im Fenster. Vorbild LeRobot/Isaac Lab: erst sehen, dann trainieren.
5. **`docs/repo-map.md`**: jeder Ordner/jedes Skript in einer Zeile, markiert *aktuell / Werkzeug / einmalige Diagnose /
   Altlast (v4)* — statt Dateien zu verschieben (Verweise bleiben gültig).
6. **`docs/weitermachen.md`** (für pib-Studierende das Wichtigste): offene Punkte nach Wert, je mit Einstiegsdatei und ADR —
   M2 Policy auf dem Nucleo (`docs/int8/`), M3 Servo-Kennwerte und Sehne/Feder/Übersetzung messen, Aktuatormodell mit
   Sehne (nur Zug + Feder), Firmware-Schnittstelle Policy ↔ Servos, Griff von oben, Arm-/IK-Anbindung.
7. **`docs/hardware-annahmen.md`**: was die Sim über die echte Hand annimmt und was davon gemessen ist (Servo-Modell ADR-012,
   Pleuel ADR-014, Kopplung ADR-011, FSR, Massen, Sehne/Feder 2026-10-13) — mit Messvorschlag je Punkt. Wer an der echten
   Hand arbeitet, braucht genau diese Liste.

### Phase 2 — Aufräumen ohne Verhaltensänderung (~½ Tag)
- Absolute Pfade: `autostart.py` relativ zum Skript; USD-Verweise prüfen (Layer/Asset-Pfad, ggf. relativ neu speichern — im
  GUI, Leon), Doku-Beispiele mit `$REPO`.
- Arbeitsnotizen trennen: `handoff.md`, `current-sprint.md`, `nachtlauf-*`, `plan-*` → `docs/protokoll/` (Tagebuch des
  Projekts, unverändert); an ihre Stelle `docs/status.md` (eine Seite: Stand, Ergebnisse, Grenzen).
- `experiments/README.md`: Abschnitt „Dein erstes Experiment“ (new → YAML ausfüllen → run → Bericht lesen → done).
- `CLAUDE.md`/`.claude/`: verallgemeinern zu `AGENTS.md` (Regeln für KI-Assistenten: API-Regeln, Einheiten, Experiment-
  Pflicht — die sind für jeden wertvoll) oder entfernen; Persönliches raus.
- Name: „Leon“ in Doku/Entscheidungen neutral („entschieden“), Autor im README und `CITATION.cff`.

### Phase 3 — Prüfbar machen (~½ Tag)
- `scripts/selbsttest.sh`: Asset-Prüfung, Training 2 Iterationen × 64 Umgebungen, Bewertung 16 Episoden, Leaderboard-Bau —
  ~5 min, Ergebnis „ok/Fehler“. Danach README-Schritte auf einem frischen Klon (anderer Pfad) ausführen.
- Versionen festschreiben: Tabelle in Getting Started + `env_isaaclab-freeze.txt` als Referenz (nicht als Installationsweg:
  Isaac Lab installiert man mit `isaaclab.sh --install`).

### Phase 4 — Veröffentlichung (wenn Lizenzen geklärt)
- `LICENSE` für den eigenen Code, `THIRD_PARTY.md` (pib-CAD/Meshes isento, Isaac Lab BSD-3 für abgeleitete Terme,
  topic_based_ros2_control, YCB CC BY 4.0 nur referenziert, Isaac-Sim-Assets nicht weiterverteilt), `CITATION.cff`.
- HF-Repo öffentlich mit Model Card (oder nur Release-Assets), `gitleaks` über die Historie, Release + optional Zenodo-DOI.

### Bewusst nicht (Aufwand ≫ Nutzen, Risiko für Belegtes)
- Bezeichner, CLI-Optionen, JSON-Schlüssel, Experimentberichte übersetzen. Stattdessen Glossar DE → EN.
- Dateien verschieben/umbenennen im Code (`isaac_lab/`, `isaac_sim/`). Stattdessen Repo-Karte.
- v4 löschen — nur als Altlast markieren (läuft parallel, ADR/README).

## Offene Entscheidungen (Leon)

1. **Sprache**: Vorschlag *Einstieg englisch* (README, Getting Started, Repo-Karte, Weitermachen, Hardware-Annahmen, Glossar),
   *Tiefe bleibt deutsch* (ADRs, Berichte, Code-Kommentare) mit Hinweis. Wenn die Studierenden sicher deutschsprachig sind
   (Hochschule, pib-Community in Nürnberg): Einstieg zweisprachig oder deutsch?
2. **Branch**: `feature/rl-grasping` → `main` mergen und Standardbranch? Was ist mit `feature/ros2-control` (Team-Integration)?
3. **Lizenz** eigener Code (MIT, BSD-3 wie Isaac Lab, Apache-2.0) — und die pib-CAD-Lizenz bei isento erfragen (Meshes/URDF
   aus deren Onshape liegen im Repo).
4. **Policies**: HF-Repo öffentlich machen oder nur die besten als GitHub-Release-Asset?
5. **KI-Assistenten-Dateien**: zu `AGENTS.md` verallgemeinern oder entfernen?
6. **Empfänger/Frist**: Wer bekommt die Abgabe (Hochschule, pib-Team), bis wann, öffentlich oder privat?
