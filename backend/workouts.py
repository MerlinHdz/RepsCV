"""Single-process workout lifecycle, monotonic deadlines, and once-only scoring."""

import asyncio
from dataclasses import dataclass, field
from datetime import timezone
import math
import time

from fastapi import HTTPException, WebSocketDisconnect
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from backend.database import Workout, WorkoutSession, XPTransaction, utcnow
from backend.rep_counter import RepCounter


@dataclass(frozen=True)
class WorkoutLimits:
    first_rep_seconds: float = 20.0
    between_rep_seconds: float = 5.0
    tracking_loss_seconds: float = 2.0
    timer_poll_seconds: float = 0.2
    max_message_bytes: int = 8192


class SystemClock:
    monotonic = staticmethod(time.monotonic)
    utcnow = staticmethod(utcnow)


@dataclass
class Runtime:
    user_id: int
    mode: str
    counter: RepCounter
    started_mono: float
    deadline_mono: float | None
    last_good_mono: float
    last_sequence: int = -1
    storage_failed: bool = False
    socket: object | None = None
    timer: asyncio.Task | None = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    send_lock: asyncio.Lock = field(default_factory=asyncio.Lock)


def iso(value):
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")


def result_payload(session, workout=None, xp=None):
    return {
        "type": "workout_result", "session_id": session.id,
        "mode": session.mode, "status": session.status,
        "rep_count": session.rep_count,
        "duration_ms": workout.duration_ms if workout else session.duration_ms,
        "xp_earned": xp.amount if xp else 0,
        "new_personal_best": workout.new_personal_best if workout else False,
        "completed_at": iso(workout.completed_at) if workout else None,
    }


def validate_pose_message(message):
    if not isinstance(message, dict) or message.get("type") != "landmarks":
        return False
    sequence, timestamp = message.get("sequence"), message.get("timestamp_ms")
    aspect, points = message.get("aspect_ratio"), message.get("points")
    if type(sequence) is not int or sequence < 0 or type(timestamp) not in (int, float):
        return False
    if not math.isfinite(timestamp) or timestamp < 0:
        return False
    if type(aspect) not in (int, float) or not math.isfinite(aspect) or not 0.3 <= aspect <= 4:
        return False
    return points is None or (isinstance(points, dict) and len(points) <= 33)


