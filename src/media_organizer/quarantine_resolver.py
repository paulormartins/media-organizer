from __future__ import annotations

import hashlib
import logging
from pathlib import Path

from .history import HistoryDatabase
from .models import AppConfig, OperationAction


class QuarantineResolver:
    """Analyzes files quarantined because their destination already existed."""

    def __init__(
        self,
        config: AppConfig,
        dry_run: bool = False,
        delete_confirmed: bool = False,
    ) -> None:
        self.config = config
        self.dry_run = dry_run
        self.delete_confirmed = delete_confirmed

        self.history = HistoryDatabase(
            database_path=config.database.path,
            enabled=config.database.enabled,
        )

        self.history.initialize()

    def run(self) -> dict[str, int]:
        statistics = {
            "operations_checked": 0,
            "missing_quarantine_files": 0,
            "missing_destination_files": 0,
            "confirmed_duplicates": 0,
            "different_files": 0,
            "deleted_duplicates": 0,
            "errors": 0,
        }

        operations = self._list_exists_operations()

        for operation in operations:
            statistics["operations_checked"] += 1

            quarantine_path = Path(
                operation["destination"]
            )

            original_destination = self._extract_original_destination(
                operation["reason"] or ""
            )

            if original_destination is None:
                logging.warning(
                    "Unable to determine original destination "
                    "for operation %s",
                    operation["id"],
                )
                statistics["errors"] += 1
                continue

            if not quarantine_path.is_file():
                logging.warning(
                    "Quarantine file is missing: %s",
                    quarantine_path,
                )
                statistics["missing_quarantine_files"] += 1
                continue

            if not original_destination.is_file():
                logging.warning(
                    "Original destination is missing: %s",
                    original_destination,
                )
                statistics["missing_destination_files"] += 1
                continue

            try:
                quarantine_size = quarantine_path.stat().st_size
                destination_size = original_destination.stat().st_size

            except OSError as exc:
                logging.error(
                    "Unable to inspect operation %s: %s",
                    operation["id"],
                    exc,
                )
                statistics["errors"] += 1
                continue

            if quarantine_size != destination_size:
                statistics["different_files"] += 1

                logging.warning(
                    "Files differ in size; preserving both: "
                    "quarantine=%s destination=%s",
                    quarantine_path,
                    original_destination,
                )
                continue

            try:
                quarantine_checksum = self._sha256(
                    quarantine_path
                )

                destination_checksum = self._sha256(
                    original_destination
                )

            except OSError as exc:
                logging.error(
                    "Unable to calculate checksum for operation %s: %s",
                    operation["id"],
                    exc,
                )
                statistics["errors"] += 1
                continue

            if quarantine_checksum != destination_checksum:
                statistics["different_files"] += 1

                logging.warning(
                    "Files have different checksums; preserving both: "
                    "quarantine=%s destination=%s",
                    quarantine_path,
                    original_destination,
                )
                continue

            statistics["confirmed_duplicates"] += 1

            logging.info(
                "Confirmed duplicate: quarantine=%s destination=%s",
                quarantine_path,
                original_destination,
            )

            if not self.delete_confirmed:
                continue

            if self.dry_run:
                logging.info(
                    "Dry-run: would remove confirmed duplicate: %s",
                    quarantine_path,
                )
                continue

            try:
                quarantine_path.unlink()
            except OSError as exc:
                logging.error(
                    "Unable to remove confirmed duplicate %s: %s",
                    quarantine_path,
                    exc,
                )
                statistics["errors"] += 1
                continue

            statistics["deleted_duplicates"] += 1

            logging.info(
                "Removed confirmed duplicate: %s",
                quarantine_path,
            )

            self._remove_empty_parents(
                quarantine_path.parent
            )

        return statistics

    def _list_exists_operations(self):
        if not self.config.database.enabled:
            return []

        with self.history._connection() as connection:
            cursor = connection.execute(
                """
                SELECT
                    id,
                    destination,
                    reason
                FROM operations
                WHERE
                    action = ?
                    AND status = ?
                ORDER BY id ASC
                """,
                (
                    OperationAction.QUARANTINE.value,
                    "EXISTS",
                ),
            )

            return list(cursor.fetchall())

    @staticmethod
    def _extract_original_destination(
        reason: str,
    ) -> Path | None:
        prefixes = (
            "Destination already exists: ",
            "Library scan destination already exists: ",
        )

        for prefix in prefixes:
            if reason.startswith(prefix):
                value = reason.removeprefix(
                    prefix
                ).strip()

                if value:
                    return Path(value)

        return None

    @staticmethod
    def _sha256(
        path: Path,
        chunk_size: int = 8 * 1024 * 1024,
    ) -> str:
        digest = hashlib.sha256()

        with path.open("rb") as file_handle:
            for chunk in iter(
                lambda: file_handle.read(chunk_size),
                b"",
            ):
                digest.update(chunk)

        return digest.hexdigest()

    def _remove_empty_parents(
        self,
        starting_directory: Path,
    ) -> None:
        root = self.config.quarantine.path.resolve()
        current = starting_directory.resolve()

        while current != root:
            try:
                current.rmdir()
            except OSError:
                break

            logging.info(
                "Removed empty quarantine directory: %s",
                current,
            )

            current = current.parent