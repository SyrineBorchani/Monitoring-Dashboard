from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import delete, desc, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from App.analytics import parse_datetime
from App.models import Dataset, Incident, RefreshHistory, Report, Workspace


class PowerBIStorage:
    def __init__(self, db: Session) -> None:
        self.db = db

    def upsert_workspaces(self, workspaces: List[Dict[str, Any]]) -> None:
        for workspace in workspaces:
            statement = insert(Workspace).values(
                id=workspace["workspaceId"],
                name=workspace.get("workspaceName"),
                is_read_only=workspace.get("isReadOnly"),
                is_on_dedicated_capacity=workspace.get("isOnDedicatedCapacity"),
                raw_payload=workspace,
                synced_at=datetime.utcnow(),
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

    def upsert_reports(self, workspace_id: str, reports: List[Dict[str, Any]]) -> None:
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
                synced_at=datetime.utcnow(),
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

    def upsert_datasets(
        self,
        workspace_id: str,
        datasets: List[Dict[str, Any]],
    ) -> None:
        for dataset in datasets:
            statement = insert(Dataset).values(
                id=dataset["datasetId"],
                workspace_id=workspace_id,
                name=dataset.get("datasetName"),
                configured_by=dataset.get("configuredBy"),
                is_refreshable=dataset.get("isRefreshable"),
                raw_payload=dataset,
                synced_at=datetime.utcnow(),
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

    def upsert_refresh_history(
        self,
        workspace_id: str,
        dataset_id: str,
        refresh_history: List[Dict[str, Any]],
    ) -> None:
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
                synced_at=datetime.utcnow(),
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

    def replace_incidents(
        self,
        workspace_id: str,
        dataset_id: str,
        incidents: List[Dict[str, Any]],
    ) -> None:
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
                synced_at=datetime.utcnow(),
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
