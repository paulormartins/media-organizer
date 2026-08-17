from __future__ import annotations

import logging
from pathlib import Path

from .history import HistoryDatabase
from .models import (
    AppConfig,
    OperationAction,
    Plan,
    PlanStatus,
)
from .organizer import Organizer
from .parser import plan_episode, plan_movie


class RetryError(RuntimeError):
    """Raised when a previous operation cannot be retried safely."""


class RetryService:
    """Retries a previous quarantine operation."""

    def __init__(
        self,
        config: AppConfig,
        history: HistoryDatabase,
        dry_run: bool = False,
    ) -> None:
        self.config = config
        self.history = history
        self.dry_run = dry_run

    def retry(
        self,
        operation_id: int,
    ) -> bool:
        operation = self.history.get_operation(
            operation_id
        )

        if operation is None:
            raise RetryError(
                f"Operation not found: {operation_id}"
            )

        if operation["action"] != OperationAction.QUARANTINE.value:
            raise RetryError(
                "Only QUARANTINE operations can be retried."
            )

        current_path = Path(
            operation["destination"]
        )

        if not current_path.exists():
            raise RetryError(
                f"Quarantined file does not exist: {current_path}"
            )

        if not current_path.is_file():
            raise RetryError(
                f"Quarantine path is not a regular file: {current_path}"
            )

        plan = self._build_plan(
            current_path=current_path,
            media_type=operation["media_type"],
        )

        if plan.status is not PlanStatus.READY:
            raise RetryError(
                f"File is still not recognized: {plan.reason}"
            )

        logging.info(
            "Retrying operation %s using file %s",
            operation_id,
            current_path,
        )

        organizer = Organizer(
            config=self.config,
            dry_run=self.dry_run,
        )

        result = organizer.apply(plan)

        if not result:
            raise RetryError(
                f"Retry failed for operation {operation_id}"
            )

        if not self.dry_run:
            self.history.record(
                plan=plan,
                action=OperationAction.RETRY,
                status=PlanStatus.READY,
                destination=plan.destination,
                reason=f"Retry of operation {operation_id}",
                size_bytes=operation["size_bytes"],
                checksum=operation["checksum"],
                parent_operation_id=operation_id,
            )

        return True

    def _build_plan(
        self,
        current_path: Path,
        media_type: str,
    ) -> Plan:
        if media_type == "movie":
            return plan_movie(
                source=current_path,
                destination_root=self.config.movies.destination,
            )

        if media_type == "series":
            return plan_episode(
                source=current_path,
                destination_root=self.config.series.destination,
            )

        raise RetryError(
            f"Unsupported media type: {media_type}"
        )