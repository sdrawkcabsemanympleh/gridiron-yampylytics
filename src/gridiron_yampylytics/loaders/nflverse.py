"""nflverse data caching module.

This module downloads data from nflreadpy (nflverse) and caches it locally as CSV files.
Useful for SQL exploration, offline analysis, and reproducible research.

For programmatic use:
    from src.gridiron_yampylytics.loaders.nflverse import cache_nflverse_data
    result = cache_nflverse_data(dataset="all", seasons=True)

Available datasets:
    - pbp: Play-by-play data (1999-2025) - LARGE
    - player_stats: Weekly/seasonal player statistics (2012-2025)
    - rosters: Weekly rosters (2006-2025)
    - draft_picks: Draft history (1967-2025)
    - combine: NFL Combine results (2000-2024)
    - contracts: Player contracts (2000s-2025)
    - ids: Player ID mappings (all)
    - schedules: Game schedules (1999-2025)
    - injuries: Injury reports (recent)
    - depth_charts: Team depth charts (2017-2025)

Additional datasets available from nflreadr (not yet implemented):
    - qbr, nextgen_stats, snap_counts, participation, ftn_charting,
      trades, players, team_stats, pfr_passing, roster_status,
      ff_opportunity, ff_rankings
"""
import logging
from pathlib import Path
from typing import Any
from datetime import datetime
import nflreadpy as nfl

from src.gridiron_yampylytics.manifest import update_dataset
from src.gridiron_yampylytics.utils.parallel import Task, run_tasks_parallel

# Configure logging for thread-safe output with thread names
logger = logging.getLogger(__name__)


def setup_cache_dirs(base_dir: Path | None = None) -> dict[str, Path]:
    """Create cache directory structure.

    :param base_dir: Base directory for caching (default: data/nflverse)
    :return: Dictionary mapping dataset names to their cache directories
    """
    if base_dir is None:
        base_dir = Path.cwd() / "data" / "nflverse"

    base_dir.mkdir(parents=True, exist_ok=True)

    # All files go directly in data/nflverse/ (no subdirectories)
    dirs = {
        "pbp": base_dir,
        "player_stats": base_dir,
        "rosters": base_dir,
        "draft_picks": base_dir,
        "combine": base_dir,
        "contracts": base_dir,
        "ids": base_dir,
        "schedules": base_dir,
        "injuries": base_dir,
        "depth_charts": base_dir,
    }

    return dirs


def cache_pbp(seasons: int | list[int] | bool, cache_dir: Path) -> None:
    """Cache play-by-play data.

    :param seasons: Season(s) to load (True for all, None for current, int/list for specific)
    :param cache_dir: Directory to save cached files
    """
    logger.info(f"Loading play-by-play data (seasons={seasons})...")
    df = nfl.load_pbp(seasons=seasons)

    output_file = cache_dir / "pbp.csv" if seasons is True else cache_dir / f"pbp_{seasons}.csv"
    df.write_csv(output_file)
    logger.info(f"  ✓ Saved {len(df):,} rows to {output_file}")


def cache_player_stats(seasons: int | list[int] | bool, cache_dir: Path) -> None:
    """Cache player statistics.

    :param seasons: Season(s) to load
    :param cache_dir: Directory to save cached files
    """
    logger.info(f"Loading player stats (seasons={seasons})...")
    df = nfl.load_player_stats(seasons=seasons)

    output_file = cache_dir / "player_stats.csv" if seasons is True else cache_dir / f"player_stats_{seasons}.csv"
    df.write_csv(output_file)
    logger.info(f"  ✓ Saved {len(df):,} rows to {output_file}")


def cache_rosters(seasons: int | list[int] | bool, cache_dir: Path) -> None:
    """Cache weekly rosters.

    :param seasons: Season(s) to load
    :param cache_dir: Directory to save cached files
    """
    logger.info(f"Loading rosters (seasons={seasons})...")
    df = nfl.load_rosters(seasons=seasons)

    # Sanitize headshot_url column to fix CSV parsing issues
    # nflverse data has unescaped commas in URLs which breaks CSV format
    if 'headshot_url' in df.columns:
        logger.info("  ⚙ Sanitizing headshot_url column (URL-encoding commas)...")
        df = df.with_columns(
            df['headshot_url'].str.replace_all(',', '%2C')  # URL-encode commas
        )

    output_file = cache_dir / "rosters.csv" if seasons is True else cache_dir / f"rosters_{seasons}.csv"
    df.write_csv(output_file)
    logger.info(f"  ✓ Saved {len(df):,} rows to {output_file}")