class WorkoutManager:
    def __init__(self, session_factory, clock=None, limits=WorkoutLimits()):
        self.session_factory = session_factory
        self.clock = clock or SystemClock()
        self.limits = limits
        self.runtimes = {}
        self.start_lock = asyncio.Lock()

    def recover_startup(self):
        # Monotonic deadlines cannot survive a process restart. Fail closed for Max Set.
        with self.session_factory() as db:
            rows = db.scalars(select(WorkoutSession).where(
                WorkoutSession.status == "active", WorkoutSession.mode == "max_set")).all()
            for row in rows:
                row.status = "interrupted"
                row.ended_at = self.clock.utcnow()
            db.commit()

    def active_for_user(self, user_id):
        with self.session_factory() as db:
            row = db.scalar(select(WorkoutSession).where(
                WorkoutSession.user_id == user_id, WorkoutSession.status == "active"))
            if row is None:
                return None
            return {"id": row.id, "mode": row.mode, "rep_count": row.rep_count,
                    "status": row.status, "started_at": iso(row.started_at)}

    def _runtime(self, row):
        runtime = self.runtimes.get(row.id)
        if runtime is None:
            now = self.clock.monotonic()
            started = row.started_at.replace(tzinfo=timezone.utc)
            elapsed = max(0.0, (self.clock.utcnow() - started).total_seconds())
            counter = RepCounter()
            counter.reps = row.rep_count
            runtime = Runtime(row.user_id, row.mode, counter, now - elapsed, None, now)
            self.runtimes[row.id] = runtime
        return runtime

    async def start(self, user_id, mode):
        if mode not in ("normal", "max_set"):
            raise HTTPException(422, "Mode must be normal or max_set.")
        async with self.start_lock:
            with self.session_factory() as db:
                if db.scalar(select(WorkoutSession.id).where(
                    WorkoutSession.user_id == user_id, WorkoutSession.status == "active")):
                    raise HTTPException(409, "Finish the active workout first.")
                row = WorkoutSession(user_id=user_id, exercise_type="pushup", mode=mode,
                                     status="active", started_at=self.clock.utcnow(), rep_count=0)
                db.add(row)
                try:
                    db.commit()
                except IntegrityError:
                    db.rollback()
                    raise HTTPException(409, "Finish the active workout first.") from None
                db.refresh(row)
                now = self.clock.monotonic()
                deadline = now + self.limits.first_rep_seconds if mode == "max_set" else None
                runtime = Runtime(user_id, mode, RepCounter(), now, deadline, now)
                self.runtimes[row.id] = runtime
                if mode == "max_set":
                    runtime.timer = asyncio.create_task(self._timer(row.id, user_id))
                return {"id": row.id, "mode": mode, "status": "active", "rep_count": 0,
                        "started_at": iso(row.started_at),
                        "remaining_ms": round((deadline - now) * 1000) if deadline else None}

    async def _timer(self, session_id, user_id):
        try:
            while True:
                await asyncio.sleep(self.limits.timer_poll_seconds)
                try:
                    if await self.tick(session_id, user_id):
                        return
                except SQLAlchemyError:
                    # Keep trying to persist an interrupted result when storage returns.
                    runtime = self.runtimes.get(session_id)
                    if runtime:
                        runtime.storage_failed = True
        except asyncio.CancelledError:
            return

    async def tick(self, session_id, user_id):
        runtime = self.runtimes.get(session_id)
        if runtime is None or runtime.mode != "max_set":
            return False
        now = self.clock.monotonic()
        reason = self._terminal_reason(runtime, now)
        if reason:
            await self.finish(user_id, session_id, reason)
            return True
        return False

    def _terminal_reason(self, runtime, now):
        if runtime.storage_failed:
            return "interrupted"
        if runtime.mode != "max_set":
            return None
        lost_at = runtime.last_good_mono + self.limits.tracking_loss_seconds
        if now > lost_at and lost_at < runtime.deadline_mono:
            return "interrupted"
        if now >= runtime.deadline_mono:
            return "timeout"
        return None

    async def connect(self, user_id, session_id, socket):
        with self.session_factory() as db:
            row = db.get(WorkoutSession, session_id)
            if row is None or row.user_id != user_id or row.status != "active":
                raise HTTPException(404, "Active workout not found.")
            runtime = self._runtime(row)
        async with runtime.lock:
            if runtime.socket is not None:
                raise HTTPException(409, "Workout socket already connected.")
            runtime.socket = socket
            runtime.last_sequence = -1  # Sequence numbers are scoped to one socket connection.
        return runtime

    async def disconnect(self, user_id, session_id, socket):
        runtime = self.runtimes.get(session_id)
        if runtime is None:
            return
        async with runtime.lock:
            if runtime.socket is not socket:
                return
            runtime.socket = None
        if runtime.mode == "max_set":
            await self.finish(user_id, session_id, "interrupted")

    async def update(self, user_id, session_id, message):
        with self.session_factory() as db:
            row = db.get(WorkoutSession, session_id)
            if row is None or row.user_id != user_id:
                raise HTTPException(404, "Workout not found.")
            if row.status != "active":
                return result_payload(row, *self._saved(db, row.id))
            runtime = self._runtime(row)
        if not validate_pose_message(message):
            runtime.counter.error_response("Invalid pose frame.")
            return {"type": "error", "feedback": "Invalid pose frame.", "rep_count": runtime.counter.reps}
        await self.tick(session_id, user_id)
        expired = None
        async with runtime.lock:
            now = self.clock.monotonic()
            expired = self._terminal_reason(runtime, now)
            if expired is None:
                if message["sequence"] <= runtime.last_sequence:
                    return {"type": "ignored", "feedback": "Duplicate or stale frame."}
                runtime.last_sequence = message["sequence"]
                previous = runtime.counter.reps
                result = runtime.counter.update({"aspect_ratio": message["aspect_ratio"],
                                                  "landmarks": message["points"]}, now=now)
                if result["tracking"] == "tracked":
                    runtime.last_good_mono = now
                if result["reps"] > previous and runtime.mode == "max_set":
                    runtime.deadline_mono = now + self.limits.between_rep_seconds
                with self.session_factory() as db:
                    row = db.get(WorkoutSession, session_id)
                    if row.status != "active":
                        return result_payload(row, *self._saved(db, row.id))
                    row.rep_count = result["reps"]
                    row.tracking_status = result["tracking"]
                    db.commit()
                return {"type": "workout_update", "rep_count": result["reps"],
                        "phase": result["state"], "tracking": result["tracking"],
                        "form_valid": result["form_valid"], "feedback": result["feedback"],
                        "elapsed_ms": round((now - runtime.started_mono) * 1000),
                        "remaining_ms": max(0, round((runtime.deadline_mono - now) * 1000))
                        if runtime.deadline_mono is not None else None}
        return await self.finish(user_id, session_id, expired)

    def _saved(self, db, session_id):
        workout = db.scalar(select(Workout).where(Workout.session_id == session_id))
        xp = db.scalar(select(XPTransaction).where(XPTransaction.workout_id == workout.id)) if workout else None
        return workout, xp

    async def finish(self, user_id, session_id, reason="manual"):
        with self.session_factory() as db:
            row = db.get(WorkoutSession, session_id)
            if row is None or row.user_id != user_id:
                raise HTTPException(404, "Workout not found.")
            runtime = self._runtime(row) if row.status == "active" else self.runtimes.get(session_id)
            if row.status != "active":
                return result_payload(row, *self._saved(db, session_id))
        async with runtime.lock:
            with self.session_factory() as db:
                row = db.get(WorkoutSession, session_id)
                if row.status != "active":
                    return result_payload(row, *self._saved(db, session_id))
                now = self.clock.monotonic()
                reason = self._terminal_reason(runtime, now) or reason
                completed = reason in ("manual", "timeout")
                row.status = "completed" if completed else "interrupted"
                row.ended_at = self.clock.utcnow()
                row.duration_ms = max(0, round((now - runtime.started_mono) * 1000))
                workout = xp = None
                if completed:
                    previous_pb = db.scalar(select(func.max(Workout.rep_count)).where(
                        Workout.user_id == user_id, Workout.mode == "max_set")) or 0
                    new_pb = runtime.mode == "max_set" and row.rep_count > previous_pb
                    workout = Workout(session_id=session_id, user_id=user_id,
                                      exercise_type="pushup", mode=runtime.mode,
                                      rep_count=row.rep_count,
                                      duration_ms=row.duration_ms,
                                      completed_at=row.ended_at, new_personal_best=new_pb)
                    db.add(workout)
                    db.flush()
                    xp = XPTransaction(workout_id=workout.id, user_id=user_id,
                                       amount=10 * row.rep_count, created_at=row.ended_at)
                    db.add(xp)
                db.commit()
                payload = result_payload(row, workout, xp)
            if runtime.timer is not None and runtime.timer is not asyncio.current_task():
                runtime.timer.cancel()
        socket = runtime.socket
        if socket is not None:
            try:
                async with runtime.send_lock:
                    await socket.send_json(payload)
                    await socket.close()
            except (RuntimeError, WebSocketDisconnect, OSError):
                pass
            runtime.socket = None
        self.runtimes.pop(session_id, None)
        return payload

    def history(self, user_id):
        with self.session_factory() as db:
            rows = db.execute(select(Workout, XPTransaction).join(
                XPTransaction, XPTransaction.workout_id == Workout.id).where(
                Workout.user_id == user_id).order_by(Workout.completed_at.desc(), Workout.id.desc())).all()
            return [result_payload(db.get(WorkoutSession, workout.session_id), workout, xp)
                    for workout, xp in rows]

    def status(self, user_id, session_id):
        with self.session_factory() as db:
            row = db.get(WorkoutSession, session_id)
            if row is None or row.user_id != user_id:
                raise HTTPException(404, "Workout not found.")
            if row.status != "active":
                return result_payload(row, *self._saved(db, session_id))
            return {"id": row.id, "mode": row.mode, "status": row.status,
                    "rep_count": row.rep_count, "started_at": iso(row.started_at)}
