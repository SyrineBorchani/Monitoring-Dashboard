from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import importlib
import json
import logging
from datetime import date, datetime, time
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List
from uuid import UUID

from App.config import Settings, get_settings


logger = logging.getLogger(__name__)

QUERY_INSIGHTS_SQL = """
SELECT TOP ({top})
    distributed_statement_id,
    database_name,
    submit_time,
    start_time,
    end_time,
    statement_type,
    total_elapsed_time_ms,
    program_name,
    status,
    login_name,
    command,
    error_code
FROM queryinsights.exec_requests_history
ORDER BY end_time DESC, start_time DESC;
""".strip()


@dataclass(frozen=True)
class FabricSQLCollector:
    settings: Settings

    def collect_item_queries(
        self,
        fabric_items: List[Dict[str, Any]],
    ) -> Dict[str, List[Dict[str, Any]]]:
        if not self.settings.fabric_sql_monitoring_enabled:
            return {}

        source = self._source_mode()
        if source in {"auto", "live"}:
            live_queries, had_live_errors = self._collect_item_queries_live(fabric_items)
            if source == "live":
                return live_queries
            if live_queries or not had_live_errors:
                return live_queries
            logger.warning(
                "Falling back to Fabric notebook export because live SQL collection failed."
            )

        if source not in {"auto", "export", "notebook_export"}:
            logger.warning(
                "Unknown FABRIC_SQL_SOURCE=%s. Supported values are auto, live, and export.",
                self.settings.fabric_sql_source,
            )
            return {}

        return self._collect_item_queries_from_export(fabric_items)

    def _collect_item_queries_from_export(
        self,
        fabric_items: List[Dict[str, Any]],
    ) -> Dict[str, List[Dict[str, Any]]]:
        export_path = self.settings.fabric_sql_notebook_export_path
        if not export_path:
            logger.warning(
                "Skipping Fabric SQL monitoring because FABRIC_SQL_NOTEBOOK_EXPORT_PATH is not configured."
            )
            return {}

        path = Path(export_path)
        if not path.exists():
            logger.warning(
                "Skipping Fabric SQL monitoring because notebook export file was not found: %s",
                path,
            )
            return {}

        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            logger.warning(
                "Skipping Fabric SQL monitoring because notebook export file could not be read: %s",
                error,
            )
            return {}

        return self.collect_item_queries_from_payload(fabric_items, payload)

    def _source_mode(self) -> str:
        source = str(self.settings.fabric_sql_source or "auto").strip().lower()
        if source == "notebook":
            return "export"
        return source or "auto"

    def _collect_item_queries_live(
        self,
        fabric_items: List[Dict[str, Any]],
    ) -> tuple[Dict[str, List[Dict[str, Any]]], bool]:
        pyodbc = self._load_pyodbc_module()
        if pyodbc is None:
            logger.warning(
                "Skipping live Fabric SQL monitoring because pyodbc is not installed."
            )
            return {}, True

        queries_by_item: Dict[str, List[Dict[str, Any]]] = {}
        had_errors = False
        top = max(1, int(self.settings.fabric_sql_top))
        sql = QUERY_INSIGHTS_SQL.format(top=top)

        for fabric_item in fabric_items:
            if not self._is_sql_item_eligible(fabric_item):
                continue

            connection_string = self._build_odbc_connection_string(fabric_item)
            if not connection_string:
                had_errors = True
                logger.warning(
                    "Skipping live Fabric SQL monitoring for item %s because its SQL connection metadata is incomplete.",
                    fabric_item.get("itemId"),
                )
                continue

            try:
                rows = self._query_item_rows(pyodbc, connection_string, sql)
            except Exception as error:
                had_errors = True
                logger.warning(
                    "Live Fabric SQL monitoring failed for item %s (%s): %s",
                    fabric_item.get("itemName") or fabric_item.get("itemId"),
                    fabric_item.get("itemId"),
                    error,
                )
                continue

            queries_by_item[str(fabric_item["itemId"])] = rows

        return queries_by_item, had_errors

    def _load_pyodbc_module(self) -> Any | None:
        try:
            return importlib.import_module("pyodbc")
        except ImportError:
            return None

    def _is_sql_item_eligible(self, fabric_item: Dict[str, Any]) -> bool:
        if not fabric_item.get("itemId"):
            return False
        if not fabric_item.get("isSqlEnabled"):
            return False
        provisioning_status = str(fabric_item.get("sqlProvisioningStatus") or "").strip()
        if provisioning_status and provisioning_status.lower() != "success":
            logger.info(
                "Skipping Fabric SQL monitoring for item %s because SQL provisioning status is %s.",
                fabric_item.get("itemId"),
                provisioning_status,
            )
            return False
        return True

    def _build_odbc_connection_string(self, fabric_item: Dict[str, Any]) -> str | None:
        server = str(fabric_item.get("connectionString") or "").strip()
        database = str(fabric_item.get("itemName") or "").strip()
        if not server or not database:
            return None

        return ";".join(
            [
                f"DRIVER={{{self.settings.fabric_sql_odbc_driver}}}",
                f"SERVER={server}",
                f"DATABASE={database}",
                f"UID={self.settings.client_id}",
                f"PWD={self.settings.client_secret}",
                "Authentication=ActiveDirectoryServicePrincipal",
                "Encrypt=Yes",
                "TrustServerCertificate=No",
            ]
        )

    def _query_item_rows(
        self,
        pyodbc: Any,
        connection_string: str,
        sql: str,
    ) -> List[Dict[str, Any]]:
        connection = pyodbc.connect(
            connection_string,
            timeout=max(1, int(self.settings.fabric_sql_connect_timeout)),
        )
        try:
            cursor = connection.cursor()
            try:
                cursor.timeout = max(1, int(self.settings.fabric_sql_command_timeout))
            except Exception:
                logger.debug("ODBC cursor timeout is not supported by the current driver.")
            cursor.execute(sql)
            columns = [str(item[0]) for item in cursor.description or []]
            rows = cursor.fetchall()
            return [
                {
                    column: self._normalize_sql_value(value)
                    for column, value in zip(columns, row)
                }
                for row in rows
            ]
        finally:
            connection.close()

    def _normalize_sql_value(self, value: Any) -> Any:
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, date):
            return datetime.combine(value, time.min).isoformat()
        if isinstance(value, Decimal):
            return float(value)
        if isinstance(value, UUID):
            return str(value)
        return value

    def collect_item_queries_from_payload(
        self,
        fabric_items: List[Dict[str, Any]],
        payload: Any,
    ) -> Dict[str, List[Dict[str, Any]]]:
        normalized_rows = self._normalize_export_rows(payload)
        if not normalized_rows:
            return {}

        item_lookup = {
            str(item.get("itemId")): item
            for item in fabric_items
            if item.get("itemId")
        }
        name_lookup = {}
        for item in fabric_items:
            item_name = str(item.get("itemName") or "").strip().casefold()
            if item_name:
                name_lookup[item_name] = item

        queries_by_item: Dict[str, List[Dict[str, Any]]] = {}
        for row in normalized_rows:
            if not isinstance(row, dict):
                continue
            fabric_item = self._resolve_item(row, item_lookup, name_lookup)
            if fabric_item is None:
                continue

            item_id = str(fabric_item["itemId"])
            queries_by_item.setdefault(item_id, []).append(dict(row))

        return queries_by_item

    def _normalize_export_rows(self, payload: Any) -> List[Dict[str, Any]]:
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]

        if not isinstance(payload, dict):
            return []

        for key in ("value", "rows", "queries", "executions"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]

        items = payload.get("items")
        if not isinstance(items, list):
            return []

        rows: List[Dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            item_rows = None
            for key in ("rows", "queries", "executions", "value"):
                candidate = item.get(key)
                if isinstance(candidate, list):
                    item_rows = candidate
                    break
            if not item_rows:
                continue
            for row in item_rows:
                if not isinstance(row, dict):
                    continue
                enriched = dict(row)
                for field in ("itemId", "itemName", "workspaceId", "itemType"):
                    if item.get(field) is not None and enriched.get(field) is None:
                        enriched[field] = item.get(field)
                rows.append(enriched)
        return rows

    def _resolve_item(
        self,
        row: Dict[str, Any],
        item_lookup: Dict[str, Dict[str, Any]],
        name_lookup: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Any] | None:
        for key in ("itemId", "warehouseId", "lakehouseId", "artifactId"):
            value = row.get(key)
            if value is None:
                continue
            item = item_lookup.get(str(value))
            if item is not None:
                return item

        for key in ("itemName", "database_name", "databaseName"):
            value = str(row.get(key) or "").strip().casefold()
            if not value:
                continue
            item = name_lookup.get(value)
            if item is not None:
                return item

        return None


@lru_cache(maxsize=1)
def get_fabric_sql_collector() -> FabricSQLCollector:
    return FabricSQLCollector(get_settings())
