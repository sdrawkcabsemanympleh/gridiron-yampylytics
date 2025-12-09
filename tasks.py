"""Invoke tasks for gridiron-yampylytics - simplified NFL data analysis toolkit.

Use these commands to download, process, and analyze NFL data without memorizing
lengthy uv commands.

Quick start:
    inv setup              # Default setup
    inv status             # See what data you have
    inv sql                # Open Harlequin SQL explorer
"""


from invoke import task
from typing import List, Optional

@task
def load_data(c):
    """Download all NFL data sources (nflverse + GM executives).

    This is a simple wrapper that calls both data loaders sequentially.
    For more control over what gets downloaded, use the individual tasks or
    call scripts/cache_nflreadpy_data.py directly with its options.
    """
    c.run('uv run python -m scripts.load_all_data')


@task
def clean_depth_charts(c):
    """The depth charts change schema in 2024-2025 and need to be separated into legacy and modern datasets to be
    usable.  This completes that operation.
    """
    c.run('uv run python -m scripts.clean_depth_charts')


@task
def combine_gm_data(c):
    """The GM data is scraped into a bunch of messy datafiles.  This script combines them into something more usable."""
    c.run('uv run python -m scripts.combine_gm_data')


@task(help={
    'all_datasets': 'Will load all datasets if supplied, including very large ones.',
})
def generate_yamplayer_id(c, all_datasets=False):
    """Generates universal yamplayer ID's and applies them to datasets.  Applies only to reasonable sized sests by
    default."""
    if all_datasets:
        c.run('uv run python -m scripts.generate_yamplayer_id --all_datasets')
    else:
        c.run('uv run python -m scripts.generate_yamplayer_id')


@task
def calculate_yas(c):
    """Calculates the yampylytics Athletic Score (YAS), similar to the Relative Athletic Score by MathBomb"""
    c.run('uv run python -m scripts.calculate_yas')


@task(help={
    'include_large': 'Include large datasets like pbp in yamplayer_id processing',
})
def process_data(c, include_large=False):
    """Process raw data: clean depth charts, combine GM data, inject yamplayer_ids, calculate YAS.

    Steps:
    1. clean_depth_charts - Split 2024+ schema from legacy depth charts
    2. combine_gm_data - Merge scraped GM executive CSVs into unified file
    3. generate_yamplayer_id - Inject universal player IDs into all datasets
    4. calculate_yas - Calculate Yampylytics Athletic Score (YAS) from combine data
    """
    c.invoke(clean_depth_charts)
    c.invoke(combine_gm_data)
    c.invoke(generate_yamplayer_id, all_datasets=include_large)
    c.invoke(calculate_yas)

@task(help={
    'all_datasets': 'Include all datasets including very large ones',
    'as_tables': 'Load as tables with indexes (uses disk space) instead of lightweight views',
    'include_pbp': 'Include play-by-play data (only applies when as_tables=True)'
})
def create_duckdb(c, all_datasets=False, include_pbp=False, as_tables=False):
    """Create a local DuckDB database with the loaded data.

    Views (default): Lightweight, no disk space, always reflects current CSVs
    Tables (--as-tables): Faster queries with indexes, uses disk space, snapshot of CSVs
    """
    if as_tables:
        if all_datasets:
            suffix = ' --all_datasets'
        elif include_pbp:
            suffix = ' --include_pbp'
        else:
            suffix = ''
        c.run(f'uv run python -m scripts.create_duckdb_tables{suffix}')
    else:
        c.run('uv run python -m scripts.create_duckdb_views')


@task(help={
    'unix':  'Set this flag on Unix/Linux systems to avoid timezone data compatibility issues'
})
def sql(c, unix=False):
    """Start Harlequin SQL explorer for interactive data analysis.

    Opens an interactive SQL terminal (like DBeaver/DataGrip but in your terminal)
    for exploring the gridiron_yampylytics.db database.

    On Windows: Uses --no-download-tzdata flag for compatibility
    On Unix/Linux: Omit --no-download-tzdata (set unix=True)
    """
    suffix = '' if unix else ' --no-download-tzdata'
    c.run(f'uv run harlequin gridiron_yampylytics.db{suffix}')


@task
def status(c):
    """Show status of downloaded data and database.

    Displays:
    - What nflverse datasets are downloaded (with sizes)
    - GM/executive data status
    - DuckDB database status
    - Quick start recommendations based on what's missing
    """
    c.run('uv run python -m scripts.show_status')


@task
def setup(c):
    """Complete setup: download data, process it, and create database.

    This runs all setup steps with sensible defaults:
    - Downloads all NFL data (nflverse + GM executives)
    - Processes and enriches data (yamplayer_id, YAS scores, etc.)
    - Creates DuckDB with lightweight views

    Grab a coffee - this will take a bit depending on your network speed.
    """
    c.invoke(load_data)
    c.invoke(process_data)
    c.invoke(create_duckdb)


@task
def yampy_setup(c):
    """Maximum yampage setup: full data + performance optimizations.

    Like setup, but with tables instead of views for faster queries.
    Assumes you have disk space and want maximum performance.
    """
    c.invoke(load_data)
    c.invoke(process_data)
    c.invoke(create_duckdb, as_tables=True)
