from __future__ import annotations

import logging
from pathlib import Path

from .models import AppConfig, Plan, PlanStatus
from .organizer import Organizer
from .parser import (
    VIDEO_EXTENSIONS,
    plan_episode,
    plan_movie,
)


class LibraryScanner:
    """Scans existing libraries and repairs files outside the expected layout."""

    def __init__(
        self,
        config: AppConfig,
        dry_run: bool = False,
    ) -> None:
        self.config = config
        self.dry_run = dry_run
        self.organizer = Organizer(
            config=config,
            dry_run=dry_run,
        )

    def scan_all(self) -> dict[str, int]:
        """Scan movie and series libraries."""

        statistics = {
            "files_scanned": 0,
            "already_correct": 0,
            "reorganized": 0,
            "quarantined": 0,
            "failed": 0,
        }

        self._scan_library(
            media_type="movie",
            root=self.config.movies.destination,
            statistics=statistics,
        )

        self._scan_library(
            media_type="series",
            root=self.config.series.destination,
            statistics=statistics,
        )

        return statistics

    def _scan_library(
        self,
        media_type: str,
        root: Path,
        statistics: dict[str, int],
    ) -> None:
        if not root.exists():
            logging.warning(
                "Library directory does not exist: %s",
                root,
            )
            return

        logging.info(
            "Scanning %s library: %s",
            media_type,
            root,
        )

        for source in self._iter_video_files(root):
            statistics["files_scanned"] += 1

            plan = self._build_plan(
                source=source,
                media_type=media_type,
                root=root,
            )

            if plan.status is not PlanStatus.READY:
                logging.warning(
                    "Unable to build a valid plan: "
                    "source=%s status=%s reason=%s",
                    source,
                    plan.status.value,
                    plan.reason,
                )

                if self.organizer.apply(plan):
                    statistics["quarantined"] += 1
                else:
                    statistics["failed"] += 1

                continue

            if self._is_already_correct(plan):
                statistics["already_correct"] += 1

                logging.debug(
                    "File already follows the expected layout: %s",
                    source,
                )
                continue

            if self._destination_conflicts_with_source(
                plan
            ):
                logging.warning(
                    "Destination conflicts with another file: %s",
                    plan.destination,
                )

                conflict_plan = Plan(
                    source=plan.source,
                    destination=plan.destination,
                    media_type=plan.media_type,
                    title=plan.title,
                    year=plan.year,
                    season=plan.season,
                    episode=plan.episode,
                    status=PlanStatus.EXISTS,
                    reason=(
                        "Library scan destination already exists: "
                        f"{plan.destination}"
                    ),
                )

                if self.organizer.apply(conflict_plan):
                    statistics["quarantined"] += 1
                else:
                    statistics["failed"] += 1

                continue

            if self.organizer.apply(plan):
                statistics["reorganized"] += 1
            else:
                statistics["failed"] += 1

    def _build_plan(
        self,
        source: Path,
        media_type: str,
        root: Path,
    ) -> Plan:
        if media_type == "movie":
            return plan_movie(
                source=source,
                destination_root=root,
            )

        if media_type == "series":
            return plan_episode(
                source=source,
                destination_root=root,
            )

        return Plan(
            source=source,
            destination=source,
            media_type=media_type,
            title="",
            status=PlanStatus.ERROR,
            reason=f"Unsupported media type: {media_type}",
        )

    @staticmethod
    def _iter_video_files(
        root: Path,
    ):
        for path in root.rglob("*"):
            if (
                path.is_file()
                and path.suffix.lower()
                in VIDEO_EXTENSIONS
            ):
                yield path

    @staticmethod
    def _is_already_correct(
        plan: Plan,
    ) -> bool:
        try:
            return (
                plan.source.resolve()
                == plan.destination.resolve()
            )
        except OSError:
            return (
                plan.source.absolute()
                == plan.destination.absolute()
            )

    @staticmethod
    def _destination_conflicts_with_source(
        plan: Plan,
    ) -> bool:
        if not plan.destination.exists():
            return False

        try:
            return (
                plan.destination.resolve()
                != plan.source.resolve()
            )
        except OSError:
            return (
                plan.destination.absolute()
                != plan.source.absolute()
            )