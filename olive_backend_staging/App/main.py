from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from App.database import init_db
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
app.mount("/static", StaticFiles(directory="App/static"), name="static")


@app.get("/health")
def health_check():
    return {"status": "ok"}
