"""Invoke tasks for gridiron-yampylytics - simplified NFL data analysis toolkit.

Use these commands to download, process, and analyze NFL data without memorizing
lengthy uv commands.

Quick start:
    inv setup              # Default setup
    inv status             # See what data you have
    inv sql                # Open Harlequin SQL explorer
"""
import os
import sys
from invoke import task

# Configure UTF-8 output for all invoke tasks (emojis and unicode support)
sys.stdout.reconfigure(encoding='utf-8')

@task(help={
    'datasets': 'Specific dataset(s) to download (comma-separated, e.g., "pbp,rosters"). Leave empty for all datasets.',
    'seasons': 'Specific season(s) to download (space-separated, e.g., "2023 2024"). Omit for current season.',
    'all_seasons': 'Download all available seasons for each dataset',
    'no_gm': 'Skip GM data download (faster, GM scraper is slow)',
    'sequential': 'Use sequential execution instead of parallel (for debugging)',
    'max_workers': 'Maximum number of parallel workers (default: unlimited)',
})
def load_data(c, datasets=None, seasons=None, all_seasons=False, no_gm=False, sequential=False, max_workers=None):
    """Download NFL data sources (nflverse + GM executives) in parallel.

    Flexible data loading with optional granular control over datasets and seasons.
    For preset workflows, use setup tasks: setup-quick, setup-analysis, full-setup, yampy-setup

    Examples:
        inv load-data                                    # All datasets, all seasons, with GM (default)
        inv load-data --no-gm                           # All datasets, all seasons, skip GM scraper
        inv load-data --datasets=pbp,rosters            # Specific datasets only, all seasons
        inv load-data --datasets=combine --seasons="2023 2024"  # Specific dataset and seasons
        inv load-data --all-seasons                     # Explicitly request all seasons
        inv load-data --sequential                       # Sequential mode for debugging
        inv load-data --max-workers=4                   # Limit to 4 parallel workers

    :param datasets: Comma-separated dataset names (default: all)
    :param seasons: Space-separated season years (default: current season)
    :param all_seasons: Download all available seasons
    :param no_gm: Skip GM data download (faster, GM scraper is slow)
    :param sequential: Use sequential execution instead of parallel
    :param max_workers: Maximum number of parallel workers
    """
    cmd = 'uv run python -m scripts.download_data'

    # Dataset selection
    if datasets:
        # User specified specific datasets (comma-separated -> space-separated)
        cmd += f' --datasets {datasets.replace(",", " ")}'
    else:
        # Default to all datasets
        cmd += ' --all'

    # Season selection
    if all_seasons:
        cmd += ' --all-seasons'
    elif seasons:
        cmd += f' --seasons {seasons}'
    # else: defaults to current season

    # GM data
    if not no_gm or datasets:
        cmd += ' --gm'

    # Execution options
    if sequential:
        cmd += ' --sequential'
    if max_workers:
        cmd += f' --max-workers={max_workers}'

    c.run(cmd)


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
    clean_depth_charts(c)
    combine_gm_data(c)
    generate_yamplayer_id(c, all_datasets=include_large)
    calculate_yas(c)

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


@task
def sql(c):
    """Start Harlequin SQL explorer for interactive data analysis.

    Opens an interactive SQL terminal (like DBeaver/DataGrip but in your terminal)
    for exploring the gridiron_yampylytics.db database.

    Automatically detects Windows and adds --no-download-tzdata flag for compatibility.
    """
    suffix = ' --no-download-tzdata' if os.name == 'nt' else ''
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
def setup_quick(c, no_gm=False):
    """Quick setup: essentials only for fast start.

    Downloads minimal datasets for quick exploration (in parallel):
    - Combine data (all years - no season filter)
    - Draft picks (all years - no season filter)
    - Rosters (current season only for speed)
    - GM data (all teams, unless --no-gm)

    Processes and creates DuckDB views. Fast setup (~1-2 min).

    :param no_gm: Skip GM data download (faster, GM scraper is slow)
    """
    cmd = 'uv run python -m scripts.download_data --essential'
    if not no_gm:
        cmd += ' --gm'
    c.run(cmd)
    process_data(c)
    create_duckdb(c)


@task
def setup_analysis(c, no_gm=False, as_tables=False):
    """Analysis-ready setup: omits largest tables.

    Downloads comprehensive datasets for analysis (in parallel):
    - All nflverse data EXCEPT pbp (which is huge)
    - Includes: rosters, stats, combine, draft, contracts, schedules, etc.
    - GM executive data (unless --no-gm)

    Processes and creates DuckDB views. Moderate setup time (~5-10 min).

    :param no_gm: Skip GM data download (faster, GM scraper is slow)
    :param as_tables: Creates indexed tables in duckdb
    """
    cmd = 'uv run python -m scripts.download_data --analysis --all-seasons'
    if not no_gm:
        cmd += ' --gm'
    c.run(cmd)
    process_data(c)
    create_duckdb(c, as_tables=as_tables)


@task
def full_setup(c, no_gm=False):
    """Complete setup: download all datasets, process it, and create database.

    This runs all setup steps with sensible defaults (in parallel):
    - Downloads all NFL data (nflverse + GM executives unless --no-gm)
    - Processes and enriches data (yamplayer_id, YAS scores, etc.)
    - Creates DuckDB with lightweight views

    Grab a coffee - this could potentially take a bit depending on your network speed.

    :param no_gm: Skip GM data download (faster, GM scraper is slow)
    """
    cmd = 'uv run python -m scripts.download_data --yampy --all-seasons'
    if not no_gm:
        cmd += ' --gm'
    c.run(cmd)
    process_data(c)
    create_duckdb(c)


@task
def yampy_setup(c, no_gm=False):
    """Maximum yampage setup: full data + performance optimizations.

    Like setup, but with tables instead of views for faster queries (in parallel).
    Assumes you have disk space and want maximum performance.

    :param no_gm: Skip GM data download (faster, GM scraper is slow)
    """
    cmd = 'uv run python -m scripts.download_data --yampy --all-seasons'
    if not no_gm:
        cmd += ' --gm'
    c.run(cmd)
    process_data(c)
    create_duckdb(c, as_tables=True)
