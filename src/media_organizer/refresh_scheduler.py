from __future__ import annotations

import logging
from threading import Lock, Timer

from .arr_client import ArrClient, ArrError
from .jellyfin import JellyfinClient, JellyfinError


class RefreshScheduler:
    """
    Group refresh requests for Jellyfin, Radarr, and Sonarr.

    Multiple imports received within the debounce interval generate
    only one refresh request for each affected integration.
    """

    SUPPORTED_MEDIA_TYPES = {
        "movie",
        "series",
    }

    def __init__(
        self,
        jellyfin: JellyfinClient,
        radarr: ArrClient,
        sonarr: ArrClient,
        delay_seconds: float = 30.0,
    ) -> None:
        if delay_seconds <= 0:
            raise ValueError(
                "delay_seconds must be greater than zero"
            )

        self.jellyfin = jellyfin
        self.radarr = radarr
        self.sonarr = sonarr
        self.delay_seconds = delay_seconds

        self._timer: Timer | None = None
        self._lock = Lock()

        self._pending_movies = 0
        self._pending_episodes = 0

    def request_refresh(
        self,
        media_type: str,
    ) -> None:
        """Schedule refreshes for one successfully imported item."""

        normalized_media_type = media_type.strip().lower()

        if normalized_media_type not in self.SUPPORTED_MEDIA_TYPES:
            logging.warning(
                "Refresh ignored for unsupported media type: %s",
                media_type,
            )
            return

        with self._lock:
            if normalized_media_type == "movie":
                self._pending_movies += 1
            else:
                self._pending_episodes += 1

            if self._timer is not None:
                self._timer.cancel()

            self._timer = Timer(
                self.delay_seconds,
                self._execute_pending_refreshes,
            )

            self._timer.daemon = True
            self._timer.start()

            pending_movies = self._pending_movies
            pending_episodes = self._pending_episodes

        logging.info(
            "Integration refresh scheduled in %.1f seconds "
            "(movies=%s episodes=%s)",
            self.delay_seconds,
            pending_movies,
            pending_episodes,
        )

    def flush(self) -> None:
        """Immediately execute pending refresh requests."""

        with self._lock:
            timer = self._timer
            self._timer = None

            pending_movies = self._pending_movies
            pending_episodes = self._pending_episodes

            self._pending_movies = 0
            self._pending_episodes = 0

            if timer is not None:
                timer.cancel()

        self._refresh_services(
            pending_movies=pending_movies,
            pending_episodes=pending_episodes,
        )

    def cancel(self) -> None:
        """Cancel every pending refresh."""

        with self._lock:
            if self._timer is not None:
                self._timer.cancel()

            self._timer = None
            self._pending_movies = 0
            self._pending_episodes = 0

    def _execute_pending_refreshes(self) -> None:
        with self._lock:
            self._timer = None

            pending_movies = self._pending_movies
            pending_episodes = self._pending_episodes

            self._pending_movies = 0
            self._pending_episodes = 0

        self._refresh_services(
            pending_movies=pending_movies,
            pending_episodes=pending_episodes,
        )

    def _refresh_services(
        self,
        pending_movies: int,
        pending_episodes: int,
    ) -> None:
        total_imports = (
            pending_movies
            + pending_episodes
        )

        if total_imports == 0:
            return

        self._refresh_jellyfin(
            total_imports=total_imports,
        )

        if pending_movies > 0:
            self._refresh_radarr(
                pending_movies=pending_movies,
            )

        if pending_episodes > 0:
            self._refresh_sonarr(
                pending_episodes=pending_episodes,
            )

    def _refresh_jellyfin(
        self,
        total_imports: int,
    ) -> None:
        if not self.jellyfin.enabled:
            return

        try:
            self.jellyfin.refresh_library()

        except JellyfinError as exc:
            logging.error(
                "Jellyfin refresh failed after %s imports: %s",
                total_imports,
                exc,
            )
            return

        logging.info(
            "Jellyfin refresh completed for %s imports",
            total_imports,
        )

    def _refresh_radarr(
        self,
        pending_movies: int,
    ) -> None:
        if not self.radarr.enabled:
            return

        try:
            response = self.radarr.execute_command(
                "RefreshMovie"
            )

        except ArrError as exc:
            logging.error(
                "Radarr refresh failed after %s movie imports: %s",
                pending_movies,
                exc,
            )
            return

        logging.info(
            "Radarr refresh requested for %s movie imports "
            "(command_id=%s)",
            pending_movies,
            response.get("id"),
        )

    def _refresh_sonarr(
        self,
        pending_episodes: int,
    ) -> None:
        if not self.sonarr.enabled:
            return

        try:
            response = self.sonarr.execute_command(
                "RefreshSeries"
            )

        except ArrError as exc:
            logging.error(
                "Sonarr refresh failed after %s episode imports: %s",
                pending_episodes,
                exc,
            )
            return

        logging.info(
            "Sonarr refresh requested for %s episode imports "
            "(command_id=%s)",
            pending_episodes,
            response.get("id"),
        )