"""
pib_sim.launch.py — starts the complete ros2_control stack for Isaac Sim.

Prerequisite: Isaac Sim is running, USD (with Action Graph) loaded, start.py executed, Play pressed.

Start:
  source /opt/ros/jazzy/setup.bash
  source <repo>/ros2_ws/install/setup.bash
  ros2 launch pib_bringup pib_sim.launch.py
"""
import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import RegisterEventHandler
from launch.event_handlers import OnProcessExit
from launch_ros.actions import Node


def generate_launch_description():
    # URDF einlesen
    urdf_path = os.path.join(
        get_package_share_directory("pib_description_v4"),
        "urdf", "pib_upperbody.urdf"
    )
    with open(urdf_path, "r") as f:
        robot_description = f.read()

    # Controller-Konfiguration
    controllers_yaml = os.path.join(
        get_package_share_directory("pib_bringup"),
        "config", "controllers.yaml"
    )

    # robot_state_publisher — publishes the URDF on the /robot_description topic
    # (Jazzy: controller_manager subscribes to the topic instead of reading a parameter)
    robot_state_publisher = Node(
        package="robot_state_publisher",
        executable="robot_state_publisher",
        parameters=[{"robot_description": robot_description}],
        output="screen",
    )

    # Controller Manager
    controller_manager = Node(
        package="controller_manager",
        executable="ros2_control_node",
        parameters=[
            {"robot_description": robot_description},
            controllers_yaml,
        ],
        output="screen",
    )

    # JointStateBroadcaster spawnen
    joint_state_broadcaster_spawner = Node(
        package="controller_manager",
        executable="spawner",
        arguments=["joint_state_broadcaster"],
    )

    # spawn the JointTrajectoryController — only after the JointStateBroadcaster
    joint_trajectory_controller_spawner = Node(
        package="controller_manager",
        executable="spawner",
        arguments=["joint_trajectory_controller"],
    )

    delay_jtc = RegisterEventHandler(
        event_handler=OnProcessExit(
            target_action=joint_state_broadcaster_spawner,
            on_exit=[joint_trajectory_controller_spawner],
        )
    )

    return LaunchDescription([
        robot_state_publisher,
        controller_manager,
        joint_state_broadcaster_spawner,
        delay_jtc,
    ])
