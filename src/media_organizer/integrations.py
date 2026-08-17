from __future__ import annotations

import logging

import requests

from .models import AppConfig, Plan


class Integrations:
    def __init__(self, config: AppConfig) -> None:
        self.config = config

    def notify(self, plan: Plan) -> None:
        self._refresh_jellyfin()
        if plan.media_type == "movie":
            self._refresh_arr(self.config.radarr, "RefreshMovie")
        elif plan.media_type == "series":
            self._refresh_arr(self.config.sonarr, "RefreshSeries")

    def _refresh_jellyfin(self) -> None:
        cfg = self.config.jellyfin
        if not cfg.enabled:
            return

        try:
            response = requests.post(
                f"{cfg.url}/Library/Refresh",
                headers={"X-Emby-Token": cfg.api_key},
                timeout=15,
            )
            response.raise_for_status()
            logging.info("Jellyfin library refresh requested")
        except requests.RequestException as exc:
            logging.error("Jellyfin refresh failed: %s", exc)

    @staticmethod
    def _refresh_arr(cfg, command: str) -> None:
        if not cfg.enabled:
            return

        try:
            response = requests.post(
                f"{cfg.url}/api/v3/command",
                headers={"X-Api-Key": cfg.api_key},
                json={"name": command},
                timeout=15,
            )
            response.raise_for_status()
            logging.info("%s requested", command)
        except requests.RequestException as exc:
            logging.error("%s failed: %s", command, exc)
