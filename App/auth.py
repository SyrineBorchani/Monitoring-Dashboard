from functools import lru_cache
import logging
import time
from typing import Dict

import requests

from App.config import Settings, get_settings


logger = logging.getLogger(__name__)


class EntraIdAuthClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._tokens: Dict[str, str] = {}
        self._expires_at: Dict[str, float] = {}

    def get_access_token(
        self,
        force_refresh: bool = False,
        scope: str | None = None,
    ) -> str:
        requested_scope = scope or self.settings.powerbi_scope
        now = time.time()
        if (
            not force_refresh
            and self._tokens.get(requested_scope)
            and now < self._expires_at.get(requested_scope, 0.0) - 60
        ):
            return self._tokens[requested_scope]

        try:
            response = requests.post(
                self.settings.token_url,
                data={
                    "grant_type": "client_credentials",
                    "client_id": self.settings.client_id,
                    "client_secret": self.settings.client_secret,
                    "scope": requested_scope,
                },
                timeout=30,
            )
            response.raise_for_status()
        except requests.HTTPError as error:
            status_code = (
                error.response.status_code
                if error.response is not None
                else "unknown"
            )
            logger.warning(
                "Microsoft Entra token request failed with status %s.",
                status_code,
            )
            raise
        except requests.RequestException:
            logger.exception("Microsoft Entra token request failed before a token was issued.")
            raise

        try:
            payload = response.json()
        except ValueError as error:
            logger.warning("Microsoft Entra token response was not valid JSON.")
            raise requests.RequestException(
                "Microsoft Entra token response was not valid JSON."
            ) from error

        access_token = payload.get("access_token")
        if not access_token:
            logger.warning("Microsoft Entra token response did not contain access_token.")
            raise requests.RequestException(
                "Microsoft Entra token response missing access_token."
            )

        try:
            expires_in = int(payload.get("expires_in", 3600))
        except (TypeError, ValueError):
            expires_in = 3600

        self._tokens[requested_scope] = access_token
        self._expires_at[requested_scope] = now + expires_in
        return self._tokens[requested_scope]


@lru_cache(maxsize=1)
def get_auth_client() -> EntraIdAuthClient:
    return EntraIdAuthClient(get_settings())
