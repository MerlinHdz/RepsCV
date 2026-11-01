
from fastapi import FastAPI
from fastapi import WebSocket

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

    while True:
        message = await websocket.receive_text()
        await websocket.send_text(f"Python received: {message}")