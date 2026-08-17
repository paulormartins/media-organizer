from __future__ import annotations

import logging
import time
from pathlib import Path
from threading import Event, Lock, Thread, Timer

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from .jellyfin import JellyfinClient
from .models import AppConfig, Plan
from .organizer import Organizer
from .parser import (
    VIDEO_EXTENSIONS,
    plan_episode,
    plan_movie,
)
from .refresh_scheduler import RefreshScheduler
from .arr_client import ArrClient

import time

IGNORED_FILE_NAMES = {
    ".DS_Store",
    "Thumbs.db",
    "desktop.ini",
}

IGNORED_FILE_PREFIXES = {
    ".",
    "._",
}


def is_supported_media_file(path: Path) -> bool:
    """Return True when a path is a supported, non-hidden media file."""

    if path.name in IGNORED_FILE_NAMES:
        return False

    if any(
        path.name.startswith(prefix)
        for prefix in IGNORED_FILE_PREFIXES
    ):
        return False

    return path.suffix.lower() in VIDEO_EXTENSIONS


class MediaEventHandler(FileSystemEventHandler):
    """Handle new, modified, and moved media files."""

    def __init__(
        self,
        config: AppConfig,
        organizer: Organizer,
    ) -> None:
        self.config = config
        self.organizer = organizer

        self._timers: dict[Path, Timer] = {}
        self._processing: set[Path] = set()
        self._lock = Lock()

    def on_created(
        self,
        event: FileSystemEvent,
    ) -> None:
        self._handle_event(event)

    def on_modified(
        self,
        event: FileSystemEvent,
    ) -> None:
        self._handle_event(event)

    def on_moved(
        self,
        event: FileSystemEvent,
    ) -> None:
        if event.is_directory:
            return

        destination_path = getattr(
            event,
            "dest_path",
            event.src_path,
        )

        self.schedule(Path(destination_path))

    def _handle_event(
        self,
        event: FileSystemEvent,
    ) -> None:
        if event.is_directory:
            return

        self.schedule(Path(event.src_path))

    def schedule(
        self,
        path: Path,
        delay_seconds: float | None = None,
    ) -> None:
        """Schedule a file for processing after a debounce delay."""

        if not is_supported_media_file(path):
            logging.debug(
                "Ignoring unsupported or hidden file: %s",
                path,
            )
            return

        delay = (
            float(self.config.minimum_age_seconds)
            if delay_seconds is None
            else max(float(delay_seconds), 1.0)
        )

        with self._lock:
            existing_timer = self._timers.pop(
                path,
                None,
            )

            if existing_timer is not None:
                existing_timer.cancel()

            timer = Timer(
                delay,
                self._process_safely,
                args=(path,),
            )

            timer.daemon = True
            self._timers[path] = timer
            timer.start()

        logging.info(
            "Media file scheduled for processing in %.1f seconds: %s",
            delay,
            path,
        )

    def process_existing_file(
        self,
        path: Path,
    ) -> None:
        """
        Schedule a file found by the recovery scanner.

        Files already older than minimum_age_seconds are processed
        almost immediately. Newer files wait only for their remaining age.
        """

        if not is_supported_media_file(path):
            return

        remaining_seconds = self._remaining_age_seconds(path)

        self.schedule(
            path=path,
            delay_seconds=max(
                remaining_seconds,
                1.0,
            ),
        )

    def _process_safely(
        self,
        path: Path,
    ) -> None:
        with self._lock:
            self._timers.pop(
                path,
                None,
            )

            if path in self._processing:
                logging.debug(
                    "File is already being processed: %s",
                    path,
                )
                return

            self._processing.add(path)

        try:
            self._process_file(path)

        except Exception:
            logging.exception(
                "Unexpected error while processing media file: %s",
                path,
            )

        finally:
            with self._lock:
                self._processing.discard(path)

    def _process_file(
        self,
        path: Path,
    ) -> None:
        if not path.exists():
            logging.info(
                "File no longer exists; skipping: %s",
                path,
            )
            return

        if not path.is_file():
            logging.warning(
                "Path is not a regular file: %s",
                path,
            )
            return

        if not is_supported_media_file(path):
            return

        if not self._is_old_enough(path):
            remaining_seconds = self._remaining_age_seconds(path)

            logging.info(
                "File is too new; rescheduling in %.1f seconds: %s",
                remaining_seconds,
                path,
            )

            self.schedule(
                path=path,
                delay_seconds=max(
                    remaining_seconds,
                    1.0,
                ),
            )
            return

        if not self._is_stable(path):
            logging.info(
                "File is still changing; rescheduling: %s",
                path,
            )

            self.schedule(
                path=path,
                delay_seconds=float(
                    self.config.minimum_age_seconds
                ),
            )
            return

        plan = self._build_plan(path)

        logging.info(
            "Processing media file: source=%s status=%s",
            plan.source,
            plan.status.value,
        )

        applied = self.organizer.apply(plan)

        if applied:
            logging.info(
                "Media processing completed: "
                "source=%s destination=%s",
                plan.source,
                plan.destination,
            )
            return

        logging.warning(
            "Media processing was not applied: "
            "source=%s status=%s reason=%s",
            plan.source,
            plan.status.value,
            plan.reason,
        )

    def _is_old_enough(
        self,
        path: Path,
    ) -> bool:
        try:
            age_seconds = (
                time.time()
                - path.stat().st_mtime
            )

        except OSError as exc:
            logging.warning(
                "Unable to determine file age: file=%s error=%s",
                path,
                exc,
            )
            return False

        return (
            age_seconds
            >= self.config.minimum_age_seconds
        )

    def _remaining_age_seconds(
        self,
        path: Path,
    ) -> float:
        try:
            age_seconds = (
                time.time()
                - path.stat().st_mtime
            )

        except OSError:
            return float(
                self.config.minimum_age_seconds
            )

        return max(
            float(self.config.minimum_age_seconds)
            - age_seconds,
            1.0,
        )

    def _is_stable(
        self,
        path: Path,
    ) -> bool:
        try:
            first_stat = path.stat()

            time.sleep(
                self.config.verify_interval_seconds
            )

            if not path.exists():
                return False

            second_stat = path.stat()

        except OSError as exc:
            logging.warning(
                "Unable to inspect file stability: "
                "file=%s error=%s",
                path,
                exc,
            )
            return False

        return (
            first_stat.st_size
            == second_stat.st_size
            and first_stat.st_mtime_ns
            == second_stat.st_mtime_ns
        )

    def _build_plan(
        self,
        path: Path,
    ) -> Plan:
        if path.is_relative_to(
            self.config.movies.source
        ):
            return plan_movie(
                source=path,
                destination_root=(
                    self.config.movies.destination
                ),
            )

        if path.is_relative_to(
            self.config.series.source
        ):
            return plan_episode(
                source=path,
                destination_root=(
                    self.config.series.destination
                ),
            )

        raise ValueError(
            "File is outside configured staging directories: "
            f"{path}"
        )

    def cancel_all(self) -> None:
        """Cancel all pending processing timers."""

        with self._lock:
            timers = list(
                self._timers.values()
            )

            self._timers.clear()

        for timer in timers:
            timer.cancel()


