from __future__ import annotations

from typing import Any, Dict

import requests

from App.auth import get_auth_client
from App.powerbi_client import get_powerbi_client


def check_external_dependencies() -> Dict[str, Any]:
    auth_client = get_auth_client()
    powerbi_client = get_powerbi_client()

    result: Dict[str, Any] = {
        "entra": {"status": "unknown"},
        "powerbi": {"status": "unknown"},
    }

    try:
        auth_client.get_access_token(force_refresh=True)
        result["entra"] = {"status": "ok"}
    except requests.HTTPError as error:
        status_code = error.response.status_code if error.response is not None else None
        result["entra"] = {
            "status": "error",
            "detail": "Microsoft Entra token request failed.",
            "upstreamStatus": status_code,
        }
        result["powerbi"] = {
            "status": "skipped",
            "detail": "Power BI check skipped because Entra authentication failed.",
        }
        return result
    except requests.RequestException as error:
        result["entra"] = {
            "status": "error",
            "detail": str(error),
        }
        result["powerbi"] = {
            "status": "skipped",
            "detail": "Power BI check skipped because Entra authentication failed.",
        }
        return result

    try:
        workspaces = powerbi_client.list_workspaces()
        result["powerbi"] = {
            "status": "ok",
            "workspaceCount": len(workspaces),
        }
    except requests.HTTPError as error:
        status_code = error.response.status_code if error.response is not None else None
        result["powerbi"] = {
            "status": "error",
            "detail": "Power BI API request failed.",
            "upstreamStatus": status_code,
        }
    except requests.RequestException as error:
        result["powerbi"] = {
            "status": "error",
            "detail": str(error),
        }

    return result
