"""A real short timer proves Max Set expires without another client message."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from fastapi.testclient import TestClient

from backend.main import create_app
from backend.workouts import WorkoutLimits


class TimerTests(unittest.TestCase):
    def test_background_timer_finalizes_without_frame_or_poll(self):
        with TemporaryDirectory() as directory:
            app = create_app(f"sqlite:///{Path(directory) / 'timer.db'}",
                             limits=WorkoutLimits(first_rep_seconds=0.15,
                                                  tracking_loss_seconds=1,
                                                  timer_poll_seconds=0.01))
            with TestClient(app) as client:
                registered = client.post("/api/auth/register", json={
                    "username": "timer_student", "password": "password123"})
                csrf = registered.json()["csrf_token"]
                started = client.post("/api/workouts/start", json={"exercise": "pushup", "mode": "max_set"},
                                      headers={"X-CSRF-Token": csrf})
                session_id = started.json()["id"]
                with client.websocket_connect(f"/ws/workouts/{session_id}",
                                              headers={"Origin": "http://testserver"}) as socket:
                    result = socket.receive_json()
                    self.assertEqual(result["type"], "workout_result")
                    self.assertEqual((result["status"], result["xp_earned"]), ("completed", 0))
                self.assertEqual(len(client.get("/api/workouts").json()), 1)

    def test_background_timer_interrupts_tracking_loss_without_frame(self):
        with TemporaryDirectory() as directory:
            app = create_app(f"sqlite:///{Path(directory) / 'loss.db'}",
                             limits=WorkoutLimits(first_rep_seconds=1,
                                                  tracking_loss_seconds=0.12,
                                                  timer_poll_seconds=0.01))
            with TestClient(app) as client:
                registered = client.post("/api/auth/register", json={
                    "username": "loss_student", "password": "password123"})
                started = client.post("/api/workouts/start", json={"exercise": "pushup", "mode": "max_set"},
                                      headers={"X-CSRF-Token": registered.json()["csrf_token"]})
                session_id = started.json()["id"]
                with client.websocket_connect(f"/ws/workouts/{session_id}",
                                              headers={"Origin": "http://testserver"}) as socket:
                    result = socket.receive_json()
                    self.assertEqual(result["status"], "interrupted")
                    self.assertEqual(result["xp_earned"], 0)
                self.assertEqual(client.get("/api/workouts").json(), [])


if __name__ == "__main__":
    unittest.main()