class StagingScanner:
    """Periodically recover files missed by filesystem events."""

    def __init__(
        self,
        config: AppConfig,
        handler: MediaEventHandler,
        interval_seconds: float = 300.0,
    ) -> None:
        if interval_seconds <= 0:
            raise ValueError(
                "interval_seconds must be greater than zero"
            )

        self.config = config
        self.handler = handler
        self.interval_seconds = interval_seconds

        self._stop_event = Event()
        self._thread: Thread | None = None

    def start(self) -> None:
        """Run an initial scan and start periodic recovery scans."""

        self.scan_once()

        self._thread = Thread(
            target=self._run,
            name="media-organizer-staging-scanner",
            daemon=True,
        )

        self._thread.start()

        logging.info(
            "Periodic staging scan enabled every %.1f seconds",
            self.interval_seconds,
        )

    def stop(self) -> None:
        """Stop the periodic scanner."""

        self._stop_event.set()

        if self._thread is not None:
            self._thread.join(timeout=10)

    def scan_once(self) -> None:
        """Scan movie and series staging directories once."""

        total_found = 0

        for root in (
            self.config.movies.source,
            self.config.series.source,
        ):
            if not root.exists():
                logging.warning(
                    "Staging directory does not exist: %s",
                    root,
                )
                continue

            try:
                paths = list(root.rglob("*"))

            except OSError:
                logging.exception(
                    "Unable to scan staging directory: %s",
                    root,
                )
                continue

            for path in paths:
                try:
                    if not path.is_file():
                        continue

                except OSError:
                    logging.warning(
                        "Unable to inspect staging path: %s",
                        path,
                    )
                    continue

                if not is_supported_media_file(path):
                    continue

                total_found += 1

                self.handler.process_existing_file(path)

        logging.info(
            "Staging scan completed: supported_files_found=%s",
            total_found,
        )

    def _run(self) -> None:
        while not self._stop_event.wait(
            self.interval_seconds
        ):
            try:
                self.scan_once()

            except Exception:
                logging.exception(
                    "Unexpected error during periodic staging scan"
                )

def run(
    config: AppConfig,
    dry_run: bool = False,
) -> None:
    """Start the filesystem watcher and staging recovery scanner."""

    required_directories = (
        config.movies.source,
        config.movies.destination,
        config.series.source,
        config.series.destination,
        config.quarantine.path,
    )

    for directory in required_directories:
        directory.mkdir(
            parents=True,
            exist_ok=True,
        )

    jellyfin_client = JellyfinClient(
        integration=config.jellyfin,
    )

    radarr_client = ArrClient(
        name="Radarr",
        integration=config.radarr,
    )

    sonarr_client = ArrClient(
        name="Sonarr",
        integration=config.sonarr,
    )

    refresh_scheduler = RefreshScheduler(
        jellyfin=jellyfin_client,
        radarr=radarr_client,
        sonarr=sonarr_client,
        delay_seconds=30.0,
    )

    organizer = Organizer(
        config=config,
        dry_run=dry_run,
        refresh_scheduler=refresh_scheduler,
    )

    handler = MediaEventHandler(
        config=config,
        organizer=organizer,
    )

    observer = Observer()

    observer.schedule(
        handler,
        str(config.movies.source),
        recursive=True,
    )

    observer.schedule(
        handler,
        str(config.series.source),
        recursive=True,
    )

    scanner = StagingScanner(
        config=config,
        handler=handler,
        interval_seconds=300.0,
    )

    observer.start()
    scanner.start()

    logging.info(
        "Watching movie staging directory: %s",
        config.movies.source,
    )

    logging.info(
        "Watching series staging directory: %s",
        config.series.source,
    )

    try:
        while True:
            if not observer.is_alive():
                raise RuntimeError(
                    "Filesystem observer stopped unexpectedly"
                )

            time.sleep(1)

    except KeyboardInterrupt:
        logging.info(
            "Watcher shutdown requested"
        )

    finally:
        logging.info(
            "Stopping media watcher"
        )

        scanner.stop()

        observer.stop()
        observer.join(timeout=10)

        handler.cancel_all()
        refresh_scheduler.flush()

        logging.info(
            "Media watcher stopped"
        )