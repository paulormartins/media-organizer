from __future__ import annotations

import logging
import shutil
from pathlib import Path

from .history import HistoryDatabase
from .models import (
    AppConfig,
    OperationAction,
    Plan,
    PlanStatus,
)


class UndoError(RuntimeError):
    """Raised when an operation cannot be safely undone."""


class UndoService:
    """Safely reverses previous import or quarantine operations."""

    SUPPORTED_ACTIONS = {
        OperationAction.IMPORT.value,
        OperationAction.QUARANTINE.value,
    }

    def __init__(
        self,
        config: AppConfig,
        history: HistoryDatabase,
        dry_run: bool = False,
    ) -> None:
        self.config = config
        self.history = history
        self.dry_run = dry_run

    def undo(
        self,
        operation_id: int,
    ) -> bool:
        operation = self.history.get_operation(
            operation_id
        )

        if operation is None:
            raise UndoError(
                f"Operation not found: {operation_id}"
            )

        if operation["action"] not in self.SUPPORTED_ACTIONS:
            raise UndoError(
                "Only IMPORT and QUARANTINE operations "
                "can be undone."
            )

        if self.history.was_undone(operation_id):
            raise UndoError(
                f"Operation {operation_id} was already undone."
            )

        source = Path(operation["source"])
        destination = Path(operation["destination"])

        self._validate_paths(
            original_source=source,
            current_location=destination,
        )

        if not destination.exists():
            raise UndoError(
                f"Current file does not exist: {destination}"
            )

        if not destination.is_file():
            raise UndoError(
                f"Current path is not a regular file: {destination}"
            )

        if source.exists():
            raise UndoError(
                f"Original source path already exists: {source}"
            )

        logging.info(
            "Undoing operation %s: %s -> %s",
            operation_id,
            destination,
            source,
        )

        if self.dry_run:
            logging.info(
                "Dry-run enabled; no file was moved."
            )
            return True

        try:
            source.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            shutil.move(
                str(destination),
                str(source),
            )

        except OSError as exc:
            raise UndoError(
                f"Failed to undo operation {operation_id}: {exc}"
            ) from exc

        plan = Plan(
            source=destination,
            destination=source,
            media_type=operation["media_type"],
            title=operation["title"] or "",
            year=operation["year"],
            season=operation["season"],
            episode=operation["episode"],
            status=PlanStatus.READY,
            reason=(
                f"Undo of operation {operation_id}"
            ),
        )

        self.history.record(
            plan=plan,
            action=OperationAction.UNDO,
            status=PlanStatus.READY,
            destination=source,
            reason=f"Reversed operation {operation_id}",
            size_bytes=operation["size_bytes"],
            checksum=operation["checksum"],
            parent_operation_id=operation_id,
        )

        self._remove_empty_directories(
            destination.parent
        )

        logging.info(
            "Operation %s undone successfully.",
            operation_id,
        )

        return True

    def _validate_paths(
        self,
        original_source: Path,
        current_location: Path,
    ) -> None:
        mount_root = (
            self.config.safety.mount_path
            .resolve()
        )

        resolved_source = original_source.resolve(
            strict=False
        )

        resolved_destination = current_location.resolve(
            strict=False
        )

        if not resolved_source.is_relative_to(
            mount_root
        ):
            raise UndoError(
                f"Original source is outside the media mount: "
                f"{original_source}"
            )

        if not resolved_destination.is_relative_to(
            mount_root
        ):
            raise UndoError(
                f"Current file is outside the media mount: "
                f"{current_location}"
            )

        if resolved_source == resolved_destination:
            raise UndoError(
                "Source and destination are the same path."
            )

    @staticmethod
    def _remove_empty_directories(
        starting_directory: Path,
    ) -> None:
        protected_names = {
            "",
            "mnt",
            "media",
            "TEMP",
            "Filmes",
            "Series",
            "Quarantine",
        }

        current = starting_directory

        while current.name not in protected_names:
            try:
                current.rmdir()

            except FileNotFoundError:
                current = current.parent
                continue

            except OSError:
                break

            logging.info(
                "Removed empty directory after undo: %s",
                current,
            )

            current = current.parent