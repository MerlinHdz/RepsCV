"""Read-only workout summaries and Taiwan-week XP rankings.

Only completed workouts and persisted XP transactions contribute to public
statistics. SQLite stores UTC datetimes as naive values, so query boundaries
are normalized to UTC before comparison.
"""

from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import func, select

from backend.database import User, Workout, WorkoutSession, XPTransaction
from backend.workouts import iso, result_payload


TAIPEI = ZoneInfo("Asia/Taipei")
UTC = timezone.utc


def taiwan_week_bounds(now_utc: datetime) -> tuple[datetime, datetime]:
    """Return inclusive Monday and exclusive next Monday, both in UTC."""
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=UTC)
    local_today = now_utc.astimezone(TAIPEI).date()
    monday = local_today - timedelta(days=local_today.weekday())
    start_local = datetime.combine(monday, time.min, TAIPEI)
    return start_local.astimezone(UTC), (start_local + timedelta(days=7)).astimezone(UTC)


def _saved_workouts(db, user_id: int, limit: int | None = None) -> list[dict]:
    statement = (select(Workout, WorkoutSession, XPTransaction)
                 .join(WorkoutSession, WorkoutSession.id == Workout.session_id)
                 .join(XPTransaction, XPTransaction.workout_id == Workout.id)
                 .where(Workout.user_id == user_id)
                 .order_by(Workout.completed_at.desc(), Workout.id.desc()))
    if limit is not None:
        statement = statement.limit(limit)
    return [result_payload(session, workout, xp)
            for workout, session, xp in db.execute(statement).all()]


def workout_history(session_factory, user_id: int) -> list[dict]:
    with session_factory() as db:
        return _saved_workouts(db, user_id)


def dashboard(session_factory, user: User, now_utc: datetime) -> dict:
    week_start, week_end = taiwan_week_bounds(now_utc)
    with session_factory() as db:
        lifetime_xp = db.scalar(select(func.coalesce(func.sum(XPTransaction.amount), 0))
                                .where(XPTransaction.user_id == user.id))
        weekly_xp = db.scalar(select(func.coalesce(func.sum(XPTransaction.amount), 0))
                              .where(XPTransaction.user_id == user.id,
                                     XPTransaction.created_at >= week_start,
                                     XPTransaction.created_at < week_end))
        total_reps = db.scalar(select(func.coalesce(func.sum(Workout.rep_count), 0))
                               .where(Workout.user_id == user.id))
        personal_best = db.scalar(select(func.max(Workout.rep_count)).where(
            Workout.user_id == user.id, Workout.mode == "max_set", Workout.rep_count > 0))
        return {
            "username": user.username,
            "lifetime_xp": int(lifetime_xp),
            "weekly_xp": int(weekly_xp),
            "total_pushups": int(total_reps),
            "max_set_personal_best": personal_best,
            "recent_workouts": _saved_workouts(db, user.id, limit=5),
            "week_start": iso(week_start),
            "week_end": iso(week_end),
            "timezone": "Asia/Taipei",
        }


def weekly_leaderboard(session_factory, current_user_id: int, now_utc: datetime) -> dict:
    week_start, week_end = taiwan_week_bounds(now_utc)
    with session_factory() as db:
        weekly_totals = (select(
            XPTransaction.user_id.label("user_id"),
            func.sum(XPTransaction.amount).label("total"),
        ).where(XPTransaction.created_at >= week_start,
                XPTransaction.created_at < week_end)
         .group_by(XPTransaction.user_id).subquery())
        xp = func.coalesce(weekly_totals.c.total, 0).label("weekly_xp")
        rows = db.execute(select(User.id, User.username, xp)
                          .outerjoin(weekly_totals, weekly_totals.c.user_id == User.id)
                          .order_by(xp.desc(), User.username.asc(), User.id.asc())).all()

    entries = []
    last_xp = None
    current_rank = None
    for position, (user_id, username, total) in enumerate(rows, start=1):
        amount = int(total)
        if amount != last_xp:
            rank = position
            last_xp = amount
        is_current = user_id == current_user_id
        if is_current:
            current_rank = rank
        entries.append({"rank": rank, "user_id": user_id,
                        "username": username, "weekly_xp": amount,
                        "is_current_user": is_current})
    return {
        "period": "weekly",
        "week_start": iso(week_start),
        "week_end": iso(week_end),
        "timezone": "Asia/Taipei",
        "current_user_rank": current_rank,
        "entries": entries,
    }
