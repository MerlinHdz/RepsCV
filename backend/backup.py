"""Consistent SQLite online backup; restore only while the app is stopped."""

import argparse
from contextlib import closing
from pathlib import Path
import sqlite3

from sqlalchemy.engine import make_url
from backend.database import database_url


def backup(source: Path, destination: Path):
    if not source.is_file():
        raise ValueError("Source database does not exist")
    if destination.exists():
        raise ValueError("Backup destination already exists; choose a new filename")
    # Exclusive creation prevents accidental overwrite; SQLite backup includes live WAL data.
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("xb"):
        pass
    try:
        with closing(sqlite3.connect(f"file:{source.resolve()}?mode=ro", uri=True)) as src:
            with closing(sqlite3.connect(destination)) as dst:
                src.backup(dst)
                if dst.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise RuntimeError("Backup integrity check failed")
    except Exception:
        destination.unlink(missing_ok=True)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    url = make_url(database_url())
    if url.drivername != "sqlite" or not url.database:
        parser.error("REPSCV_DATABASE_URL must point to a SQLite file")
    backup(Path(url.database), args.destination)
    print("Verified backup created; store an encrypted copy off the host")


if __name__ == "__main__":
    main()
