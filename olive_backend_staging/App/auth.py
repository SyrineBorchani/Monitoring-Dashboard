from functools import lru_cache
import time
from typing import Optional

import requests

from App.config import Settings, get_settings


class EntraIdAuthClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._token: Optional[str] = None
        self._expires_at = 0.0

    def get_access_token(self, force_refresh: bool = False) -> str:
        now = time.time()
        if (
            not force_refresh
            and self._token
            and now < self._expires_at - 60
        ):
            return self._token

        response = requests.post(
            self.settings.token_url,
            data={
                "grant_type": "client_credentials",
                "client_id": self.settings.client_id,
                "client_secret": self.settings.client_secret,
                "scope": self.settings.powerbi_scope,
            },
            timeout=30,
        )
        response.raise_for_status()

        payload = response.json()
        self._token = payload["access_token"]
        self._expires_at = now + int(payload.get("expires_in", 3600))
        return self._token


@lru_cache(maxsize=1)
def get_auth_client() -> EntraIdAuthClient:
    return EntraIdAuthClient(get_settings())
