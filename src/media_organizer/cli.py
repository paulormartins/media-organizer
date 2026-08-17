from __future__ import annotations

import argparse
import logging
from pathlib import Path

from .config import load_config
from .health import HealthService, print_health_report
from .history import HistoryDatabase
from .quarantine_cleanup import QuarantineCleanup
from .quarantine_resolver import QuarantineResolver
from .retry import RetryError, RetryService
from .safety import SafetyError, validate_environment
from .scanner import LibraryScanner
from .undo import UndoError, UndoService
from .watcher import run


def build_parser() -> argparse.ArgumentParser:
    """Build the Media Organizer command-line parser."""

    parser = argparse.ArgumentParser(
        description="Media Organizer",
    )

    parser.add_argument(
        "--config",
        type=Path,
        default=Path(
            "/etc/media-organizer/config.yaml"
        ),
        help="Path to the YAML configuration file",
    )

    subparsers = parser.add_subparsers(
        dest="command",
    )

    watch_parser = subparsers.add_parser(
        "watch",
        help="Start the media filesystem watcher",
    )

    watch_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate operations without moving files",
    )

    subparsers.add_parser(
        "check",
        help="Validate configuration and runtime safety",
    )

    subparsers.add_parser(
        "health",
        help=(
            "Run health checks for Media Organizer "
            "and its integrations"
        ),
    )

    history_parser = subparsers.add_parser(
        "history",
        help="Display recent media operations",
    )

    history_parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum number of history entries to display",
    )

    retry_parser = subparsers.add_parser(
        "retry",
        help="Retry a previous quarantine operation",
    )

    retry_parser.add_argument(
        "operation_id",
        type=int,
        help="Quarantine operation ID to retry",
    )

    retry_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate the retry without moving files",
    )

    resolve_parser = subparsers.add_parser(
        "resolve-quarantine",
        help=(
            "Analyze files quarantined because "
            "destinations already existed"
        ),
    )

    resolve_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be removed without changing files",
    )

    resolve_parser.add_argument(
        "--delete-confirmed",
        action="store_true",
        help=(
            "Delete files only when size and SHA-256 "
            "match the destination"
        ),
    )

    scan_parser = subparsers.add_parser(
        "scan-library",
        help=(
            "Scan and repair existing movie "
            "and series libraries"
        ),
    )

    scan_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Display planned changes without moving files",
    )

    undo_parser = subparsers.add_parser(
        "undo",
        help=(
            "Reverse a previous import "
            "or quarantine operation"
        ),
    )

    undo_parser.add_argument(
        "operation_id",
        type=int,
        help="History operation ID to reverse",
    )

    undo_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate the undo without moving files",
    )

    cleanup_parser = subparsers.add_parser(
        "cleanup-quarantine",
        help="Perform maintenance on the quarantine directory",
    )

    cleanup_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate operations without removing files",
    )

    return parser


def configure_logging() -> None:
    """Configure application logging."""

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )


def load_configuration(
    config_path: Path,
):
    """Load configuration without running environment safety checks."""

    try:
        return load_config(config_path)

    except FileNotFoundError as exc:
        logging.critical(
            "Configuration file not found: %s",
            exc,
        )
        raise SystemExit(1) from exc

    except KeyError as exc:
        logging.critical(
            "Required configuration field is missing: %s",
            exc,
        )
        raise SystemExit(1) from exc

    except (TypeError, ValueError) as exc:
        logging.critical(
            "Invalid configuration value: %s",
            exc,
        )
        raise SystemExit(1) from exc


def load_and_validate_config(
    config_path: Path,
):
    """Load configuration and validate the runtime environment."""

    config = load_configuration(
        config_path
    )

    try:
        validate_environment(config)

    except SafetyError as exc:
        logging.critical(
            "Safety validation failed: %s",
            exc,
        )
        raise SystemExit(1) from exc

    except OSError as exc:
        logging.critical(
            "Environment validation failed: %s",
            exc,
        )
        raise SystemExit(1) from exc

    return config


def display_history(
    history: HistoryDatabase,
    limit: int,
) -> None:
    """Print recent history operations."""

    rows = history.list_recent(
        limit=limit,
    )

    if not rows:
        print("No history entries found.")
        return

    for row in rows:
        print(
            f"[{row['id']}] "
            f"{row['created_at']} "
            f"{row['action']} "
            f"{row['status']} "
            f"{row['media_type']}"
        )

        print(
            f"  Source:      {row['source']}"
        )

        if row["destination"]:
            print(
                f"  Destination: {row['destination']}"
            )

        if row["reason"]:
            print(
                f"  Reason:      {row['reason']}"
            )

        if row["size_bytes"] is not None:
            print(
                "  Size:        "
                f"{format_file_size(row['size_bytes'])}"
            )

        print()


def format_file_size(
    size_bytes: int,
) -> str:
    """Format a byte count using binary units."""

    size = float(size_bytes)

    for unit in (
        "B",
        "KiB",
        "MiB",
        "GiB",
        "TiB",
    ):
        if size < 1024 or unit == "TiB":
            return f"{size:.1f} {unit}"

        size /= 1024

    return f"{size_bytes} B"


def run_health_command(
    config_path: Path,
) -> None:
    """
    Run health checks without pre-validating the environment.

    HealthService must be allowed to report mount, UUID, disk,
    database, service, and integration failures itself.
    """

    config = load_configuration(
        config_path
    )

    service = HealthService(
        config=config,
    )

    healthy = print_health_report(
        service.run_all()
    )

    if not healthy:
        raise SystemExit(1)


