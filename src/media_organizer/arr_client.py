from __future__ import annotations

import logging
from typing import Any

import requests

from .models import Integration


class ArrError(RuntimeError):
    """Raised when communication with a Servarr application fails."""


class ArrClient:
    """Minimal API client shared by Radarr and Sonarr."""

    def __init__(
        self,
        name: str,
        integration: Integration,
        timeout_seconds: float = 15.0,
    ) -> None:
        self.name = name
        self.enabled = integration.enabled
        self.base_url = integration.url.rstrip("/")
        self.api_key = integration.api_key
        self.timeout_seconds = timeout_seconds

    def validate_configuration(self) -> None:
        if not self.enabled:
            return

        if not self.base_url:
            raise ArrError(
                f"{self.name} URL is missing."
            )

        if not self.api_key:
            raise ArrError(
                f"{self.name} API key is missing."
            )

    def get_status(self) -> dict[str, Any]:
        """Retrieve application status from the API."""

        if not self.enabled:
            return {}

        self.validate_configuration()

        try:
            response = requests.get(
                f"{self.base_url}/api/v3/system/status",
                headers={
                    "X-Api-Key": self.api_key,
                },
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()

        except requests.RequestException as exc:
            raise ArrError(
                f"Unable to connect to {self.name}: {exc}"
            ) from exc

        try:
            return response.json()

        except ValueError as exc:
            raise ArrError(
                f"{self.name} returned invalid JSON."
            ) from exc

    def execute_command(
        self,
        command_name: str,
        **parameters: Any,
    ) -> dict[str, Any]:
        """Submit an asynchronous command to the application."""

        if not self.enabled:
            return {}

        self.validate_configuration()

        payload: dict[str, Any] = {
            "name": command_name,
            **parameters,
        }

        try:
            response = requests.post(
                f"{self.base_url}/api/v3/command",
                headers={
                    "X-Api-Key": self.api_key,
                },
                json=payload,
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()

        except requests.RequestException as exc:
            raise ArrError(
                f"{self.name} command {command_name} failed: {exc}"
            ) from exc

        logging.info(
            "%s command requested successfully: %s",
            self.name,
            command_name,
        )

        try:
            return response.json()

        except ValueError:
            return {}