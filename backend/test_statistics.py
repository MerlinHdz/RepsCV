"""Dashboard, private history, and Asia/Taipei weekly ranking contracts."""

from datetime import datetime, timedelta, timezone
import unittest

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from backend.database import User, Workout, WorkoutSession, XPTransaction
from backend.statistics import taiwan_week_bounds
from backend.test_helpers import ApiCase


UTC = timezone.utc


def save_workout(factory, user_id, completed_at, reps, mode="normal"):
    """Insert the same completed rows that the workout finalizer persists."""
    with factory() as db:
        session = WorkoutSession(user_id=user_id, exercise_type="pushup", mode=mode,
                                 status="completed", started_at=completed_at - timedelta(minutes=1),
                                 ended_at=completed_at, duration_ms=60000, rep_count=reps,
                                 tracking_status="tracked")
        db.add(session)
        db.flush()
        workout = Workout(session_id=session.id, user_id=user_id, exercise_type="pushup",
                          mode=mode, rep_count=reps, duration_ms=60000,
                          completed_at=completed_at,
                          new_personal_best=mode == "max_set" and reps > 0)
        db.add(workout)
        db.flush()
        db.add(XPTransaction(workout_id=workout.id, user_id=user_id,
                             amount=10 * reps, created_at=completed_at))
        db.commit()
        return session.id


def add_user(factory, username):
    with factory() as db:
        user = User(username=username, password_hash="test-only-unused")
        db.add(user)
        db.commit()
        return user.id


