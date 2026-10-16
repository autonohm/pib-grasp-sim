# ROS 2 environment for the digital twin — source it in every terminal:  source ros2_ws/env.sh
# Environment variables only live in the shell that sets them, so every new terminal needs this once.
# Turns off an active .venv/conda (ROS 2 Jazzy runs on the system Python 3.12), sources ROS 2 and this
# workspace, sets ROS_DOMAIN_ID to the same value everywhere (0, or PIB_ROS_DOMAIN_ID) — Isaac Sim and ros2_control
# only see each other within one domain, a ROS_DOMAIN_ID from ~/.bashrc is overridden — and changes to the repo root.
_pib_ws="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
type deactivate >/dev/null 2>&1 && deactivate
type conda >/dev/null 2>&1 && [ -n "$CONDA_PREFIX" ] && conda deactivate
source /opt/ros/jazzy/setup.bash
if [ -f "$_pib_ws/install/setup.bash" ]; then
    source "$_pib_ws/install/setup.bash"
else
    echo "ros2_ws noch nicht gebaut: cd $_pib_ws && colcon build"
fi
export ROS_DOMAIN_ID="${PIB_ROS_DOMAIN_ID:-0}"
cd "$_pib_ws/.."
echo "ROS 2 Jazzy + pib-Workspace aktiv (ROS_DOMAIN_ID=$ROS_DOMAIN_ID) in $(pwd)"
unset _pib_ws
