# Hinweise für KI-Coding-Assistenten (und Menschen)

pib-Hand-Sim: digitaler Zwilling des pib-Oberkörpers (v4/v5) in NVIDIA Isaac Sim 5.1 und RL-Greifen in Isaac Lab 2.3.2 für
die reale linke v5-Hand (RoboCup 2027 @Home). Einstieg für Menschen: [README.md](README.md), [docs/getting-started.md](docs/getting-started.md).

## Session-Start
Zuerst `docs/protokoll/handoff.md` (Stand und offene Punkte der letzten Session) und [docs/weitermachen.md](docs/weitermachen.md)
lesen. Am Ende einer Session `handoff.md` aktualisieren (`.claude/commands/handoff.md`).

## Sprache
Dokumentation, Berichte und Ausgaben der Werkzeuge deutsch (mit Umlauten); Code-Kommentare und Docstrings englisch.
Bezeichner, Kommandozeilen-Optionen und JSON-Schlüssel nicht umbenennen (alte Berichte/Logs verweisen darauf) — [docs/glossar.md](docs/glossar.md).

## Stack
- **Isaac Sim 5.1** — Script Editor (`isaac_sim/start.py`) + Action Graph (Teil der USD-Stage) + `ros2_control` (ROS 2 Jazzy)
- **Isaac Lab 2.3.2** (`~/IsaacLab`, `rsl_rl` PPO) in der conda-Umgebung `env_isaaclab`
- Python 3.11, numpy 1.26 | kein Test-Framework (Prüfskripte in `isaac_lab/`, `isaac_lab/tools/`)
- Ziel-Hardware der Policy: STM32N657 (NUCLEO-N657X0, Neural-ART-NPU, int8)

## Vorzeichen und Einheiten
- Onshape und Isaacs importierte Gelenkachsen waren vorzeicheninvertiert — behoben direkt am Prim
  (`isaac_sim/tools/flip_joint_sign.py`, ADR-007). Nach einem Onshape-Neuimport erneut ausführen.
