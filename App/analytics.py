from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
import re
from statistics import mean
from typing import Any, Dict, List, Optional, Tuple


DEFAULT_DELAY_THRESHOLD_SECONDS = 3600
DEFAULT_DURATION_ANOMALY_FACTOR = 1.5
MINIMUM_ANOMALY_DURATION_SECONDS = 300


def parse_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    return datetime.fromisoformat(normalized)


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _round(value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    return round(value, 2)


def _extract_error_details(raw_exception: Any) -> Tuple[Optional[str], Optional[str]]:
    if not raw_exception:
        return None, None

    if isinstance(raw_exception, dict):
        payload = raw_exception
    else:
        try:
            payload = json.loads(raw_exception)
        except (TypeError, json.JSONDecodeError):
            text = str(raw_exception)
            return None, text

    code = payload.get("errorCode") or payload.get("code")
    message = (
        payload.get("errorDescription")
        or payload.get("message")
        or payload.get("errorMessage")
    )
    return code, message


def _connection_summary(connection_details: Any) -> Optional[str]:
    if not isinstance(connection_details, dict) or not connection_details:
        return None

    parts = []
    for key in ("server", "database", "url", "path", "account", "domain", "emailAddress"):
        value = connection_details.get(key)
        if value:
            parts.append(str(value))
    if parts:
        return " | ".join(parts)

    return ", ".join(
        f"{key}={value}"
        for key, value in connection_details.items()
        if value is not None
    ) or None


def build_workspace_record(raw_workspace: Dict[str, Any]) -> Dict[str, Any]:
    is_dedicated = bool(raw_workspace.get("isOnDedicatedCapacity"))
    return {
        **raw_workspace,
        "workspaceId": raw_workspace.get("id"),
        "workspaceName": raw_workspace.get("name"),
        "workspaceType": raw_workspace.get("type") or "Workspace",
        "capacityId": raw_workspace.get("capacityId"),
        "capacityMode": "Dedicated" if is_dedicated else "Shared",
        "defaultDatasetStorageFormat": raw_workspace.get("defaultDatasetStorageFormat"),
    }


def build_datasource_record(raw_datasource: Dict[str, Any]) -> Dict[str, Any]:
    return {
        **raw_datasource,
        "sourceSummary": _connection_summary(raw_datasource.get("connectionDetails")),
    }


def build_dataset_record(
    raw_dataset: Dict[str, Any],
    workspace: Dict[str, Any],
    datasources: List[Dict[str, Any]],
) -> Dict[str, Any]:
    data_source_types = sorted(
        {item["datasourceType"] for item in datasources if item.get("datasourceType")}
    )
    gateway_ids = sorted({item["gatewayId"] for item in datasources if item.get("gatewayId")})
    source_summaries = [item["sourceSummary"] for item in datasources if item.get("sourceSummary")]

    return {
        **raw_dataset,
        "datasetId": raw_dataset.get("id"),
        "datasetName": raw_dataset.get("name"),
        "workspaceId": workspace.get("workspaceId"),
        "workspaceName": workspace.get("workspaceName"),
        "configuredBy": raw_dataset.get("configuredBy"),
        "owner": raw_dataset.get("configuredBy"),
        "capacityId": workspace.get("capacityId"),
        "capacityMode": workspace.get("capacityMode"),
        "gatewayRequired": raw_dataset.get("isOnPremGatewayRequired"),
        "gatewayIds": gateway_ids,
        "primaryGatewayId": gateway_ids[0] if gateway_ids else None,
        "dataSources": datasources,
        "dataSourceTypes": data_source_types,
        "dataSourceSummary": source_summaries,
    }


def _extract_non_negative_int(value: Any) -> Optional[int]:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        if value < 0:
            return None
        return int(value)
    text = str(value).strip()
    if not text:
        return None
    try:
        parsed = float(text.replace(",", "."))
    except ValueError:
        return None
    if parsed < 0:
        return None
    return int(parsed)


def _extract_report_view_count(raw_report: Dict[str, Any]) -> int:
    candidate_paths = [
        ("viewCount",),
        ("views",),
        ("viewsCount",),
        ("reportViewCount",),
        ("usageCount",),
        ("nombreVues",),
        ("nombreDeVues",),
        ("nbVues",),
        ("usageMetrics", "viewCount"),
        ("usageMetrics", "views"),
        ("metrics", "viewCount"),
        ("metrics", "views"),
        ("stats", "viewCount"),
        ("stats", "views"),
    ]

    for path in candidate_paths:
        current: Any = raw_report
        for key in path:
            if not isinstance(current, dict):
                current = None
                break
            current = current.get(key)
        parsed = _extract_non_negative_int(current)
        if parsed is not None:
            return parsed

    return 0


def build_report_record(
    raw_report: Dict[str, Any],
    workspace: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        **raw_report,
        "reportId": raw_report.get("id"),
        "reportName": raw_report.get("name"),
        "workspaceId": workspace.get("workspaceId"),
        "workspaceName": workspace.get("workspaceName"),
        "datasetId": raw_report.get("datasetId"),
        "viewCount": _extract_report_view_count(raw_report),
    }


def build_refresh_record(
    raw_refresh: Dict[str, Any],
    workspace: Dict[str, Any],
    dataset: Dict[str, Any],
) -> Dict[str, Any]:
    start_time = parse_datetime(raw_refresh.get("startTime"))
    end_time = parse_datetime(raw_refresh.get("endTime"))

    duration_seconds: Optional[float] = None
    if start_time and end_time:
        duration_seconds = max((end_time - start_time).total_seconds(), 0.0)
    elif start_time and raw_refresh.get("status") not in {"Completed", "Failed"}:
        duration_seconds = max((_now_utc() - start_time).total_seconds(), 0.0)

    error_code, error_message = _extract_error_details(raw_refresh.get("serviceExceptionJson"))
    if not error_code and not error_message:
        for attempt in raw_refresh.get("refreshAttempts", []):
            error_code, error_message = _extract_error_details(
                attempt.get("serviceExceptionJson")
            )
            if error_code or error_message:
                break

    refresh_id = raw_refresh.get("requestId") or (
        f"{dataset.get('datasetId')}:{raw_refresh.get('startTime')}"
    )
    is_delayed = bool(
        duration_seconds is not None
        and duration_seconds >= DEFAULT_DELAY_THRESHOLD_SECONDS
    )

    return {
        **raw_refresh,
        "refreshId": refresh_id,
        "requestId": raw_refresh.get("requestId"),
        "workspaceId": workspace.get("workspaceId"),
        "workspaceName": workspace.get("workspaceName"),
        "datasetId": dataset.get("datasetId"),
        "datasetName": dataset.get("datasetName"),
        "capacityId": dataset.get("capacityId"),
        "gatewayIds": dataset.get("gatewayIds", []),
        "dataSourceTypes": dataset.get("dataSourceTypes", []),
        "durationSeconds": _round(duration_seconds),
        "durationMinutes": _round(
            None if duration_seconds is None else duration_seconds / 60.0
        ),
        "errorCode": error_code,
        "errorMessage": error_message,
        "refreshAttemptCount": len(raw_refresh.get("refreshAttempts", [])),
        "isDelayed": is_delayed,
    }


def build_fabric_item_record(
    raw_item: Dict[str, Any],
    workspace: Dict[str, Any],
    item_type: str,
) -> Dict[str, Any]:
    properties = raw_item.get("properties") or {}
    sql_properties = properties.get("sqlEndpointProperties") or {}
    display_name = raw_item.get("displayName") or raw_item.get("name")

    return {
        **raw_item,
        "itemId": raw_item.get("id"),
        "itemName": display_name,
        "itemType": raw_item.get("type") or item_type,
        "workspaceId": workspace.get("workspaceId"),
        "workspaceName": workspace.get("workspaceName"),
        "description": raw_item.get("description"),
        "connectionString": properties.get("connectionString")
        or sql_properties.get("connectionString"),
        "sqlEndpointId": sql_properties.get("id"),
        "sqlProvisioningStatus": sql_properties.get("provisioningStatus"),
        "createdAt": properties.get("createdDate"),
        "updatedAt": properties.get("lastUpdatedTime"),
        "oneLakeTablesPath": properties.get("oneLakeTablesPath"),
        "oneLakeFilesPath": properties.get("oneLakeFilesPath"),
        "collationType": properties.get("collationType"),
        "isSqlEnabled": bool(
            properties.get("connectionString")
            or sql_properties.get("connectionString")
        ),
    }


def _extract_failure_reason(raw_failure: Any) -> Optional[str]:
    if raw_failure is None:
        return None
    if isinstance(raw_failure, str):
        return raw_failure.strip() or None
    if not isinstance(raw_failure, dict):
        return str(raw_failure)
    for key in ("message", "errorCode", "error", "code"):
        value = raw_failure.get(key)
        if value:
            return str(value)
    return json.dumps(raw_failure, ensure_ascii=False)


def build_fabric_execution_record(
    raw_execution: Dict[str, Any],
    fabric_item: Dict[str, Any],
) -> Dict[str, Any]:
    start_time = parse_datetime(raw_execution.get("startTimeUtc"))
    end_time = parse_datetime(raw_execution.get("endTimeUtc"))

    duration_seconds: Optional[float] = None
    if start_time and end_time:
        duration_seconds = max((end_time - start_time).total_seconds(), 0.0)
    elif start_time and raw_execution.get("status") not in {"Completed", "Failed", "Cancelled"}:
        duration_seconds = max((_now_utc() - start_time).total_seconds(), 0.0)

    execution_id = raw_execution.get("id") or (
        f"{fabric_item.get('itemId')}:{raw_execution.get('startTimeUtc')}"
    )

    return {
        **raw_execution,
        "executionId": execution_id,
        "workspaceId": fabric_item.get("workspaceId"),
        "workspaceName": fabric_item.get("workspaceName"),
        "itemId": fabric_item.get("itemId"),
        "itemName": fabric_item.get("itemName"),
        "itemType": fabric_item.get("itemType"),
        "durationSeconds": _round(duration_seconds),
        "durationMinutes": _round(
            None if duration_seconds is None else duration_seconds / 60.0
        ),
        "failureReasonText": _extract_failure_reason(raw_execution.get("failureReason")),
    }


def _normalize_identifier(value: Any, fallback: str) -> str:
    text = str(value or "").strip()
    return text or fallback


def _extract_procedure_name(command: str) -> Optional[str]:
    if not command:
        return None
    match = re.search(
        r"\bexec(?:ute)?\s+(?:@?\w+\s*=\s*)?(?:\[?([\w]+)\]?\.)?\[?([\w]+)\]?",
        command,
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    schema_name = match.group(1)
    procedure_name = match.group(2)
    if schema_name:
        return f"{schema_name}.{procedure_name}"
    return procedure_name


def build_fabric_sql_execution_record(
    raw_query: Dict[str, Any],
    fabric_item: Dict[str, Any],
) -> Dict[str, Any]:
    duration_seconds = _round(
        None
        if raw_query.get("total_elapsed_time_ms") is None
        else float(raw_query.get("total_elapsed_time_ms")) / 1000.0
    )
    command = str(raw_query.get("command") or "")
    statement_type = str(raw_query.get("statement_type") or "")
    procedure_name = _extract_procedure_name(command)
    is_stored_procedure = bool(
        procedure_name
        or statement_type.strip().lower() in {"exec", "execute"}
    )

    return {
        **raw_query,
        "queryId": _normalize_identifier(
            raw_query.get("distributed_statement_id"),
            f"{fabric_item.get('itemId')}:{raw_query.get('start_time')}",
        ),
        "workspaceId": fabric_item.get("workspaceId"),
        "workspaceName": fabric_item.get("workspaceName"),
        "itemId": fabric_item.get("itemId"),
        "itemName": fabric_item.get("itemName"),
        "itemType": fabric_item.get("itemType"),
        "startTime": raw_query.get("start_time"),
        "endTime": raw_query.get("end_time"),
        "startTimeUtc": raw_query.get("start_time"),
        "endTimeUtc": raw_query.get("end_time"),
        "durationSeconds": duration_seconds,
        "durationMinutes": _round(
            None if duration_seconds is None else duration_seconds / 60.0
        ),
        "statementType": statement_type or None,
        "status": raw_query.get("status"),
        "command": command or None,
        "loginName": raw_query.get("login_name"),
        "errorCode": raw_query.get("error_code"),
        "procedureName": procedure_name,
        "isStoredProcedure": is_stored_procedure,
        "submittedAt": raw_query.get("submit_time"),
        "databaseName": raw_query.get("database_name"),
        "totalElapsedMs": raw_query.get("total_elapsed_time_ms"),
    }


def _incident_signature(incident_type: str, refresh: Dict[str, Any]) -> str:
    return (
        f"{incident_type}:"
        f"{refresh.get('workspaceId')}:"
        f"{refresh.get('datasetId')}:"
        f"{refresh.get('refreshId')}"
    )


def _classify_timing_issue(refresh: Dict[str, Any]) -> Tuple[str, str, str]:
    if refresh.get("refreshType") == "Scheduled":
        return (
            "Planification",
            "Moyenne",
            "Vérifier la fréquence des refreshs, les chevauchements et la file d'attente.",
        )
    return (
        "Source de données",
        "Moyenne",
        "Analyser la latence de la source, de la gateway et des étapes de transformation.",
    )


def _classify_refresh_issue(refresh: Dict[str, Any]) -> Tuple[str, str, str]:
    error_code = (refresh.get("errorCode") or "").lower()
    error_message = (refresh.get("errorMessage") or "").lower()
    haystack = f"{error_code} {error_message}"

    if "credential" in haystack or "login" in haystack or "auth" in haystack:
        return (
            "Credentials",
            "Haute",
            "Mettre a jour les credentials du dataset ou de la gateway dans Power BI.",
        )
    if "gateway" in haystack:
        return (
            "Gateway",
            "Haute",
            "Verifier la disponibilite de la gateway, les mappings et l'acces reseau.",
        )
    if "capacity" in haystack or "memory" in haystack or "resource" in haystack:
        return (
            "Capacite",
            "Haute",
            "Analyser la saturation, le throttling et la concurrence sur la capacite.",
        )
    if "mashup" in haystack or "power query" in haystack or "folding" in haystack:
        return (
            "Power Query",
            "Moyenne",
            "Revoir le query folding, les transformations couteuses et les filtres tardifs.",
        )
    if "model" in haystack or "semantic" in haystack or "schema" in haystack or "cardinality" in haystack:
        return (
            "Modele semantique",
            "Haute",
            "Verifier le modele, les relations, la cardinalite et les changements de schema.",
        )
    if (
        "schedule" in haystack
        or "queued" in haystack
        or "concurr" in haystack
        or "slot" in haystack
        or "not executed" in haystack
    ):
        return (
            "Planification",
            "Moyenne",
            "Etaler les refreshs et verifier les conflits de planification.",
        )
    if "timeout" in haystack or "slow" in haystack:
        return (
            "Source de donnees",
            "Moyenne",
            "Verifier la disponibilite de la source, le reseau et les temps de reponse.",
        )
    if refresh.get("dataSourceTypes"):
        return (
            "Source de donnees",
            "Haute",
            "Inspecter la disponibilite de la source, la connectivite et la requete amont.",
        )
    return (
        "Modele semantique",
        "Haute",
        "Verifier le modele semantique et relancer le refresh apres correction.",
    )


def derive_incidents(refreshes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    incidents: List[Dict[str, Any]] = []
    durations_by_dataset: Dict[str, List[float]] = defaultdict(list)
    refreshes_by_dataset: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

    for refresh in refreshes:
        duration = refresh.get("durationSeconds")
        if duration is not None and refresh.get("status") == "Completed":
            durations_by_dataset[refresh["datasetId"]].append(float(duration))
        refreshes_by_dataset[refresh["datasetId"]].append(refresh)

    dataset_average_duration = {
        dataset_id: mean(durations)
        for dataset_id, durations in durations_by_dataset.items()
        if durations
    }
    latest_consecutive_failures: Dict[str, Dict[str, Any]] = {}

    for dataset_id, dataset_refreshes in refreshes_by_dataset.items():
        sorted_refreshes = sorted(
            dataset_refreshes,
            key=lambda item: item.get("startTime") or "",
            reverse=True,
        )
        streak = []
        for refresh in sorted_refreshes:
            if refresh.get("status") == "Failed":
                streak.append(refresh)
                continue
            break
        if len(streak) >= 2:
            latest_consecutive_failures[dataset_id] = streak[0]

    for refresh in refreshes:
        detected_at = refresh.get("endTime") or refresh.get("startTime")
        base_incident = {
            "workspaceId": refresh.get("workspaceId"),
            "workspaceName": refresh.get("workspaceName"),
            "datasetId": refresh.get("datasetId"),
            "datasetName": refresh.get("datasetName"),
            "refreshId": refresh.get("refreshId"),
            "detectedAt": detected_at,
            "gatewayIds": refresh.get("gatewayIds", []),
            "dataSourceTypes": refresh.get("dataSourceTypes", []),
            "capacityId": refresh.get("capacityId"),
            "status": refresh.get("status"),
        }

        if refresh.get("status") == "Failed":
            suspected_cause, severity, recommendation = _classify_refresh_issue(refresh)
            incidents.append(
                {
                    **base_incident,
                    "incidentId": _incident_signature("FailedRefresh", refresh),
                    "incidentType": "FailedRefresh",
                    "severity": severity,
                    "suspectedCause": suspected_cause,
                    "recommendation": recommendation,
                    "errorCode": refresh.get("errorCode"),
                    "errorMessage": refresh.get("errorMessage"),
                }
            )

        if refresh.get("isDelayed"):
            suspected_cause, severity, recommendation = _classify_timing_issue(refresh)
            incidents.append(
                {
                    **base_incident,
                    "incidentId": _incident_signature("DelayedRefresh", refresh),
                    "incidentType": "DelayedRefresh",
                    "severity": severity,
                    "suspectedCause": suspected_cause,
                    "recommendation": recommendation,
                    "errorCode": refresh.get("errorCode"),
                    "errorMessage": refresh.get("errorMessage"),
                }
            )

        average_duration = dataset_average_duration.get(refresh.get("datasetId"))
        duration_seconds = refresh.get("durationSeconds")
        is_anomalous = bool(
            average_duration
            and duration_seconds
            and duration_seconds >= MINIMUM_ANOMALY_DURATION_SECONDS
            and duration_seconds > average_duration * DEFAULT_DURATION_ANOMALY_FACTOR
        )
        if is_anomalous:
            incidents.append(
                {
                    **base_incident,
                    "incidentId": _incident_signature("DurationAnomaly", refresh),
                    "incidentType": "DurationAnomaly",
                    "severity": "Moyenne",
                    "suspectedCause": "Power Query",
                    "recommendation": (
                        "Comparer cette duree aux executions precedentes et optimiser les transformations."
                    ),
                    "errorCode": refresh.get("errorCode"),
                    "errorMessage": refresh.get("errorMessage"),
                }
            )

        if (
            refresh.get("refreshType") == "Scheduled"
            and refresh.get("status") not in {"Completed", "Failed"}
            and not refresh.get("endTime")
        ):
            incidents.append(
                {
                    **base_incident,
                    "incidentId": _incident_signature("RefreshNotExecuted", refresh),
                    "incidentType": "RefreshNotExecuted",
                    "severity": "Moyenne",
                    "suspectedCause": "Planification",
                    "recommendation": (
                        "Verifier si le refresh planifie a ete bloque dans la file d'attente ou annule."
                    ),
                    "errorCode": refresh.get("errorCode"),
                    "errorMessage": refresh.get("errorMessage"),
                }
            )

        consecutive_failure_refresh = latest_consecutive_failures.get(refresh.get("datasetId"))
        if consecutive_failure_refresh and consecutive_failure_refresh.get("refreshId") == refresh.get("refreshId"):
            suspected_cause, severity, recommendation = _classify_refresh_issue(refresh)
            incidents.append(
                {
                    **base_incident,
                    "incidentId": _incident_signature("ConsecutiveFailures", refresh),
                    "incidentType": "ConsecutiveFailures",
                    "severity": severity,
                    "suspectedCause": suspected_cause,
                    "recommendation": (
                        f"{recommendation} Plusieurs echecs consecutifs exigent une analyse prioritaire."
                    ),
                    "errorCode": refresh.get("errorCode"),
                    "errorMessage": refresh.get("errorMessage"),
                }
            )

    return incidents


def _group_refreshes_by_day(refreshes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    daily_groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for refresh in refreshes:
        start_time = parse_datetime(refresh.get("startTime"))
        if start_time is None:
            continue
        daily_groups[start_time.date().isoformat()].append(refresh)

    daily_performance = []
    for day_key in sorted(daily_groups):
        items = daily_groups[day_key]
        durations = [
            float(item["durationSeconds"])
            for item in items
            if item.get("durationSeconds") is not None
        ]
        daily_performance.append(
            {
                "date": day_key,
                "totalRefreshes": len(items),
                "failedRefreshes": sum(1 for item in items if item.get("status") == "Failed"),
                "delayedRefreshes": sum(1 for item in items if item.get("isDelayed")),
                "averageDurationSeconds": _round(mean(durations) if durations else 0.0),
                "maximumDurationSeconds": _round(max(durations) if durations else 0.0),
            }
        )

    return daily_performance


def _build_refresh_timeline(
    refreshes: List[Dict[str, Any]],
    limit: Optional[int] = None,
) -> List[Dict[str, Any]]:
    timeline = [
        {
            "timestamp": item.get("startTime"),
            "datasetId": item.get("datasetId"),
            "datasetName": item.get("datasetName"),
            "status": item.get("status"),
            "isDelayed": bool(item.get("isDelayed")),
            "durationSeconds": item.get("durationSeconds"),
        }
        for item in refreshes
        if item.get("startTime") and item.get("durationSeconds") is not None
    ]
    timeline.sort(key=lambda item: item["timestamp"] or "")
    if limit is None:
        return timeline
    return timeline[-limit:]


def _build_fabric_execution_timeline(
    executions: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    timeline = [
        {
            "timestamp": item.get("startTimeUtc") or item.get("startTime"),
            "itemId": item.get("itemId"),
            "itemName": item.get("itemName"),
            "itemType": item.get("itemType"),
            "status": item.get("status"),
            "durationSeconds": item.get("durationSeconds"),
        }
        for item in executions
        if (item.get("startTimeUtc") or item.get("startTime"))
        and item.get("durationSeconds") is not None
    ]
    timeline.sort(key=lambda item: item["timestamp"] or "")
    return timeline


def _summarize_fabric_monitoring(
    fabric_items: List[Dict[str, Any]],
    fabric_executions: List[Dict[str, Any]],
    fabric_sql_executions: List[Dict[str, Any]],
) -> Dict[str, Any]:
    item_type_counter = Counter(item.get("itemType") for item in fabric_items if item.get("itemType"))
    execution_durations = [
        float(item["durationSeconds"])
        for item in fabric_executions
        if item.get("durationSeconds") is not None
    ]
    execution_durations_by_item: Dict[Tuple[str, str, str], List[float]] = defaultdict(list)
    execution_failures_by_item: Counter = Counter()

    for execution in fabric_executions:
        key = (
            execution.get("itemId"),
            execution.get("itemName") or execution.get("itemId"),
            execution.get("itemType") or "FabricItem",
        )
        duration = execution.get("durationSeconds")
        if duration is not None:
            execution_durations_by_item[key].append(float(duration))
        if str(execution.get("status") or "").lower() == "failed":
            execution_failures_by_item[key] += 1

    slowest_items = [
        {
            "itemId": item_id,
            "itemName": item_name,
            "itemType": item_type,
            "averageDurationSeconds": _round(mean(durations)),
            "maximumDurationSeconds": _round(max(durations)),
            "executionCount": len(durations),
        }
        for (item_id, item_name, item_type), durations in execution_durations_by_item.items()
        if durations
    ]
    slowest_items.sort(
        key=lambda item: item.get("averageDurationSeconds") or 0.0,
        reverse=True,
    )

    items_with_failures = [
        {
            "itemId": item_id,
            "itemName": item_name,
            "itemType": item_type,
            "failureCount": failure_count,
        }
        for (item_id, item_name, item_type), failure_count in execution_failures_by_item.items()
    ]
    items_with_failures.sort(key=lambda item: item["failureCount"], reverse=True)

    stored_procedure_executions = [
        item for item in fabric_sql_executions if item.get("isStoredProcedure")
    ]
    procedure_groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for execution in stored_procedure_executions:
        procedure_name = execution.get("procedureName") or execution.get("command") or "Procedure"
        procedure_groups[procedure_name].append(execution)

    slowest_procedures = []
    for procedure_name, procedure_items in procedure_groups.items():
        durations = [
            float(item["durationSeconds"])
            for item in procedure_items
            if item.get("durationSeconds") is not None
        ]
        if not durations:
            continue
        slowest_procedures.append(
            {
                "procedureName": procedure_name,
                "averageDurationSeconds": _round(mean(durations)),
                "maximumDurationSeconds": _round(max(durations)),
                "executionCount": len(procedure_items),
                "latestItemName": (
                    sorted(
                        procedure_items,
                        key=lambda item: item.get("startTime") or "",
                        reverse=True,
                    )[0].get("itemName")
                ),
            }
        )
    slowest_procedures.sort(
        key=lambda item: item.get("averageDurationSeconds") or 0.0,
        reverse=True,
    )

    return {
        "inventory": {
            "totalItems": len(fabric_items),
            "warehouseCount": item_type_counter.get("Warehouse", 0),
            "lakehouseCount": item_type_counter.get("Lakehouse", 0),
            "sqlEnabledItems": sum(1 for item in fabric_items if item.get("isSqlEnabled")),
        },
        "executions": {
            "total": len(fabric_executions),
            "completed": sum(
                1
                for item in fabric_executions
                if str(item.get("status") or "").lower() == "completed"
            ),
            "failed": sum(
                1
                for item in fabric_executions
                if str(item.get("status") or "").lower() == "failed"
            ),
            "inProgress": sum(
                1
                for item in fabric_executions
                if str(item.get("status") or "").lower() not in {"completed", "failed", "cancelled"}
            ),
            "averageDurationSeconds": _round(
                mean(execution_durations) if execution_durations else 0.0
            ),
            "maximumDurationSeconds": _round(
                max(execution_durations) if execution_durations else 0.0
            ),
            "slowestItems": slowest_items[:5],
            "mostFailures": items_with_failures[:5],
        },
        "procedures": {
            "sqlExecutionCount": len(fabric_sql_executions),
            "storedProcedureExecutionCount": len(stored_procedure_executions),
            "slowestStoredProcedures": slowest_procedures[:5],
        },
    }


def summarize_monitoring(
    refreshes: List[Dict[str, Any]],
    incidents: List[Dict[str, Any]],
    datasets: Optional[List[Dict[str, Any]]] = None,
    fabric_items: Optional[List[Dict[str, Any]]] = None,
    fabric_executions: Optional[List[Dict[str, Any]]] = None,
    fabric_sql_executions: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    datasets = datasets or []
    fabric_items = fabric_items or []
    fabric_executions = fabric_executions or []
    fabric_sql_executions = fabric_sql_executions or []
    total_refreshes = len(refreshes)
    successful_refreshes = [item for item in refreshes if item.get("status") == "Completed"]
    failed_refreshes = [item for item in refreshes if item.get("status") == "Failed"]
    in_progress_refreshes = [
        item
        for item in refreshes
        if item.get("status") not in {"Completed", "Failed"}
    ]
    durations = [
        float(item["durationSeconds"])
        for item in refreshes
        if item.get("durationSeconds") is not None
    ]

    duration_by_dataset: Dict[Tuple[str, str], List[float]] = defaultdict(list)
    failure_count_by_dataset: Counter = Counter()
    for refresh in refreshes:
        key = (refresh.get("datasetId"), refresh.get("datasetName") or refresh.get("datasetId"))
        duration = refresh.get("durationSeconds")
        if duration is not None:
            duration_by_dataset[key].append(float(duration))
        if refresh.get("status") == "Failed":
            failure_count_by_dataset[key] += 1

    slowest_datasets = [
        {
            "datasetId": dataset_id,
            "datasetName": dataset_name,
            "averageDurationSeconds": _round(mean(dataset_durations)),
            "maxDurationSeconds": _round(max(dataset_durations)),
            "refreshCount": len(dataset_durations),
        }
        for (dataset_id, dataset_name), dataset_durations in duration_by_dataset.items()
    ]
    slowest_datasets.sort(
        key=lambda item: item["averageDurationSeconds"] or 0.0,
        reverse=True,
    )

    datasets_with_failures = [
        {
            "datasetId": dataset_id,
            "datasetName": dataset_name,
            "failureCount": failure_count,
        }
        for (dataset_id, dataset_name), failure_count in failure_count_by_dataset.items()
    ]
    datasets_with_failures.sort(key=lambda item: item["failureCount"], reverse=True)

    incident_cause_counter = Counter(
        incident.get("suspectedCause")
        for incident in incidents
        if incident.get("suspectedCause")
    )
    gateway_counter: Counter = Counter()
    capacity_counter: Counter = Counter()
    datasource_counter: Counter = Counter()

    for incident in incidents:
        for gateway_id in incident.get("gatewayIds", []):
            gateway_counter[gateway_id] += 1
        if incident.get("capacityId"):
            capacity_counter[incident["capacityId"]] += 1
        for datasource_type in incident.get("dataSourceTypes", []):
            datasource_counter[datasource_type] += 1

    fabric_summary = _summarize_fabric_monitoring(
        fabric_items,
        fabric_executions,
        fabric_sql_executions,
    )

    return {
        "totals": {
            "refreshes": total_refreshes,
            "successfulRefreshes": len(successful_refreshes),
            "failedRefreshes": len(failed_refreshes),
            "inProgressRefreshes": len(in_progress_refreshes),
            "incidents": len(incidents),
            "delayedRefreshes": sum(1 for item in refreshes if item.get("isDelayed")),
            "durationAnomalies": sum(
                1
                for item in incidents
                if item.get("incidentType") == "DurationAnomaly"
            ),
        },
        "rates": {
            "successRate": _round(
                0.0 if total_refreshes == 0 else len(successful_refreshes) / total_refreshes
            ),
            "failureRate": _round(
                0.0 if total_refreshes == 0 else len(failed_refreshes) / total_refreshes
            ),
        },
        "durations": {
            "averageSeconds": _round(mean(durations) if durations else 0.0),
            "maximumSeconds": _round(max(durations) if durations else 0.0),
        },
        "datasets": {
            "slowest": slowest_datasets[:5],
            "mostFailures": datasets_with_failures[:5],
        },
        "incidents": {
            "byCauseType": [
                {"causeType": cause_type, "count": count}
                for cause_type, count in incident_cause_counter.most_common()
            ],
            "byGateway": [
                {"gatewayId": gateway_id, "count": count}
                for gateway_id, count in gateway_counter.most_common()
            ],
            "byCapacity": [
                {"capacityId": capacity_id, "count": count}
                for capacity_id, count in capacity_counter.most_common()
            ],
            "credentialsRelated": sum(
                1
                for item in incidents
                if item.get("suspectedCause") == "Credentials"
            ),
            "byDataSource": [
                {"datasourceType": datasource_type, "count": count}
                for datasource_type, count in datasource_counter.most_common()
            ],
        },
        "fabric": fabric_summary,
        "thresholds": {
            "delayedRefreshSeconds": DEFAULT_DELAY_THRESHOLD_SECONDS,
            "durationAnomalyFactor": DEFAULT_DURATION_ANOMALY_FACTOR,
        },
        "trends": {
            "refreshTimeline": _build_refresh_timeline(refreshes),
            "dailyRefreshPerformance": _group_refreshes_by_day(refreshes),
            "fabricExecutionTimeline": _build_fabric_execution_timeline(
                fabric_executions
            ),
        },
    }
