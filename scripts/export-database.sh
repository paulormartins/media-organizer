#!/usr/bin/env bash

set -euo pipefail

SOURCE_DATABASE="$HOME/.local/share/media-organizer/history.db"
EXPORT_DIRECTORY="$HOME/sqlite-export"
EXPORT_DATABASE="$EXPORT_DIRECTORY/history-copy.db"
TEMP_DATABASE="$EXPORT_DIRECTORY/history-copy.tmp.db"

mkdir -p "$EXPORT_DIRECTORY"

if [[ ! -f "$SOURCE_DATABASE" ]]; then
    echo "Source database not found: $SOURCE_DATABASE" >&2
    exit 1
fi

rm -f "$TEMP_DATABASE"

sqlite3 "$SOURCE_DATABASE" \
    ".backup '$TEMP_DATABASE'"

mv -f "$TEMP_DATABASE" "$EXPORT_DATABASE"

echo "Database exported successfully:"
echo "$EXPORT_DATABASE"