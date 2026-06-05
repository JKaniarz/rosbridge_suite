from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import TYPE_CHECKING
import bson

import launch_ros
from launch.actions import DeclareLaunchArgument
from launch.launch_description import LaunchDescription
from launch.substitutions import LaunchConfiguration
from launch_testing.actions import ReadyToTest
from rclpy.qos import HistoryPolicy, QoSProfile, ReliabilityPolicy
from std_msgs.msg import Int32
from twisted.python import log

sys.path.append(str(Path(__file__).parent))  # enable importing from common.py in this directory

import common
from common import expect_messages, sleep, websocket_test

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from common import TestClientProtocol
    from rclpy.node import Node


log.startLogging(sys.stderr)

def generate_test_description() -> LaunchDescription:
    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "use_events_executor",
                default_value="false",
                description="Use EventsExecutor instead of SingleThreadedExecutor",
            ),
            launch_ros.actions.Node(
                executable="rosbridge_websocket",
                package="rosbridge_server",
                parameters=[
                    {
                        "port": 0,
                        "use_events_executor": LaunchConfiguration("use_events_executor"),
                        "bson_only_mode": True,
                    }
                ],
            ),
            ReadyToTest(),
        ]
    )


class TestBsonPublisher(unittest.TestCase):
    @websocket_test
    async def test_bson_publisher(
        self, node: Node, make_client: Callable[[], Awaitable[TestClientProtocol]]
    ) -> None:

        pub_a = await make_client()

        sub_a = await make_client()
        sub_a_completed_future, sub_a.message_handler = expect_messages(
            1, "Sub A", node.get_logger()
        )
        executor = node.executor
        assert executor is not None
        sub_a_completed_future.add_done_callback(lambda _: executor.wake())
 
        await sleep(node, 1)  # wait for publisher to be set up

        pub_a.sendBson(
            {"op": "advertise", "topic": "/a_topic", "type": "std_msgs/Int32"}
        )
            
        sub_a.sendBson(
            {"op": "subscribe", "topic": "/a_topic", "type": "std_msgs/Int32"}
        )

        await sleep(node, 1)  # wait for subscriber to be set up

        # guaranteed to blow up bytes.decode("utf-8") if BSON is processed as JSON
        KABOOM = {"op": "publish", "topic": "/a_topic", "msg": {"data": 0x800080}}

        pub_a.sendBson(KABOOM)

        self.assertEqual(
            await sub_a_completed_future,
            [bson.encode(KABOOM)],
        )
