from functools import lru_cache
import logging
from typing import Any, Dict, List, Optional

import requests

from App.auth import EntraIdAuthClient, get_auth_client
from App.config import Settings, get_settings


logger = logging.getLogger(__name__)


class PowerBIClient:
    def __init__(self, settings: Settings, auth_client: EntraIdAuthClient) -> None:
        self.settings = settings
        self.auth_client = auth_client

    def _request_url(
        self,
        method: str,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        scope: Optional[str] = None,
    ) -> Dict[str, Any]:
        try:
            response = requests.request(
                method,
                url,
                headers={
                    "Authorization": f"Bearer {self.auth_client.get_access_token(scope=scope)}",
                    "Content-Type": "application/json",
                },
                params=params,
                timeout=30,
            )
        except requests.RequestException:
            logger.exception(
                "Power BI/Fabric request failed before a response was received: %s %s",
                method,
                url,
            )
            raise

        if response.status_code == 401:
            logger.warning(
                "Power BI/Fabric request returned 401 for %s %s; retrying once with a refreshed token.",
                method,
                url,
            )
            response = requests.request(
                method,
                url,
                headers={
                    "Authorization": (
                        f"Bearer {self.auth_client.get_access_token(force_refresh=True, scope=scope)}"
                    ),
                    "Content-Type": "application/json",
                },
                params=params,
                timeout=30,
            )

        try:
            response.raise_for_status()
        except requests.HTTPError as error:
            logger.warning(
                "Power BI/Fabric request failed with status %s for %s %s.",
                response.status_code,
                method,
                url,
            )
            raise error
        try:
            payload = response.json()
        except ValueError as error:
            logger.warning("Power BI/Fabric API returned invalid JSON for %s %s.", method, url)
            raise requests.RequestException(
                "Power BI/Fabric API returned invalid JSON."
            ) from error
        if not isinstance(payload, dict):
            logger.warning(
                "Power BI/Fabric API returned an unexpected payload shape for %s %s.",
                method,
                url,
            )
            raise requests.RequestException(
                "Power BI/Fabric API returned an unexpected payload shape."
            )
        return payload

    def _request(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        *,
        base_url: Optional[str] = None,
        scope: Optional[str] = None,
    ) -> Dict[str, Any]:
        url = f"{(base_url or self.settings.powerbi_base_url).rstrip('/')}/{path.lstrip('/')}"
        return self._request_url(method, url, params=params, scope=scope)

    @staticmethod
    def _value(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        value = payload.get("value", [])
        if value is None:
            return []
        if not isinstance(value, list):
            logger.warning("Power BI API returned a non-list value payload.")
            raise requests.RequestException(
                "Power BI API returned an unexpected value payload."
            )
        return value

    def _request_paginated_value(
        self,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        base_url: Optional[str] = None,
        scope: Optional[str] = None,
        page_limit: int = 20,
    ) -> List[Dict[str, Any]]:
        payload = self._request(
            "GET",
            path,
            params=params,
            base_url=base_url,
            scope=scope,
        )
        items = self._value(payload)
        next_url = payload.get("continuationUri")
        next_token = payload.get("continuationToken")
        pages = 1

        while (next_url or next_token) and pages < page_limit:
            if next_url:
                payload = self._request_url("GET", next_url, scope=scope)
            else:
                next_params = dict(params or {})
                next_params["continuationToken"] = next_token
                payload = self._request(
                    "GET",
                    path,
                    params=next_params,
                    base_url=base_url,
                    scope=scope,
                )
            items.extend(self._value(payload))
            next_url = payload.get("continuationUri")
            next_token = payload.get("continuationToken")
            pages += 1

        return items

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

    def list_workspace_warehouses(self, workspace_id: str) -> List[Dict[str, Any]]:
        return self._request_paginated_value(
            f"workspaces/{workspace_id}/warehouses",
            base_url=self.settings.fabric_base_url,
            scope=self.settings.fabric_scope,
        )

    def list_workspace_lakehouses(self, workspace_id: str) -> List[Dict[str, Any]]:
        return self._request_paginated_value(
            f"workspaces/{workspace_id}/lakehouses",
            base_url=self.settings.fabric_base_url,
            scope=self.settings.fabric_scope,
        )

    def get_lakehouse(self, workspace_id: str, lakehouse_id: str) -> Dict[str, Any]:
        return self._request(
            "GET",
            f"workspaces/{workspace_id}/lakehouses/{lakehouse_id}",
            base_url=self.settings.fabric_base_url,
            scope=self.settings.fabric_scope,
        )

    def get_warehouse_connection_string(
        self,
        workspace_id: str,
        warehouse_id: str,
    ) -> str | None:
        payload = self._request(
            "GET",
            f"workspaces/{workspace_id}/warehouses/{warehouse_id}/connectionString",
            base_url=self.settings.fabric_base_url,
            scope=self.settings.fabric_scope,
        )
        value = payload.get("connectionString")
        if not value:
            return None
        return str(value)

    def list_item_job_instances(
        self,
        workspace_id: str,
        item_id: str,
    ) -> List[Dict[str, Any]]:
        return self._request_paginated_value(
            f"workspaces/{workspace_id}/items/{item_id}/jobs/instances",
            base_url=self.settings.fabric_base_url,
            scope=self.settings.fabric_scope,
        )


@lru_cache(maxsize=1)
def get_powerbi_client() -> PowerBIClient:
    return PowerBIClient(get_settings(), get_auth_client())

