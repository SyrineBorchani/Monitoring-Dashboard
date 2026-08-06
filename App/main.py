from contextlib import asynccontextmanager

from fastapi import FastAPI, status
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from App.database import check_database_connection, init_db
from App.dependency_checks import check_external_dependencies
from App.routes.ui import STATIC_DIR
from App.routes.powerbi import router as powerbi_router
from App.routes.ui import router as ui_router


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="OliveSoft Monitoring Power BI Service",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(powerbi_router)
app.include_router(ui_router)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/health")
def health_check():
    database_ok, detail = check_database_connection()
    if database_ok:
        return {"status": "ok", "database": "ok"}

    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={
            "status": "degraded",
            "database": "unavailable",
            "detail": detail or "Database connection check failed.",
        },
    )


@app.get("/health/dependencies")
def dependency_health_check():
    dependency_status = check_external_dependencies()
    statuses = {
        dependency_status["entra"]["status"],
        dependency_status["powerbi"]["status"],
    }
    if statuses.issubset({"ok"}):
        return dependency_status

    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content=dependency_status,
    )
