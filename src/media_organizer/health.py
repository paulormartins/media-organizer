from __future__ import annotations

import sqlite3
import subprocess
from dataclasses import dataclass

from .arr_client import ArrClient, ArrError
from .history import HistoryDatabase
from .jellyfin import JellyfinClient, JellyfinError
from .models import AppConfig, Integration
from .safety import SafetyError, validate_environment


@dataclass(frozen=True)
class HealthResult:
    """Represents the result of one health check."""

    name: str
    healthy: bool
    message: str
    required: bool = True


class HealthService:
    """Runs health checks for Media Organizer and its integrations."""

    def __init__(
        self,
        config: AppConfig,
        service_name: str = "media-organizer.service",
    ) -> None:
        self.config = config
        self.service_name = service_name

    def run_all(self) -> list[HealthResult]:
        """Run all configured health checks."""

        return [
            self._check_environment(),
            self._check_database(),
            self._check_watcher_service(),
            self._check_jellyfin(),
            self._check_arr(
                name="Radarr",
                integration=self.config.radarr,
            ),
            self._check_arr(
                name="Sonarr",
                integration=self.config.sonarr,
            ),
        ]

    def _check_environment(self) -> HealthResult:
        try:
            validate_environment(self.config)

        except SafetyError as exc:
            return HealthResult(
                name="Environment",
                healthy=False,
                message=str(exc),
            )

        except OSError as exc:
            return HealthResult(
                name="Environment",
                healthy=False,
                message=f"Environment check failed: {exc}",
            )

        return HealthResult(
            name="Environment",
            healthy=True,
            message="Mount, UUID, paths, and free space are valid.",
        )

    def _check_database(self) -> HealthResult:
        if not self.config.database.enabled:
            return HealthResult(
                name="SQLite",
                healthy=True,
                message="Disabled in configuration.",
                required=False,
            )

        history = HistoryDatabase(
            database_path=self.config.database.path,
            enabled=True,
        )

        try:
            history.initialize()

            with sqlite3.connect(
                self.config.database.path,
                timeout=10,
            ) as connection:
                integrity_result = connection.execute(
                    "PRAGMA quick_check"
                ).fetchone()

                connection.execute(
                    "SELECT COUNT(*) FROM operations"
                ).fetchone()

        except (sqlite3.Error, OSError) as exc:
            return HealthResult(
                name="SQLite",
                healthy=False,
                message=f"Database check failed: {exc}",
            )

        if (
            integrity_result is None
            or integrity_result[0] != "ok"
        ):
            result_message = (
                integrity_result[0]
                if integrity_result
                else "No integrity result returned"
            )

            return HealthResult(
                name="SQLite",
                healthy=False,
                message=(
                    f"Integrity check failed: {result_message}"
                ),
            )

        return HealthResult(
            name="SQLite",
            healthy=True,
            message=(
                "Database is accessible and passed quick_check: "
                f"{self.config.database.path}"
            ),
        )

    def _check_watcher_service(self) -> HealthResult:
        try:
            result = subprocess.run(
                [
                    "systemctl",
                    "is-active",
                    self.service_name,
                ],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )

        except (OSError, subprocess.SubprocessError) as exc:
            return HealthResult(
                name="Watcher",
                healthy=False,
                message=f"Unable to query systemd: {exc}",
            )

        status = (
            result.stdout.strip()
            or result.stderr.strip()
            or "unknown"
        )

        if result.returncode != 0 or status != "active":
            return HealthResult(
                name="Watcher",
                healthy=False,
                message=f"Service status: {status}",
            )

        return HealthResult(
            name="Watcher",
            healthy=True,
            message=f"{self.service_name} is active.",
        )

    def _check_jellyfin(self) -> HealthResult:
        integration = self.config.jellyfin

        if not integration.enabled:
            return HealthResult(
                name="Jellyfin",
                healthy=True,
                message="Disabled in configuration.",
                required=False,
            )

        client = JellyfinClient(
            integration=integration,
        )

        try:
            information = client.test_connection()

        except JellyfinError as exc:
            return HealthResult(
                name="Jellyfin",
                healthy=False,
                message=str(exc),
            )

        server_name = information.get(
            "ServerName",
            "Unknown server",
        )

        version = information.get(
            "Version",
            "Unknown version",
        )

        return HealthResult(
            name="Jellyfin",
            healthy=True,
            message=f"{server_name}, version {version}.",
        )

    @staticmethod
    def _check_arr(
        name: str,
        integration: Integration,
    ) -> HealthResult:
        if not integration.enabled:
            return HealthResult(
                name=name,
                healthy=True,
                message="Disabled in configuration.",
                required=False,
            )

        client = ArrClient(
            name=name,
            integration=integration,
        )

        try:
            status = client.get_status()

        except ArrError as exc:
            return HealthResult(
                name=name,
                healthy=False,
                message=str(exc),
            )

        version = status.get(
            "version",
            "Unknown version",
        )

        instance_name = status.get(
            "instanceName",
            name,
        )

        startup_path = status.get(
            "startupPath",
        )

        message = (
            f"{instance_name}, version {version}."
        )

        if startup_path:
            message += f" Startup path: {startup_path}"

        return HealthResult(
            name=name,
            healthy=True,
            message=message,
        )


def print_health_report(
    results: list[HealthResult],
) -> bool:
    """
    Print a formatted health report.

    Returns:
        True when all required checks are healthy.
    """

    print()
    print("Media Organizer Health Check")
    print("=" * 60)

    for result in results:
        if not result.required:
            marker = "○"
            state = "OPTIONAL"

        elif result.healthy:
            marker = "✓"
            state = "OK"

        else:
            marker = "✗"
            state = "FAIL"

        print(
            f"{marker} "
            f"{result.name:<14} "
            f"{state:<8} "
            f"{result.message}"
        )

    required_results = [
        result
        for result in results
        if result.required
    ]

    healthy = all(
        result.healthy
        for result in required_results
    )

    print("=" * 60)

    print(
        "Overall status: "
        f"{'HEALTHY' if healthy else 'UNHEALTHY'}"
    )

    print()

    return healthy