class StatisticsTests(ApiCase):
    def test_authentication_and_empty_new_user(self):
        self.assertEqual(self.client.get("/api/dashboard").status_code, 401)
        self.assertEqual(self.client.get("/api/workouts").status_code, 401)
        self.assertEqual(self.client.get("/api/leaderboard?period=weekly").status_code, 401)
        self.register("first_student")
        dashboard = self.client.get("/api/dashboard").json()
        self.assertEqual((dashboard["lifetime_xp"], dashboard["weekly_xp"],
                          dashboard["total_pushups"]), (0, 0, 0))
        self.assertIsNone(dashboard["max_set_personal_best"])
        self.assertEqual(dashboard["recent_workouts"], [])
        self.assertEqual(self.client.get("/api/workouts").json(), [])
        leaders = self.client.get("/api/leaderboard?period=weekly").json()
        self.assertEqual((leaders["current_user_rank"], leaders["entries"][0]["weekly_xp"]), (1, 0))
        self.assertEqual(self.client.get("/api/leaderboard?period=all_time").status_code, 422)

    def test_dashboard_aggregates_saved_results_and_excludes_interrupted(self):
        user_id = self.register()["id"]
        now = self.clock.utcnow()
        factory = self.app.state.session_factory
        save_workout(factory, user_id, now - timedelta(days=20), 4)
        save_workout(factory, user_id, now - timedelta(days=1), 7, "max_set")
        save_workout(factory, user_id, now - timedelta(hours=2), 5, "max_set")
        save_workout(factory, user_id, now - timedelta(hours=1), 0)
        with factory() as db:
            db.add(WorkoutSession(user_id=user_id, exercise_type="pushup", mode="max_set",
                                  status="interrupted", started_at=now,
                                  ended_at=now, rep_count=50, tracking_status="lost"))
            db.commit()
        summary = self.client.get("/api/dashboard").json()
        self.assertEqual((summary["lifetime_xp"], summary["weekly_xp"],
                          summary["total_pushups"], summary["max_set_personal_best"]),
                         (160, 120, 16, 7))
        self.assertEqual([entry["rep_count"] for entry in summary["recent_workouts"]], [0, 5, 7, 4])
        self.assertEqual(summary["timezone"], "Asia/Taipei")

    def test_history_order_and_ownership(self):
        owner_id = self.register("owner_student")["id"]
        other_id = add_user(self.app.state.session_factory, "other_student")
        now = self.clock.utcnow()
        older = save_workout(self.app.state.session_factory, owner_id, now - timedelta(days=2), 2)
        newer = save_workout(self.app.state.session_factory, owner_id, now, 3, "max_set")
        save_workout(self.app.state.session_factory, other_id, now + timedelta(minutes=1), 99)
        history = self.client.get("/api/workouts").json()
        self.assertEqual([entry["session_id"] for entry in history], [newer, older])
        self.assertEqual([entry["xp_earned"] for entry in history], [30, 20])
        self.assertEqual(history[0]["duration_ms"], 60000)
        self.assertTrue(history[0]["new_personal_best"])
        with TestClient(self.app) as second:
            second_login = second.post("/api/auth/register", json={
                "username": "fresh_student", "password": "password123"})
            self.assertEqual(second_login.status_code, 201)
            self.assertEqual(second.get("/api/workouts").json(), [])

    def test_leaderboard_ties_zero_xp_users_and_refresh(self):
        self.clock.base = datetime(2026, 11, 11, 12, tzinfo=UTC)
        current = self.register("zoe")["id"]
        amy = add_user(self.app.state.session_factory, "amy")
        bea = add_user(self.app.state.session_factory, "bea")
        add_user(self.app.state.session_factory, "zero")
        now = self.clock.utcnow()
        for user_id, reps in ((amy, 2), (bea, 2), (current, 1)):
            save_workout(self.app.state.session_factory, user_id, now, reps)
        response = self.client.get("/api/leaderboard?period=weekly").json()
        self.assertEqual([(row["username"], row["rank"], row["weekly_xp"])
                          for row in response["entries"]],
                         [("amy", 1, 20), ("bea", 1, 20), ("zoe", 3, 10), ("zero", 4, 0)])
        self.assertEqual(response["current_user_rank"], 3)
        self.assertTrue(response["entries"][2]["is_current_user"])
        self.assertEqual(self.client.get("/api/leaderboard?period=weekly").json(), response)
        with self.app.state.session_factory() as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(XPTransaction)), 3)

    def test_taiwan_week_boundary_and_year_change(self):
        before = datetime(2027, 1, 3, 15, 59, 59, tzinfo=UTC)
        after = datetime(2027, 1, 3, 16, 0, 0, tzinfo=UTC)
        self.assertEqual(taiwan_week_bounds(before),
                         (datetime(2026, 12, 27, 16, tzinfo=UTC), after))
        self.assertEqual(taiwan_week_bounds(after),
                         (after, datetime(2027, 1, 10, 16, tzinfo=UTC)))
        self.clock.base = before
        user_id = self.register()["id"]
        start, end = taiwan_week_bounds(before)
        for timestamp in (start - timedelta(seconds=1), start,
                          end - timedelta(seconds=1), end):
            save_workout(self.app.state.session_factory, user_id, timestamp, 1)
        summary = self.client.get("/api/dashboard").json()
        self.assertEqual((summary["lifetime_xp"], summary["weekly_xp"]), (40, 20))
        self.assertEqual(summary["week_start"], "2026-12-27T16:00:00Z")
        self.assertEqual(self.client.get("/api/leaderboard").json()["entries"][0]["weekly_xp"], 20)

    def test_sunday_night_and_monday_morning_use_taipei_calendar(self):
        sunday = datetime(2026, 11, 8, 15, 59, 59, tzinfo=UTC)
        monday = sunday + timedelta(seconds=1)
        self.assertEqual(taiwan_week_bounds(sunday),
                         (datetime(2026, 11, 1, 16, tzinfo=UTC), monday))
        self.assertEqual(taiwan_week_bounds(monday),
                         (monday, datetime(2026, 11, 15, 16, tzinfo=UTC)))
        self.clock.base = monday + timedelta(minutes=5)
        user_id = self.register()["id"]
        factory = self.app.state.session_factory
        save_workout(factory, user_id, sunday, 8)
        save_workout(factory, user_id, monday, 3)
        self.assertEqual(self.client.get("/api/dashboard").json()["weekly_xp"], 30)
        self.assertEqual(self.client.get("/api/leaderboard").json()["entries"][0]["weekly_xp"], 30)

    def test_dashboard_recent_workouts_are_limited_but_totals_are_not(self):
        user_id = self.register()["id"]
        now = self.clock.utcnow()
        factory = self.app.state.session_factory
        for offset in range(8):
            save_workout(factory, user_id, now - timedelta(hours=offset), offset + 1)
        summary = self.client.get("/api/dashboard").json()
        self.assertEqual(summary["lifetime_xp"], 360)
        self.assertEqual(summary["total_pushups"], 36)
        self.assertEqual([row["rep_count"] for row in summary["recent_workouts"]],
                         [1, 2, 3, 4, 5])
        self.assertEqual(len(self.client.get("/api/workouts").json()), 8)

    def test_personal_best_uses_saved_max_sets_and_zero_rep_results_still_appear(self):
        user_id = self.register()["id"]
        now = self.clock.utcnow()
        factory = self.app.state.session_factory
        save_workout(factory, user_id, now - timedelta(hours=3), 20, "normal")
        save_workout(factory, user_id, now - timedelta(hours=2), 5, "max_set")
        save_workout(factory, user_id, now - timedelta(hours=1), 5, "max_set")
        save_workout(factory, user_id, now, 0, "normal")
        summary = self.client.get("/api/dashboard").json()
        self.assertEqual(summary["max_set_personal_best"], 5)
        self.assertEqual(summary["total_pushups"], 30)
        self.assertEqual(summary["lifetime_xp"], 300)
        self.assertEqual(summary["recent_workouts"][0]["xp_earned"], 0)
        self.assertEqual(summary["recent_workouts"][0]["status"], "completed")

    def test_zero_xp_users_tie_and_sort_by_username(self):
        self.register("zoe")
        add_user(self.app.state.session_factory, "charlie")
        add_user(self.app.state.session_factory, "alice")
        leaders = self.client.get("/api/leaderboard?period=weekly").json()
        self.assertEqual([(row["username"], row["rank"], row["weekly_xp"])
                          for row in leaders["entries"]],
                         [("alice", 1, 0), ("charlie", 1, 0), ("zoe", 1, 0)])
        self.assertEqual(leaders["current_user_rank"], 1)

    def test_weekly_xp_comes_from_transaction_time_and_query_is_read_only(self):
        self.clock.base = datetime(2026, 11, 11, 12, tzinfo=UTC)
        user_id = self.register()["id"]
        now = self.clock.utcnow()
        factory = self.app.state.session_factory
        session_id = save_workout(factory, user_id, now, 4)
        week_start, _ = taiwan_week_bounds(now)
        with factory() as db:
            transaction = db.scalar(select(XPTransaction).join(Workout).where(
                Workout.session_id == session_id))
            transaction.created_at = week_start - timedelta(seconds=1)
            db.commit()
        summary = self.client.get("/api/dashboard").json()
        self.assertEqual((summary["lifetime_xp"], summary["weekly_xp"],
                          summary["total_pushups"]), (40, 0, 4))
        self.assertEqual(self.client.get("/api/leaderboard").json()["entries"][0]["weekly_xp"], 0)
        for _ in range(3):
            self.client.get("/api/dashboard")
            self.client.get("/api/leaderboard?period=weekly")
        with factory() as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(XPTransaction)), 1)

    def test_dashboard_and_history_survive_logout_and_login(self):
        account = self.register("returning_student")
        workout_id = save_workout(self.app.state.session_factory, account["id"],
                                  self.clock.utcnow(), 6, "max_set")
        logout = self.post("/api/auth/logout")
        self.assertEqual(logout.status_code, 200)
        for path in ("/api/dashboard", "/api/workouts", "/api/leaderboard"):
            self.assertEqual(self.client.get(path).status_code, 401)
        login = self.client.post("/api/auth/login", json={
            "username": "returning_student", "password": "password123"})
        self.assertEqual(login.status_code, 200)
        self.assertEqual(self.client.get("/api/dashboard").json()["lifetime_xp"], 60)
        history = self.client.get("/api/workouts").json()
        self.assertEqual(len(history), 1)
        self.assertEqual((history[0]["session_id"], history[0]["rep_count"],
                          history[0]["xp_earned"]), (workout_id, 6, 60))

    def test_leaderboard_recalculates_when_taiwan_week_changes(self):
        sunday = datetime(2026, 12, 27, 15, 59, 59, tzinfo=UTC)
        monday = sunday + timedelta(seconds=1)
        self.clock.base = sunday
        first_id = self.register("first_student")["id"]
        second_id = add_user(self.app.state.session_factory, "second_student")
        factory = self.app.state.session_factory
        save_workout(factory, first_id, sunday, 9)
        save_workout(factory, second_id, monday, 2)
        old_week = self.client.get("/api/leaderboard?period=weekly").json()
        self.assertEqual([(row["username"], row["weekly_xp"])
                          for row in old_week["entries"]],
                         [("first_student", 90), ("second_student", 0)])
        self.clock.advance(1)
        new_week = self.client.get("/api/leaderboard?period=weekly").json()
        self.assertEqual([(row["username"], row["weekly_xp"])
                          for row in new_week["entries"]],
                         [("second_student", 20), ("first_student", 0)])
        self.assertEqual(new_week["current_user_rank"], 2)


if __name__ == "__main__":
    unittest.main()
