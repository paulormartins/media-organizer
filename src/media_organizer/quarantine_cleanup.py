from __future__ import annotations

import logging
from pathlib import Path

from .models import AppConfig


HIDDEN_FILE_NAMES = {
    ".DS_Store",
    "Thumbs.db",
    "desktop.ini",
}

HIDDEN_FILE_PREFIXES = {
    "._",
}


class QuarantineCleanup:
    """
    Performs non-destructive quarantine maintenance.

    Media files are never deleted automatically. Only operating-system
    metadata files and empty directories are removed.
    """

    def __init__(
        self,
        config: AppConfig,
        dry_run: bool = False,
    ) -> None:
        self.config = config
        self.dry_run = dry_run

    def run(self) -> dict[str, int]:
        statistics = {
            "hidden_files_found": 0,
            "hidden_files_removed": 0,
            "empty_directories_removed": 0,
            "media_files_preserved": 0,
            "errors": 0,
        }

        root = self.config.quarantine.path

        if not self.config.quarantine.enabled:
            logging.info(
                "Quarantine cleanup skipped because quarantine is disabled."
            )
            return statistics

        if not root.exists():
            logging.info(
                "Quarantine directory does not exist: %s",
                root,
            )
            return statistics

        if not root.is_dir():
            logging.error(
                "Quarantine path is not a directory: %s",
                root,
            )
            statistics["errors"] += 1
            return statistics

        self._remove_hidden_files(
            root=root,
            statistics=statistics,
        )

        self._count_preserved_files(
            root=root,
            statistics=statistics,
        )

        if self.config.quarantine.remove_empty_directories:
            self._remove_empty_directories(
                root=root,
                statistics=statistics,
            )

        return statistics

    def _remove_hidden_files(
        self,
        root: Path,
        statistics: dict[str, int],
    ) -> None:
        if not self.config.quarantine.cleanup_hidden_files:
            return

        for path in root.rglob("*"):
            try:
                if not path.is_file():
                    continue
            except OSError:
                statistics["errors"] += 1
                logging.exception(
                    "Unable to inspect quarantine path: %s",
                    path,
                )
                continue

            if not self._is_removable_metadata_file(path):
                continue

            statistics["hidden_files_found"] += 1

            if self.dry_run:
                logging.info(
                    "Dry-run: would remove metadata file: %s",
                    path,
                )
                continue

            try:
                path.unlink()
            except OSError:
                statistics["errors"] += 1
                logging.exception(
                    "Unable to remove metadata file: %s",
                    path,
                )
                continue

            statistics["hidden_files_removed"] += 1

            logging.info(
                "Removed metadata file from quarantine: %s",
                path,
            )

    @staticmethod
    def _count_preserved_files(
        root: Path,
        statistics: dict[str, int],
    ) -> None:
        for path in root.rglob("*"):
            try:
                if (
                    path.is_file()
                    and not QuarantineCleanup._is_removable_metadata_file(path)
                ):
                    statistics["media_files_preserved"] += 1
            except OSError:
                statistics["errors"] += 1

    def _remove_empty_directories(
        self,
        root: Path,
        statistics: dict[str, int],
    ) -> None:
        directories = sorted(
            (
                path
                for path in root.rglob("*")
                if path.is_dir()
            ),
            key=lambda path: len(path.parts),
            reverse=True,
        )

        for directory in directories:
            if directory == root:
                continue

            try:
                if any(directory.iterdir()):
                    continue

                if self.dry_run:
                    logging.info(
                        "Dry-run: would remove empty directory: %s",
                        directory,
                    )
                    continue

                directory.rmdir()

            except OSError:
                statistics["errors"] += 1
                logging.exception(
                    "Unable to remove empty quarantine directory: %s",
                    directory,
                )
                continue

            statistics["empty_directories_removed"] += 1

            logging.info(
                "Removed empty quarantine directory: %s",
                directory,
            )

    @staticmethod
    def _is_removable_metadata_file(
        path: Path,
    ) -> bool:
        if path.name in HIDDEN_FILE_NAMES:
            return True

        return any(
            path.name.startswith(prefix)
            for prefix in HIDDEN_FILE_PREFIXES
        )