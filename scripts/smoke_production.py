"""Local HTTPS smoke with a disposable database/certificate; no Vite required."""

from http.cookiejar import CookieJar
import json
import os
from pathlib import Path
import socket
import ssl
import subprocess
import sys
from tempfile import TemporaryDirectory
import time
from urllib.request import build_opener, HTTPCookieProcessor, HTTPSHandler, Request

ROOT = Path(__file__).resolve().parents[1]


def main():
    with TemporaryDirectory(prefix="repscv-smoke-") as directory:
        root = Path(directory)
        with socket.socket() as reservation:
            reservation.bind(("127.0.0.1", 0))
            port = reservation.getsockname()[1]
        cert, key = root / "cert.pem", root / "key.pem"
        subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
                        "-keyout", str(key), "-out", str(cert), "-days", "1",
                        "-subj", "/CN=localhost"], check=True, capture_output=True)
        origin = f"https://localhost:{port}"
        env = {**os.environ, "REPSCV_ENV": "production", "REPSCV_PUBLIC_ORIGIN": origin,
               "REPSCV_DATABASE_URL": f"sqlite:///{root / 'smoke.db'}",
               "REPSCV_FRONTEND_DIST": str(ROOT / "frontend/dist")}
        # Self-signed certificate is trusted only by this local disposable smoke client.
        client = build_opener(HTTPCookieProcessor(CookieJar()),
                              HTTPSHandler(context=ssl._create_unverified_context()))

        def request(path, body=None, csrf=None):
            headers = {"Origin": origin}
            if csrf:
                headers["X-CSRF-Token"] = csrf
            data = None
            if body is not None:
                data = json.dumps(body).encode()
                headers["Content-Type"] = "application/json"
            with client.open(Request(origin + path, data=data, headers=headers), timeout=5) as response:
                return response.read()

        process = subprocess.Popen([sys.executable, "-m", "uvicorn", "backend.main:app",
                                    "--host", "127.0.0.1", "--port", str(port),
                                    "--ssl-certfile", str(cert), "--ssl-keyfile", str(key),
                                    "--no-access-log"], cwd=ROOT, env=env)
        try:
            for _ in range(50):
                try:
                    request("/api/health")
                    break
                except OSError:
                    if process.poll() is not None:
                        raise RuntimeError("Server failed to start")
                    time.sleep(.1)
            else:
                raise RuntimeError("Health check timed out")
            assert b'<div id="root">' in request("/dashboard")
            assert len(request("/mediapipe/pose_landmarker_lite.task")) > 5_000_000
            account = json.loads(request("/api/auth/register", {"username": "smoke_student", "password": "smoke-password-only"}))
            csrf = account["csrf_token"]
            session = json.loads(request("/api/workouts/start", {"exercise": "pushup", "mode": "normal"}, csrf))
            first = json.loads(request(f"/api/workouts/{session['id']}/finish", {}, csrf))
            second = json.loads(request(f"/api/workouts/{session['id']}/finish", {}, csrf))
            assert first == second and first["xp_earned"] == 0
            assert len(json.loads(request("/api/workouts"))) == 1
            assert json.loads(request("/api/dashboard"))["lifetime_xp"] == 0
            assert json.loads(request("/api/leaderboard?period=weekly"))["current_user_rank"] == 1
            print("PASS: real HTTPS server, static routes/model, secure-cookie auth, saved zero-rep workout, duplicate Finish, dashboard and leaderboard")
        finally:
            process.terminate()
            process.wait(timeout=10)


if __name__ == "__main__":
    main()
