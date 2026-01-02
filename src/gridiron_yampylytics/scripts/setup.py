"""Setup scripts for quick project initialization.

This module provides different setup workflows optimized for different use cases:
- quick: Fast setup with essential data only
- analysis: Comprehensive data for analysis (excludes pbp)
- full: Complete dataset with views
- yampy: Complete dataset with indexed tables for max performance

Each setup runs the full workflow: download → process → create database
"""
import sys
import argparse
from typing import Optional
from gridiron_yampylytics.scripts import download_data, process_data
from gridiron_yampylytics.scripts import create_duckdb_views, create_duckdb_tables


def _run_setup(
    download_mode: str,
    include_gm: bool = True,
    all_seasons: bool = False,
    use_tables: bool = False,
    allow_gm_override: bool = True
) -> None:
    """Run the complete setup workflow.

    :param download_mode: Download mode flag (--essential, --analysis, --yampy)
    :param include_gm: Include GM data download
    :param all_seasons: Download all available seasons
    :param use_tables: Create indexed tables instead of views
    :param allow_gm_override: Allow --no-gm flag to override include_gm
    """
    # Parse optional --gm and --no-gm flags
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--gm', action='store_true', help='Include GM data download')
    parser.add_argument('--no-gm', action='store_true', help='Skip GM data download')
    args, _ = parser.parse_known_args()

    # Determine if we should include GM data
    if allow_gm_override:
        if args.gm:
            final_include_gm = True
        elif args.no_gm:
            final_include_gm = False
        else:
            final_include_gm = include_gm  # Use default
    else:
        final_include_gm = include_gm

    print("=" * 80)
    print("GRIDIRON-YAMPYLYTICS SETUP")
    print("=" * 80)
    print()

    # Step 1: Download data
    print("[1/3] Downloading data...")
    print("-" * 80)
    download_args = [download_mode]
    if all_seasons:
        download_args.append('--all-seasons')
    if final_include_gm:
        download_args.append('--gm')

    # Manipulate sys.argv to pass args to download_data.main()
    original_argv = sys.argv.copy()
    try:
        sys.argv = ['download_data'] + download_args
        download_data.main()
    finally:
        sys.argv = original_argv
    print()

    # Step 2: Process data
    print("[2/3] Processing data...")
    print("-" * 80)
    # Manipulate sys.argv to pass GM flag to process_data.main()
    original_argv = sys.argv.copy()
    try:
        process_args = ['process_data']
        if not final_include_gm:
            process_args.append('--no-gm')
        sys.argv = process_args
        process_data.main()
    finally:
        sys.argv = original_argv
    print()

    # Step 3: Create database
    print("[3/3] Creating DuckDB database...")
    print("-" * 80)
    if use_tables:
        create_duckdb_tables.main()
    else:
        create_duckdb_views.main()
    print()

    print("=" * 80)
    print("✅ SETUP COMPLETE!")
    print("=" * 80)
    print()
    print("Next steps:")
    print("  uv run show-status    # Check what data you have")
    print("  uv run sql            # Explore data with Harlequin SQL browser")
    print()


def quick() -> None:
    """Quick setup: essentials only for fast start.

    Downloads minimal datasets for quick exploration:
    - Combine data (all years)
    - Draft picks (all years)
    - Rosters (current season only for speed)
    - GM data excluded by default for speed (add --gm to include)

    Processes and creates DuckDB views. Fast setup (~1 min).

    Usage:
        uv run setup-quick           # Fast setup, no GM data
        uv run setup-quick --gm      # Include GM data
    """
    # Check for --help before running
    if '--help' in sys.argv or '-h' in sys.argv:
        print(quick.__doc__)
        return

    _run_setup(
        download_mode='--essential',
        include_gm=False,  # Changed: GM data OFF by default for quick setup
        all_seasons=False,
        use_tables=False
    )


def analysis() -> None:
    """Analysis-ready setup: omits largest tables.

    Downloads comprehensive datasets for analysis:
    - All nflverse data EXCEPT pbp (which is huge)
    - Includes: rosters, stats, combine, draft, contracts, schedules, etc.
    - GM executive data (unless --no-gm)

    Processes and creates DuckDB views. Moderate setup time (~5-10 min).

    Usage:
        uv run setup-analysis
        uv run setup-analysis --no-gm  # Skip GM data
    """
    if '--help' in sys.argv or '-h' in sys.argv:
        print(analysis.__doc__)
        return

    _run_setup(
        download_mode='--analysis',
        include_gm=True,
        all_seasons=True,
        use_tables=False
    )


def full() -> None:
    """Complete setup: download all datasets, process it, and create database.

    This runs all setup steps with sensible defaults:
    - Downloads all NFL data (nflverse + GM executives unless --no-gm)
    - Processes and enriches data (yamplayer_id, YAS scores, etc.)
    - Creates DuckDB with lightweight views

    Grab a coffee - this could take a bit depending on your network speed.

    Usage:
        uv run setup-full
        uv run setup-full --no-gm  # Skip GM data
    """
    if '--help' in sys.argv or '-h' in sys.argv:
        print(full.__doc__)
        return

    _run_setup(
        download_mode='--yampy',
        include_gm=True,
        all_seasons=True,
        use_tables=False
    )


def yampy() -> None:
    """Maximum yampage setup: full data + performance optimizations.

    Like full setup, but with tables instead of views for faster queries.
    Assumes you have disk space and want maximum performance.

    Usage:
        uv run setup-yampy
        uv run setup-yampy --no-gm  # Skip GM data
    """
    if '--help' in sys.argv or '-h' in sys.argv:
        print(yampy.__doc__)
        return

    _run_setup(
        download_mode='--yampy',
        include_gm=True,
        all_seasons=True,
        use_tables=True
    )


if __name__ == "__main__":
    # If run directly, show help
    print("Setup scripts for gridiron-yampylytics")
    print()
    print("Usage:")
    print("  uv run setup-quick      # Fast setup with essentials")
    print("  uv run setup-analysis   # Analysis-ready (no pbp)")
    print("  uv run setup-full       # Complete data with views")
    print("  uv run setup-yampy      # Complete data with tables")
    print()
    print("All commands support --no-gm to skip GM data download")
