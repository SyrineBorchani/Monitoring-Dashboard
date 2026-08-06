# Fabric Notebook Export

This project can ingest Fabric SQL telemetry without any local ODBC driver.

The backend now prefers a live SQL connection when `FABRIC_SQL_MONITORING_ENABLED=true` and `FABRIC_SQL_SOURCE` is `auto` or `live`. Use this export flow as a fallback when the host cannot use ODBC directly, or when you want to backfill SQL telemetry manually.

## Expected flow

1. Run a Fabric notebook or SQL query inside the target Warehouse or Lakehouse SQL endpoint.
2. Export the query results to JSON.
3. Save that JSON locally and point `FABRIC_SQL_NOTEBOOK_EXPORT_PATH` to it, or import it through the API.
4. Run the dashboard sync.

## Suggested query

Run this query from the SQL query editor or from a Fabric notebook connected to the target item:

```sql
SELECT TOP (50)
    distributed_statement_id,
    database_name,
    submit_time,
    start_time,
    end_time,
    statement_type,
    total_elapsed_time_ms,
    status,
    login_name,
    command,
    error_code
FROM queryinsights.exec_requests_history
ORDER BY end_time DESC, start_time DESC;
```

## Preferred export shape

If you export one item at a time, wrap the rows like this:

```json
{
  "items": [
    {
      "itemId": "warehouse-or-lakehouse-id",
      "itemName": "Finance Warehouse",
      "workspaceId": "workspace-id",
      "itemType": "Warehouse",
      "rows": [
        {
          "distributed_statement_id": "sql-exec-1",
          "database_name": "Finance Warehouse",
          "submit_time": "2026-08-04T08:00:00Z",
          "start_time": "2026-08-04T08:00:05Z",
          "end_time": "2026-08-04T08:03:05Z",
          "statement_type": "EXECUTE",
          "total_elapsed_time_ms": 180000,
          "status": "Succeeded",
          "login_name": "service-principal",
          "command": "EXEC dbo.RefreshFinanceSnapshot",
          "error_code": 0
        }
      ]
    }
  ]
}
```

The collector also accepts a flat JSON array when rows already contain `itemId` or `itemName`.

