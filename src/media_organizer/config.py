from __future__ import annotations

from pathlib import Path

import yaml

from .models import (
    AppConfig,
    Database,
    Integration,
    Library,
    Quarantine,
    Safety,
)


def _integration(
    data: dict,
    name: str,
) -> Integration:
    raw = data.get("integrations", {}).get(name, {})

    return Integration(
        enabled=bool(raw.get("enabled", False)),
        url=str(
            raw.get(
                "url","",)
        ).strip().rstrip("/"),
        api_key=str(
            raw.get(
                "api_key","",)
        ).strip(),
    )


def load_config(path: Path) -> AppConfig:
    if not path.is_file():
        raise FileNotFoundError(
            f"Config file not found: {path}"
        )

    data = yaml.safe_load(
        path.read_text(encoding="utf-8")
    ) or {}

    watcher = data.get("watcher", {})
    safety = data.get("safety", {})
    quarantine = data.get("quarantine", {})
    database = data.get("database", {})

    return AppConfig(
        minimum_age_seconds=int(
            watcher.get(
                "minimum_age_seconds",
                600,
            )
        ),
        verify_interval_seconds=int(
            watcher.get(
                "verify_interval_seconds",
                5,
            )
        ),
        movies=Library(
            source=Path(
                data["movies"]["source"]
            ),
            destination=Path(
                data["movies"]["destination"]
            ),
        ),
        series=Library(
            source=Path(
                data["series"]["source"]
            ),
            destination=Path(
                data["series"]["destination"]
            ),
        ),
        safety=Safety(
            mount_path=Path(
                safety.get(
                    "mount_path",
                    "/mnt/media",
                )
            ),
            expected_uuid=str(
                safety.get(
                    "expected_uuid",
                    "",
                )
            ).strip(),
            minimum_free_gb=float(
                safety.get(
                    "minimum_free_gb",
                    30,
                )
            ),
        ),
        quarantine=Quarantine(
            enabled=bool(
                quarantine.get(
                    "enabled",
                    True,
                )
            ),
            path=Path(
                quarantine.get(
                    "path",
                    "/mnt/media/TEMP/Quarantine",
                )
            ),
            cleanup_hidden_files=bool(
                quarantine.get(
                    "cleanup_hidden_files",
                    True,
                )
            ),
            remove_empty_directories=bool(
                quarantine.get(
                    "remove_empty_directories",
                    True,
                )
            ),
            retention_days=max(
                1,
                int(
                    quarantine.get(
                        "retention_days",
                        15,
                    )
                ),
            ),
        ),
        database=Database(
            enabled=bool(
                database.get(
                    "enabled",
                    True,
                )
            ),
            path=Path(
                database.get(
                    "path",
                    "/home/paulo/.local/share/media-organizer/history.db",
                )
            ),
        ),
        jellyfin=_integration(
            data,
            "jellyfin",
        ),
        radarr=_integration(
            data,
            "radarr",
        ),
        sonarr=_integration(
            data,
            "sonarr",
        ),
    )