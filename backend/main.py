
"""HTTP health check and per-connection push-up tracking WebSocket."""

import json
import math

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from backend.rep_counter import RepCounter

app = FastAPI()


@app.get("/")
def home():
    return {"message": "Welcome to RepsCV!"}


@app.get("/api/health")
def health():
    return {"status": "ok", "app": "RepsCV"}


def valid_frame(data):
    if not isinstance(data, dict):
        return False
    aspect = data.get("aspect_ratio")
    if type(aspect) not in (int, float) or not math.isfinite(aspect) or not 0.3 <= aspect <= 4:
        return False
    landmarks = data.get("landmarks")
    return landmarks is None or (isinstance(landmarks, dict) and len(landmarks) <= 33)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    counter = RepCounter()
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                data = None
            if not valid_frame(data):
                await websocket.send_json(counter.error_response("Invalid pose frame."))
                continue
            await websocket.send_json(counter.update(data))
    except WebSocketDisconnect:
        pass
