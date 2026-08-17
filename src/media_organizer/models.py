from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class PlanStatus(str, Enum):
    READY = "READY"
    UNKNOWN = "UNKNOWN"
    DUPLICATE = "DUPLICATE"
    EXISTS = "EXISTS"
    ERROR = "ERROR"
    SKIP = "SKIP"


class OperationAction(str, Enum):
    IMPORT = "IMPORT"
    QUARANTINE = "QUARANTINE"
    SKIP = "SKIP"
    ERROR = "ERROR"
    UNDO = "UNDO"
    RETRY = "RETRY"


@dataclass(frozen=True)
class Library:
    source: Path
    destination: Path


@dataclass(frozen=True)
class Integration:
    enabled: bool = False
    url: str = ""
    api_key: str = ""


@dataclass(frozen=True)
class Safety:
    mount_path: Path
    expected_uuid: str
    minimum_free_gb: float


@dataclass(frozen=True)
class Quarantine:
    enabled: bool
    path: Path
    cleanup_hidden_files: bool = True
    remove_empty_directories: bool = True
    retention_days: int = 15


@dataclass(frozen=True)
class Database:
    enabled: bool
    path: Path
    cleanup_hidden_files: bool = True
    remove_empty_directories: bool = True
    retention_days: int = 15


@dataclass(frozen=True)
class AppConfig:
    minimum_age_seconds: int
    verify_interval_seconds: int
    movies: Library
    series: Library
    safety: Safety
    quarantine: Quarantine
    database: Database
    jellyfin: Integration
    radarr: Integration
    sonarr: Integration


@dataclass(frozen=True)
class Plan:
    source: Path
    destination: Path
    media_type: str
    title: str
    year: str | None = None
    season: int | None = None
    episode: int | None = None
    status: PlanStatus = PlanStatus.READY
    reason: str = ""