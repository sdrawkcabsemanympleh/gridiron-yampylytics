"""nflverse data caching module.

This module downloads data from nflreadpy (nflverse) and caches it locally as CSV files.
Useful for SQL exploration, offline analysis, and reproducible research.

For programmatic use:
    from gridiron_yampylytics.loaders.nflverse import cache_nflverse_data
    result = cache_nflverse_data(dataset="all", seasons=True)

Datasets are defined in DATASET_CONFIG below. Adding a new dataset requires only
adding an entry to that configuration dictionary.
"""
import logging
from pathlib import Path
from typing import Any
from datetime import datetime
import nflreadpy as nfl
from gridiron_yampylytics.manifest import update_dataset
from gridiron_yampylytics.utils.parallel import Task, run_tasks_parallel

# Configure logging for thread-safe output with thread names
logger = logging.getLogger(__name__)

# ============================================================================
# DATASET CONFIGURATION
# ============================================================================
# All nflverse datasets with their metadata. Adding a new dataset requires
# only adding an entry here - everything else is auto-generated.
DATASET_CONFIG = {
    # SEASON-BASED DATASETS (support seasons parameter)
    'pbp': {
        'has_seasons': True,
        'description': 'Play-by-play data',
        'groups': {'LARGE'},
        'coverage': '1999-2025',
    },
    'player_stats': {
        'has_seasons': True,
        'description': 'Weekly/seasonal player statistics',
        'groups': {'ANALYSIS'},
        'coverage': '2012-2025',
    },
    'rosters': {
        'has_seasons': True,
        'description': 'Weekly rosters',
        'groups': {'ESSENTIAL'},
        'coverage': '2006-2025',
    },
    'schedules': {
        'has_seasons': True,
        'description': 'Game schedules',
        'groups': {'ANALYSIS'},
        'coverage': '1999-2025',
    },
    'injuries': {
        'has_seasons': True,
        'description': 'Injury reports',
        'groups': {'ANALYSIS'},
        'coverage': '2009-2025',
    },
    'depth_charts': {
        'has_seasons': True,
        'description': 'Team depth charts',
        'groups': {'ANALYSIS'},
        'coverage': '2017-2025',
    },
    'snap_counts': {
        'has_seasons': True,
        'description': 'Player snap counts from PFR',
        'groups': {'ANALYSIS'},
        'coverage': '2012-2025',
    },
    'ff_opportunity': {
        'has_seasons': True,
        'description': 'Fantasy opportunity metrics - expected vs actual',
        'groups': {'ANALYSIS'},
        'coverage': '2006-2024',
    },
    'officials': {
        'has_seasons': True,
        'description': 'Referee assignments',
        'groups': {'ANALYSIS'},
        'coverage': '2015-2025',
    },
    'nextgen_stats': {
        'has_seasons': True,
        'description': 'Next Gen Stats - player tracking data',
        'groups': {'ANALYSIS'},
        'coverage': '2016-2025',
    },
    'team_stats': {
        'has_seasons': True,
        'description': 'Team-level statistics',
        'groups': {'ESSENTIAL'},
        'coverage': '2002-2025',
    },
    'participation': {
        'has_seasons': True,
        'description': 'Player participation on specific plays',
        'groups': {'LARGE'},
        'coverage': '2016-2025',
    },
    'ftn_charting': {
        'has_seasons': True,
        'description': 'Detailed play charting data',
        'groups': {'ANALYSIS'},
        'coverage': '2022-2025',
    },
    'rosters_weekly': {
        'has_seasons': True,
        'description': 'Weekly roster changes',
        'groups': {'LARGE'},
        'coverage': '2002-2025',
    },
    # NO-SEASON DATASETS (load all data at once)
    'draft_picks': {
        'has_seasons': False,
        'description': 'Draft history',
        'groups': {'ESSENTIAL'},
        'coverage': '1967-2025',
    },
    'combine': {
        'has_seasons': False,
        'description': 'NFL Combine results',
        'groups': {'ESSENTIAL'},
        'coverage': '2000-2024',
    },
    'contracts': {
        'has_seasons': False,
        'description': 'Player contracts',
        'groups': {'ANALYSIS'},
        'coverage': '2000s-2025',
    },
    'ids': {
        'has_seasons': False,
        'description': 'Player ID mappings',
        'groups': {'ANALYSIS'},
        'coverage': 'all',
    },
    'players': {
        'has_seasons': False,
        'description': 'Comprehensive player info with multi-platform IDs',
        'groups': {'ESSENTIAL'},
        'coverage': 'all',
    },
    'teams': {
        'has_seasons': False,
        'description': 'Team metadata (abbr, names, colors, logos)',
        'groups': {'ESSENTIAL'},
        'coverage': 'all',
    },
    'ff_rankings': {
        'has_seasons': False,
        'description': 'Fantasy football rankings and projections',
        'groups': {'ESSENTIAL'},
        'coverage': 'all',
    },
    'trades': {
        'has_seasons': False,
        'description': 'Trade transactions',
        'groups': {'ESSENTIAL'},
        'coverage': 'all',
    },
    'ff_playerids': {
        'has_seasons': False,
        'description': 'Cross-platform fantasy player ID mappings',
        'groups': {'ESSENTIAL'},
        'coverage': 'all',
    },
}


