"""CLI wrapper for data status utility.

This script is a thin wrapper around the show_status function.
For programmatic use, import and call the function directly:

    from src.gridiron_yampylytics.utils.status import show_status
    result = show_status()

Usage:
    uv run python -m scripts.show_status

Shows status of downloaded data files and database, providing
a quick overview of what's available locally.
"""
import sys
from src.gridiron_yampylytics.utils.status import show_status


def main() -> None:
    """CLI entry point for status display."""
    sys.stdout.reconfigure(encoding='utf-8')
    show_status()


if __name__ == "__main__":
    main()
