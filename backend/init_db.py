"""Create missing RepsCV SQLite tables without dropping or rewriting data."""

from backend.database import Base, database_url, make_database
from backend.departments import normalize_existing_departments


def main():
    engine, session_factory = make_database()
    Base.metadata.create_all(engine)
    normalize_existing_departments(session_factory)
    engine.dispose()
    print(f"RepsCV schema ready: {database_url()}")


if __name__ == "__main__":
    main()
