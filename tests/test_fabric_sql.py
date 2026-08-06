from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from App.fabric_sql import FabricSQLCollector


def test_collect_item_queries_from_payload_matches_rows_by_item_id() -> None:
    collector = FabricSQLCollector(
        SimpleNamespace(
            fabric_sql_monitoring_enabled=True,
            fabric_sql_source="export",
            fabric_sql_notebook_export_path="",
            fabric_sql_odbc_driver="ODBC Driver 18 for SQL Server",
            fabric_sql_connect_timeout=15,
            fabric_sql_command_timeout=30,
            fabric_sql_top=50,
            client_id="client-id",
            client_secret="client-secret",
        )
    )
    fabric_items = [
        {
            "itemId": "warehouse-1",
            "itemName": "Finance Warehouse",
        }
    ]
    payload = {
        "items": [
            {
                "itemId": "warehouse-1",
                "itemName": "Finance Warehouse",
                "rows": [
                    {
                        "distributed_statement_id": "sql-exec-1",
                        "database_name": "Finance Warehouse",
                    }
                ],
            }
        ]
    }

    result = collector.collect_item_queries_from_payload(fabric_items, payload)

    assert list(result) == ["warehouse-1"]
    assert result["warehouse-1"][0]["distributed_statement_id"] == "sql-exec-1"


def test_collect_item_queries_reads_export_file_and_matches_by_database_name() -> None:
    with TemporaryDirectory(dir=Path.cwd()) as temp_dir:
        export_path = Path(temp_dir) / "fabric-export.json"
        export_path.write_text(
            json.dumps(
                [
                    {
                        "distributed_statement_id": "sql-exec-2",
                        "database_name": "Operations Lakehouse",
                        "statement_type": "SELECT",
                    }
                ]
            ),
            encoding="utf-8",
        )
        collector = FabricSQLCollector(
            SimpleNamespace(
                fabric_sql_monitoring_enabled=True,
                fabric_sql_source="export",
                fabric_sql_notebook_export_path=str(export_path),
                fabric_sql_odbc_driver="ODBC Driver 18 for SQL Server",
                fabric_sql_connect_timeout=15,
                fabric_sql_command_timeout=30,
                fabric_sql_top=50,
                client_id="client-id",
                client_secret="client-secret",
            )
        )
        fabric_items = [
            {
                "itemId": "lakehouse-1",
                "itemName": "Operations Lakehouse",
            }
        ]

        result = collector.collect_item_queries(fabric_items)

    assert list(result) == ["lakehouse-1"]
    assert result["lakehouse-1"][0]["statement_type"] == "SELECT"


class _FakeCursor:
    def __init__(self, rows):
        self._rows = rows
        self.timeout = None
        self.description = [
            ("distributed_statement_id",),
            ("database_name",),
            ("submit_time",),
            ("start_time",),
            ("end_time",),
            ("statement_type",),
            ("total_elapsed_time_ms",),
            ("status",),
            ("login_name",),
            ("command",),
            ("error_code",),
        ]
        self.executed_sql = None

    def execute(self, sql: str) -> None:
        self.executed_sql = sql

    def fetchall(self):
        return self._rows


class _FakeConnection:
    def __init__(self, rows):
        self.cursor_instance = _FakeCursor(rows)
        self.closed = False

    def cursor(self):
        return self.cursor_instance

    def close(self) -> None:
        self.closed = True


class _FakePyodbc:
    def __init__(self, rows):
        self.rows = rows
        self.connection_strings = []
        self.connections = []

    def connect(self, connection_string: str, timeout: int):
        self.connection_strings.append((connection_string, timeout))
        connection = _FakeConnection(self.rows)
        self.connections.append(connection)
        return connection


def test_collect_item_queries_live_uses_odbc_and_returns_rows(monkeypatch) -> None:
    collector = FabricSQLCollector(
        SimpleNamespace(
            fabric_sql_monitoring_enabled=True,
            fabric_sql_source="live",
            fabric_sql_notebook_export_path="",
            fabric_sql_odbc_driver="ODBC Driver 18 for SQL Server",
            fabric_sql_connect_timeout=9,
            fabric_sql_command_timeout=21,
            fabric_sql_top=7,
            client_id="client-id",
            client_secret="client-secret",
        )
    )
    fake_pyodbc = _FakePyodbc(
        [
            (
                "sql-exec-3",
                "Finance Warehouse",
                "2026-08-04T08:00:00",
                "2026-08-04T08:00:05",
                "2026-08-04T08:03:05",
                "EXECUTE",
                180000,
                "Succeeded",
                "service-principal",
                "EXEC dbo.RefreshFinanceSnapshot",
                0,
            )
        ]
    )
    monkeypatch.setattr(
        FabricSQLCollector,
        "_load_pyodbc_module",
        lambda self: fake_pyodbc,
    )

    result = collector.collect_item_queries(
        [
            {
                "itemId": "warehouse-1",
                "itemName": "Finance Warehouse",
                "itemType": "Warehouse",
                "connectionString": "finance-warehouse.fabric.microsoft.com",
                "isSqlEnabled": True,
            }
        ]
    )

    assert list(result) == ["warehouse-1"]
    assert result["warehouse-1"][0]["distributed_statement_id"] == "sql-exec-3"
    connection_string, timeout = fake_pyodbc.connection_strings[0]
    assert "SERVER=finance-warehouse.fabric.microsoft.com" in connection_string
    assert "DATABASE=Finance Warehouse" in connection_string
    assert "Authentication=ActiveDirectoryServicePrincipal" in connection_string
    assert timeout == 9
    assert "TOP (7)" in fake_pyodbc.connections[0].cursor_instance.executed_sql
    assert fake_pyodbc.connections[0].cursor_instance.timeout == 21
    assert fake_pyodbc.connections[0].closed is True


def test_collect_item_queries_auto_falls_back_to_export_when_live_is_unavailable(
    monkeypatch,
) -> None:
    with TemporaryDirectory(dir=Path.cwd()) as temp_dir:
        export_path = Path(temp_dir) / "fabric-export.json"
        export_path.write_text(
            json.dumps(
                [
                    {
                        "distributed_statement_id": "sql-exec-4",
                        "database_name": "Finance Warehouse",
                        "statement_type": "SELECT",
                    }
                ]
            ),
            encoding="utf-8",
        )
        collector = FabricSQLCollector(
            SimpleNamespace(
                fabric_sql_monitoring_enabled=True,
                fabric_sql_source="auto",
                fabric_sql_notebook_export_path=str(export_path),
                fabric_sql_odbc_driver="ODBC Driver 18 for SQL Server",
                fabric_sql_connect_timeout=15,
                fabric_sql_command_timeout=30,
                fabric_sql_top=50,
                client_id="client-id",
                client_secret="client-secret",
            )
        )
        monkeypatch.setattr(
            FabricSQLCollector,
            "_load_pyodbc_module",
            lambda self: None,
        )

        result = collector.collect_item_queries(
            [
                {
                    "itemId": "warehouse-1",
                    "itemName": "Finance Warehouse",
                    "itemType": "Warehouse",
                    "connectionString": "finance-warehouse.fabric.microsoft.com",
                    "isSqlEnabled": True,
                }
            ]
        )

    assert list(result) == ["warehouse-1"]
    assert result["warehouse-1"][0]["distributed_statement_id"] == "sql-exec-4"
