
from fastapi import FastAPI

app = FastAPI()


@app.get("/")
def home():
    return {"message": "Welcome to RepsCV!"}


@app.get("/api/health")
def health():
    return {"status": "ok", "app": "RepsCV"}
