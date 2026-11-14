"""Production origin, static serving, durable records, and recovery contracts."""

from contextlib import closing
from pathlib import Path
import os
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from datetime import timedelta

from fastapi import HTTPException
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from backend.backup import backup
from backend.config import Settings
from backend.main import create_app
from backend.rate_limit import AuthThrottle
from backend.test_helpers import FakeClock
from backend.workouts import WorkoutLimits
from backend.database import LoginSession, utcnow
from sqlalchemy import select
from sqlalchemy.exc import OperationalError


class ProductionTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.dist = self.root / "dist"
        self.dist.mkdir()
        (self.dist / "assets").mkdir()
        (self.dist / "index.html").write_text("<html>RepsCV production</html>")
        (self.dist / "assets/app.js").write_text("console.log('RepsCV')")
        self.env = patch.dict(os.environ, {
            "REPSCV_ENV": "production", "REPSCV_PUBLIC_ORIGIN": "https://repscv.example",
            "REPSCV_DATABASE_URL": f"sqlite:///{self.root / 'app.db'}",
            "REPSCV_FRONTEND_DIST": str(self.dist),
        })
        self.env.start()
        self.clock = FakeClock()

    def tearDown(self):
        self.env.stop()
        self.directory.cleanup()

    def app(self):
        return create_app(clock=self.clock, limits=WorkoutLimits(timer_poll_seconds=3600))

    def client(self, app=None):
        return TestClient(app or self.app(), base_url="https://repscv.example")

    def register(self, client):
        response = client.post("/api/auth/register", json={
            "username": "student", "password": "password123"},
            headers={"Origin": "https://repscv.example"})
        self.assertEqual(response.status_code, 201, response.text)
        return response

    def test_static_routes_api_boundaries_and_security_headers(self):
        with self.client() as client:
            for path in ("/", "/dashboard", "/history", "/leaderboard", "/result/12"):
                response = client.get(path)
                self.assertIn("RepsCV production", response.text)
                self.assertEqual(response.headers["x-content-type-options"], "nosniff")
            self.assertEqual(client.get("/assets/app.js").status_code, 200)
            for path in ("/api/missing", "/ws/missing", "/assets/missing.js", "/.env"):
                self.assertEqual(client.get(path).status_code, 404)
            self.assertEqual(client.get("/api/dashboard").status_code, 401)
            self.assertEqual(client.get("/api/health").json()["status"], "ok")
            self.assertEqual(client.get("/api/health").headers["cache-control"], "no-store")
            self.assertEqual(client.get("/", headers={"Host": "evil.example"}).status_code, 400)

    def test_secure_cookie_csrf_and_strict_origin(self):
        with self.client() as client:
            response = self.register(client)
            cookie = response.headers["set-cookie"]
            for attribute in ("Secure", "HttpOnly", "SameSite=lax"):
                self.assertIn(attribute, cookie)
            token = response.json()["csrf_token"]
            self.assertEqual(client.post("/api/workouts/start", json={
                "exercise": "pushup", "mode": "normal"}).status_code, 403)
            headers = {"X-CSRF-Token": token, "Origin": "https://evil.example"}
            self.assertEqual(client.patch("/api/profile", json={"department": None},
                                          headers=headers).status_code, 403)
            headers["Origin"] = "https://repscv.example"
            self.assertEqual(client.patch("/api/profile", json={"department": "CS"},
                                          headers=headers).status_code, 200)
            invalid = client.post("/api/auth/login", json={"username": "x", "password": "secret"})
            self.assertNotIn("secret", invalid.text)

    def test_production_websocket_authentication_and_origin(self):
        with self.client() as client:
            with self.assertRaises(WebSocketDisconnect):
                with client.websocket_connect("wss://repscv.example/ws/workouts/1", headers={"Origin": "https://repscv.example"}):
                    pass
            token = self.register(client).json()["csrf_token"]
            session = client.post("/api/workouts/start", json={"exercise": "pushup", "mode": "normal"},
                                  headers={"X-CSRF-Token": token}).json()["id"]
            with self.assertRaises(WebSocketDisconnect):
                with client.websocket_connect(f"wss://repscv.example/ws/workouts/{session}", headers={"Origin": "https://evil.example"}):
                    pass
            with client.websocket_connect(f"wss://repscv.example/ws/workouts/{session}", headers={"Origin": "https://repscv.example"}) as socket:
                socket.send_json({})
                self.assertEqual(socket.receive_json()["type"], "error")

    def test_restart_preserves_login_results_and_idempotent_finish(self):
        with self.client() as first:
            token = self.register(first).json()["csrf_token"]
            cookie = first.cookies.get("repscv_session")
            headers = {"X-CSRF-Token": token}
            session = first.post("/api/workouts/start", json={"exercise": "pushup", "mode": "normal"}, headers=headers).json()["id"]
            finished = first.post(f"/api/workouts/{session}/finish", headers=headers).json()
            self.assertEqual(finished["xp_earned"], 0)
        with self.client() as second:
            second.cookies.set("repscv_session", cookie)
            self.assertEqual(second.get("/api/auth/me").status_code, 200)
            self.assertEqual(second.post(f"/api/workouts/{session}/finish", headers=headers).json(), finished)
            self.assertEqual(len(second.get("/api/workouts").json()), 1)
            session = second.post("/api/workouts/start", json={"exercise": "pushup", "mode": "max_set"}, headers=headers).json()["id"]
        with self.client() as third:
            third.cookies.set("repscv_session", cookie)
            result = third.get(f"/api/workouts/{session}").json()
            self.assertEqual((result["status"], result["xp_earned"]), ("interrupted", 0))

    def test_backup_restores_verified_records_without_overwrite(self):
        with self.client() as client:
            self.register(client)
            destination = self.root / "backup.db"
            backup(self.root / "app.db", destination)
            with self.assertRaises(ValueError):
                backup(self.root / "app.db", destination)
            with closing(sqlite3.connect(destination)) as db:
                self.assertEqual(db.execute("SELECT username FROM users").fetchone()[0], "student")
                self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0], "ok")

    def test_configuration_fails_closed(self):
        for values in ({"REPSCV_PUBLIC_ORIGIN": "http://example.com"},
                       {"REPSCV_PUBLIC_ORIGIN": "https://example.com/path"},
                       {"REPSCV_DATABASE_URL": "sqlite:///relative.db"},
                       {"REPSCV_ENV": "typo"}):
            with self.subTest(values=values), patch.dict(os.environ, values):
                with self.assertRaises(ValueError):
                    Settings.load()
        with patch.dict(os.environ, {"REPSCV_FRONTEND_DIST": str(self.root / "missing")}):
            with self.assertRaises(ValueError):
                self.app()

    def test_auth_throttle_expires_without_sleep(self):
        throttle = AuthThrottle(limit=2, window=60, clock=self.clock.monotonic)
        throttle.check("client")
        throttle.check("client")
        with self.assertRaises(HTTPException) as error:
            throttle.check("client")
        self.assertEqual(error.exception.status_code, 429)
        self.clock.advance(60)
        throttle.check("client")

    def test_expired_login_cannot_access_http_or_websocket(self):
        app = self.app()
        with self.client(app) as client:
            self.register(client)
            with app.state.session_factory() as db:
                login = db.scalar(select(LoginSession))
                login.expires_at = utcnow() - timedelta(seconds=1)
                db.commit()
            self.assertEqual(client.get("/api/auth/me").status_code, 401)
            with self.assertRaises(WebSocketDisconnect) as error:
                with client.websocket_connect("wss://repscv.example/ws/workouts/1",
                                               headers={"Origin": "https://repscv.example"}):
                    pass
            self.assertEqual(error.exception.code, 4401)

    def test_health_database_failure_returns_safe_unavailable_response(self):
        app = self.app()
        with self.client(app) as client:
            with patch("sqlalchemy.orm.Session.execute", side_effect=OperationalError(
                    "sensitive SQL", {}, Exception("private storage path"))):
                response = client.get("/api/health")
            self.assertEqual(response.status_code, 503)
            self.assertNotIn("private", response.text)
            self.assertNotIn("sensitive", response.text)

    def test_maintenance_has_no_database_connections_and_blocks_workouts(self):
        with patch.dict(os.environ, {"REPSCV_MAINTENANCE": "1"}):
            with self.client() as client:
                self.assertFalse((self.root / "app.db").exists())
                self.assertEqual(client.get("/api/health").json()["status"], "maintenance")
                self.assertEqual(client.get("/api/auth/me").status_code, 503)
                with self.assertRaises(WebSocketDisconnect) as error:
                    with client.websocket_connect("wss://repscv.example/ws/workouts/1"):
                        pass
                self.assertEqual(error.exception.code, 1013)
                self.assertFalse((self.root / "app.db").exists())

    def test_frame_storage_failure_interrupts_attempt_without_xp(self):
        with self.client() as client:
            token = self.register(client).json()["csrf_token"]
            session = client.post("/api/workouts/start", json={"exercise": "pushup", "mode": "normal"},
                                  headers={"X-CSRF-Token": token}).json()["id"]
            with client.websocket_connect(f"wss://repscv.example/ws/workouts/{session}",
                                           headers={"Origin": "https://repscv.example"}) as socket:
                with patch("sqlalchemy.orm.Session.commit", side_effect=OperationalError(
                        "write failed", {}, Exception("disk full"))):
                    socket.send_json({"type": "landmarks", "sequence": 0, "timestamp_ms": 0,
                                      "aspect_ratio": 1.33, "points": None})
                    with self.assertRaises(WebSocketDisconnect) as error:
                        socket.receive_json()
                    self.assertEqual(error.exception.code, 1011)
            result = client.post(f"/api/workouts/{session}/finish",
                                 headers={"X-CSRF-Token": token}).json()
            self.assertEqual((result["status"], result["xp_earned"]), ("interrupted", 0))
            self.assertEqual(client.get("/api/workouts").json(), [])



if __name__ == "__main__":
    unittest.main()