def cache_draft_picks(cache_dir: Path) -> None:
    """Cache draft picks (no season filter - loads all).

    :param cache_dir: Directory to save cached files
    """
    logger.info("Loading draft picks (all years)...")
    df = nfl.load_draft_picks()

    output_file = cache_dir / "draft_picks.csv"
    df.write_csv(output_file)
    logger.info(f"  ✓ Saved {len(df):,} rows to {output_file}")


def cache_combine(cache_dir: Path) -> None:
    """Cache NFL Combine results (no season filter - loads all).

    :param cache_dir: Directory to save cached files
    """
    logger.info("Loading combine results (all years)...")
    df = nfl.load_combine()

    output_file = cache_dir / "combine.csv"
    df.write_csv(output_file)
    logger.info(f"  ✓ Saved {len(df):,} rows to {output_file}")


def cache_contracts(cache_dir: Path) -> None:
    """Cache player contracts (no season filter - loads all).

    Saved as Parquet because contracts contain nested year-by-year data.

    :param cache_dir: Directory to save cached files
    """
    logger.info("Loading player contracts (all years)...")
    df = nfl.load_contracts()

    output_file = cache_dir / "contracts.parquet"
    df.write_parquet(output_file)
    logger.info(f"  ✓ Saved {len(df):,} rows to {output_file} (Parquet format - includes nested year-by-year contract details)")


def cache_ids(cache_dir: Path) -> None:
    """Cache player ID mappings (no season filter - loads all).

    Uses load_ff_playerids (fantasy football player IDs) for cross-platform ID mapping.

    :param cache_dir: Directory to save cached files
    """
    logger.info("Loading player ID mappings...")
    df = nfl.load_ff_playerids()

    output_file = cache_dir / "player_ids.csv"
    df.write_csv(output_file)
    logger.info(f"  ✓ Saved {len(df):,} rows to {output_file}")


def cache_schedules(seasons: int | list[int] | bool, cache_dir: Path) -> None:
    """Cache game schedules.

    :param seasons: Season(s) to load
    :param cache_dir: Directory to save cached files
    """
    logger.info(f"Loading schedules (seasons={seasons})...")
    df = nfl.load_schedules(seasons=seasons)

    output_file = cache_dir / "schedules.csv" if seasons is True else cache_dir / f"schedules_{seasons}.csv"
    df.write_csv(output_file)
    logger.info(f"  ✓ Saved {len(df):,} rows to {output_file}")


def cache_injuries(seasons: int | list[int] | bool, cache_dir: Path) -> None:
    """Cache injury reports.

    Walks forward from 2009 until hitting a 404, loading all available years.

    :param seasons: Season(s) to load (if True, auto-detects available years)
    :param cache_dir: Directory to save cached files
    """
    if seasons is True:
        # Walk forward from 2009 until we hit a year that doesn't exist
        logger.info("Loading injuries (auto-detecting available years)...")
        current_year = datetime.now().year
        start_year = 2009  # injuries data starts in 2009

        available_seasons = []
        for year in range(start_year, current_year + 1):
            try:
                # Test if this year exists
                test_df = nfl.load_injuries(seasons=year)
                available_seasons.append(year)
            except Exception:
                # Year doesn't exist, we've reached the end
                break

        if not available_seasons:
            raise Exception("No injury data available")

        logger.info(f"  Found injury data for {len(available_seasons)} seasons ({min(available_seasons)}-{max(available_seasons)})")
        df = nfl.load_injuries(seasons=available_seasons)
        output_file = cache_dir / "injuries.csv"
    else:
        logger.info(f"Loading injuries (seasons={seasons})...")
        df = nfl.load_injuries(seasons=seasons)
        output_file = cache_dir / f"injuries_{seasons}.csv"

    df.write_csv(output_file)
    logger.info(f"  ✓ Saved {len(df):,} rows to {output_file}")