- Referenz: `shoulder_horizontal_right: +20` = Arm vorne; `elbow_right: +90` = voll gebeugt. Ausnahme v5-Handgelenk: −60° = gebeugt.
- **Einheiten am Prim** (USD-Schema, nicht raten): Angular-Drive `stiffness` Nm/**°**, `damping` Nm·s/**°**,
  `physxJoint:maxJointVelocity` °/s, `physxJoint:armature` kg·m². Für ω_n/ζ ×180/π auf rad umrechnen. ROS-2-Topics in rad.

## Isaac Sim — Regeln
- Kein `time.sleep()` → `await app.next_update_async()` (Editor) / `sim_app.update()` (Standalone)
- `_load_mod(name, path)` in `start.py`/`setup_stage.py` umgeht veraltete `.pyc`
- `start.py` jede Session vor Play ausführen (PhysX cacht Stiffness/Damping nicht), danach Stop → Play
- `set_joint_limits()` verwenden (`fix_joint_limits` gibt es nicht mehr)
- Gelenknamen nie erfinden → `config/pib_hand_config_v4.py`/`_v5.py` oder die URDF
- **Mimic-Folgegelenke** (`distal`/`tip`, `thumb_*_tip`) haben bewusst Stiffness/Damping 0 — nie einen Antrieb darauf setzen
  (ADR-011); Gearing/Offset nur in `setup_stage.py` → `MIMIC_JOINTS`
- Isaac Sim 5.1 hat keine Mimic-Compliance und kein `solveArticulationContactLast` (nur 6.0-Doku)
- OmniGraph-Live-Werte nur über `og.Controller.get()` lesbar; per `og.Controller` gesetzte Werte landen nicht zuverlässig in der
  USD → Persistentes direkt in der USD anlegen, nach Graph-Skripten speichern **und neu öffnen**, Knoten nicht im Stage-Tree
  umbenennen (ADR-013)
- Script Node (falls je nötig): Klassen/Instanzen nie auf Modulebene, nur in `setup(db)` + `db.per_instance_state` (ADR-009)
- Einfache, einmalige Stage-/Graph-Änderungen lieber im GUI; Skripte nur für Wiederholungen oder Diagnose. Diagnose-Skripte
  schreiben zusätzlich nach `isaac_sim/tools/_*.txt` (die Script-Editor-Konsole lässt sich nicht kopieren)

## Isaac Lab — Regeln (ADR-015)
- Pakete **nur** in `env_isaaclab`, nie in Isaac Sims eigenes Python; eine Projekt-`.venv` vorher deaktivieren
- Starten über `~/IsaacLab/isaaclab.sh -p isaac_lab/<skript>.py`
- Tests/Vorführungen mit Fenster (zum Zuschauen), headless nur fürs Training; nur ein Isaac-Prozess gleichzeitig (8 GB VRAM)
- Isaac-Lab-API nie raten — gegen `~/IsaacLab/source` prüfen; Vorbild ist Dexsuite (`isaaclab_tasks/manager_based/manipulation/dexsuite`)
- Hand-USD: Mimic/Grenzen/Antriebe sind eingebrannt (`isaac_sim/tools/bake_hand_asset_v5.py`) — nach Änderungen an
  `setup_stage.py`/Config erneut ausführen und speichern
- Kontaktsensor mit Objekt-Filter: **ein** `ContactSensorCfg` pro Fingerspitze
- Skripte enden mit Bericht-Datei + `os._exit(0)` (`simulation_app.close()` hängt)
- `SceneEntityCfg` mit Körper-/Gelenknamen **nie** als Standardargument einer mdp-Funktion — Isaac Lab löst sie nur in den
  `params` eines Terms auf (ADR-017)
- Training/Bewertung als **Experiment** über `isaac_lab/experiments.py` (ADR-016, `experiments/README.md`): Hypothese und genau eine
  Änderung vorher, 5 Seeds, Bewertung nach eval-v2 (nur innerhalb eines Protokolls vergleichen, ADR-021), nie über die
  Trainings-Belohnung vergleichen; Trainingsvarianten als Task-IDs in `isaac_lab/pib_grasp/__init__.py`. Urteile im YAML setzt ein
  Mensch — Assistenten schreiben Entwürfe.
- Vorbild **als Ganzes** prüfen, bevor Terme übernommen werden (ADR-022): passt die Aufgabe, fehlt ein Gegenstück in anderer
  Software (rl_games `bounds_loss` → rsl_rl), wie groß ist das Budget
- Neue Szenen/Varianten/Objekte vor einem Lauf prüfen: Start ohne Überlappung (`tools/analyse_reset.py`, ≥ 256 Starts),
  Szenenprüfung (`tools/check_objekt.py`/`check_multi.py`), Belohnungsdiagnose (`tools/reward_diag.py`), Kurztraining lang genug
  für alle Codepfade
- Orchestrierung: `conda activate env_isaaclab && /usr/bin/python3 isaac_lab/experiments.py …`; Prozesse nicht per `pkill -f`
  suchen/beenden (trifft die eigene Shell), sondern über `ps -eo pid,args`; während eines `run` nichts unter `isaac_lab/` ändern

## Arbeitsweise
- Bewährte Praxis (NVIDIA, Literatur) zuerst und mit Quelle; eigene Terme nur einzeln und begründet
- Keine automatischen Commits ohne Rückfrage; Commit-Nachrichten deutsch
- Ergebnisse ehrlich berichten (gesichert vs. nicht gesichert, Zahl der Seeds)

## Wo was steht
[docs/repo-karte.md](docs/repo-karte.md) (alle Dateien) · [docs/architecture.md](docs/architecture.md) ·
[docs/conventions.md](docs/conventions.md) · [docs/decisions.md](docs/decisions.md) (ADR-001–022) ·
[docs/hardware-annahmen.md](docs/hardware-annahmen.md) · [docs/protokoll/current-sprint.md](docs/protokoll/current-sprint.md)
