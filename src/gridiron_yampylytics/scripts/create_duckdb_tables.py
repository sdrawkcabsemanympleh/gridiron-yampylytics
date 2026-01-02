"""CLI wrapper for DuckDB table creation.

This script is a thin wrapper around the create_duckdb_tables function.
For programmatic use, import and call the function directly:

    from src.gridiron_yampylytics.database.tables import create_duckdb_tables
    result = create_duckdb_tables(include_pbp=False)

Usage:
    uv run python -m scripts.create_duckdb_tables
    uv run python -m scripts.create_duckdb_tables --include-pbp

Creates a DuckDB database with materialized tables and optimized indexes.

Database size: ~580 MB (default) | ~3.2 GB (with pbp)
"""
import sys
import argparse
from src.gridiron_yampylytics.database.tables import create_duckdb_tables


def main() -> None:
    """CLI entry point for DuckDB table creation."""
    # Configure UTF-8 output for Windows console
    if sys.platform == 'win32':
        sys.stdout.reconfigure(encoding='utf-8')

    parser = argparse.ArgumentParser(
        description="Create DuckDB database with materialized tables and indexes"
    )
    parser.add_argument(
        "--include-pbp",
        action="store_true",
        help="Include play-by-play data (adds ~2.6 GB to database)",
    )
    args = parser.parse_args()

    result = create_duckdb_tables(include_pbp=args.include_pbp)

    # Exit if user aborted
    if result.get('aborted'):
        sys.exit(1)


if __name__ == "__main__":
    main()
