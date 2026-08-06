from functools import lru_cache

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from App.config import get_settings
from App.migrations import migrate_database


@lru_cache(maxsize=1)
def _get_session_factory() -> sessionmaker:
    settings = get_settings()
    engine = create_engine(settings.database_url, pool_pre_ping=True)
    migrate_database(engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


def init_db() -> None:
    _get_session_factory()


def get_db_session() -> Session:
    return _get_session_factory()()


def check_database_connection() -> tuple[bool, str | None]:
    session = get_db_session()
    try:
        session.execute(text("SELECT 1")).scalar_one()
        return True, None
    except Exception as error:
        return False, str(error)
    finally:
        session.close()
