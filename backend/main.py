
from fastapi import FastAPI
from fastapi import WebSocket
from backend.rep_counter import RepCounter
import math
from fastapi import WebSocketDisconnect

app = FastAPI()


@app.get("/")
def home():
    return {"message": "Welcome to RepsCV!"}


@app.get("/api/health")
def health():
    return {"status": "ok", "app": "RepsCV"}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()

    # Each connection gets its own counter.
    counter = RepCounter()

    try:
        while True:
            data = await websocket.receive_json()

            angle = data.get("angle")

            if (
                type(angle) not in (int, float)
                or not math.isfinite(angle)
                or not 0 <= angle <= 180
            ):
                await websocket.send_json({
                    "error": "Invalid elbow angle"
                })
                continue

            reps = counter.update(angle)

            await websocket.send_json({
                "reps": reps,
                "state": counter.state,
                "angle": angle
            })

    except WebSocketDisconnect:
        print("Client disconnected")