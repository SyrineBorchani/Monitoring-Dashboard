from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, RedirectResponse


router = APIRouter(tags=["ui"])

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


def _dashboard_path() -> Path:
    dashboard_path = STATIC_DIR / "dashboard.html"

    if not dashboard_path.is_file():
        raise HTTPException(status_code=404, detail="Dashboard asset not found.")

    try:
        with dashboard_path.open("rb"):
            pass
    except PermissionError as error:
        raise HTTPException(
            status_code=503,
            detail="Dashboard asset is not readable.",
        ) from error

    return dashboard_path


@router.get("/", include_in_schema=False)
def home():
    return RedirectResponse(url="/dashboard")


@router.get("/dashboard", include_in_schema=False)
def dashboard():
    return FileResponse(_dashboard_path())
