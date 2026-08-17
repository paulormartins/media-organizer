# Media Organizer

> Intelligent media organizer for Jellyfin, Radarr and Sonarr.

Media Organizer is a Python application that automatically watches staging folders, identifies movies and TV episodes, renames them using a standardized naming convention, moves them into the correct library structure, records every operation in SQLite, and integrates with Jellyfin, Radarr and Sonarr.

The project was designed for home servers and NAS environments where media is frequently added manually or downloaded by external applications.

---

# Features

## Automatic Watcher

- Watches movie and TV staging folders.
- Detects newly added files.
- Waits until files become stable before processing.
- Prevents partially copied files from being moved.

---

## Intelligent Parsing

Automatically recognizes:

Movies

```
Movie.Name.2025.2160p.BluRay.mkv
```

↓

```
Movie Name (2025)
```

Episodes

```
House.of.the.Dragon.S03E07.2160p.mkv
```

↓

```
House of the Dragon
Season 03
Episode 07
```

---

## Automatic Library Organization

Movies

```
Movies/

Movie Name (2025)/
    Movie Name (2025).mkv
```

Series

```
Series/

House of the Dragon/
    Season 03/
        House of the Dragon - S03E07.mkv
```

---

## SQLite History

Every operation is permanently recorded.

Stored information includes:

- source path
- destination path
- media type
- timestamp
- operation
- status
- reason

Supports:

- Undo
- Retry
- History

---

## Health Check

```
media-organizer health
```

Example

```
✓ Environment
✓ SQLite
✓ Watcher
✓ Jellyfin
✓ Radarr
✓ Sonarr
```

---

## Library Scanner

Normalize an existing library.

```
media-organizer scan-library
```

Supports:

- dry-run
- quarantine
- history
- automatic rename

---

## Quarantine

Files that cannot be identified are automatically isolated.

Example

```
Metal - A Headbanger's Journey.mp4
```

↓

```
TEMP/
    Quarantine/
        unknown/
```

Nothing is deleted automatically.

---

## Undo

```
media-organizer undo 25
```

Moves a file back to its original location.

---

## Retry

```
media-organizer retry 25
```

Attempts to organize a previously failed operation.

---

## Dry Run

Every major command supports safe execution.

Example

```
media-organizer scan-library --dry-run
```

No files are modified.

---

## Jellyfin Integration

Automatically requests a library refresh after imports.

Multiple imports are grouped into a single refresh request.

---

## Radarr Integration

Automatically requests

```
RefreshMovie
```

after movie imports.

---

## Sonarr Integration

Automatically requests

```
RefreshSeries
```

after episode imports.

---

# Architecture

```
                   New File
                       │
                       ▼
                Directory Watcher
                       │
                       ▼
                   Parser
                       │
            ┌──────────┴──────────┐
            ▼                     ▼
      Valid Media           Unknown Media
            │                     │
            ▼                     ▼
       Organizer            Quarantine
            │
            ▼
        SQLite History
            │
            ▼
      Refresh Scheduler
            │
     ┌──────┼─────────┐
     ▼      ▼         ▼
 Jellyfin Radarr    Sonarr
```

---

# Project Structure

```
src/
    media_organizer/

        parser.py

        organizer.py

        scanner.py

        watcher.py

        history.py

        retry.py

        undo.py

        safety.py

        health.py

        jellyfin.py

        arr_client.py

        refresh_scheduler.py

        cli.py
```

---

# Installation

Clone

```
git clone https://github.com/paulormartins/media-organizer.git
```

Create virtual environment

```
python -m venv .venv
```

Install

```
pip install -e .
```

---

# Configuration

```
/etc/media-organizer/config.yaml
```

Example

```yaml
watcher:

movies:

series:

database:

quarantine:

integrations:
```

---

# Available Commands

Health

```
media-organizer health
```

Watch

```
media-organizer
```

History

```
media-organizer history
```

Undo

```
media-organizer undo 5
```

Retry

```
media-organizer retry 5
```

Scan Library

```
media-organizer scan-library
```

Dry Run

```
media-organizer scan-library --dry-run
```

---

# Safety

Media Organizer never:

- deletes files
- overwrites existing media
- renames existing folders without confirmation

Unknown files are moved to quarantine.

---

# Current Status

Implemented

- Watcher
- Parser
- Organizer
- Library Scanner
- SQLite History
- Retry
- Undo
- Health Check
- Quarantine
- Jellyfin Integration
- Radarr Integration
- Sonarr Integration
- Refresh Scheduler

---

# Roadmap

Upcoming

- Web Dashboard
- TMDb metadata lookup
- Duplicate detection
- Automatic subtitle organization
- Docker image
- REST API
- Webhooks
- Metrics
- Pytest suite
- GitHub Actions

---

# License

MIT

---

# Author

Paulo Rafael Costa Martins

Computer Engineer

GitHub

https://github.com/paulormartins