import duckdb
from pathlib import Path

con = duckdb.connect('gridiron_yampylytics.db')

# Find all CSV and Parquet files
for csv_file in Path('.').rglob('*.csv'):
    table_name = csv_file.stem  # filename without extension
    con.execute(f"CREATE OR REPLACE VIEW {table_name} AS SELECT * FROM '{csv_file}'")
    print(f"Created view: {table_name}")

for parquet_file in Path('.').rglob('*.parquet'):
    table_name = parquet_file.stem
    con.execute(f"CREATE OR REPLACE VIEW {table_name} AS SELECT * FROM '{parquet_file}'")
    print(f"Created view: {table_name}")

con.close()
print("\nDone! Now run: uv run harlequin nfl_data.db")
