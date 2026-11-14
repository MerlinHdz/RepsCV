"""Validated deployment settings; development remains usable without an env file."""

from dataclasses import dataclass
import os
from pathlib import Path
from urllib.parse import urlsplit

from sqlalchemy.engine import make_url


@dataclass(frozen=True)
class Settings:
    production: bool
    public_origin: str | None
    database_url: str
    frontend_dist: Path
    secure_cookies: bool
    maintenance: bool = False

    @classmethod
    def load(cls, database_url=None):
        environment = os.environ.get("REPSCV_ENV", "development")
        if environment not in {"development", "production"}:
            raise ValueError("REPSCV_ENV must be development or production")
        production = environment == "production"
        origin = os.environ.get("REPSCV_PUBLIC_ORIGIN") or None
        if origin:
            parsed = urlsplit(origin)
            if (parsed.scheme not in {"http", "https"} or not parsed.hostname
                    or parsed.path or parsed.query or parsed.fragment or parsed.username):
                raise ValueError("REPSCV_PUBLIC_ORIGIN must be an origin without a path")
        if production and (not origin or urlsplit(origin).scheme != "https"):
            raise ValueError("Production requires REPSCV_PUBLIC_ORIGIN=https://your-host")
        url = database_url or os.environ.get("REPSCV_DATABASE_URL", "sqlite:///./repscv.db")
        parsed_db = make_url(url)
        if parsed_db.drivername != "sqlite":
            raise ValueError("This single-process MVP requires SQLite")
        if production and (not parsed_db.database or not Path(parsed_db.database).is_absolute()):
            raise ValueError("Production SQLite must use an absolute persistent path")
        dist = Path(os.environ.get("REPSCV_FRONTEND_DIST", "frontend/dist")).resolve()
        return cls(production, origin, url, dist,
                   production or os.environ.get("REPSCV_SECURE_COOKIES") == "1",
                   os.environ.get("REPSCV_MAINTENANCE") == "1")

    def origin_allowed(self, origin, scheme, host):
        if self.public_origin:
            return origin == self.public_origin
        extras = os.environ.get("REPSCV_ALLOWED_ORIGINS", "").split(",")
        return origin == f"{scheme}://{host}" or origin in {item.strip() for item in extras if item.strip()}
