from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
import os
from urllib.parse import quote_plus

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR / ".env"
load_dotenv(ENV_PATH)


def _env_flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _normalize_database_url(database_url: str) -> str:
    if database_url.startswith("postgres://"):
        return database_url.replace("postgres://", "postgresql+pg8000://", 1)
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+pg8000://", 1)
    if database_url.startswith("postgresql+psycopg2://"):
        return database_url.replace(
            "postgresql+psycopg2://",
            "postgresql+pg8000://",
            1,
        )
    return database_url


@dataclass(frozen=True)
class Settings:
    tenant_id: str
    client_id: str
    client_secret: str
    powerbi_base_url: str
    fabric_base_url: str
    database_url: str
    powerbi_scope: str = "https://analysis.windows.net/powerbi/api/.default"
    fabric_scope: str = "https://api.fabric.microsoft.com/.default"
    fabric_sql_monitoring_enabled: bool = False
    fabric_sql_source: str = "auto"
    fabric_sql_notebook_export_path: str = ""
    fabric_sql_odbc_driver: str = "ODBC Driver 18 for SQL Server"
    fabric_sql_connect_timeout: int = 15
    fabric_sql_command_timeout: int = 30
    fabric_sql_top: int = 50

    @property
    def token_url(self) -> str:
        return (
            f"https://login.microsoftonline.com/{self.tenant_id}"
            "/oauth2/v2.0/token"
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        postgres_host = _require_env("POSTGRES_HOST")
        postgres_port = os.getenv("POSTGRES_PORT", "5432")
        postgres_db = _require_env("POSTGRES_DB")
        postgres_user = _require_env("POSTGRES_USER")
        postgres_password = quote_plus(_require_env("POSTGRES_PASSWORD"))
        database_url = (
            "postgresql+pg8000://"
            f"{postgres_user}:{postgres_password}@{postgres_host}:{postgres_port}/"
            f"{postgres_db}"
        )
    else:
        database_url = _normalize_database_url(database_url)

    return Settings(
        tenant_id=_require_env("TENANT_ID"),
        client_id=_require_env("CLIENT_ID"),
        client_secret=_require_env("CLIENT_SECRET"),
        powerbi_base_url=os.getenv(
            "POWERBI_BASE_URL",
            "https://api.powerbi.com/v1.0/myorg",
        ).rstrip("/"),
        fabric_base_url=os.getenv(
            "FABRIC_BASE_URL",
            "https://api.fabric.microsoft.com/v1",
        ).rstrip("/"),
        database_url=database_url,
        powerbi_scope=os.getenv(
            "POWERBI_SCOPE",
            "https://analysis.windows.net/powerbi/api/.default",
        ),
        fabric_scope=os.getenv(
            "FABRIC_SCOPE",
            "https://api.fabric.microsoft.com/.default",
        ),
        fabric_sql_monitoring_enabled=_env_flag("FABRIC_SQL_MONITORING_ENABLED"),
        fabric_sql_source=os.getenv("FABRIC_SQL_SOURCE", "auto").strip().lower() or "auto",
        fabric_sql_notebook_export_path=os.getenv(
            "FABRIC_SQL_NOTEBOOK_EXPORT_PATH",
            "",
        ).strip(),
        fabric_sql_odbc_driver=os.getenv(
            "FABRIC_SQL_ODBC_DRIVER",
            "ODBC Driver 18 for SQL Server",
        ).strip()
        or "ODBC Driver 18 for SQL Server",
        fabric_sql_connect_timeout=int(
            os.getenv("FABRIC_SQL_CONNECT_TIMEOUT", "15")
        ),
        fabric_sql_command_timeout=int(
            os.getenv("FABRIC_SQL_COMMAND_TIMEOUT", "30")
        ),
        fabric_sql_top=int(os.getenv("FABRIC_SQL_TOP", "50")),
    )
