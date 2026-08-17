from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path

from .models import AppConfig


class SafetyError(RuntimeError):
    """Raised when the runtime environment is unsafe for file operations."""


def _run(command: list[str]) -> str:
    result = subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _get_mount_source(path: Path) -> str:
    try:
        source = _run(
            [
                "findmnt",
                "-n",
                "-o",
                "SOURCE",
                "--target",
                str(path),
            ]
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        raise SafetyError(
            f"{path} is not a mounted filesystem."
        ) from exc

    if not source:
        raise SafetyError(
            f"Unable to determine the mounted device for {path}."
        )

    return source


def _get_device_uuid(device: str) -> str:
    try:
        device_uuid = _run(
            [
                "blkid",
                "-s",
                "UUID",
                "-o",
                "value",
                device,
            ]
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        raise SafetyError(
            f"Unable to retrieve the UUID for device {device}."
        ) from exc

    if not device_uuid:
        raise SafetyError(
            f"Device {device} does not expose a valid UUID."
        )

    return device_uuid


def _get_free_space_gb(path: Path) -> float:
    stats = os.statvfs(path)
    free_bytes = stats.f_bavail * stats.f_frsize
    return free_bytes / (1024**3)


def _validate_library_paths(
    config: AppConfig,
    mount_path: Path,
) -> None:
    mount_root = mount_path.resolve()

    for name, library in (
        ("movies", config.movies),
        ("series", config.series),
    ):
        source = library.source.resolve()
        destination = library.destination.resolve()

        if not source.is_relative_to(mount_root):
            raise SafetyError(
                f"{name} source is outside the configured mount point: {source}"
            )

        if not destination.is_relative_to(mount_root):
            raise SafetyError(
                f"{name} destination is outside the configured mount point: "
                f"{destination}"
            )

        if source == destination:
            raise SafetyError(
                f"{name} source and destination cannot be the same directory."
            )


def validate_environment(config: AppConfig) -> None:
    mount_path = config.safety.mount_path

    if not mount_path.exists():
        raise SafetyError(
            f"Mount path does not exist: {mount_path}"
        )

    if not mount_path.is_dir():
        raise SafetyError(
            f"Mount path is not a directory: {mount_path}"
        )

    source = _get_mount_source(mount_path)
    actual_uuid = _get_device_uuid(source)
    expected_uuid = config.safety.expected_uuid

    if expected_uuid and actual_uuid != expected_uuid:
        raise SafetyError(
            f"Unexpected filesystem mounted at {mount_path}. "
            f"Expected UUID: {expected_uuid}. "
            f"Detected UUID: {actual_uuid}."
        )

    free_space = _get_free_space_gb(mount_path)

    if free_space < config.safety.minimum_free_gb:
        raise SafetyError(
            f"Insufficient free disk space. "
            f"Available: {free_space:.1f} GiB, "
            f"required: {config.safety.minimum_free_gb:.1f} GiB."
        )

    _validate_library_paths(config, mount_path)

    logging.info(
        "Environment validation completed successfully "
        "(device=%s, uuid=%s, free_space=%.1f GiB)",
        source,
        actual_uuid,
        free_space,
    )
