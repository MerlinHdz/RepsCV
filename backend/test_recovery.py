"""Persistence and safe single-process restart behavior."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from fastapi.testclient import TestClient

from backend.main import create_app
from backend.test_helpers import FakeClock
from backend.workouts import WorkoutLimits


class RecoveryTests(unittest.TestCase):
    def test_normal_survives_restart_and_max_set_fails_closed(self):
        with TemporaryDirectory() as directory:
            url = f"sqlite:///{Path(directory) / 'recovery.db'}"
            clock = FakeClock()
            limits = WorkoutLimits(timer_poll_seconds=3600)
            with TestClient(create_app(url, clock=clock, limits=limits)) as first:
                registered = first.post("/api/auth/register", json={
                    "username": "restart_student", "password": "password123"})
                csrf = registered.json()["csrf_token"]
                cookies = dict(first.cookies)
                normal = first.post("/api/workouts/start", json={"exercise": "pushup", "mode": "normal"},
                                    headers={"X-CSRF-Token": csrf}).json()["id"]

            clock.advance(5)
            with TestClient(create_app(url, clock=clock, limits=limits)) as second:
                second.cookies.update(cookies)
                self.assertEqual(second.get("/api/auth/me").json()["active_workout"]["id"], normal)
                finished = second.post(f"/api/workouts/{normal}/finish", headers={"X-CSRF-Token": csrf}).json()
                self.assertEqual((finished["status"], finished["xp_earned"]), ("completed", 0))
                max_set = second.post("/api/workouts/start", json={"exercise": "pushup", "mode": "max_set"},
                                      headers={"X-CSRF-Token": csrf}).json()["id"]
                cookies = dict(second.cookies)

            with TestClient(create_app(url, clock=clock, limits=limits)) as third:
                third.cookies.update(cookies)
                status = third.get(f"/api/workouts/{max_set}").json()
                self.assertEqual((status["status"], status["xp_earned"]), ("interrupted", 0))
                self.assertIsNone(third.get("/api/auth/me").json()["active_workout"])
                self.assertEqual(len(third.get("/api/workouts").json()), 1)


if __name__ == "__main__":
    unittest.main()
