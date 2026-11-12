"""RepsCV authenticated API and workout-specific landmark WebSocket."""

from contextlib import asynccontextmanager
from datetime import timedelta, timezone
import hashlib
import hmac
import json
import os
import re
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from fastapi import FastAPI, HTTPException, Request, Response, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from backend.database import Base, LoginSession, User, make_database, utcnow
from backend.workouts import WorkoutLimits, WorkoutManager, validate_pose_message


COOKIE_NAME = "repscv_session"
PASSWORD_HASHER = PasswordHasher()
USERNAME = re.compile(r"^[A-Za-z0-9_]{3,20}$")


class Credentials(BaseModel):
    username: str
    password: str
    department: str | None = Field(default=None, max_length=100)


class ProfileUpdate(BaseModel):
    department: str | None = Field(max_length=100)


class WorkoutStart(BaseModel):
    exercise: str
    mode: str


def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def allowed_origin(origin, scheme, host):
    expected = f"{scheme}://{host}"
    extras = {value.strip() for value in os.environ.get("REPSCV_ALLOWED_ORIGINS", "").split(",") if value.strip()}
    return origin == expected or origin in extras


def create_app(database_url=None, clock=None, limits=None):
    engine, session_factory = make_database(database_url)
    manager = WorkoutManager(session_factory, clock=clock, limits=limits or WorkoutLimits())

    @asynccontextmanager
    async def lifespan(application):
        Base.metadata.create_all(engine)
        manager.recover_startup()
        yield
        for runtime in list(manager.runtimes.values()):
            if runtime.mode == "max_set" and runtime.timer is not None:
                runtime.timer.cancel()
        engine.dispose()

    application = FastAPI(lifespan=lifespan)
    application.state.manager = manager
    application.state.session_factory = session_factory

    def auth(request):
        token = request.cookies.get(COOKIE_NAME)
        if not token:
            raise HTTPException(401, "Login required.")
        with session_factory() as db:
            login = db.scalar(select(LoginSession).where(LoginSession.token_hash == token_hash(token)))
            if login is None or login.expires_at.replace(tzinfo=timezone.utc) <= utcnow():
                raise HTTPException(401, "Session expired or invalid.")
            user = db.get(User, login.user_id)
            if user is None:
                raise HTTPException(401, "Session expired or invalid.")
            return user, login

    def check_http_origin(request):
        origin = request.headers.get("origin")
        if origin and not allowed_origin(origin, request.url.scheme, request.headers["host"]):
            raise HTTPException(403, "Origin not allowed.")

    def csrf(request, login):
        check_http_origin(request)
        supplied = request.headers.get("x-csrf-token", "")
        if not hmac.compare_digest(supplied, login.csrf_token):
            raise HTTPException(403, "CSRF token required.")

    def issue_cookie(response, request, user_id):
        token = secrets.token_urlsafe(32)
        csrf_token = secrets.token_urlsafe(32)
        with session_factory() as db:
            db.add(LoginSession(user_id=user_id, token_hash=token_hash(token), csrf_token=csrf_token,
                                expires_at=utcnow() + timedelta(days=7)))
            db.commit()
        response.set_cookie(COOKIE_NAME, token, httponly=True,
                            secure=request.url.scheme == "https" or os.environ.get("REPSCV_SECURE_COOKIES") == "1",
                            samesite="lax", max_age=7 * 24 * 3600, path="/")
        return csrf_token

    @application.get("/")
    def home():
        return {"message": "Welcome to RepsCV!"}

    @application.get("/api/health")
    def health():
        return {"status": "ok", "app": "RepsCV"}

    @application.post("/api/auth/register", status_code=201)
    def register(body: Credentials, request: Request, response: Response):
        check_http_origin(request)
        username = body.username.strip()
        if not USERNAME.fullmatch(username):
            raise HTTPException(422, "Username must be 3–20 letters, digits, or underscores.")
        if len(body.password) < 8 or len(body.password) > 128:
            raise HTTPException(422, "Password must be 8–128 characters.")
        department = body.department.strip() if body.department else None
        with session_factory() as db:
            user = User(username=username, password_hash=PASSWORD_HASHER.hash(body.password),
                        department=department or None)
            db.add(user)
            try:
                db.commit()
            except IntegrityError:
                db.rollback()
                raise HTTPException(409, "Username already exists.") from None
            db.refresh(user)
            user_id = user.id
        csrf_token = issue_cookie(response, request, user_id)
        return {"id": user_id, "username": username, "department": department or None,
                "csrf_token": csrf_token}

    @application.post("/api/auth/login")
    def login(body: Credentials, request: Request, response: Response):
        check_http_origin(request)
        with session_factory() as db:
            user = db.scalar(select(User).where(User.username == body.username.strip()))
            try:
                valid = bool(user and PASSWORD_HASHER.verify(user.password_hash, body.password))
            except (VerifyMismatchError, InvalidHashError):
                valid = False
            if not valid:
                raise HTTPException(401, "Invalid username or password.")
            user_id, username, department = user.id, user.username, user.department
        csrf_token = issue_cookie(response, request, user_id)
        return {"id": user_id, "username": username, "department": department,
                "csrf_token": csrf_token}

    @application.post("/api/auth/logout")
    def logout(request: Request, response: Response):
        _, login_session = auth(request)
        csrf(request, login_session)
        with session_factory() as db:
            row = db.get(LoginSession, login_session.id)
            db.delete(row)
            db.commit()
        response.delete_cookie(COOKIE_NAME, path="/")
        return {"status": "logged_out"}

    @application.get("/api/auth/me")
    def me(request: Request):
        user, login_session = auth(request)
        return {"id": user.id, "username": user.username, "department": user.department,
                "csrf_token": login_session.csrf_token,
                "active_workout": manager.active_for_user(user.id)}

    @application.patch("/api/profile")
    def profile(body: ProfileUpdate, request: Request):
        user, login_session = auth(request)
        csrf(request, login_session)
        with session_factory() as db:
            row = db.get(User, user.id)
            row.department = body.department.strip() or None if body.department is not None else None
            db.commit()
            return {"id": row.id, "username": row.username, "department": row.department}

    @application.post("/api/workouts/start", status_code=201)
    async def start_workout(body: WorkoutStart, request: Request):
        user, login_session = auth(request)
        csrf(request, login_session)
        if body.exercise != "pushup":
            raise HTTPException(422, "Only pushup is supported.")
        return await manager.start(user.id, body.mode)

    @application.post("/api/workouts/{session_id}/finish")
    async def finish_workout(session_id: int, request: Request):
        user, login_session = auth(request)
        csrf(request, login_session)
        return await manager.finish(user.id, session_id)

    @application.get("/api/workouts")
    def workouts(request: Request):
        user, _ = auth(request)
        return manager.history(user.id)

    @application.get("/api/workouts/{session_id}")
    async def workout_status(session_id: int, request: Request):
        user, _ = auth(request)
        await manager.tick(session_id, user.id)
        return manager.status(user.id, session_id)

    @application.websocket("/ws/workouts/{session_id}")
    async def workout_socket(socket: WebSocket, session_id: int):
        scheme = "https" if socket.url.scheme == "wss" else "http"
        origin = socket.headers.get("origin")
        if not origin or not allowed_origin(origin, scheme, socket.headers.get("host", "")):
            await socket.close(code=4403)
            return
        try:
            user, _ = auth(socket)
            runtime = await manager.connect(user.id, session_id, socket)
        except HTTPException as error:
            await socket.close(code=4401 if error.status_code == 401 else error.status_code + 4000)
            return
        await socket.accept()
        try:
            while True:
                raw = await socket.receive_text()
                auth(socket)  # Logout in another tab revokes this socket on its next frame.
                if len(raw.encode("utf-8")) > manager.limits.max_message_bytes:
                    response = {"type": "error", "feedback": "Pose frame too large."}
                    runtime.counter.error_response(response["feedback"])
                else:
                    try:
                        message = json.loads(raw)
                    except json.JSONDecodeError:
                        message = None
                    response = await manager.update(user.id, session_id, message)
                async with runtime.send_lock:
                    await socket.send_json(response)
                if response.get("type") == "workout_result":
                    break
        except HTTPException:
            await socket.close(code=4401)
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            await manager.disconnect(user.id, session_id, socket)

    return application


app = create_app()
