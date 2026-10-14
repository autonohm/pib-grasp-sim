# Fremdbestandteile

| Bestandteil | Wo im Repo | Herkunft | Lizenz |
|---|---|---|---|
| pib-CAD: Meshes (STL), URDF-Exporte, USD-Geometrie | `ros2_ws/src/pib_description_v4/meshes/`, `ros2_ws/src/pib_description_v5/`, `pib_hand_left_urdf_v5/`, `pib_upperbody_urdf_v5/`, `isaac_sim/usd/` | pib von isento GmbH (öffentliches Onshape-Dokument, [pib.rocks](https://pib.rocks)), exportiert mit `onshape-to-robot` | **ungeklärt** — vor einer Weitergabe bei isento erfragen |
| `topic_based_ros2_control` | `ros2_ws/src/topic_based_ros2_control/` | PickNik Robotics (Jafar, Marq Rasmussen) | BSD-Lizenz, siehe `LICENSE` im Ordner |
| Isaac Lab (Dexsuite-Muster) | Teile von `isaac_lab/pib_grasp/mdp.py` und `env_cfg.py` sind an Isaac Labs Dexsuite angelehnt bzw. davon abgeleitet; `train.py`/`play.py` rufen Isaac Labs Skripte auf | NVIDIA, [isaac-sim/IsaacLab](https://github.com/isaac-sim/IsaacLab) | BSD-3-Clause (Copyright-Hinweis von Isaac Lab beibehalten) |
| YCB-Objekte | **nicht im Repo** — zur Laufzeit von NVIDIAs Asset-Server geladen (`ISAAC_NUCLEUS_DIR/Props/YCB`) | YCB Object and Model Set (Yale, Berkeley, CMU) | CC BY 4.0 |
| Isaac-Sim-Assets | **nicht im Repo**, nur referenziert | NVIDIA | NVIDIA-Lizenz, nicht weiterverteilen |
| Policies (Release-ZIPs) | GitHub-Release `v0.1-praesentation` | in diesem Projekt trainiert | wie der eigene Code (siehe `LICENSE`) |