def run_history_command(
    config,
    limit: int,
) -> None:
    """Display operation history."""

    history = HistoryDatabase(
        database_path=config.database.path,
        enabled=config.database.enabled,
    )

    history.initialize()

    display_history(
        history=history,
        limit=max(1, limit),
    )


def run_retry_command(
    config,
    operation_id: int,
    dry_run: bool,
) -> None:
    """Retry a previous quarantine operation."""

    history = HistoryDatabase(
        database_path=config.database.path,
        enabled=config.database.enabled,
    )

    history.initialize()

    service = RetryService(
        config=config,
        history=history,
        dry_run=dry_run,
    )

    try:
        service.retry(
            operation_id=operation_id,
        )

    except RetryError as exc:
        logging.critical(
            "Retry failed: %s",
            exc,
        )
        raise SystemExit(1) from exc


def run_undo_command(
    config,
    operation_id: int,
    dry_run: bool,
) -> None:
    """Reverse a previous history operation."""

    history = HistoryDatabase(
        database_path=config.database.path,
        enabled=config.database.enabled,
    )

    history.initialize()

    service = UndoService(
        config=config,
        history=history,
        dry_run=dry_run,
    )

    try:
        service.undo(
            operation_id=operation_id,
        )

    except UndoError as exc:
        logging.critical(
            "Undo failed: %s",
            exc,
        )
        raise SystemExit(1) from exc


def run_library_scan_command(
    config,
    dry_run: bool,
) -> None:
    """Run a library scan and print statistics."""

    scanner = LibraryScanner(
        config=config,
        dry_run=dry_run,
    )

    statistics = scanner.scan_all()

    print()
    print("Library scan completed")
    print(
        "  Files scanned:    "
        f"{statistics['files_scanned']}"
    )
    print(
        "  Already correct:  "
        f"{statistics['already_correct']}"
    )
    print(
        "  Reorganized:      "
        f"{statistics['reorganized']}"
    )
    print(
        "  Quarantined:      "
        f"{statistics['quarantined']}"
    )
    print(
        "  Failed:           "
        f"{statistics['failed']}"
    )

    if dry_run:
        print()
        print(
            "Dry-run completed. "
            "No files were modified."
        )


def run_quarantine_cleanup_command(
    config,
    dry_run: bool,
) -> None:
    """Run non-destructive quarantine maintenance."""

    cleaner = QuarantineCleanup(
        config=config,
        dry_run=dry_run,
    )

    statistics = cleaner.run()

    print()
    print("Quarantine cleanup completed")
    print(
        "  Hidden files found:        "
        f"{statistics['hidden_files_found']}"
    )
    print(
        "  Hidden files removed:      "
        f"{statistics['hidden_files_removed']}"
    )
    print(
        "  Empty directories removed: "
        f"{statistics['empty_directories_removed']}"
    )
    print(
        "  Media files preserved:     "
        f"{statistics['media_files_preserved']}"
    )
    print(
        "  Errors:                    "
        f"{statistics['errors']}"
    )

    if dry_run:
        print()
        print(
            "Dry-run completed. "
            "No files were modified."
        )


def run_quarantine_resolution_command(
    config,
    dry_run: bool,
    delete_confirmed: bool,
) -> None:
    """Analyze and optionally delete confirmed duplicates."""

    resolver = QuarantineResolver(
        config=config,
        dry_run=dry_run,
        delete_confirmed=delete_confirmed,
    )

    statistics = resolver.run()

    print()
    print("Quarantine resolution completed")
    print(
        "  Operations checked:        "
        f"{statistics['operations_checked']}"
    )
    print(
        "  Confirmed duplicates:      "
        f"{statistics['confirmed_duplicates']}"
    )
    print(
        "  Different files preserved: "
        f"{statistics['different_files']}"
    )
    print(
        "  Missing quarantine files:  "
        f"{statistics['missing_quarantine_files']}"
    )
    print(
        "  Missing destination files: "
        f"{statistics['missing_destination_files']}"
    )
    print(
        "  Deleted duplicates:        "
        f"{statistics['deleted_duplicates']}"
    )
    print(
        "  Errors:                    "
        f"{statistics['errors']}"
    )

    if dry_run:
        print()
        print(
            "Dry-run completed. "
            "No files were modified."
        )


def main() -> None:
    """Run the Media Organizer CLI."""

    args = build_parser().parse_args()
    configure_logging()

    command = args.command or "watch"

    if command == "health":
        run_health_command(
            config_path=args.config,
        )
        return

    config = load_and_validate_config(
        args.config
    )

    if command == "check":
        logging.info(
            "Configuration and environment validation "
            "completed successfully"
        )
        return

    if command == "history":
        run_history_command(
            config=config,
            limit=args.limit,
        )
        return

    if command == "resolve-quarantine":
        run_quarantine_resolution_command(
            config=config,
            dry_run=args.dry_run,
            delete_confirmed=args.delete_confirmed,
        )
        return

    if command == "retry":
        run_retry_command(
            config=config,
            operation_id=args.operation_id,
            dry_run=args.dry_run,
        )
        return

    if command == "scan-library":
        run_library_scan_command(
            config=config,
            dry_run=args.dry_run,
        )
        return

    if command == "cleanup-quarantine":
        run_quarantine_cleanup_command(
            config=config,
            dry_run=args.dry_run,
        )
        return

    if command == "undo":
        run_undo_command(
            config=config,
            operation_id=args.operation_id,
            dry_run=args.dry_run,
        )
        return

    if command == "watch":
        run(
            config=config,
            dry_run=args.dry_run,
        )
        return

    raise SystemExit(
        f"Unsupported command: {command}"
    )


if __name__ == "__main__":
    main()