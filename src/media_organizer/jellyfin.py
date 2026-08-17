from __future__ import annotations

import logging

import requests

from .models import Integration


class JellyfinError(RuntimeError):
    """Raised when communication with Jellyfin fails."""


class JellyfinClient:
    """Minimal client for Jellyfin library operations."""

    def __init__(
        self,
        integration: Integration,
        timeout_seconds: float = 15.0,
    ) -> None:
        self.enabled = integration.enabled
        self.base_url = integration.url.rstrip("/")
        self.api_key = integration.api_key
        self.timeout_seconds = timeout_seconds

    def validate_configuration(self) -> None:
        """Validate required Jellyfin integration settings."""

        if not self.enabled:
            return

        if not self.base_url:
            raise JellyfinError(
                "Jellyfin URL is missing."
            )

        if not self.api_key:
            raise JellyfinError(
                "Jellyfin API key is missing."
            )

    def test_connection(self) -> dict:
        """Retrieve public server information."""

        self.validate_configuration()

        if not self.enabled:
            return {}

        try:
            response = requests.get(
                f"{self.base_url}/System/Info/Public",
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise JellyfinError(
                f"Unable to connect to Jellyfin: {exc}"
            ) from exc

        try:
            return response.json()
        except ValueError as exc:
            raise JellyfinError(
                "Jellyfin returned an invalid JSON response."
            ) from exc

    def refresh_library(self) -> bool:
        """Request a full Jellyfin media-library refresh."""

        if not self.enabled:
            logging.debug(
                "Jellyfin integration is disabled."
            )
            return False

        self.validate_configuration()

        try:
            response = requests.post(
                f"{self.base_url}/Library/Refresh",
                headers={
                    "X-Emby-Token": self.api_key,
                },
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise JellyfinError(
                f"Jellyfin library refresh failed: {exc}"
            ) from exc

        logging.info(
            "Jellyfin library refresh requested successfully."
        )

        return True