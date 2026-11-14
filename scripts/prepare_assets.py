"""Bundle pinned on-device pose resources. Run after npm ci, before Vite."""

import hashlib
from pathlib import Path
import shutil
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
MODEL_URL = "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task"
MODEL_SHA256 = "59929e1d1ee95287735ddd833b19cf4ac46d29bc7afddbbf6753c459690d574a"


def prepare():
    target = ROOT / "frontend/public/mediapipe"
    target.mkdir(parents=True, exist_ok=True)
    model = target / "pose_landmarker_lite.task"
    if not model.exists() or hashlib.sha256(model.read_bytes()).hexdigest() != MODEL_SHA256:
        with urlopen(MODEL_URL, timeout=60) as response:
            data = response.read(10 * 1024 * 1024)
        if hashlib.sha256(data).hexdigest() != MODEL_SHA256:
            raise RuntimeError("Pose model checksum mismatch; refusing to bundle")
        model.write_bytes(data)
    source = ROOT / "frontend/node_modules/@mediapipe/tasks-vision/wasm"
    if not source.is_dir():
        raise RuntimeError("Run npm ci in frontend first")
    shutil.copytree(source, target / "wasm", dirs_exist_ok=True)
    print("RepsCV pose assets ready (model checksum verified)")


if __name__ == "__main__":
    prepare()
