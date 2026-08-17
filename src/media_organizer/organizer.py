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
from .refresh_scheduler import RefreshScheduler


class Organizer:
    """Move media files to the library or quarantine directory."""

    QUARANTINE_STATUSES = {
        PlanStatus.UNKNOWN,
        PlanStatus.DUPLICATE,
        PlanStatus.EXISTS,
        PlanStatus.ERROR,
    }

    def __init__(
        self,
        config: AppConfig,
        dry_run: bool = False,
        refresh_scheduler: RefreshScheduler | None = None,
    ) -> None:
        self.config = config
        self.dry_run = dry_run
        self.refresh_scheduler = refresh_scheduler

        self.history = HistoryDatabase(
            database_path=config.database.path,
            enabled=config.database.enabled,
        )

        self.history.initialize()

    def apply(
        self,
        plan: Plan,
    ) -> bool:
        """Apply one organization plan."""

        if not plan.source.exists():
            logging.warning(
                "Source file no longer exists: %s",
                plan.source,
            )

            self.history.record(
                plan=plan,
                action=OperationAction.ERROR,
                status=PlanStatus.ERROR,
                reason="Source file no longer exists",
            )

            return False

        if not plan.source.is_file():
            logging.warning(
                "Source path is not a regular file: %s",
                plan.source,
            )

            self.history.record(
                plan=plan,
                action=OperationAction.ERROR,
                status=PlanStatus.ERROR,
                reason="Source path is not a regular file",
            )

            return False

        if plan.status is PlanStatus.SKIP:
            logging.info(
                "File intentionally skipped: source=%s reason=%s",
                plan.source,
                plan.reason,
            )

            self.history.record(
                plan=plan,
                action=OperationAction.SKIP,
            )

            return False

        if plan.status in self.QUARANTINE_STATUSES:
            return self._handle_rejected_plan(plan)

        if plan.status is not PlanStatus.READY:
            logging.warning(
                "Unsupported plan status: "
                "source=%s status=%s reason=%s",
                plan.source,
                plan.status.value,
                plan.reason,
            )

            self.history.record(
                plan=plan,
                action=OperationAction.ERROR,
                status=PlanStatus.ERROR,
                reason=(
                    f"Unsupported plan status: "
                    f"{plan.status.value}"
                ),
            )

            return False

        if plan.destination.exists():
            logging.warning(
                "Destination already exists: %s",
                plan.destination,
            )

            return self._move_to_quarantine(
                plan=plan,
                status=PlanStatus.EXISTS,
                reason=(
                    f"Destination already exists: "
                    f"{plan.destination}"
                ),
            )

        try:
            source_resolved = plan.source.resolve()
            destination_resolved = plan.destination.resolve(
                strict=False
            )

        except OSError as exc:
            logging.warning(
                "Unable to resolve organization paths: %s",
                exc,
            )

            return self._move_to_quarantine(
                plan=plan,
                status=PlanStatus.ERROR,
                reason=f"Unable to resolve paths: {exc}",
            )

        if source_resolved == destination_resolved:
            return self._move_to_quarantine(
                plan=plan,
                status=PlanStatus.ERROR,
                reason=(
                    "Source and destination resolve "
                    "to the same file"
                ),
            )

        return self._move_to_library(plan)

    def _handle_rejected_plan(
        self,
        plan: Plan,
    ) -> bool:
        """Handle a plan that cannot be imported normally."""

        if not self.config.quarantine.enabled:
            logging.warning(
                "Plan rejected and quarantine is disabled: "
                "source=%s status=%s reason=%s",
                plan.source,
                plan.status.value,
                plan.reason,
            )

            self.history.record(
                plan=plan,
                action=OperationAction.SKIP,
                status=plan.status,
                reason=(
                    "Quarantine disabled. "
                    f"Original reason: {plan.reason}"
                ),
            )

            return False

        return self._move_to_quarantine(
            plan=plan,
            status=plan.status,
            reason=plan.reason,
        )

    def _move_to_library(
        self,
        plan: Plan,
    ) -> bool:
        """Move a validated media file to its final destination."""

        logging.info(
            "Moving media file to library: %s -> %s",
            plan.source,
            plan.destination,
        )

        source_size = self._get_file_size(
            plan.source
        )

        if self.dry_run:
            logging.info(
                "Dry-run enabled; library move was not performed."
            )
            return True

        try:
            plan.destination.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            shutil.move(
                str(plan.source),
                str(plan.destination),
            )

        except OSError as exc:
            logging.exception(
                "Failed to move file to library: %s",
                exc,
            )

            self.history.record(
                plan=plan,
                action=OperationAction.ERROR,
                status=PlanStatus.ERROR,
                reason=f"Library move failed: {exc}",
                size_bytes=source_size,
            )

            # The source may still exist when shutil.move fails.
            # Only try quarantine when it is still available.
            if plan.source.exists():
                return self._move_to_quarantine(
                    plan=plan,
                    status=PlanStatus.ERROR,
                    reason=f"Library move failed: {exc}",
                )

            return False

        self._remove_empty_source_directories(
            plan.source.parent
        )

        self.history.record(
            plan=plan,
            action=OperationAction.IMPORT,
            status=PlanStatus.READY,
            destination=plan.destination,
            size_bytes=source_size,
        )

        self._request_integration_refresh(
            media_type=plan.media_type,
        )

        logging.info(
            "Media file moved successfully: %s",
            plan.destination,
        )

        return True

    def _request_integration_refresh(
        self,
        media_type: str,
    ) -> None:
        """
        Request integration refreshes without failing the import.

        At this point the file has already been moved and recorded.
        A scheduler failure must not mark the import as failed.
        """

        if self.refresh_scheduler is None:
            return

        try:
            self.refresh_scheduler.request_refresh(
                media_type=media_type,
            )

        except Exception:
            logging.exception(
                "Unable to schedule integration refresh "
                "for media type %s",
                media_type,
            )

    def _move_to_quarantine(
        self,
        plan: Plan,
        status: PlanStatus,
        reason: str,
    ) -> bool:
        """Move a rejected media file into quarantine."""

        if not self.config.quarantine.enabled:
            logging.warning(
                "Quarantine is disabled; "
                "preserving file at source: %s",
                plan.source,
            )

            self.history.record(
                plan=plan,
                action=OperationAction.SKIP,
                status=status,
                reason=reason,
            )

            return False

        quarantine_directory = (
            self.config.quarantine.path
            / status.value.lower()
        )

        destination = self._unique_destination(
            quarantine_directory
            / plan.source.name
        )

        logging.warning(
            "Moving file to quarantine: "
            "source=%s destination=%s status=%s reason=%s",
            plan.source,
            destination,
            status.value,
            reason,
        )

        source_size = self._get_file_size(
            plan.source
        )

        if self.dry_run:
            logging.info(
                "Dry-run enabled; quarantine move was not performed."
            )
            return True

        try:
            destination.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            shutil.move(
                str(plan.source),
                str(destination),
            )

        except OSError as exc:
            logging.exception(
                "Failed to move file to quarantine: %s",
                exc,
            )

            self.history.record(
                plan=plan,
                action=OperationAction.ERROR,
                status=PlanStatus.ERROR,
                reason=f"Quarantine move failed: {exc}",
                size_bytes=source_size,
            )

            return False

        self._remove_empty_source_directories(
            plan.source.parent
        )

        self.history.record(
            plan=plan,
            action=OperationAction.QUARANTINE,
            status=status,
            reason=reason,
            destination=destination,
            size_bytes=source_size,
        )

        logging.info(
            "File moved to quarantine successfully: %s",
            destination,
        )

        return True

    @staticmethod
    def _get_file_size(
        path: Path,
    ) -> int | None:
        """Return a file size or None when it cannot be read."""

        try:
            return path.stat().st_size

        except OSError:
            return None

    @staticmethod
    def _unique_destination(
        destination: Path,
    ) -> Path:
        """Return a destination path that does not overwrite a file."""

        if not destination.exists():
            return destination

        counter = 1

        while True:
            candidate = destination.with_name(
                f"{destination.stem}_{counter}"
                f"{destination.suffix}"
            )

            if not candidate.exists():
                return candidate

            counter += 1

    def _remove_empty_source_directories(
        self,
        starting_directory: Path,
    ) -> None:
        """
        Remove empty source directories without crossing safe boundaries.
        """

        try:
            mount_root = (
                self.config.safety.mount_path.resolve()
            )

            protected_paths = {
                mount_root,
                self.config.movies.source.resolve(),
                self.config.movies.destination.resolve(),
                self.config.series.source.resolve(),
                self.config.series.destination.resolve(),
                self.config.quarantine.path.resolve(),
            }

            current = starting_directory.resolve()

        except OSError as exc:
            logging.warning(
                "Unable to initialize directory cleanup: %s",
                exc,
            )
            return

        while current not in protected_paths:
            if not current.is_relative_to(
                mount_root
            ):
                logging.warning(
                    "Cleanup stopped outside the media mount: %s",
                    current,
                )
                break

            try:
                current.rmdir()

            except FileNotFoundError:
                current = current.parent
                continue

            except OSError:
                # Directory is not empty or cannot be removed.
                break

            logging.info(
                "Removed empty source directory: %s",
                current,
            )

            current = current.parent