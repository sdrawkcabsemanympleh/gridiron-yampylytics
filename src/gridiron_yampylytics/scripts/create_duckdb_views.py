"""CLI wrapper for DuckDB view creation.

This script is a thin wrapper around the create_duckdb_views function.
For programmatic use, import and call the function directly:

    from src.gridiron_yampylytics.database.views import create_duckdb_views
    result = create_duckdb_views()

Usage:
    uv run python -m scripts.create_duckdb_views

Creates a DuckDB database with auto-generated views from all CSV and Parquet
files in the data directory. Views are lightweight and always reflect current CSVs.
"""
import sys
from src.gridiron_yampylytics.database.views import create_duckdb_views


def main() -> None:
    """CLI entry point for DuckDB view creation."""
    sys.stdout.reconfigure(encoding='utf-8')
    create_duckdb_views()


if __name__ == "__main__":
    main()
