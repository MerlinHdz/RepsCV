import unittest

from starlette.websockets import WebSocketDisconnect

from backend.test_helpers import ApiCase
from backend.test_rep_counter import frame, wire


class WebSocketTests(ApiCase):
    def test_authenticated_landmarks_and_sequence_check(self):
        self.register()
        session_id = self.start()
        with self.websocket(session_id) as socket:
            response = self.pose(socket, 170)
            self.assertEqual(response["type"], "workout_update")
            self.assertEqual(response["rep_count"], 0)
            socket.send_json(wire(frame(90), self.sequence - 1))
            self.assertEqual(socket.receive_json()["type"], "ignored")
            self.assertEqual(self.rep(socket)["rep_count"], 1)
        saved = self.post(f"/api/workouts/{session_id}/finish").json()
        self.assertEqual((saved["rep_count"], saved["xp_earned"]), (1, 10))

    def test_invalid_frames_never_grant_reps(self):
        self.register()
        session_id = self.start()
        with self.websocket(session_id) as socket:
            socket.send_text("{")
            self.assertEqual(socket.receive_json()["type"], "error")
            socket.send_text("x" * 9000)
            self.assertEqual(socket.receive_json()["type"], "error")
            invalid = wire(frame(170), 0)
            invalid["aspect_ratio"] = float("nan")
            socket.send_json(invalid)
            self.assertEqual(socket.receive_json()["type"], "error")
        self.assertEqual(self.post(f"/api/workouts/{session_id}/finish").json()["xp_earned"], 0)

    def test_missing_or_wrong_origin_and_no_auth_are_rejected(self):
        self.register()
        session_id = self.start()
        with self.assertRaises(WebSocketDisconnect) as wrong:
            with self.websocket(session_id, "https://evil.example") as socket:
                socket.receive_json()
        self.assertEqual(wrong.exception.code, 4403)
        other = self.client.__class__(self.app)
        with other:
            with self.assertRaises(WebSocketDisconnect) as unauthenticated:
                with other.websocket_connect(f"/ws/workouts/{session_id}", headers={"Origin": "http://testserver"}) as socket:
                    socket.receive_json()
        self.assertEqual(unauthenticated.exception.code, 4401)

    def test_other_user_socket_and_revoked_login_are_rejected(self):
        self.register()
        session_id = self.start()
        from fastapi.testclient import TestClient
        with TestClient(self.app) as second:
            second.post("/api/auth/register", json={"username": "other_student", "password": "password123"})
            with self.assertRaises(WebSocketDisconnect) as forbidden:
                with second.websocket_connect(f"/ws/workouts/{session_id}",
                                              headers={"Origin": "http://testserver"}) as socket:
                    socket.receive_json()
            self.assertEqual(forbidden.exception.code, 4404)
        with self.websocket(session_id) as socket:
            self.assertEqual(self.post("/api/auth/logout").status_code, 200)
            socket.send_json(wire(frame(170), 0))
            with self.assertRaises(WebSocketDisconnect) as revoked:
                socket.receive_json()
            self.assertEqual(revoked.exception.code, 4401)


if __name__ == "__main__":
    unittest.main()
