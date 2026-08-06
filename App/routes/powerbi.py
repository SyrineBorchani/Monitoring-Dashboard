import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, HTTPException, Query
import requests

from App.analytics import (
    build_dataset_record,
    build_datasource_record,
    build_fabric_execution_record,
    build_fabric_item_record,
    build_report_record,
    build_fabric_sql_execution_record,
    build_refresh_record,
    build_workspace_record,
    derive_incidents,
    summarize_monitoring,
)
from App.database import get_db_session
from App.fabric_sql import get_fabric_sql_collector
from App.powerbi_client import get_powerbi_client
from App.storage import PowerBIStorage


router = APIRouter(prefix="/api/powerbi", tags=["powerbi"])
logger = logging.getLogger(__name__)
FABRIC_EXECUTION_LIMIT = 20


def _has_required_identifier(payload: Any) -> bool:
    return isinstance(payload, dict) and bool(payload.get("id"))


def _safe_workspace_record(raw_workspace: Any) -> Optional[Dict[str, Any]]:
    if not _has_required_identifier(raw_workspace):
        logger.warning("Skipping malformed Power BI workspace payload: %s", raw_workspace)
        return None
    return build_workspace_record(raw_workspace)


def _safe_datasource_record(raw_datasource: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(raw_datasource, dict):
        logger.warning("Skipping malformed Power BI datasource payload: %s", raw_datasource)
        return None
    return build_datasource_record(raw_datasource)


def _safe_report_record(
    raw_report: Any,
    workspace: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    if not _has_required_identifier(raw_report):
        logger.warning(
            "Skipping malformed Power BI report payload for workspace %s: %s",
            workspace.get("workspaceId"),
            raw_report,
        )
        return None
    return build_report_record(raw_report, workspace)


def _safe_dataset_record(
    raw_dataset: Any,
    workspace: Dict[str, Any],
    datasources: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    if not _has_required_identifier(raw_dataset):
        logger.warning("Skipping malformed Power BI dataset payload: %s", raw_dataset)
        return None
    return build_dataset_record(raw_dataset, workspace, datasources)


def _safe_refresh_record(
    raw_refresh: Any,
    workspace: Dict[str, Any],
    dataset: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    if not isinstance(raw_refresh, dict):
        logger.warning("Skipping malformed Power BI refresh payload: %s", raw_refresh)
        return None
    return build_refresh_record(raw_refresh, workspace, dataset)


def _safe_fabric_item_record(
    raw_item: Any,
    workspace: Dict[str, Any],
    item_type: str,
) -> Optional[Dict[str, Any]]:
    if not _has_required_identifier(raw_item):
        logger.warning(
            "Skipping malformed Fabric %s payload: %s",
            item_type,
            raw_item,
        )
        return None
    return build_fabric_item_record(raw_item, workspace, item_type)


def _prepare_fabric_item_payload(
    raw_item: Any,
    workspace_id: str,
    item_type: str,
) -> Any:
    if not isinstance(raw_item, dict) or not raw_item.get("id"):
        return raw_item

    payload = dict(raw_item)
    properties = dict(payload.get("properties") or {})
    payload["properties"] = properties

    if item_type == "Warehouse" and not properties.get("connectionString"):
        connection_string = _client().get_warehouse_connection_string(
            workspace_id,
            str(payload["id"]),
        )
        if connection_string:
            properties["connectionString"] = connection_string
        return payload

    if item_type == "Lakehouse":
        sql_properties = dict(properties.get("sqlEndpointProperties") or {})
        if sql_properties.get("connectionString") and sql_properties.get("id"):
            return payload

        details = _client().get_lakehouse(workspace_id, str(payload["id"]))
        if not isinstance(details, dict):
            return payload

        detail_properties = dict(details.get("properties") or {})
        detail_sql = dict(detail_properties.get("sqlEndpointProperties") or {})
        merged_sql = {**detail_sql, **sql_properties}
        merged_sql = {key: value for key, value in merged_sql.items() if value is not None}
        merged_properties = {**detail_properties, **properties}
        if merged_sql:
            merged_properties["sqlEndpointProperties"] = merged_sql
        payload.update({key: value for key, value in details.items() if key != "properties"})
        payload["properties"] = merged_properties

    return payload


def _safe_fabric_execution_record(
    raw_execution: Any,
    fabric_item: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    if not isinstance(raw_execution, dict):
        logger.warning(
            "Skipping malformed Fabric execution payload for item %s: %s",
            fabric_item.get("itemId"),
            raw_execution,
        )
        return None
    return build_fabric_execution_record(raw_execution, fabric_item)


def _safe_fabric_sql_execution_record(
    raw_execution: Any,
    fabric_item: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    if not isinstance(raw_execution, dict):
        logger.warning(
            "Skipping malformed Fabric SQL execution payload for item %s: %s",
            fabric_item.get("itemId"),
            raw_execution,
        )
        return None
    return build_fabric_sql_execution_record(raw_execution, fabric_item)


def _raise_api_error(error: requests.HTTPError) -> None:
    response = error.response
    detail = "Power BI API request failed."

    if response is not None:
        try:
            detail = response.json()
        except ValueError:
            detail = response.text or detail
        raise HTTPException(status_code=response.status_code, detail=detail) from error

    raise HTTPException(status_code=502, detail=detail) from error


def _client():
    return get_powerbi_client()


def _storage() -> PowerBIStorage:
    return PowerBIStorage(get_db_session())


def _fabric_sql_collector():
    return get_fabric_sql_collector()


def _upstream_status_code(error: Exception) -> Optional[int]:
    if isinstance(error, requests.HTTPError) and error.response is not None:
        return error.response.status_code
    return None


def _is_fallback_eligible(error: Exception) -> bool:
    if isinstance(error, requests.Timeout):
        return True
    if isinstance(error, requests.HTTPError):
        status_code = _upstream_status_code(error)
        return bool(status_code == 429 or (status_code is not None and status_code >= 500))
    return isinstance(error, requests.RequestException)


def _fallback_warning(error: Exception) -> str:
    status_code = _upstream_status_code(error)
    if status_code == 429:
        return "Live Power BI data was rate-limited. Returned cached data instead."
    if status_code is not None and status_code >= 500:
        return "Live Power BI data was unavailable upstream. Returned cached data instead."
    if isinstance(error, requests.Timeout):
        return "Live Power BI data timed out. Returned cached data instead."
    return "Live Power BI data was unavailable. Returned cached data instead."


def _cached_response_payload(
    payload: Dict[str, Any],
    error: Exception,
) -> Dict[str, Any]:
    response_payload = dict(payload)
    response_payload["mode"] = "cached"
    response_payload["warning"] = _fallback_warning(error)
    status_code = _upstream_status_code(error)
    if status_code is not None:
        response_payload["upstreamStatus"] = status_code
    return response_payload


def _recover_live_response(
    error: Exception,
    *,
    endpoint_name: str,
    cached_payload_builder,
) -> Dict[str, Any]:
    logger.warning(
        "Live Power BI request failed for %s. fallback_eligible=%s status=%s detail=%s",
        endpoint_name,
        _is_fallback_eligible(error),
        _upstream_status_code(error),
        str(error),
    )

    if _is_fallback_eligible(error):
        logger.warning("Serving cached Power BI response for %s.", endpoint_name)
        return _cached_response_payload(cached_payload_builder(), error)

    if isinstance(error, requests.HTTPError):
        _raise_api_error(error)
    raise HTTPException(status_code=502, detail=str(error)) from error


def _mode_payload() -> Dict[str, Any]:
    return {
        "mode": "live",
        "title": "Environnement connecte",
        "description": (
            "Le dashboard interroge les APIs Power BI et historise les donnees dans la "
            "base PostgreSQL configuree."
        ),
    }


def _cached_reports(storage: PowerBIStorage, workspace_id: Optional[str] = None) -> List[Dict[str, Any]]:
    reports = storage.get_reports()
    if workspace_id is not None:
        reports = [item for item in reports if item.get("workspaceId") == workspace_id]
    return reports


def _cached_datasets(
    storage: PowerBIStorage,
    workspace_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    datasets = storage.get_datasets()
    if workspace_id is not None:
        datasets = [item for item in datasets if item.get("workspaceId") == workspace_id]
    return datasets


def _fetch_live_workspaces(storage: PowerBIStorage) -> List[Dict[str, Any]]:
    workspaces = []
    for item in _client().list_workspaces():
        workspace = _safe_workspace_record(item)
        if workspace is not None:
            workspaces.append(workspace)
    storage.upsert_workspaces(workspaces)
    return workspaces


def _find_workspace(storage: PowerBIStorage, workspace_id: str) -> Dict[str, Any]:
    workspaces = _fetch_live_workspaces(storage)
    for workspace in workspaces:
        if workspace["workspaceId"] == workspace_id:
            return workspace
    raise HTTPException(status_code=404, detail="Workspace not found.")


def _fetch_live_datasets(
    storage: PowerBIStorage,
    workspaces: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    workspaces = workspaces or _fetch_live_workspaces(storage)
    all_datasets: List[Dict[str, Any]] = []

    for workspace in workspaces:
        workspace_id = workspace["workspaceId"]
        datasets = []
        for raw_dataset in _client().list_workspace_datasets(workspace_id):
            if not _has_required_identifier(raw_dataset):
                logger.warning(
                    "Skipping malformed Power BI dataset payload for workspace %s: %s",
                    workspace_id,
                    raw_dataset,
                )
                continue
            datasources = []
            for item in _client().list_dataset_datasources(
                workspace_id,
                raw_dataset["id"],
            ):
                datasource = _safe_datasource_record(item)
                if datasource is not None:
                    datasources.append(datasource)
            dataset = _safe_dataset_record(raw_dataset, workspace, datasources)
            if dataset is not None:
                datasets.append(dataset)
        storage.upsert_datasets(workspace_id, datasets)
        all_datasets.extend(datasets)

    return all_datasets


def _fetch_live_reports(
    storage: PowerBIStorage,
    workspaces: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    workspaces = workspaces or _fetch_live_workspaces(storage)
    all_reports: List[Dict[str, Any]] = []

    for workspace in workspaces:
        workspace_id = workspace["workspaceId"]
        reports = []
        for raw_report in _client().list_workspace_reports(workspace_id):
            report = _safe_report_record(raw_report, workspace)
            if report is not None:
                reports.append(report)
        storage.upsert_reports(workspace_id, reports)
        all_reports.extend(reports)

    return all_reports


def _fetch_live_refreshes(
    storage: PowerBIStorage,
    datasets: List[Dict[str, Any]],
    refresh_top: int,
) -> List[Dict[str, Any]]:
    refreshes: List[Dict[str, Any]] = []

    for dataset in datasets:
        workspace = {
            "workspaceId": dataset["workspaceId"],
            "workspaceName": dataset.get("workspaceName"),
        }
        raw_refreshes = _client().list_dataset_refresh_history(
            dataset["workspaceId"],
            dataset["datasetId"],
            top=refresh_top,
        )
        normalized_refreshes = []
        for item in raw_refreshes:
            refresh = _safe_refresh_record(item, workspace, dataset)
            if refresh is not None:
                normalized_refreshes.append(refresh)
        storage.upsert_refresh_history(
            dataset["workspaceId"],
            dataset["datasetId"],
            normalized_refreshes,
        )
        dataset_incidents = derive_incidents(normalized_refreshes)
        storage.replace_incidents(
            dataset["workspaceId"],
            dataset["datasetId"],
            dataset_incidents,
        )
        refreshes.extend(normalized_refreshes)

    return refreshes


def _fetch_live_fabric_items(
    storage: PowerBIStorage,
    workspaces: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    workspaces = workspaces or _fetch_live_workspaces(storage)
    fabric_items: List[Dict[str, Any]] = []

    for workspace in workspaces:
        workspace_id = workspace["workspaceId"]
        for raw_item in _client().list_workspace_warehouses(workspace_id):
            item = _safe_fabric_item_record(
                _prepare_fabric_item_payload(raw_item, workspace_id, "Warehouse"),
                workspace,
                "Warehouse",
            )
            if item is not None:
                fabric_items.append(item)
        for raw_item in _client().list_workspace_lakehouses(workspace_id):
            item = _safe_fabric_item_record(
                _prepare_fabric_item_payload(raw_item, workspace_id, "Lakehouse"),
                workspace,
                "Lakehouse",
            )
            if item is not None:
                fabric_items.append(item)

    storage.upsert_fabric_items(fabric_items)
    return fabric_items


def _fetch_live_fabric_executions(
    storage: PowerBIStorage,
    fabric_items: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    all_executions: List[Dict[str, Any]] = []

    for fabric_item in fabric_items:
        raw_executions = _client().list_item_job_instances(
            fabric_item["workspaceId"],
            fabric_item["itemId"],
        )[:FABRIC_EXECUTION_LIMIT]
        executions = []
        for raw_execution in raw_executions:
            execution = _safe_fabric_execution_record(raw_execution, fabric_item)
            if execution is not None:
                executions.append(execution)
        storage.upsert_fabric_executions(fabric_item["itemId"], executions)
        all_executions.extend(executions)

    return all_executions


def _fetch_live_fabric_sql_executions(
    storage: PowerBIStorage,
    fabric_items: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    queries_by_item = _fabric_sql_collector().collect_item_queries(fabric_items)
    return _persist_fabric_sql_queries(storage, fabric_items, queries_by_item)


def _persist_fabric_sql_queries(
    storage: PowerBIStorage,
    fabric_items: List[Dict[str, Any]],
    queries_by_item: Dict[str, List[Dict[str, Any]]],
) -> List[Dict[str, Any]]:
    all_queries: List[Dict[str, Any]] = []
    item_lookup = {item["itemId"]: item for item in fabric_items}

    for item_id, raw_queries in queries_by_item.items():
        fabric_item = item_lookup.get(item_id)
        if fabric_item is None:
            continue
        queries = []
        for raw_query in raw_queries:
            query = _safe_fabric_sql_execution_record(raw_query, fabric_item)
            if query is not None:
                queries.append(query)
        storage.upsert_fabric_sql_executions(item_id, queries)
        all_queries.extend(queries)

    return all_queries


def _sync_monitoring_snapshot(
    storage: PowerBIStorage,
    refresh_top: int,
) -> Dict[str, Any]:
    workspaces = _fetch_live_workspaces(storage)
    datasets = _fetch_live_datasets(storage, workspaces)
    refreshes = _fetch_live_refreshes(storage, datasets, refresh_top)
    incidents = storage.get_incidents(limit=5000)
    fabric_items = _fetch_live_fabric_items(storage, workspaces)
    fabric_executions = _fetch_live_fabric_executions(storage, fabric_items)
    fabric_sql_executions = _fetch_live_fabric_sql_executions(storage, fabric_items)
    return {
        "workspaces": workspaces,
        "datasets": datasets,
        "refreshes": refreshes,
        "incidents": incidents,
        "fabricItems": fabric_items,
        "fabricExecutions": fabric_executions,
        "fabricSqlExecutions": fabric_sql_executions,
    }


@router.get("/mode")
def get_operating_mode():
    return _mode_payload()


@router.get("/workspaces")
def get_workspaces():
    storage = _storage()
    try:
        return {"value": _fetch_live_workspaces(storage)}
    except requests.RequestException as error:
        return _recover_live_response(
            error,
            endpoint_name="get_workspaces",
            cached_payload_builder=lambda: {"value": storage.get_workspaces()},
        )
    finally:
        storage.db.close()


@router.get("/reports")
def get_reports():
    storage = _storage()
    try:
        return {"value": _fetch_live_reports(storage)}
    except requests.RequestException as error:
        return _recover_live_response(
            error,
            endpoint_name="get_reports",
            cached_payload_builder=lambda: {"value": _cached_reports(storage)},
        )
    finally:
        storage.db.close()


@router.get("/datasets")
def get_datasets():
    storage = _storage()
    try:
        return {"value": _fetch_live_datasets(storage)}
    except requests.RequestException as error:
        return _recover_live_response(
            error,
            endpoint_name="get_datasets",
            cached_payload_builder=lambda: {"value": _cached_datasets(storage)},
        )
    finally:
        storage.db.close()


@router.get("/refreshes")
def get_refreshes(
    refresh_top: int = Query(default=10, ge=1, le=100),
):
    storage = _storage()
    try:
        datasets = _fetch_live_datasets(storage)
        return {
            "value": _fetch_live_refreshes(storage, datasets, refresh_top),
        }
    except requests.RequestException as error:
        return _recover_live_response(
            error,
            endpoint_name="get_refreshes",
            cached_payload_builder=lambda: {"value": storage.get_refresh_history(limit=5000)},
        )
    finally:
        storage.db.close()


@router.get("/incidents")
def get_incidents(
    refresh_top: int = Query(default=10, ge=1, le=100),
):
    storage = _storage()
    try:
        _sync_monitoring_snapshot(storage, refresh_top)
        return {"value": storage.get_incidents(limit=5000)}
    except requests.RequestException as error:
        return _recover_live_response(
            error,
            endpoint_name="get_incidents",
            cached_payload_builder=lambda: {"value": storage.get_incidents(limit=5000)},
        )
    finally:
        storage.db.close()


@router.get("/workspaces/{workspace_id}/reports")
def get_workspace_reports(workspace_id: str):
    storage = _storage()
    try:
        workspace = _find_workspace(storage, workspace_id)
        reports = []
        for raw_report in _client().list_workspace_reports(workspace_id):
            report = _safe_report_record(raw_report, workspace)
            if report is not None:
                reports.append(report)
        storage.upsert_reports(workspace_id, reports)
        return {"value": reports}
    except requests.RequestException as error:
        return _recover_live_response(
            error,
            endpoint_name="get_workspace_reports",
            cached_payload_builder=lambda: {"value": _cached_reports(storage, workspace_id)},
        )
    finally:
        storage.db.close()


@router.get("/workspaces/{workspace_id}/datasets")
def get_workspace_datasets(workspace_id: str):
    storage = _storage()
    try:
        workspace = _find_workspace(storage, workspace_id)
        datasets = []
        for raw_dataset in _client().list_workspace_datasets(workspace_id):
            if not _has_required_identifier(raw_dataset):
                logger.warning(
                    "Skipping malformed Power BI dataset payload for workspace %s: %s",
                    workspace_id,
                    raw_dataset,
                )
                continue
            datasources = []
            for item in _client().list_dataset_datasources(
                workspace_id,
                raw_dataset["id"],
            ):
                datasource = _safe_datasource_record(item)
                if datasource is not None:
                    datasources.append(datasource)
            dataset = _safe_dataset_record(raw_dataset, workspace, datasources)
            if dataset is not None:
                datasets.append(dataset)
        storage.upsert_datasets(workspace_id, datasets)
        return {"value": datasets}
    except requests.RequestException as error:
        return _recover_live_response(
            error,
            endpoint_name="get_workspace_datasets",
            cached_payload_builder=lambda: {"value": _cached_datasets(storage, workspace_id)},
        )
    finally:
        storage.db.close()


@router.get("/workspaces/{workspace_id}/datasets/{dataset_id}/refreshes")
def get_dataset_refresh_history(
    workspace_id: str,
    dataset_id: str,
    top: int = Query(default=10, ge=1, le=100),
):
    storage = _storage()
    try:
        workspace = _find_workspace(storage, workspace_id)
        dataset_payload = None
        for item in _fetch_live_datasets(storage, [workspace]):
            if item["datasetId"] == dataset_id:
                dataset_payload = item
                break
        if dataset_payload is None:
            raise HTTPException(status_code=404, detail="Dataset not found.")

        refresh_history = []
        for item in _client().list_dataset_refresh_history(
            workspace_id,
            dataset_id,
            top=top,
        ):
            refresh = _safe_refresh_record(item, workspace, dataset_payload)
            if refresh is not None:
                refresh_history.append(refresh)
        storage.upsert_refresh_history(workspace_id, dataset_id, refresh_history)
        storage.replace_incidents(
            workspace_id,
            dataset_id,
            derive_incidents(refresh_history),
        )
        return {"value": refresh_history}
    except requests.RequestException as error:
        return _recover_live_response(
            error,
            endpoint_name="get_dataset_refresh_history",
            cached_payload_builder=lambda: {
                "value": storage.get_refresh_history(
                    workspace_id=workspace_id,
                    dataset_id=dataset_id,
                    limit=5000,
                )
            },
        )
    finally:
        storage.db.close()


@router.post("/monitoring/sync")
def sync_monitoring_snapshot(
    refresh_top: int = Query(default=10, ge=1, le=100),
):
    storage = _storage()
    try:
        snapshot = _sync_monitoring_snapshot(storage, refresh_top)
        return {
            "message": "Le snapshot de monitoring a ete synchronise.",
            "counts": {
                "workspaces": len(snapshot["workspaces"]),
                "datasets": len(snapshot["datasets"]),
                "refreshes": len(snapshot["refreshes"]),
                "incidents": len(snapshot["incidents"]),
                "fabricItems": len(snapshot["fabricItems"]),
                "fabricExecutions": len(snapshot["fabricExecutions"]),
                "fabricSqlExecutions": len(snapshot["fabricSqlExecutions"]),
            },
        }
    except requests.RequestException as error:
        logger.warning(
            "Monitoring sync failed. status=%s detail=%s",
            _upstream_status_code(error),
            str(error),
        )
        if isinstance(error, requests.HTTPError):
            _raise_api_error(error)
        raise HTTPException(status_code=502, detail=str(error)) from error
    finally:
        storage.db.close()


@router.get("/monitoring/indicators")
def get_monitoring_indicators(
    live: bool = Query(default=False),
    refresh_top: int = Query(default=10, ge=1, le=100),
):
    storage = _storage()
    try:
        if live:
            snapshot = _sync_monitoring_snapshot(storage, refresh_top)
            refreshes = snapshot["refreshes"]
            incidents = snapshot["incidents"]
            datasets = snapshot["datasets"]
            fabric_items = snapshot["fabricItems"]
            fabric_executions = snapshot["fabricExecutions"]
            fabric_sql_executions = snapshot["fabricSqlExecutions"]
        else:
            refreshes = storage.get_refresh_history(limit=5000)
            incidents = storage.get_incidents(limit=5000)
            datasets = storage.get_datasets()
            fabric_items = storage.get_fabric_items()
            fabric_executions = storage.get_fabric_executions(limit=5000)
            fabric_sql_executions = storage.get_fabric_sql_executions(limit=5000)
        return summarize_monitoring(
            refreshes,
            incidents,
            datasets,
            fabric_items,
            fabric_executions,
            fabric_sql_executions,
        )
    except requests.RequestException as error:
        if not live:
            return _recover_live_response(
                error,
                endpoint_name="get_monitoring_indicators_offline",
                cached_payload_builder=lambda: summarize_monitoring(
                    storage.get_refresh_history(limit=5000),
                    storage.get_incidents(limit=5000),
                    storage.get_datasets(),
                    storage.get_fabric_items(),
                    storage.get_fabric_executions(limit=5000),
                    storage.get_fabric_sql_executions(limit=5000),
                ),
            )
        return _recover_live_response(
            error,
            endpoint_name="get_monitoring_indicators_live",
            cached_payload_builder=lambda: summarize_monitoring(
                storage.get_refresh_history(limit=5000),
                storage.get_incidents(limit=5000),
                storage.get_datasets(),
                storage.get_fabric_items(),
                storage.get_fabric_executions(limit=5000),
                storage.get_fabric_sql_executions(limit=5000),
            ),
        )
    finally:
        storage.db.close()


@router.post("/fabric/sql-executions/import")
def import_fabric_sql_executions(payload: Any = Body(...)):
    storage = _storage()
    try:
        fabric_items = storage.get_fabric_items()
        if not fabric_items:
            fabric_items = _fetch_live_fabric_items(storage)
        if not fabric_items:
            raise HTTPException(
                status_code=400,
                detail="No Fabric items are available to match the notebook export.",
            )

        queries_by_item = _fabric_sql_collector().collect_item_queries_from_payload(
            fabric_items,
            payload,
        )
        executions = _persist_fabric_sql_queries(storage, fabric_items, queries_by_item)
        return {
            "counts": {
                "fabricItemsMatched": len(queries_by_item),
                "fabricSqlExecutions": len(executions),
            }
        }
    except requests.RequestException as error:
        return _recover_live_response(
            error,
            endpoint_name="import_fabric_sql_executions",
            cached_payload_builder=lambda: {
                "counts": {
                    "fabricItemsMatched": 0,
                    "fabricSqlExecutions": 0,
                }
            },
        )
    finally:
        storage.db.close()


@router.get("/storage/workspaces")
def get_stored_workspaces():
    storage = _storage()
    try:
        return {"value": storage.get_workspaces()}
    finally:
        storage.db.close()


@router.get("/storage/reports")
def get_stored_reports():
    storage = _storage()
    try:
        return {"value": storage.get_reports()}
    finally:
        storage.db.close()


@router.get("/storage/datasets")
def get_stored_datasets():
    storage = _storage()
    try:
        return {"value": storage.get_datasets()}
    finally:
        storage.db.close()


@router.get("/storage/refreshes")
def get_stored_refresh_history(
    workspace_id: Optional[str] = None,
    dataset_id: Optional[str] = None,
    limit: int = Query(default=50, ge=1, le=5000),
):
    storage = _storage()
    try:
        return {
            "value": storage.get_refresh_history(
                workspace_id=workspace_id,
                dataset_id=dataset_id,
                limit=limit,
            )
        }
    finally:
        storage.db.close()


@router.get("/storage/incidents")
def get_stored_incidents(
    workspace_id: Optional[str] = None,
    dataset_id: Optional[str] = None,
    limit: int = Query(default=100, ge=1, le=5000),
):
    storage = _storage()
    try:
        return {
            "value": storage.get_incidents(
                workspace_id=workspace_id,
                dataset_id=dataset_id,
                limit=limit,
            )
        }
    finally:
        storage.db.close()


@router.get("/storage/fabric/items")
def get_stored_fabric_items():
    storage = _storage()
    try:
        return {"value": storage.get_fabric_items()}
    finally:
        storage.db.close()


@router.get("/storage/fabric/executions")
def get_stored_fabric_executions(
    workspace_id: Optional[str] = None,
    item_id: Optional[str] = None,
    limit: int = Query(default=100, ge=1, le=5000),
):
    storage = _storage()
    try:
        return {
            "value": storage.get_fabric_executions(
                workspace_id=workspace_id,
                item_id=item_id,
                limit=limit,
            )
        }
    finally:
        storage.db.close()


@router.get("/storage/fabric/sql-executions")
def get_stored_fabric_sql_executions(
    workspace_id: Optional[str] = None,
    item_id: Optional[str] = None,
    limit: int = Query(default=100, ge=1, le=5000),
):
    storage = _storage()
    try:
        return {
            "value": storage.get_fabric_sql_executions(
                workspace_id=workspace_id,
                item_id=item_id,
                limit=limit,
            )
        }
    finally:
        storage.db.close()

