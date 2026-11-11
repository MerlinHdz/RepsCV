# RepsCV

Real-time push-up tracking with React, MediaPipe Pose Landmarker, and a Python
FastAPI WebSocket. The browser handles camera capture, skeleton drawing, and
landmark transport. Python validates the pose and owns the rep count.

## Run locally

With Python 3.13 and Node.js installed:

```sh
uv sync
uv run uvicorn backend.main:app --reload
```

In a second terminal:

```sh
cd frontend
npm ci
npm run dev
```

Open the Vite URL on localhost, place the camera to your side, and keep your
shoulder, hip, ankle, and at least one full arm in view. Camera access requires
localhost or HTTPS. MediaPipe WASM and its pose model load from external URLs.
The frontend connects to `ws(s)://<page-host>:8000/ws` by default; set
`VITE_WS_URL` to use a different WebSocket endpoint.

Each WebSocket connection is a separate workout session. Reconnecting resets
the displayed count because the Python counter starts a new session.

## Detection contract

The browser sends normalized image landmarks and their visibility and presence
scores, plus the video aspect ratio. It sends `landmarks: null` when no pose is
found. No camera frames or video bytes are sent to Python. Python calculates
elbow and body angles, rejects poor visibility, bent body alignment, unsuitable
camera orientation, and large differences between visible arms. It accepts one
visible arm, but an unfinished rep cannot switch between single visible arms.

Python returns `reps`, movement `state`, `tracking`, `form_valid`, `feedback`,
and measured angles for every frame. Thresholds are centralized in
`backend/rep_counter.py` as `Thresholds`. A rep requires a stable top, stable
bottom, and stable return to top with minimum elapsed time. Lost tracking or a
long frame gap clears an unfinished rep.

## Checks

```sh
.venv/bin/python -m unittest discover -s backend -p 'test_*.py' -v
cd frontend
npm test
npm run lint
npm run build
```

The detector has synthetic sequence tests. Its thresholds and real-world count
accuracy still need testing with recorded and live camera sessions across
different people, lighting, clothing, phone positions, and push-up styles.
