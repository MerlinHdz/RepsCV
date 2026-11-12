# RepsCV

RepsCV tracks push-ups with browser-based MediaPipe landmarks and a Python
FastAPI workout engine. Camera video stays in the browser. Python validates the
pose, counts repetitions, controls workout timing, and saves eligible results
and XP to SQLite. The old project name in `spec.md` refers to RepsCV.

## Local setup

Use Python 3.13, Node.js 24, and `uv`. From the repository root:

```sh
uv sync
uv run python -m backend.init_db
uv run uvicorn backend.main:app --reload
```

In another terminal:

```sh
cd frontend
npm ci
npm run dev
```

Open the Vite URL on localhost. Vite proxies `/api` and `/ws` to FastAPI on
port 8000, so cookies and WebSockets stay on one browser origin. For a phone,
serve the built frontend and proxy `/api` and `/ws` through one HTTPS domain.
Set `REPSCV_SECURE_COOKIES=1` when TLS terminates before FastAPI, and configure
the reverse proxy to pass the original Host, Origin, and protocol. `REPSCV_ALLOWED_ORIGINS`
may contain comma-separated additional trusted origins. Camera access requires
HTTPS or localhost. MediaPipe WASM and its model currently load from external
URLs, so an internet connection is needed.

`REPSCV_DATABASE_URL` defaults to `sqlite:///./repscv.db`. `backend.init_db`
and app startup call SQLAlchemy `create_all`, which creates missing tables and
indexes without deleting data. This is the initial schema approach; it does
not modify existing columns. Back up the SQLite file and add a migration before
changing this schema in a later version. Run one FastAPI process for this MVP:
Max Set deadlines and active pose counters live in that process. Multiple
workers would need shared coordination and are unsupported.

## Workout behavior

Registering signs the user in. The login cookie is HTTP-only, SameSite=Lax,
and Secure on HTTPS or with `REPSCV_SECURE_COOKIES=1`. Its random token is
stored only as a SHA-256 hash in `login_sessions`; passwords use Argon2. State
changing HTTP requests require the `X-CSRF-Token` returned by login/register
or `/api/auth/me`. WebSockets require the cookie, the exact allowed Origin,
and ownership of an active workout.

The user chooses Push-ups and a mode, prepares the camera, then presses Start.
The server allows one active workout per user. Normal Workout has unlimited
rest and ends only on explicit Finish; zero reps save with zero XP. Max Set
requires a first accepted rep within 20 seconds, then another within 5 seconds
of each accepted rep. A 0.2-second server timer enforces deadlines without
waiting for another frame. Tracking unusable for more than 2 seconds or a
WebSocket disconnect interrupts Max Set. These limits are in `WorkoutLimits`
in `backend/workouts.py`.

The Python pose detector in `backend/rep_counter.py` retains its stable
top/bottom/top counting and form checks. The browser sends only landmark
coordinates, confidence, video aspect ratio, and a connection-local sequence
number. The server ignores duplicate/stale sequences and rejects messages over
8 KiB. Browser timestamps are diagnostic only; all decisions use server time.

Completed workouts insert a result and one XP transaction in one database
transaction. XP is exactly `10 × accepted reps`, including a zero-amount
transaction for a completed zero-rep workout. Database uniqueness on
`workouts.session_id` and `xp_transactions.workout_id` prevents duplicate
awards. Interrupted attempts remain in `workout_sessions` for diagnosis but do
not appear in official history, earn XP, or establish a personal best. A Max
Set PB is earned only when a completed result strictly exceeds earlier saved
Max Set results; ties do not create a new PB.

Normal Workout survives navigation or refresh: `/api/auth/me` returns the
active session, its saved rep count, and the browser can prepare the camera and
reconnect to that same session. The pose phase is re-established after a long
tracking gap. A Max Set refresh closes its WebSocket and interrupts the set;
the UI reads the terminal status. An active Max Set left by a server restart
is marked interrupted at startup because its monotonic deadline cannot be
recovered. Duplicate Finish/End requests return the same saved result. A
normal workout abandoned without Finish stays active until the user returns
and finishes it; there is no invented pause or timeout.

## API and WebSocket

HTTP: `POST /api/auth/register`, `POST /api/auth/login`, `POST /api/auth/logout`,
`GET /api/auth/me`, `PATCH /api/profile`, `POST /api/workouts/start`,
`POST /api/workouts/{id}/finish`, and `GET /api/workouts`. The additional
read-only `GET /api/workouts/{id}` returns active status or a terminal result,
including interrupted attempts, so the client can recover after a disconnect.
Start accepts `{ "exercise": "pushup", "mode": "normal" | "max_set" }`.
Finish accepts no rep or XP fields.

Connect to `/ws/workouts/{id}` after Start. A frame is:

```json
{
  "type": "landmarks",
  "sequence": 42,
  "timestamp_ms": 2800,
  "aspect_ratio": 1.333,
  "points": {
    "left_shoulder": {"x": 0.42, "y": 0.35, "visibility": 0.98, "presence": 0.98}
  }
}
```

`points: null` reports no pose. The production client sends both sides' needed
landmarks when available. Server events are `workout_update` with `rep_count`,
`phase`, `tracking`, `form_valid`, `feedback`, `elapsed_ms`, and `remaining_ms`;
`workout_result` on terminal completion/interruption; or `error`/`ignored` for
bad or duplicate frames. The existing detector uses `UNKNOWN`, `UP`, and
`DOWN` phase names.

## Tests and source share

```sh
uv run python -m unittest discover -s backend -p 'test_*.py' -v
cd frontend
npm test
npm run lint
npm run build
cd ..
git diff --check
python3 scripts/source_share.py
```

`scripts/source_share.py` counts first-party Git tracked and currently untracked
reviewable `.py`, `.js`, `.jsx`, `.mjs`, `.ts`, `.tsx`, `.html`, and `.css`
files by source lines and UTF-8 bytes. It excludes dependencies, build output,
generated files, lockfiles, and binary assets. This is the specification's
internal metric; the course's official measurement method should be confirmed
with the TA.

### Manual acceptance check

1. On localhost or an HTTPS phone deployment, register, log out, log back in,
   and change the optional department.
2. Choose Normal Workout, allow camera access, confirm preview and skeleton,
   start, perform push-ups, rest, and press Finish. Check the result and saved
   entry after refresh. Also finish a zero-rep Normal Workout.
3. Start another Normal Workout, complete a rep, refresh, prepare the camera,
   reconnect, and verify the count continues from the server session.
4. Choose Max Set, verify the prominent countdown, complete reps, and use End.
   Repeat with a timeout, then with camera/WebSocket loss; interrupted attempts
   should show 0 XP and no PB.
5. Repeat Finish/End or refresh a result; XP and the saved workout must appear
   only once. Check the layout at 360–390 CSS pixels wide.

Automated tests use synthetic landmarks and a simulated camera protocol. The
existing detector was reportedly camera-tested before this lifecycle change;
the complete new flow still needs real-phone validation, including framing,
timing, network loss, and HTTPS cookies. No real-device accuracy claim follows
from these automated checks.
