# RepsCV

**Track your push-ups. Save your progress. Make every rep count.**

[**Open RepsCV →**](https://repscv.onrender.com/)

RepsCV is a mobile-first fitness web app that uses your camera to track push-ups
and give live feedback. Complete workouts, earn XP, build your personal record,
and see where you stand on the weekly leaderboard—all from your browser.

## Try it

1. Open [repscv.onrender.com](https://repscv.onrender.com/) and create an account.
2. Choose Push-ups and select Normal Workout or Max Set.
3. Allow camera access and position your phone to the side, with your full body visible.
4. Check the preview and tracking feedback, then start your workout.
5. Finish your session and review your results, dashboard, and history.

Use Safari on iPhone or Chrome on Android as a starting point. A stable internet
connection is required for live counting. Tracking depends on lighting, framing,
and how clearly the camera can see your body.

## Features

- **Live tracking:** camera preview, skeleton overlay, server-counted reps, and form feedback.
- **Normal Workout:** train at your pace with unlimited rest; press Finish when done.
- **Max Set:** complete your first rep within 20 seconds, then each next rep within 5 seconds.
- **Saved progress:** workout results, history, lifetime XP, and completed Max Set personal bests.
- **Dashboard:** recent workouts, total valid push-ups, and weekly progress.
- **Weekly leaderboard:** rank by earned XP, with equal XP sharing the same rank.
- **Profile:** account details and an optional, editable NTHU department.

Registration and Profile use the same optional department dropdown, served by
`GET /api/departments`. Python validates selections and stores the short code
(for example, `CS`); clearing a selection stores `NULL`.

Existing databases need no schema change or reset. On startup (or when running
`python -m backend.init_db`), an idempotent transaction converts known department
codes, exact full names, and dropdown labels to canonical codes, ignoring case
and extra whitespace. Blank entries become `NULL`. Unrecognized text is retained
and displayed in Profile until its owner chooses a listed department or clears
it; it is never guessed or discarded. Credentials, sessions, workouts, and XP
are untouched by this conversion. Back up an existing database with
`uv run python -m backend.backup /path/to/new-backup.db` before upgrading.

Completed workouts earn **10 XP per accepted push-up**. A zero-rep workout can
be saved and earns zero XP. Interrupted Max Sets earn no XP or personal best.
Max Sets are interrupted by a dropped workout connection or prolonged tracking
loss, so keep the workout page open while exercising.

The leaderboard week runs from Monday at 00:00 to the following Monday at 00:00
in **Asia/Taipei**. Workout history displays times in your device’s timezone.

## How it works

```text
Phone camera → MediaPipe pose landmarks → WebSocket → Python workout engine
                                                         ↓
React interface ← live rep count and feedback       SQLite results and XP
```

MediaPipe Pose Landmarker runs in the browser. The frontend sends selected body
landmarks and confidence values to Python, which validates posture and counts a
stable top–bottom–top movement as one repetition. Python also controls workout
deadlines, finalization, XP, and personal-best eligibility.

The counter follows one consistently visible arm; a sufficiently confident second
arm also checks symmetry. Endpoint confirmation requires at least two observations
spanning 80 ms. Small angle jitter can preserve pending evidence, but does not
replace the required depth or extension observations. A brief missing-landmark
gap (up to 250 ms since the last usable pose) preserves an already confirmed phase;
it cannot establish a new phase or earn a rep. Observed invalid posture or longer
tracking loss requires starting again from the top. Frozen camera frames are not
resent as new observations.

Detector parameters live in `backend/rep_counter.py`; Max Set deadlines remain
in `backend/workouts.py`. Only accepted reps renew the five-second deadline.
The workout **Details** panel shows the server's measured arm, elbow/body angles,
and movement phase to help distinguish missed depth, extension, and tracking loss.
These are camera estimates, not professional form assessments.

When checking tracker changes on a phone, first use Normal Workout and manually
compare ten controlled reps and ten quicker reps with the displayed count. Also
try shallow reps, a top hold, and briefly moving out of view: none should create
extra reps. Then try Max Set, confirming that each accepted rep renews the timer
and five seconds without another accepted rep ends the set. Repeat with the same
framing on iPhone/Safari and Android/Chrome; automated landmark sequences alone
do not establish camera accuracy.

**Camera video stays on your device.** Audio is disabled, and the app does not
record or upload video. Body coordinates are transmitted to the backend for
live validation and counting.

| Layer | Technology |
| --- | --- |
| Interface | React, TypeScript, Vite |
| Browser pose estimation | MediaPipe Pose Landmarker |
| API and live workout engine | Python, FastAPI, WebSockets |
| Data storage | SQLite, SQLAlchemy |
| Password hashing | Argon2 |

## Run locally with Docker

Install and start Docker, then run these commands from the repository root:

```sh
docker build -t repscv .
docker volume create repscv-data
docker run --rm --name repscv -p 8000:8000 \
  --mount source=repscv-data,target=/data \
  -e REPSCV_DATABASE_URL=sqlite:////data/repscv.db repscv
```

Open **http://localhost:8000**. Camera access works on localhost without HTTPS.
If port 8000 is already in use, stop the other server first or change the port
mapping to `-p 8001:8000` and open http://localhost:8001.

The named Docker volume preserves accounts and workouts when the container
stops. It uses a separate database from a native local checkout. Press `Ctrl+C`
to stop the app; rerun the `docker run` command to start it again. Keep the volume
to retain your data.

The first build needs internet access to install dependencies and download the
pose model. Model and WASM assets are then bundled with the application.

## Development setup

Prerequisites: **Python 3.13**, **Node.js 24**, and **uv**. Python 3 must also be
available as `python3` for the frontend asset preparation script.

From the repository root, start the backend:

```sh
uv sync --frozen
uv run python -m backend.init_db
uv run uvicorn backend.main:app --reload
```

In a second terminal, start the frontend:

```sh
cd frontend
npm ci
npm run dev
```

Open the localhost URL printed by Vite. Its development proxy forwards API and
WebSocket traffic to the backend on port 8000. The native development database
is `repscv.db` in the repository root; initialization creates missing tables
without resetting existing data.

To use the built frontend locally instead of Vite:

```sh
cd frontend
npm run build
cd ..
uv run python -m backend.serve
```

Stop the development backend first if it is using port 8000, then open
http://localhost:8000. Run one backend process: active workout counters and
timers currently live in that process’s memory.

## Checks

Run the Python tests from the repository root:

```sh
uv run python -m unittest discover -s backend -p 'test_*.py' -v
```

Run frontend tests, lint, and the TypeScript/production build:

```sh
cd frontend
npm test
npm run lint
npm run build
cd ..
git diff --check
```

Additional checks from the repository root:

```sh
uv run python scripts/smoke_production.py
python3 scripts/source_share.py
```

The smoke test uses a disposable local HTTPS server, certificate, and database;
it requires OpenSSL. The source-share script reports first-party source lines
and bytes, excluding dependencies and generated output.

## Project structure

```text
backend/       Pose validation, rep counting, sessions, authentication, data APIs
frontend/      React screens, camera access, MediaPipe, skeleton overlay
scripts/       Pose asset preparation, source measurement, local smoke test
Dockerfile     Reproducible frontend build and Python runtime
```

RepsCV currently supports push-ups in Normal Workout and Max Set modes. Pose
checks are camera-based estimates; automated tests verify defined movement and
session rules, rather than establishing a real-world accuracy percentage.
