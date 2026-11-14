"""Serve built assets without allowing SPA fallback to hide missing APIs/files."""

from fastapi import HTTPException
from fastapi.responses import FileResponse


def install_frontend(app, settings):
    root = settings.frontend_dist
    if settings.production and not (root / "index.html").is_file():
        raise ValueError("Frontend build missing; run npm run build in frontend first")

    @app.get("/{path:path}", include_in_schema=False)
    def frontend(path: str):
        if path.split("/", 1)[0] in {"api", "ws"}:
            raise HTTPException(404, "Not found")
        target = (root / path).resolve()
        if target.is_relative_to(root) and target.is_file():
            return FileResponse(target)
        parts = path.strip("/").split("/")
        known = path.strip("/") in {"", "dashboard", "history", "leaderboard", "profile", "workout"}
        result = len(parts) == 2 and parts[0] == "result" and parts[1].isdigit()
        if (known or result) and (root / "index.html").is_file():
            return FileResponse(root / "index.html", headers={"Cache-Control": "no-cache"})
        raise HTTPException(404, "Not found")