def cache_depth_charts(seasons: int | list[int] | bool, cache_dir: Path) -> None:
    """Cache team depth charts.

    :param seasons: Season(s) to load
    :param cache_dir: Directory to save cached files
    """
    logger.info(f"Loading depth charts (seasons={seasons})...")
    df = nfl.load_depth_charts(seasons=seasons)

    output_file = cache_dir / "depth_charts.csv" if seasons is True else cache_dir / f"depth_charts_{seasons}.csv"
    df.write_csv(output_file)
    logger.info(f"  ✓ Saved {len(df):,} rows to {output_file}")


# ============================================================================
# ADDITIONAL DATASETS (not yet implemented)
# ============================================================================
# To add new datasets, follow this pattern:
#
# def cache_nextgen_stats(seasons: int | list[int] | bool, cache_dir: Path) -> None:
#     """Cache Next Gen Stats (player tracking data)."""
#     logger.info(f"Loading Next Gen Stats (seasons={seasons})...")
#     df = nfl.load_nextgen_stats(seasons=seasons)
#     output_file = cache_dir / "nextgen_stats.csv" if seasons is True else cache_dir / f"nextgen_stats_{seasons}.csv"
#     df.write_csv(output_file)
#     logger.info(f"  ✓ Saved {len(df):,} rows to {output_file}")
#
# Then add to SEASON_DATASETS dict below:
#     "nextgen_stats": cache_nextgen_stats,
#
# Available functions from nflreadpy:
#     - nfl.load_nextgen_stats() - Next Gen tracking data
#     - nfl.load_snap_counts() - Player snap counts
#     - nfl.load_qbr() - ESPN QB ratings
#     - nfl.load_trades() - Trade transactions
#     - nfl.load_participation() - Game participation
#     - nfl.load_team_stats() - Team-level stats
#     - nfl.load_pfr_passing() - PFR passing stats
#     - nfl.load_ftn_charting() - Film charting data
#     - And more! See: https://nflreadr.nflverse.com/articles/index.html
# ============================================================================


# Dataset configuration: which datasets support season filtering
SEASON_DATASETS = {
    "pbp": cache_pbp,
    "player_stats": cache_player_stats,
    "rosters": cache_rosters,
    "schedules": cache_schedules,
    "injuries": cache_injuries,
    "depth_charts": cache_depth_charts,
}

NO_SEASON_DATASETS = {
    "draft_picks": cache_draft_picks,
    "combine": cache_combine,
    "contracts": cache_contracts,
    "ids": cache_ids,
}

# Datasets that are very large and are omitted during standard setup
LARGE_DATASETS = {"pbp"}


