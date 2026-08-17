from __future__ import annotations

import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from .models import OperationAction, Plan, PlanStatus


class HistoryDatabase:
    """Stores and retrieves media organization operations in SQLite."""

    def __init__(
        self,
        database_path: Path,
        enabled: bool = True,
    ) -> None:
        self.database_path = database_path
        self.enabled = enabled

    def initialize(self) -> None:
        """Create the database schema when it does not exist."""

        if not self.enabled:
            logging.info("History database is disabled.")
            return

        self.database_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        with self._connection() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS operations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    action TEXT NOT NULL,
                    status TEXT NOT NULL,
                    media_type TEXT NOT NULL,
                    source TEXT NOT NULL,
                    destination TEXT,
                    title TEXT,
                    year TEXT,
                    season INTEGER,
                    episode INTEGER,
                    reason TEXT,
                    size_bytes INTEGER,
                    checksum TEXT,
                    parent_operation_id INTEGER,
                    FOREIGN KEY (
                        parent_operation_id
                    ) REFERENCES operations(id)
                )
                """
            )

            self._ensure_column(
                connection=connection,
                column_name="parent_operation_id",
                definition="INTEGER",
            )

            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS
                idx_operations_created_at
                ON operations(created_at)
                """
            )

            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS
                idx_operations_status
                ON operations(status)
                """
            )

            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS
                idx_operations_source
                ON operations(source)
                """
            )

            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS
                idx_operations_parent
                ON operations(parent_operation_id)
                """
            )

        logging.info(
            "History database initialized: %s",
            self.database_path,
        )

    def record(
        self,
        plan: Plan,
        action: OperationAction,
        status: PlanStatus | None = None,
        reason: str | None = None,
        destination: Path | None = None,
        size_bytes: int | None = None,
        checksum: str | None = None,
        parent_operation_id: int | None = None,
    ) -> int | None:
        """Insert one operation into the history database."""

        if not self.enabled:
            return None

        effective_status = status or plan.status

        effective_reason = (
            reason
            if reason is not None
            else plan.reason
        )

        effective_destination = (
            destination
            if destination is not None
            else plan.destination
        )

        with self._connection() as connection:
            cursor = connection.execute(
                """
                INSERT INTO operations (
                    created_at,
                    action,
                    status,
                    media_type,
                    source,
                    destination,
                    title,
                    year,
                    season,
                    episode,
                    reason,
                    size_bytes,
                    checksum,
                    parent_operation_id
                )
                VALUES (
                    ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?
                )
                """,
                (
                    datetime.now(
                        timezone.utc
                    ).isoformat(),
                    action.value,
                    effective_status.value,
                    plan.media_type,
                    str(plan.source),
                    str(effective_destination),
                    plan.title,
                    plan.year,
                    plan.season,
                    plan.episode,
                    effective_reason,
                    size_bytes,
                    checksum,
                    parent_operation_id,
                ),
            )

            operation_id = cursor.lastrowid

        logging.info(
            "Operation recorded: id=%s action=%s",
            operation_id,
            action.value,
        )

        return operation_id

    def list_recent(
        self,
        limit: int = 20,
    ) -> list[sqlite3.Row]:
        """Return recent operations ordered from newest to oldest."""

        if not self.enabled:
            return []

        with self._connection() as connection:
            cursor = connection.execute(
                """
                SELECT
                    id,
                    created_at,
                    action,
                    status,
                    media_type,
                    source,
                    destination,
                    title,
                    year,
                    season,
                    episode,
                    reason,
                    size_bytes,
                    checksum,
                    parent_operation_id
                FROM operations
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            )

            return list(cursor.fetchall())

    def get_operation(
        self,
        operation_id: int,
    ) -> sqlite3.Row | None:
        """Return one operation by ID."""

        if not self.enabled:
            return None

        with self._connection() as connection:
            cursor = connection.execute(
                """
                SELECT
                    id,
                    created_at,
                    action,
                    status,
                    media_type,
                    source,
                    destination,
                    title,
                    year,
                    season,
                    episode,
                    reason,
                    size_bytes,
                    checksum,
                    parent_operation_id
                FROM operations
                WHERE id = ?
                """,
                (operation_id,),
            )

            return cursor.fetchone()

    def was_undone(
        self,
        operation_id: int,
    ) -> bool:
        """Return True when an operation already has an UNDO record."""

        if not self.enabled:
            return False

        with self._connection() as connection:
            cursor = connection.execute(
                """
                SELECT 1
                FROM operations
                WHERE
                    action = ?
                    AND parent_operation_id = ?
                LIMIT 1
                """,
                (
                    OperationAction.UNDO.value,
                    operation_id,
                ),
            )

            return cursor.fetchone() is not None

    @staticmethod
    def _ensure_column(
        connection: sqlite3.Connection,
        column_name: str,
        definition: str,
    ) -> None:
        """Add a missing column to an existing database."""

        columns = {
            row["name"]
            for row in connection.execute(
                "PRAGMA table_info(operations)"
            ).fetchall()
        }

        if column_name not in columns:
            connection.execute(
                f"""
                ALTER TABLE operations
                ADD COLUMN {column_name} {definition}
                """
            )

    @contextmanager
    def _connection(
        self,
    ) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(
            self.database_path,
            timeout=30,
        )

        connection.row_factory = sqlite3.Row

        try:
            connection.execute(
                "PRAGMA journal_mode=WAL"
            )

            connection.execute(
                "PRAGMA foreign_keys=ON"
            )

            yield connection
            connection.commit()

        except Exception:
            connection.rollback()
            raise

        finally:
            connection.close()