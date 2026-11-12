"""Account, workout, timeout, ownership, and atomic scoring integration tests."""

from concurrent.futures import ThreadPoolExecutor
import unittest

from sqlalchemy import func, select

from backend.database import User, Workout, WorkoutSession, XPTransaction
from backend.test_helpers import ApiCase
from backend.test_rep_counter import frame, wire


class LifecycleTests(ApiCase):
    def test_registration_login_profile_logout_and_csrf(self):
        self.assertEqual(self.client.get("/api/auth/me").status_code, 401)
        self.assertEqual(self.client.post("/api/auth/register", json={"username": "ab", "password": "password123"}).status_code, 422)
        self.assertEqual(self.client.post("/api/auth/register", json={"username": "student", "password": "short"}).status_code, 422)
        self.register("student")
        cookie = self.client.cookies.get("repscv_session")
        self.assertIsNotNone(cookie)
        with self.app.state.session_factory() as db:
            stored = db.scalar(select(User).where(User.username == "student"))
            self.assertTrue(stored.password_hash.startswith("$argon2"))
            self.assertNotEqual(stored.password_hash, "password123")
        self.assertEqual(self.client.post("/api/auth/register", json={"username": "student", "password": "password123"}).status_code, 409)
        self.assertEqual(self.client.get("/api/auth/me").json()["username"], "student")
        self.assertEqual(self.client.patch("/api/profile", json={"department": "CS"}).status_code, 403)
        self.assertEqual(self.client.patch("/api/profile", json={"department": "CS"},
                                           headers={"X-CSRF-Token": self.csrf, "Origin": "https://evil.example"}).status_code, 403)
        updated = self.client.patch("/api/profile", json={"department": "CS"}, headers={"X-CSRF-Token": self.csrf})
        self.assertEqual(updated.json()["department"], "CS")
        self.assertEqual(self.post("/api/auth/logout").status_code, 200)
        self.assertEqual(self.client.get("/api/auth/me").status_code, 401)
        self.assertEqual(self.client.post("/api/auth/login", json={"username": "student", "password": "wrongpass"}).status_code, 401)
        login = self.client.post("/api/auth/login", json={"username": "student", "password": "password123"})
        self.assertEqual(login.status_code, 200)
        self.assertIn("httponly", login.headers["set-cookie"].lower())
        self.assertIn("samesite=lax", login.headers["set-cookie"].lower())
        self.assertEqual(login.json()["department"], "CS")

    def test_normal_zero_rep_unlimited_rest_and_explicit_finish(self):
        self.register()
        empty_id = self.start()
        self.clock.advance(3600)
        self.assertEqual(self.client.get(f"/api/workouts/{empty_id}").json()["status"], "active")
        empty = self.post(f"/api/workouts/{empty_id}/finish").json()
        self.assertEqual((empty["status"], empty["rep_count"], empty["xp_earned"]), ("completed", 0, 0))
        self.assertEqual(empty["duration_ms"], 3600000)
        full_id = self.start()
        with self.websocket(full_id) as socket:
            self.assertEqual(self.rep(socket)["rep_count"], 1)
            self.clock.advance(3600)
            self.assertEqual(self.rep(socket)["rep_count"], 2)
        self.assertEqual(self.client.get(f"/api/workouts/{full_id}").json()["status"], "active")
        result = self.post(f"/api/workouts/{full_id}/finish").json()
        self.assertEqual((result["rep_count"], result["xp_earned"]), (2, 20))
        self.assertEqual(len(self.client.get("/api/workouts").json()), 2)

    def test_one_active_and_other_user_cannot_own_or_finish(self):
        self.register()
        session_id = self.start()
        self.assertEqual(self.post("/api/workouts/start", {"exercise": "pushup", "mode": "normal"}).status_code, 409)
        self.assertEqual(self.post("/api/workouts/start", {"exercise": "squat", "mode": "normal"}).status_code, 422)
        from fastapi.testclient import TestClient
        with TestClient(self.app) as second:
            registered = second.post("/api/auth/register", json={"username": "student_two", "password": "password123"})
            csrf = registered.json()["csrf_token"]
            self.assertEqual(second.get(f"/api/workouts/{session_id}").status_code, 404)
            self.assertEqual(second.post(f"/api/workouts/{session_id}/finish", headers={"X-CSRF-Token": csrf}).status_code, 404)
            self.assertEqual(second.get("/api/workouts").json(), [])
        self.assertEqual(self.client.get(f"/api/workouts/{session_id}").json()["status"], "active")

    def test_first_rep_and_between_rep_timeouts(self):
        self.register()
        first_id = self.start("max_set")
        with self.websocket(first_id) as socket:
            for _ in range(19):
                self.pose(socket, 170, step=1)
            self.clock.advance(1.1)
            result = self.client.get(f"/api/workouts/{first_id}").json()
            self.assertEqual((result["status"], result["rep_count"], result["xp_earned"]), ("completed", 0, 0))
        second_id = self.start("max_set")
        with self.websocket(second_id) as socket:
            self.assertEqual(self.rep(socket)["rep_count"], 1)
            for _ in range(4):
                self.pose(socket, 170, step=1)
            self.clock.advance(1.1)
            result = self.client.get(f"/api/workouts/{second_id}").json()
            self.assertEqual((result["status"], result["rep_count"], result["xp_earned"]), ("completed", 1, 10))
            self.assertTrue(result["new_personal_best"])

    def test_manual_max_set_pb_ties_and_normal_exclusion(self):
        self.register()
        first = self.start("max_set")
        with self.websocket(first) as socket:
            self.rep(socket)
            result = self.post(f"/api/workouts/{first}/finish").json()
            self.assertTrue(result["new_personal_best"])
            self.assertEqual(result["xp_earned"], 10)
        tied = self.start("max_set")
        with self.websocket(tied) as socket:
            self.rep(socket)
            result = self.post(f"/api/workouts/{tied}/finish").json()
            self.assertFalse(result["new_personal_best"])
        normal = self.start()
        with self.websocket(normal) as socket:
            self.rep(socket)
            self.rep(socket)
            result = self.post(f"/api/workouts/{normal}/finish").json()
            self.assertFalse(result["new_personal_best"])
            self.assertEqual(result["xp_earned"], 20)

    def test_tracking_loss_and_socket_disconnection_interrupt_max_set(self):
        self.register()
        lost_id = self.start("max_set")
        with self.websocket(lost_id) as socket:
            self.rep(socket)
            for _ in range(3):
                self.clock.advance(0.5)
                socket.send_json(wire({"aspect_ratio": 1, "landmarks": None}, self.sequence))
                self.sequence += 1
                socket.receive_json()
            self.clock.advance(0.6)
            result = self.client.get(f"/api/workouts/{lost_id}").json()
            self.assertEqual(result["status"], "interrupted")
            self.assertEqual((result["rep_count"], result["xp_earned"], result["new_personal_best"]), (1, 0, False))
        dropped_id = self.start("max_set")
        with self.websocket(dropped_id) as socket:
            self.rep(socket)
        dropped = self.client.get(f"/api/workouts/{dropped_id}").json()
        self.assertEqual((dropped["status"], dropped["xp_earned"]), ("interrupted", 0))
        self.assertEqual(len(self.client.get("/api/workouts").json()), 0)

    def test_repeated_and_concurrent_finish_are_idempotent_and_atomic(self):
        self.register()
        session_id = self.start()
        with self.websocket(session_id) as socket:
            self.rep(socket)
            def finish_once(_):
                return self.post(f"/api/workouts/{session_id}/finish")
            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(finish_once, range(2)))
        self.assertTrue(all(response.status_code == 200 for response in results))
        self.assertEqual(results[0].json(), results[1].json())
        self.assertEqual(self.post(f"/api/workouts/{session_id}/finish").json(), results[0].json())
        with self.app.state.session_factory() as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(Workout).where(Workout.session_id == session_id)), 1)
            self.assertEqual(db.scalar(select(func.count()).select_from(XPTransaction)), 1)
            self.assertEqual(db.scalar(select(XPTransaction.amount)), 10)

    def test_normal_refresh_reconnect_preserves_server_count(self):
        self.register()
        session_id = self.start()
        with self.websocket(session_id) as socket:
            self.assertEqual(self.rep(socket)["rep_count"], 1)
        self.assertEqual(self.client.get("/api/auth/me").json()["active_workout"]["id"], session_id)
        self.sequence = 0  # New browser socket starts its own sequence.
        with self.websocket(session_id) as socket:
            self.assertEqual(self.rep(socket)["rep_count"], 2)
        self.assertEqual(self.post(f"/api/workouts/{session_id}/finish").json()["xp_earned"], 20)


if __name__ == "__main__":
    unittest.main()
