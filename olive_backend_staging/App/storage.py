from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import delete, desc, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from App.analytics import parse_datetime
from App.models import (
    Dataset,
    FabricExecution,
    FabricItem,
    FabricSQLExecution,
    Incident,
    RefreshHistory,
    Report,
    Workspace,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class PowerBIStorage:
    def __init__(self, db: Session) -> None:
        self.db = db

    def upsert_workspaces(self, workspaces: List[Dict[str, Any]]) -> None:
        try:
            for workspace in workspaces:
                statement = insert(Workspace).values(
                    id=workspace["workspaceId"],
                    name=workspace.get("workspaceName"),
                    is_read_only=workspace.get("isReadOnly"),
                    is_on_dedicated_capacity=workspace.get("isOnDedicatedCapacity"),
                    raw_payload=workspace,
                    synced_at=_utcnow(),
                )
                statement = statement.on_conflict_do_update(
                    index_elements=[Workspace.id],
                    set_={
                        "name": statement.excluded.name,
                        "is_read_only": statement.excluded.is_read_only,
                        "is_on_dedicated_capacity": (
                            statement.excluded.is_on_dedicated_capacity
                        ),
                        "raw_payload": statement.excluded.raw_payload,
                        "synced_at": statement.excluded.synced_at,
                    },
                )
                self.db.execute(statement)
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

    def upsert_reports(self, workspace_id: str, reports: List[Dict[str, Any]]) -> None:
        try:
            for report in reports:
                payload = {**report, "workspaceId": workspace_id}
                statement = insert(Report).values(
                    id=report["id"],
                    workspace_id=workspace_id,
                    name=report.get("name"),
                    dataset_id=report.get("datasetId"),
                    web_url=report.get("webUrl"),
                    embed_url=report.get("embedUrl"),
                    raw_payload=payload,
                    synced_at=_utcnow(),
                )
                statement = statement.on_conflict_do_update(
                    index_elements=[Report.id],
                    set_={
                        "workspace_id": statement.excluded.workspace_id,
                        "name": statement.excluded.name,
                        "dataset_id": statement.excluded.dataset_id,
                        "web_url": statement.excluded.web_url,
                        "embed_url": statement.excluded.embed_url,
                        "raw_payload": statement.excluded.raw_payload,
                        "synced_at": statement.excluded.synced_at,
                    },
                )
                self.db.execute(statement)
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

    def upsert_datasets(
        self,
        workspace_id: str,
        datasets: List[Dict[str, Any]],
    ) -> None:
        batch_synced_at = _utcnow()
        try:
            for dataset in datasets:
                statement = insert(Dataset).values(
                    id=dataset["datasetId"],
                    workspace_id=workspace_id,
                    name=dataset.get("datasetName"),
                    configured_by=dataset.get("configuredBy"),
                    is_refreshable=dataset.get("isRefreshable"),
                    raw_payload=dataset,
                    synced_at=batch_synced_at,
                )
                statement = statement.on_conflict_do_update(
                    index_elements=[Dataset.id],
                    set_={
                        "workspace_id": statement.excluded.workspace_id,
                        "name": statement.excluded.name,
                        "configured_by": statement.excluded.configured_by,
                        "is_refreshable": statement.excluded.is_refreshable,
                        "raw_payload": statement.excluded.raw_payload,
                        "synced_at": statement.excluded.synced_at,
                    },
                )
                self.db.execute(statement)
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

    def upsert_refresh_history(
        self,
        workspace_id: str,
        dataset_id: str,
        refresh_history: List[Dict[str, Any]],
    ) -> None:
        try:
            for refresh in refresh_history:
                statement = insert(RefreshHistory).values(
                    workspace_id=workspace_id,
                    dataset_id=dataset_id,
                    request_id=refresh.get("requestId"),
                    status=refresh.get("status"),
                    refresh_type=refresh.get("refreshType"),
                    start_time=parse_datetime(refresh.get("startTime")),
                    end_time=parse_datetime(refresh.get("endTime")),
                    raw_payload=refresh,
                    synced_at=_utcnow(),
                )
                statement = statement.on_conflict_do_update(
                    constraint="uq_refresh_history_workspace_dataset_request",
                    set_={
                        "status": statement.excluded.status,
                        "refresh_type": statement.excluded.refresh_type,
                        "start_time": statement.excluded.start_time,
                        "end_time": statement.excluded.end_time,
                        "raw_payload": statement.excluded.raw_payload,
                        "synced_at": statement.excluded.synced_at,
                    },
                )
                self.db.execute(statement)
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

    def replace_incidents(
        self,
        workspace_id: str,
        dataset_id: str,
        incidents: List[Dict[str, Any]],
    ) -> None:
        try:
            self.db.execute(
                delete(Incident).where(
                    Incident.workspace_id == workspace_id,
                    Incident.dataset_id == dataset_id,
                )
            )

            for incident in incidents:
                statement = insert(Incident).values(
                    id=incident["incidentId"],
                    workspace_id=workspace_id,
                    dataset_id=dataset_id,
                    refresh_request_id=incident.get("refreshId"),
                    incident_type=incident.get("incidentType"),
                    severity=incident.get("severity"),
                    suspected_cause=incident.get("suspectedCause"),
                    recommendation=incident.get("recommendation"),
                    detected_at=parse_datetime(incident.get("detectedAt")),
                    raw_payload=incident,
                    synced_at=_utcnow(),
                )
                statement = statement.on_conflict_do_update(
                    index_elements=[Incident.id],
                    set_={
                        "severity": statement.excluded.severity,
                        "suspected_cause": statement.excluded.suspected_cause,
                        "recommendation": statement.excluded.recommendation,
                        "detected_at": statement.excluded.detected_at,
                        "raw_payload": statement.excluded.raw_payload,
                        "synced_at": statement.excluded.synced_at,
                    },
                )
                self.db.execute(statement)

            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

    def get_workspaces(self) -> List[Dict[str, Any]]:
        query = select(Workspace).order_by(Workspace.name)
        return [item.raw_payload for item in self.db.scalars(query).all()]

    def get_reports(self) -> List[Dict[str, Any]]:
        query = select(Report).order_by(Report.name)
        return [item.raw_payload for item in self.db.scalars(query).all()]

    def get_datasets(self) -> List[Dict[str, Any]]:
        query = select(Dataset).order_by(Dataset.name)
        return [item.raw_payload for item in self.db.scalars(query).all()]

    def get_refresh_history(
        self,
        workspace_id: Optional[str] = None,
        dataset_id: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        query = select(RefreshHistory).order_by(desc(RefreshHistory.start_time))
        if workspace_id:
            query = query.where(RefreshHistory.workspace_id == workspace_id)
        if dataset_id:
            query = query.where(RefreshHistory.dataset_id == dataset_id)
        query = query.limit(limit)
        return [item.raw_payload for item in self.db.scalars(query).all()]

    def upsert_fabric_items(self, fabric_items: List[Dict[str, Any]]) -> None:
        try:
            for item in fabric_items:
                statement = insert(FabricItem).values(
                    id=item["itemId"],
                    workspace_id=item["workspaceId"],
                    name=item.get("itemName"),
                    item_type=item.get("itemType"),
                    sql_endpoint_id=item.get("sqlEndpointId"),
                    raw_payload=item,
                    synced_at=_utcnow(),
                )
                statement = statement.on_conflict_do_update(
                    index_elements=[FabricItem.id],
                    set_={
                        "workspace_id": statement.excluded.workspace_id,
                        "name": statement.excluded.name,
                        "item_type": statement.excluded.item_type,
                        "sql_endpoint_id": statement.excluded.sql_endpoint_id,
                        "raw_payload": statement.excluded.raw_payload,
                        "synced_at": statement.excluded.synced_at,
                    },
                )
                self.db.execute(statement)
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

    def upsert_fabric_executions(
        self,
        item_id: str,
        fabric_executions: List[Dict[str, Any]],
    ) -> None:
        try:
            for execution in fabric_executions:
                statement = insert(FabricExecution).values(
                    item_id=item_id,
                    workspace_id=execution["workspaceId"],
                    item_type=execution.get("itemType"),
                    execution_id=execution["executionId"],
                    status=execution.get("status"),
                    job_type=execution.get("jobType"),
                    invoke_type=execution.get("invokeType"),
                    start_time=parse_datetime(execution.get("startTimeUtc")),
                    end_time=parse_datetime(execution.get("endTimeUtc")),
                    raw_payload=execution,
                    synced_at=_utcnow(),
                )
                statement = statement.on_conflict_do_update(
                    constraint="uq_fabric_executions_item_execution",
                    set_={
                        "workspace_id": statement.excluded.workspace_id,
                        "item_type": statement.excluded.item_type,
                        "status": statement.excluded.status,
                        "job_type": statement.excluded.job_type,
                        "invoke_type": statement.excluded.invoke_type,
                        "start_time": statement.excluded.start_time,
                        "end_time": statement.excluded.end_time,
                        "raw_payload": statement.excluded.raw_payload,
                        "synced_at": statement.excluded.synced_at,
                    },
                )
                self.db.execute(statement)
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

    def upsert_fabric_sql_executions(
        self,
        item_id: str,
        sql_executions: List[Dict[str, Any]],
    ) -> None:
        try:
            for execution in sql_executions:
                statement = insert(FabricSQLExecution).values(
                    item_id=item_id,
                    workspace_id=execution["workspaceId"],
                    item_type=execution.get("itemType"),
                    query_id=execution["queryId"],
                    statement_type=execution.get("statementType"),
                    status=execution.get("status"),
                    procedure_name=execution.get("procedureName"),
                    is_stored_procedure=execution.get("isStoredProcedure"),
                    start_time=parse_datetime(execution.get("startTime")),
                    end_time=parse_datetime(execution.get("endTime")),
                    raw_payload=execution,
                    synced_at=_utcnow(),
                )
                statement = statement.on_conflict_do_update(
                    constraint="uq_fabric_sql_executions_item_query",
                    set_={
                        "workspace_id": statement.excluded.workspace_id,
                        "item_type": statement.excluded.item_type,
                        "statement_type": statement.excluded.statement_type,
                        "status": statement.excluded.status,
                        "procedure_name": statement.excluded.procedure_name,
                        "is_stored_procedure": (
                            statement.excluded.is_stored_procedure
                        ),
                        "start_time": statement.excluded.start_time,
                        "end_time": statement.excluded.end_time,
                        "raw_payload": statement.excluded.raw_payload,
                        "synced_at": statement.excluded.synced_at,
                    },
                )
                self.db.execute(statement)
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

    def get_fabric_items(
        self,
        workspace_id: Optional[str] = None,
        item_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        query = select(FabricItem).order_by(FabricItem.item_type, FabricItem.name)
        if workspace_id:
            query = query.where(FabricItem.workspace_id == workspace_id)
        if item_type:
            query = query.where(FabricItem.item_type == item_type)
        return [item.raw_payload for item in self.db.scalars(query).all()]

    def get_fabric_executions(
        self,
        workspace_id: Optional[str] = None,
        item_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        query = select(FabricExecution).order_by(desc(FabricExecution.start_time))
        if workspace_id:
            query = query.where(FabricExecution.workspace_id == workspace_id)
        if item_id:
            query = query.where(FabricExecution.item_id == item_id)
        query = query.limit(limit)
        return [item.raw_payload for item in self.db.scalars(query).all()]

    def get_fabric_sql_executions(
        self,
        workspace_id: Optional[str] = None,
        item_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        query = select(FabricSQLExecution).order_by(desc(FabricSQLExecution.start_time))
        if workspace_id:
            query = query.where(FabricSQLExecution.workspace_id == workspace_id)
        if item_id:
            query = query.where(FabricSQLExecution.item_id == item_id)
        query = query.limit(limit)
        return [item.raw_payload for item in self.db.scalars(query).all()]

    def get_incidents(
        self,
        workspace_id: Optional[str] = None,
        dataset_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        query = select(Incident).order_by(desc(Incident.detected_at))
        if workspace_id:
            query = query.where(Incident.workspace_id == workspace_id)
        if dataset_id:
            query = query.where(Incident.dataset_id == dataset_id)
        query = query.limit(limit)
        return [item.raw_payload for item in self.db.scalars(query).all()]
