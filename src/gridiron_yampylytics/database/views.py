"""DuckDB view creation module.

This module creates a DuckDB database with auto-generated views from all CSV
and Parquet files in the data directory. Views are organized by directory
structure for easy navigation.

For programmatic use:
    from src.gridiron_yampylytics.database.views import create_duckdb_views
    result = create_duckdb_views()

Views are lightweight (no disk space) and always reflect current CSVs.
For faster queries with indexes, use tables instead (see database/tables.py).
"""
import os
import duckdb
from pathlib import Path
from typing import Any


def create_duckdb_views(
    db_path: Path | str | None = None,
    data_dir: Path | str | None = None
) -> dict[str, Any]:
    """Create DuckDB database with views for all CSV and Parquet files.

    Recursively scans the data directory and creates views for all data files.
    Views are named based on directory structure (e.g., data/nflverse/pbp.csv
    becomes nflverse.pbp).

    :param db_path: Path to DuckDB database file (default: gridiron_yampylytics.db)
    :param data_dir: Path to data directory (default: ./data)
    :return: Summary dict with view creation statistics
    """
    # Set default paths
    if db_path is None:
        db_path = Path.cwd() / "gridiron_yampylytics.db"
    else:
        db_path = Path(db_path)

    if data_dir is None:
        data_dir = Path.cwd() / "data"
    else:
        data_dir = Path(data_dir)

    # Set timezone environment variable
    os.environ['DUCKDB_NO_DOWNLOAD_TZDATA'] = '1'

    # Connect to database
    con = duckdb.connect(str(db_path))

    # Track schemas we've created
    created_schemas = set()

    def create_schema_if_needed(schema_name: str) -> str:
        """Create schema if it doesn't exist yet.

        :param schema_name: Name of schema to create
        :return: Sanitized schema name
        """
        # Replace invalid characters with underscores
        safe_schema = schema_name.replace('-', '_').replace(' ', '_')

        if safe_schema not in created_schemas:
            con.execute(f"CREATE SCHEMA IF NOT EXISTS {safe_schema}")
            created_schemas.add(safe_schema)

        return safe_schema

    # Track created views
    csv_views = []
    parquet_views = []

    # Find all CSV files
    for file_path in data_dir.rglob('*.csv'):
        # Get relative path parts from data_dir (excluding 'data' and filename)
        parts = file_path.relative_to(data_dir).parts[:-1]

        if parts:
            # Create schema from directory path (e.g., nflverse -> nflverse)
            schema_name = '_'.join(parts).replace('-', '_').replace(' ', '_')
            schema_name = create_schema_if_needed(schema_name)

            table_name = file_path.stem.replace('-', '_').replace(' ', '_')
            full_name = f"{schema_name}.{table_name}"
        else:
            # File directly in data directory
            table_name = file_path.stem.replace('-', '_').replace(' ', '_')
            full_name = table_name

        con.execute(f"""
            CREATE OR REPLACE VIEW
                {full_name}
                AS
                    SELECT * FROM read_csv(
                        '{file_path}',
                        union_by_name=true,
                        auto_detect=true,
                        null_padding=true
                    )
        """)
        print(f"Created view: {full_name}")
        csv_views.append(full_name)

    # Find all Parquet files
    for file_path in data_dir.rglob('*.parquet'):
        parts = file_path.relative_to(data_dir).parts[:-1]

        if parts:
            schema_name = '_'.join(parts).replace('-', '_').replace(' ', '_')
            schema_name = create_schema_if_needed(schema_name)

            table_name = file_path.stem.replace('-', '_').replace(' ', '_')
            full_name = f"{schema_name}.{table_name}"
        else:
            table_name = file_path.stem.replace('-', '_').replace(' ', '_')
            full_name = table_name

        con.execute(f"CREATE OR REPLACE VIEW {full_name} AS SELECT * FROM '{file_path}'")
        print(f"Created view: {full_name}")
        parquet_views.append(full_name)

    con.close()

    total_views = len(csv_views) + len(parquet_views)

    print(f"\nDone! Created {total_views} views ({len(csv_views)} CSV, {len(parquet_views)} Parquet)")
    print(f"Database: {db_path}")
    print(f"\nNow run: uv run harlequin {db_path}")
    print("\nYour views are organized by directory structure.")
    print("Example: SELECT * FROM nflverse.pbp")

    # Return structured data for programmatic use
    return {
        'total_views': total_views,
        'csv_views': len(csv_views),
        'parquet_views': len(parquet_views),
        'schemas': len(created_schemas),
        'db_path': db_path,
        'view_names': csv_views + parquet_views,
    }
