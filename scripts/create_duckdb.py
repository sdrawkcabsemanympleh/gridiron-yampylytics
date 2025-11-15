import duckdb
import os
from pathlib import Path

os.environ['DUCKDB_NO_DOWNLOAD_TZDATA'] = '1'
con = duckdb.connect('gridiron_yampylytics.db')

# Track schemas we've created
created_schemas = set()


def create_schema_if_needed(schema_name):
    """Create schema if it doesn't exist yet"""
    if schema_name not in created_schemas:
        # Replace invalid characters with underscores
        safe_schema = schema_name.replace('-', '_').replace(' ', '_')
        con.execute(f"CREATE SCHEMA IF NOT EXISTS {safe_schema}")
        created_schemas.add(safe_schema)
        return safe_schema
    return schema_name


# Find all CSV and Parquet files
for file_path in Path('./data').rglob('*.csv'):
    # Get relative path parts from ./data (excluding 'data' and filename)
    parts = file_path.relative_to('./data').parts[:-1]

    if parts:
        # Create schema from directory path (e.g., cached/SOURCE -> cached_SOURCE)
        schema_name = '_'.join(parts).replace('-', '_').replace(' ', '_')
        create_schema_if_needed(schema_name)

        table_name = file_path.stem.replace('-', '_').replace(' ', '_')
        full_name = f"{schema_name}.{table_name}"
    else:
        # File directly in ./data directory
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

for file_path in Path('./data').rglob('*.parquet'):
    parts = file_path.relative_to('./data').parts[:-1]

    if parts:
        schema_name = '_'.join(parts).replace('-', '_').replace(' ', '_')
        create_schema_if_needed(schema_name)

        table_name = file_path.stem.replace('-', '_').replace(' ', '_')
        full_name = f"{schema_name}.{table_name}"
    else:
        table_name = file_path.stem.replace('-', '_').replace(' ', '_')
        full_name = table_name

    con.execute(f"CREATE OR REPLACE VIEW {full_name} AS SELECT * FROM '{file_path}'")
    print(f"Created view: {full_name}")

con.close()
print("\nDone! Now run: uv run harlequin gridiron_yampylytics.db")
print("\nYour views are organized by directory structure.")
print("Example: SELECT * FROM cached_SOURCE.FILE")