def setup_cache_dirs(base_dir: Path | None = None) -> dict[str, Path]:
    """Create cache directory structure.

    :param base_dir: Base directory for caching (default: data/nflverse)
    :return: Dictionary mapping dataset names to their cache directories
    """
    if base_dir is None:
        base_dir = Path.cwd() / "data" / "nflverse"
    base_dir.mkdir(parents=True, exist_ok=True)
    # All files go directly in data/nflverse/ (no subdirectories)
    return {dataset_name: base_dir for dataset_name in DATASET_CONFIG.keys()}


def _cache_dataset(dataset_name: str, seasons: int | list[int] | bool | None, cache_dir: Path) -> dict[str, int]:
    """Generic dataset cacher - handles both season-based and non-season datasets.

    :param dataset_name: Name of the dataset to cache
    :param seasons: Season(s) to load (only used for season-based datasets)
    :param cache_dir: Directory to save cached files
    :return: Dict with row count
    """
    config = DATASET_CONFIG[dataset_name]
    has_seasons = config['has_seasons']
    # Get the nflreadpy load function dynamically
    load_func = getattr(nfl, f'load_{dataset_name}')
    # Construct log message and load data
    if has_seasons:
        logger.info(f"Loading {dataset_name} (seasons={seasons})...")
        df = load_func(seasons=seasons)
        output_file = cache_dir / f"{dataset_name}.csv" if seasons is True else cache_dir / f"{dataset_name}_{seasons}.csv"
    else:
        logger.info(f"Loading {dataset_name} (all)...")
        df = load_func()
        output_file = cache_dir / f"{dataset_name}.csv"
    # Special handling for rosters headshot_url
    if dataset_name == 'rosters' and 'headshot_url' in df.columns:
        logger.info("  ⚙ Sanitizing headshot_url column (URL-encoding commas)...")
        df = df.with_columns(df['headshot_url'].str.replace_all(',', '%2C'))
    # Write to CSV
    df.write_csv(output_file)
    rows = len(df)
    logger.info(f"  ✓ Saved {rows:,} rows to {output_file}")
    return {'rows': rows}


# Auto-generate dataset function mappings from configuration
SEASON_DATASETS = {
    name: lambda seasons, cache_dir, n=name: _cache_dataset(n, seasons, cache_dir)
    for name, config in DATASET_CONFIG.items()
    if config['has_seasons']
}

NO_SEASON_DATASETS = {
    name: lambda cache_dir, n=name: _cache_dataset(n, None, cache_dir)
    for name, config in DATASET_CONFIG.items()
    if not config['has_seasons']
}

# Datasets that are very large and are omitted during standard setup
LARGE_DATASETS = {"pbp"}


def cache_nflverse_data(
    dataset: str = "all",
    seasons: int | list[int] | bool | None = None,
    base_dir: Path | None = None,
    parallel: bool = True,
    max_workers: int | None = None,
    callback: Any = None,
) -> dict[str, Any]:
    """Cache nflverse data locally.

    :param dataset: Dataset name (e.g., 'pbp', 'player_stats') or 'all'
    :param seasons: Season(s) to load (True=all, int=single, list=multiple, None=current)
    :param base_dir: Base directory for caching (default: data/nflverse)
    :param parallel: Whether to use parallel execution (default: True)
    :param max_workers: Number of parallel workers (default: CPU count)
    :param callback: Optional callback function for progress updates
    :return: Dict with download results {'successful': [...], 'failed': [...]}
    """
    cache_dirs = setup_cache_dirs(base_dir)
    successful = []
    failed = []
    if dataset == "all":
        # Cache all datasets
        if parallel:
            # Build task list
            tasks = []
            # Season-based datasets
            for name, func in SEASON_DATASETS.items():
                if seasons is None:
                    logger.info(f"Skipping {name} (requires explicit seasons parameter)")
                    continue
                task = Task(
                    name=name,
                    func=func,
                    args=(seasons, cache_dirs[name]),
                    callback=callback,
                )
                tasks.append(task)
            # Non-season datasets
            for name, func in NO_SEASON_DATASETS.items():
                task = Task(
                    name=name,
                    func=func,
                    args=(cache_dirs[name],),
                    callback=callback,
                )
                tasks.append(task)
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
        raise ValueError(f"Unknown dataset: {dataset}. Available: {list(DATASET_CONFIG.keys())}")
    # Update manifest for successful downloads
    for dataset_name in successful:
        try:
            cache_dir = cache_dirs[dataset_name]
            files = list(cache_dir.glob(f"{dataset_name}*.csv"))
            if files:
                total_size = sum(f.stat().st_size for f in files)
                update_dataset(
                    dataset_name=dataset_name,
                    file_size_bytes=total_size,
                    last_downloaded=datetime.now().strftime("%Y-%m-%d"),
                    files=len(files),
                )
        except Exception as e:
            logger.warning(f"Failed to update manifest for {dataset_name}: {e}")
    return {"successful": successful, "failed": failed}
