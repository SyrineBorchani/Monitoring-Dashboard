# Power BI Backend Service

This service reads Microsoft Entra ID credentials from `.env`, requests an access token with the client credentials flow, calls the Power BI REST API, stores the results in PostgreSQL, and exposes live and stored monitoring endpoints.

It also supports a no-dependency proof-of-concept mode that serves seeded monitoring data directly from the app so the dashboard can be reviewed without Power BI or PostgreSQL.

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

## Monitoring data covered

- Workspace: ID, name, type, capacity mode and capacity ID
- Dataset: ID, name, workspace, owner/configured by, data source types, data source summaries, gateway IDs
- Refresh: refresh ID, dataset, refresh type, start/end date, duration, status, error code, error message
- Incident: incident ID, dataset, detection date, severity, suspected cause, recommendation
- Indicators: total refreshes, success rate, failure rate, average and max duration, slowest datasets, datasets with most failures, delayed refreshes, duration anomalies, and incident breakdowns by cause, gateway, capacity, credentials, and data source

## Run

```powershell
pip install -r requirements.txt
uvicorn App.main:app --reload
```

Open the web interface at `http://127.0.0.1:8000/dashboard`.

## Run the PoC locally

The PoC mode skips the database and Power BI calls, then loads a seeded monitoring snapshot with workspaces, datasets, refresh histories, and incidents.

```powershell
$env:POC_MODE="true"
uvicorn App.main:app --reload
```

Open `http://127.0.0.1:8000/dashboard` to review the demo dashboard. A banner in the UI will indicate that the app is running in proof-of-concept mode.

## Notes

- The Power BI tenant must allow service principals to use Power BI APIs.
- The Entra ID app registration must have Power BI API permissions and access to the target workspaces.
- `POC_MODE=true` is intended for demos and local validation only; it does not call Microsoft services or persist data.
- Set `DATABASE_URL` in `.env`, or provide `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_USER`, and `POSTGRES_PASSWORD`.
- If you use `DATABASE_URL`, prefer the `postgresql+pg8000://...` format on Windows.
- Tables are created automatically at startup.
