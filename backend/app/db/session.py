from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.db.models import Base


def build_engine(database_url: str) -> Engine:
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    return create_engine(database_url, connect_args=connect_args, pool_pre_ping=True)


engine = build_engine(settings.database_url)
SessionFactory = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)


def init_database() -> None:
    Base.metadata.create_all(engine)


def database_ready() -> bool:
    try:
        with SessionFactory() as session:
            session.execute(text("SELECT 1"))
        return inspect(engine).has_table("agent_task")
    except Exception:
        return False
