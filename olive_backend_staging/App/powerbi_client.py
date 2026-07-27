from functools import lru_cache
from typing import Any, Dict, List, Optional

import requests

from App.auth import EntraIdAuthClient, get_auth_client
from App.config import Settings, get_settings


class PowerBIClient:
    def __init__(self, settings: Settings, auth_client: EntraIdAuthClient) -> None:
        self.settings = settings
        self.auth_client = auth_client

    def _request(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        url = f"{self.settings.powerbi_base_url}/{path.lstrip('/')}"
        response = requests.request(
            method,
            url,
            headers={
                "Authorization": f"Bearer {self.auth_client.get_access_token()}",
                "Content-Type": "application/json",
            },
            params=params,
            timeout=30,
        )

        if response.status_code == 401:
            response = requests.request(
                method,
                url,
                headers={
                    "Authorization": (
                        f"Bearer {self.auth_client.get_access_token(force_refresh=True)}"
                    ),
                    "Content-Type": "application/json",
                },
                params=params,
                timeout=30,
            )

        response.raise_for_status()
        return response.json()

    @staticmethod
    def _value(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        return payload.get("value", [])

    def list_workspaces(self) -> List[Dict[str, Any]]:
        return self._value(self._request("GET", "groups"))

    def list_workspace_reports(self, workspace_id: str) -> List[Dict[str, Any]]:
        return self._value(self._request("GET", f"groups/{workspace_id}/reports"))

    def list_workspace_datasets(self, workspace_id: str) -> List[Dict[str, Any]]:
        return self._value(self._request("GET", f"groups/{workspace_id}/datasets"))

    def list_dataset_datasources(
        self,
        workspace_id: str,
        dataset_id: str,
    ) -> List[Dict[str, Any]]:
        return self._value(
            self._request(
                "GET",
                f"groups/{workspace_id}/datasets/{dataset_id}/datasources",
            )
        )

    def list_dataset_refresh_history(
        self,
        workspace_id: str,
        dataset_id: str,
        top: int = 10,
    ) -> List[Dict[str, Any]]:
        return self._value(
            self._request(
                "GET",
                f"groups/{workspace_id}/datasets/{dataset_id}/refreshes",
                params={"$top": top},
            )
        )


@lru_cache(maxsize=1)
def get_powerbi_client() -> PowerBIClient:
    return PowerBIClient(get_settings(), get_auth_client())
