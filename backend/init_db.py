"""Create missing RepsCV SQLite tables without dropping or rewriting data."""

from backend.database import Base, database_url, make_database


def main():
    engine, _ = make_database()
    Base.metadata.create_all(engine)
    engine.dispose()
    print(f"RepsCV schema ready: {database_url()}")


if __name__ == "__main__":
    main()