def cache_nflverse_data(
    dataset: str = "all",
    seasons: int | list[int] | bool | None = None,
    base_dir: Path | None = None,
    parallel: bool = True,
    max_workers: int | None = None
) -> dict[str, Any]:
    """Cache nflreadpy data locally for SQL exploration and offline analysis.

    Downloads data from nflreadpy (nflverse) and caches it locally as CSV files.

    :param dataset: Which dataset to cache ("all" or specific dataset name)
    :param seasons: Season(s) to load (True=all, None=current, int/list=specific)
    :param base_dir: Base directory for caching (default: data/nflverse)
    :param parallel: Use parallel execution (default: True)
    :param max_workers: Max concurrent workers for parallel execution (default: None = one per task)
    :return: Summary dict with caching statistics
    """
    # Configure logging for thread-safe output with thread names
    logging.basicConfig(
        level=logging.INFO,
        format='[%(threadName)s] %(message)s',
        force=True  # Override any existing config
    )

    # Setup cache directories
    cache_dirs = setup_cache_dirs(base_dir)

    logger.info("="*80)
    logger.info("NFLREADPY DATA CACHING")
    logger.info("="*80)
    logger.info(f"Dataset: {dataset}")
    logger.info(f"Seasons: {seasons if seasons is not None else 'current season'}")
    logger.info(f"Cache location: {list(cache_dirs.values())[0]}")
    logger.info("="*80)
    logger.info("")

    # Track successes and failures
    successful = []
    failed = []

    if dataset == "all":
        # Cache all datasets
        logger.info("Caching all datasets...\n")

        if parallel:
            # Build task list for parallel execution
            tasks = []

            # Add season-based datasets
            for name, func in SEASON_DATASETS.items():
                tasks.append(Task(name, func, (seasons, cache_dirs[name])))

            # Add non-season datasets
            for name, func in NO_SEASON_DATASETS.items():
                tasks.append(Task(name, func, (cache_dirs[name],)))

            # Execute in parallel
            results = run_tasks_parallel(tasks, max_workers=max_workers)
            successful = results['successful']
            failed = results['failed']

        else:
            # Sequential execution (for debugging)
            # Cache season-based datasets
            for name, func in SEASON_DATASETS.items():
                try:
                    func(seasons, cache_dirs[name])
                    successful.append(name)
                except Exception as e:
                    logger.info(f"  ⚠️  Failed: {e}")
                    failed.append((name, str(e)))

            # Cache non-season datasets
            for name, func in NO_SEASON_DATASETS.items():
                try:
                    func(cache_dirs[name])
                    successful.append(name)
                except Exception as e:
                    logger.info(f"  ⚠️  Failed: {e}")
                    failed.append((name, str(e)))

    elif dataset in SEASON_DATASETS:
        # Cache specific season-based dataset
        try:
            SEASON_DATASETS[dataset](seasons, cache_dirs[dataset])
            successful.append(dataset)
        except Exception as e:
            logger.info(f"\n❌ Error: {e}")
            failed.append((dataset, str(e)))

    elif dataset in NO_SEASON_DATASETS:
        # Cache specific non-season dataset
        if seasons:
            logger.info(f"Warning: {dataset} doesn't support season filtering. Ignoring seasons parameter.")
        try:
            NO_SEASON_DATASETS[dataset](cache_dirs[dataset])
            successful.append(dataset)
        except Exception as e:
            logger.info(f"\n❌ Error: {e}")
            failed.append((dataset, str(e)))
    else:
        raise ValueError(f"Unknown dataset: {dataset}")

    # Print summary
    logger.info("\n" + "="*80)
    logger.info("CACHING SUMMARY")
    logger.info("="*80)

    if successful:
        logger.info(f"\n✅ Successfully cached {len(successful)} dataset(s):")
        for name in successful:
            logger.info(f"   • {name}")

    if failed:
        logger.info(f"\n⚠️  Failed to cache {len(failed)} dataset(s):")
        for name, error in failed:
            logger.info(f"   • {name}: {error[:80]}...")

    logger.info("\n" + "="*80)
    logger.info(f"Data cached in: {list(cache_dirs.values())[0]}")
    logger.info("You can now import these CSVs into your SQL tool of choice.")

    # Update manifest for successfully cached datasets
    if successful:
        logger.info("\nUpdating manifest...")
        for dataset_name in successful:
            try:
                # Find the cached file(s) for this dataset
                dataset_dir = cache_dirs[dataset_name]
                files = list(dataset_dir.glob(f"{dataset_name}.*"))

                if files:
                    # Get total size of all files for this dataset
                    total_size = sum(f.stat().st_size for f in files)

                    # Update manifest with last_downloaded timestamp and size
                    update_dataset(dataset_name, {
                        "last_downloaded": datetime.now().strftime("%Y-%m-%d"),
                        "file_size_bytes": total_size,
                        "files": len(files)
                    })
            except Exception as e:
                # Don't fail the whole script if manifest update fails
                logger.info(f"  ⚠️  Warning: Could not update manifest for {dataset_name}: {e}")

        logger.info("  ✓ Manifest updated")

    # Return structured data for programmatic use
    return {
        'successful': successful,
        'failed': failed,
        'total_datasets': len(successful) + len(failed),
        'cache_dir': list(cache_dirs.values())[0] if cache_dirs else None,
    }
