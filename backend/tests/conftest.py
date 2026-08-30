import os
from pathlib import Path

TEST_DATABASE = Path(__file__).resolve().parent.parent / "test-ecommerce-agent.db"

os.environ["APP_ENV"] = "test"
os.environ["AUTH_MODE"] = "password"
os.environ["JWT_SECRET"] = "test-session-secret-with-at-least-32-characters"
os.environ["BOOTSTRAP_ADMIN_PASSWORD"] = "TestAdmin@123456"
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DATABASE.as_posix()}"
os.environ["TASK_EXECUTION_MODE"] = "inline"
os.environ["AUTO_CREATE_SCHEMA"] = "false"


def pytest_sessionstart() -> None:
    # Tests own an isolated SQLite database and create it explicitly.
    from app.db.session import init_database

    init_database()


def pytest_sessionfinish() -> None:
    from app.db.session import engine

    engine.dispose()
    TEST_DATABASE.unlink(missing_ok=True)
