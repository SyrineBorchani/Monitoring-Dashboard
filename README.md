# Service de monitoring Power BI et Fabric

Cette application permet de superviser des actifs Microsoft Power BI et
Microsoft Fabric a partir d'un backend FastAPI et d'un dashboard web.

Elle prend en charge :

- la collecte live des workspaces, rapports, datasets et refreshs Power BI ;
- la collecte de l'inventaire Fabric ;
- la collecte des executions d'items Fabric ;
- le stockage historique dans PostgreSQL ;
- la derivation d'incidents et d'indicateurs de monitoring ;
- la collecte optionnelle de l'historique SQL Fabric.

## Architecture de deploiement

Dans la configuration actuelle du projet :

- le frontend est heberge sur Vercel ;
- le backend API est heberge sur Render ;
- la base de donnees est PostgreSQL.

Le dashboard est livre sous forme statique, mais son comportement est dynamique
cote navigateur grace a JavaScript, React, D3 et aux appels API vers le backend.

## Fonctionnalites principales

### Monitoring Power BI

- Workspaces Power BI
- Rapports Power BI
- Datasets Power BI
- Datasources et gateways associees
- Historique des refreshs
- Incidents derives a partir des refreshs
- Indicateurs de synthese

### Monitoring Fabric

- Inventaire des warehouses et lakehouses
- Executions de jobs sur les items Fabric
- Resume des echecs et durees d'execution
- Historique SQL Fabric pour les items SQL-enabled

### Dashboard

- Vue de synthese des KPIs
- Vue performance
- Vue Fabric
- Vue incidents
- Synchronisation manuelle
- Rechargement manuel
- Tolerance aux echecs partiels lors du chargement

## Endpoints principaux

### Sante et interface

- `GET /health`
- `GET /health/dependencies`
- `GET /`
- `GET /dashboard`

### Collecte live Power BI / Fabric

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

### Donnees stockees

- `GET /api/powerbi/storage/workspaces`
- `GET /api/powerbi/storage/reports`
- `GET /api/powerbi/storage/datasets`
- `GET /api/powerbi/storage/refreshes`
- `GET /api/powerbi/storage/incidents`
- `GET /api/powerbi/storage/fabric/items`
- `GET /api/powerbi/storage/fabric/executions`
- `GET /api/powerbi/storage/fabric/sql-executions`
- `POST /api/powerbi/fabric/sql-executions/import`

## Donnees couvertes

### Power BI

- Workspace : identifiant, nom, type, mode de capacite, identifiant de capacite
- Dataset : identifiant, nom, workspace, owner/configured by, types de sources, resumes de sources, gateways
- Refresh : identifiant, dataset, type, dates debut/fin, duree, statut, code erreur, message erreur
- Incident : identifiant, dataset, date de detection, severite, cause suspectee, recommandation
- Indicateurs : total refreshs, taux de succes, taux d'echec, durees moyennes et maximales, datasets les plus lents, datasets avec le plus d'echecs, refreshs en retard, anomalies de duree et repartitions d'incidents

### Fabric

- Inventaire : warehouses et lakehouses disponibles dans les workspaces Fabric suivis
- Execution Fabric : type d'invocation, statut, duree, echecs recents
- SQL Fabric : historiques `queryinsights`, durees de requetes et executions de procedures stockees

## Configuration

Les variables minimales a fournir sont :

- `TENANT_ID`
- `CLIENT_ID`
- `CLIENT_SECRET`

Pour la base de donnees, il faut soit :

- definir `DATABASE_URL`

soit fournir :

- `POSTGRES_HOST`
- `POSTGRES_PORT`
- `POSTGRES_DB`
- `POSTGRES_USER`
- `POSTGRES_PASSWORD`

Variables optionnelles importantes :

- `POWERBI_BASE_URL`
- `FABRIC_BASE_URL`
- `FABRIC_SQL_MONITORING_ENABLED`
- `FABRIC_SQL_SOURCE`
- `FABRIC_SQL_NOTEBOOK_EXPORT_PATH`
- `FABRIC_SQL_ODBC_DRIVER`
- `FABRIC_SQL_CONNECT_TIMEOUT`
- `FABRIC_SQL_COMMAND_TIMEOUT`
- `FABRIC_SQL_TOP`

Un exemple complet est disponible dans [`.env.example`](./.env.example).

## Lancement en local

### Installation

```powershell
pip install -r requirements.txt
```

### Demarrage du backend

```powershell
uvicorn App.main:app --reload
```

Interface locale :

- [Dashboard](http://127.0.0.1:8000/dashboard)

## Docker

Le projet inclut un `Dockerfile` pour le backend.

Ce conteneur :

- utilise Python 3.12 ;
- installe les dependances systeme ODBC ;
- installe Microsoft ODBC Driver 18 ;
- expose le port `10000`.

## Monitoring SQL Fabric en option

Pour activer la collecte SQL Fabric en live :

- installer `pyodbc` ;
- disposer de Microsoft ODBC Driver 18 for SQL Server ;
- autoriser l'acces sortant TCP 1433 vers l'endpoint SQL Fabric ;
- definir `FABRIC_SQL_MONITORING_ENABLED=true`.

Modes possibles :

- `FABRIC_SQL_SOURCE=auto` : tente le live SQL puis bascule sur un export notebook si configure ;
- `FABRIC_SQL_SOURCE=live` : force la collecte live ;
- `FABRIC_SQL_SOURCE=export` : utilise uniquement l'export notebook.

Il est aussi possible d'importer manuellement le JSON avec :

- `POST /api/powerbi/fabric/sql-executions/import`

Le format attendu est documente dans
[FABRIC_NOTEBOOK_EXPORT.md](./FABRIC_NOTEBOOK_EXPORT.md).

## Tests

Installation des dependances de test :

```powershell
pip install -r requirements-dev.txt
```

Execution :

```powershell
python -m pytest
```

La suite de smoke tests utilise des fakes pour valider les routes API et le
dashboard sans dependre directement des APIs Microsoft en live.

Le depot contient egalement des tests pour :

- la configuration ;
- l'authentification ;
- le client Power BI/Fabric ;
- les migrations ;
- la couche storage PostgreSQL ;
- les analytics ;
- le collecteur SQL Fabric ;
- les endpoints et le framework FastAPI.

## Notes importantes

- Le tenant Power BI doit autoriser l'usage des APIs par service principal.
- L'application Entra doit disposer des permissions Power BI necessaires.
- Le meme service principal doit avoir acces aux workspaces Fabric suivis.
- Si `DATABASE_URL` est utilise, le format `postgresql+pg8000://...` est prefere.
- Les tables sont initialisees et migrees automatiquement au demarrage.
- Les appels Fabric REST utilisent `FABRIC_BASE_URL=https://api.fabric.microsoft.com/v1` par defaut.
- Le frontend Vercel re-ecrit actuellement `/api/*` vers un backend Render.

## Documentation complementaire

- [PROJECT_DOCUMENTATION.md](./PROJECT_DOCUMENTATION.md)
- [PROJECT_DOCUMENTATION.tex](./PROJECT_DOCUMENTATION.tex)
- [TESTING_STRATEGY.md](./TESTING_STRATEGY.md)
- [FABRIC_NOTEBOOK_EXPORT.md](./FABRIC_NOTEBOOK_EXPORT.md)
