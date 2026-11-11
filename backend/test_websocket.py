"""Exercise the WebSocket protocol without an HTTP test client dependency."""

import asyncio
import itertools
import json
import unittest
from unittest.mock import patch

from fastapi import WebSocketDisconnect

from backend.main import websocket_endpoint
from backend.test_rep_counter import frame


class FakeWebSocket:
    def __init__(self, messages):
        self.messages = iter(messages)
        self.responses = []
        self.accepted = False

    async def accept(self):
        self.accepted = True

    async def receive_text(self):
        try:
            return next(self.messages)
        except StopIteration:
            raise WebSocketDisconnect()

    async def send_json(self, response):
        self.responses.append(response)


class WebSocketTests(unittest.TestCase):
    def run_socket(self, messages):
        socket = FakeWebSocket(messages)
        ticks = itertools.count()
        with patch("backend.rep_counter.time.monotonic", side_effect=lambda: next(ticks) * 0.06):
            asyncio.run(websocket_endpoint(socket))
        self.assertTrue(socket.accepted)
        return socket.responses

    def test_structured_updates_and_one_count(self):
        poses = [frame(170)] * 3 + [frame(90)] * 3 + [frame(170)] * 3
        responses = self.run_socket([json.dumps(pose) for pose in poses])
        self.assertEqual(len(responses), 9)
        self.assertEqual(responses[-1]["reps"], 1)
        self.assertEqual(responses[-1]["state"], "UP")
        self.assertTrue(responses[-1]["form_valid"])
        self.assertEqual(responses[-1]["tracking"], "tracked")
        self.assertIsInstance(responses[-1]["feedback"], str)
        self.assertEqual(self.run_socket([json.dumps(frame(170))])[-1]["reps"], 0)

    def test_bad_json_and_lost_pose_have_safe_responses(self):
        responses = self.run_socket(["{", json.dumps({"aspect_ratio": 1, "landmarks": None})])
        self.assertEqual(responses[0]["tracking"], "error")
        self.assertEqual(responses[0]["reps"], 0)
        self.assertEqual(responses[1]["tracking"], "lost")
        self.assertEqual(responses[1]["state"], "UNKNOWN")

    def test_bad_frame_clears_an_unfinished_rep(self):
        messages = [json.dumps(frame(170))] * 3
        messages += [json.dumps(frame(90))] * 3
        messages += ["not json"]
        messages += [json.dumps(frame(170))] * 3
        responses = self.run_socket(messages)
        self.assertEqual(responses[5]["state"], "DOWN")
        self.assertEqual(responses[6]["state"], "UNKNOWN")
        self.assertEqual(responses[-1]["reps"], 0)


if __name__ == "__main__":
    unittest.main()
