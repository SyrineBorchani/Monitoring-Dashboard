from functools import lru_cache
import ssl

from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import Session, sessionmaker

from App.config import get_settings
from App.migrations import migrate_database


def _normalize_pg8000_url(database_url: str) -> tuple[str | URL, dict]:
    url = make_url(database_url)
    connect_args: dict = {}

    if url.drivername != "postgresql+pg8000":
        return url, connect_args

    query = dict(url.query)
    sslmode = str(query.pop("sslmode", "") or "").strip().lower()
    query.pop("channel_binding", None)

    if sslmode and sslmode not in {"disable", "allow", "prefer"}:
        connect_args["ssl_context"] = ssl.create_default_context()

    return url.set(query=query), connect_args


@lru_cache(maxsize=1)
def _get_session_factory() -> sessionmaker:
    settings = get_settings()
    database_url, connect_args = _normalize_pg8000_url(settings.database_url)
    engine = create_engine(
        database_url,
        pool_pre_ping=True,
        connect_args=connect_args,
    )
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
