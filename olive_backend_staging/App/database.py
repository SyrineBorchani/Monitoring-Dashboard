from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from App.config import get_settings, is_demo_mode
from App.models import Base


@lru_cache(maxsize=1)
def _get_session_factory() -> sessionmaker:
    settings = get_settings()
    engine = create_engine(settings.database_url, pool_pre_ping=True)
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


def init_db() -> None:
    if is_demo_mode():
        return
    _get_session_factory()


def get_db_session() -> Session:
    if is_demo_mode():
        raise RuntimeError("Database sessions are not available in demo mode.")
    return _get_session_factory()()
