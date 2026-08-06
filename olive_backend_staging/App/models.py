from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Workspace(Base):
    __tablename__ = "workspaces"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    is_read_only: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    is_on_dedicated_capacity: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    raw_payload: Mapped[Dict[str, Any]] = mapped_column(JSONB)
    synced_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    workspace_id: Mapped[str] = mapped_column(String, index=True)
    name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    dataset_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    web_url: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    embed_url: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    raw_payload: Mapped[Dict[str, Any]] = mapped_column(JSONB)
    synced_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Dataset(Base):
    __tablename__ = "datasets"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    workspace_id: Mapped[str] = mapped_column(String, index=True)
    name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    configured_by: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    is_refreshable: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    raw_payload: Mapped[Dict[str, Any]] = mapped_column(JSONB)
    synced_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class DatasetMeasurement(Base):
    __tablename__ = "dataset_measurements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[str] = mapped_column(String, index=True)
    dataset_id: Mapped[str] = mapped_column(String, index=True)
    dataset_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    measured_at: Mapped[datetime] = mapped_column(DateTime, index=True, default=utcnow)
    raw_payload: Mapped[Dict[str, Any]] = mapped_column(JSONB)


class RefreshHistory(Base):
    __tablename__ = "refresh_history"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "dataset_id",
            "request_id",
            name="uq_refresh_history_workspace_dataset_request",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[str] = mapped_column(String, index=True)
    dataset_id: Mapped[str] = mapped_column(String, index=True)
    request_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    status: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    refresh_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    start_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    end_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    raw_payload: Mapped[Dict[str, Any]] = mapped_column(JSONB)
    synced_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Incident(Base):
    __tablename__ = "incidents"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    workspace_id: Mapped[str] = mapped_column(String, index=True)
    dataset_id: Mapped[str] = mapped_column(String, index=True)
    refresh_request_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    incident_type: Mapped[str] = mapped_column(String, index=True)
    severity: Mapped[str] = mapped_column(String, index=True)
    suspected_cause: Mapped[str] = mapped_column(String, nullable=False)
    recommendation: Mapped[str] = mapped_column(String, nullable=False)
    detected_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    raw_payload: Mapped[Dict[str, Any]] = mapped_column(JSONB)
    synced_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class FabricItem(Base):
    __tablename__ = "fabric_items"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    workspace_id: Mapped[str] = mapped_column(String, index=True)
    name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    item_type: Mapped[str] = mapped_column(String, index=True)
    sql_endpoint_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    raw_payload: Mapped[Dict[str, Any]] = mapped_column(JSONB)
    synced_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class FabricExecution(Base):
    __tablename__ = "fabric_executions"
    __table_args__ = (
        UniqueConstraint(
            "item_id",
            "execution_id",
            name="uq_fabric_executions_item_execution",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    item_id: Mapped[str] = mapped_column(String, index=True)
    workspace_id: Mapped[str] = mapped_column(String, index=True)
    item_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    execution_id: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    job_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    invoke_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    start_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    end_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    raw_payload: Mapped[Dict[str, Any]] = mapped_column(JSONB)
    synced_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class FabricSQLExecution(Base):
    __tablename__ = "fabric_sql_executions"
    __table_args__ = (
        UniqueConstraint(
            "item_id",
            "query_id",
            name="uq_fabric_sql_executions_item_query",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    item_id: Mapped[str] = mapped_column(String, index=True)
    workspace_id: Mapped[str] = mapped_column(String, index=True)
    item_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    query_id: Mapped[str] = mapped_column(String, nullable=False)
    statement_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    status: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    procedure_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    is_stored_procedure: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    start_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    end_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    raw_payload: Mapped[Dict[str, Any]] = mapped_column(JSONB)
    synced_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
