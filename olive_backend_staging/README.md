# Power BI Backend Service

This service reads Microsoft Entra ID credentials from `.env`, requests an access token with the client credentials flow, calls the Power BI REST API, stores the results in PostgreSQL, and exposes live and stored monitoring endpoints.

## Endpoints

- `GET /health`
- `GET /`
- `GET /dashboard`
- `GET /api/powerbi/workspaces`
- `GET /api/powerbi/reports`
- `GET /api/powerbi/datasets`
- `GET /api/powerbi/refreshes?refresh_top=10`
- `GET /api/powerbi/incidents?refresh_top=10`
- `GET /api/powerbi/workspaces/{workspace_id}/reports`
- `GET /api/powerbi/workspaces/{workspace_id}/datasets`
- `GET /api/powerbi/workspaces/{workspace_id}/datasets/{dataset_id}/refreshes?top=10`
- `POST /api/powerbi/monitoring/sync?refresh_top=10`
- `GET /api/powerbi/monitoring/indicators?live=false`
- `GET /api/powerbi/storage/workspaces`
- `GET /api/powerbi/storage/reports`
- `GET /api/powerbi/storage/datasets`
- `GET /api/powerbi/storage/refreshes`
- `GET /api/powerbi/storage/incidents`
- `GET /api/powerbi/storage/fabric/items`
- `GET /api/powerbi/storage/fabric/executions`
- `GET /api/powerbi/storage/fabric/sql-executions`
- `POST /api/powerbi/fabric/sql-executions/import`

## Monitoring data covered

- Workspace: ID, name, type, capacity mode and capacity ID
- Dataset: ID, name, workspace, owner/configured by, data source types, data source summaries, gateway IDs
- Refresh: refresh ID, dataset, refresh type, start/end date, duration, status, error code, error message
- Incident: incident ID, dataset, detection date, severity, suspected cause, recommendation
- Indicators: total refreshes, success rate, failure rate, average and max duration, slowest datasets, datasets with most failures, delayed refreshes, duration anomalies, and incident breakdowns by cause, gateway, capacity, credentials, and data source
- Fabric inventory: warehouses and lakehouses available in the linked Fabric workspaces, including SQL endpoint metadata when exposed by Fabric
- Fabric execution telemetry: item job runs, invoke type, status, duration, and recent failures for warehouse and lakehouse items
- Fabric SQL telemetry: live query-insights collection for SQL durations and stored procedure executions across Fabric warehouses and lakehouse SQL endpoints, with optional notebook-export fallback

## Run

```powershell
pip install -r requirements.txt
uvicorn App.main:app --reload
```

Open the web interface at `http://127.0.0.1:8000/dashboard`.

## Test

The smoke suite uses mocked storage and Power BI client calls, so it can validate the API and dashboard routes without touching the real PostgreSQL database or Microsoft APIs.

```powershell
pip install -r requirements-dev.txt
python -m pytest
```

## Notes

- The Power BI tenant must allow service principals to use Power BI APIs.
- The Entra ID app registration must have Power BI API permissions and access to the target workspaces.
- The same service principal must also have access to the Fabric workspace items you want to monitor.
- Set `DATABASE_URL` in `.env`, or provide `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_USER`, and `POSTGRES_PASSWORD`.
- If you use `DATABASE_URL`, prefer the `postgresql+pg8000://...` format on Windows.
- Tables are created automatically at startup.
- Fabric REST calls use `FABRIC_BASE_URL=https://api.fabric.microsoft.com/v1` by default.
- For live Fabric SQL monitoring, install `pyodbc` plus Microsoft ODBC Driver 18 for SQL Server on the host and allow outbound TCP 1433 access to the Fabric SQL endpoint.
- Set `FABRIC_SQL_MONITORING_ENABLED=true` and use `FABRIC_SQL_SOURCE=auto` or `FABRIC_SQL_SOURCE=live` to query `queryinsights.exec_requests_history` directly from each SQL-enabled warehouse or lakehouse endpoint during sync.
- `FABRIC_SQL_SOURCE=auto` tries live SQL first and falls back to `FABRIC_SQL_NOTEBOOK_EXPORT_PATH` when that export is configured.
- You can also import the same JSON manually with `POST /api/powerbi/fabric/sql-executions/import`.
- The expected export shape is documented in [FABRIC_NOTEBOOK_EXPORT.md](./FABRIC_NOTEBOOK_EXPORT.md).

