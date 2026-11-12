"""Deterministic HTTP/WebSocket integration harness for workout tests."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Lock
import unittest

from fastapi.testclient import TestClient

from backend.main import create_app
from backend.test_rep_counter import frame, wire
from backend.workouts import WorkoutLimits


class FakeClock:
    def __init__(self):
        self.seconds = 0.0
        self.lock = Lock()
        self.base = datetime(2026, 11, 11, tzinfo=timezone.utc)

    def advance(self, seconds):
        with self.lock:
            self.seconds += seconds

    def monotonic(self):
        with self.lock:
            return self.seconds

    def utcnow(self):
        return self.base + timedelta(seconds=self.monotonic())


class ApiCase(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.clock = FakeClock()
        path = Path(self.directory.name) / "test.db"
        self.app = create_app(f"sqlite:///{path}", clock=self.clock,
                              limits=WorkoutLimits(timer_poll_seconds=3600))
        self.client_context = TestClient(self.app)
        self.client = self.client_context.__enter__()
        self.csrf = None
        self.sequence = 0

    def tearDown(self):
        self.client_context.__exit__(None, None, None)
        self.directory.cleanup()

    def register(self, username="student_one", password="password123"):
        response = self.client.post("/api/auth/register", json={"username": username, "password": password})
        self.assertEqual(response.status_code, 201, response.text)
        self.csrf = response.json()["csrf_token"]
        return response.json()

    def post(self, path, body=None):
        return self.client.post(path, json=body, headers={"X-CSRF-Token": self.csrf})

    def start(self, mode="normal"):
        response = self.post("/api/workouts/start", {"exercise": "pushup", "mode": mode})
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()["id"]

    def websocket(self, session_id, origin="http://testserver"):
        return self.client.websocket_connect(f"/ws/workouts/{session_id}",
                                             headers={"Origin": origin})

    def pose(self, socket, angle=170, step=0.06, **kwargs):
        self.clock.advance(step)
        message = wire(frame(angle, **kwargs), self.sequence)
        self.sequence += 1
        socket.send_json(message)
        return socket.receive_json()

    def rep(self, socket):
        responses = [self.pose(socket, angle) for angle in ([170] * 3 + [90] * 3 + [170] * 3)]
        self.assertEqual(responses[-1]["type"], "workout_update")
        return responses[-1]
