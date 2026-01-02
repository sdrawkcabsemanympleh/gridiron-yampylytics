"""Parallel data loading for all data sources.

Unified parallel downloader for nflverse datasets and GM/executive data.
Coordinates downloads across multiple data sources for efficient setup.
"""
import logging
from pathlib import Path
from typing import Any, Optional
from datetime import datetime

from gridiron_yampylytics.loaders.nflverse import (
    SEASON_DATASETS,
    NO_SEASON_DATASETS,
    setup_cache_dirs,
)
from gridiron_yampylytics.loaders.gm_data import download_gm_data
from gridiron_yampylytics.manifest import update_dataset
from gridiron_yampylytics.utils.parallel import Task, run_tasks_parallel

# Import TYPE_CHECKING to avoid circular imports
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from gridiron_yampylytics.ui import ConsoleUI, TaskStatus, DisplayMode
else:
    # Import DisplayMode for runtime checks (it's just an enum, no circular dependency issue)
    from gridiron_yampylytics.ui import DisplayMode

logger = logging.getLogger(__name__)


def download_datasets_parallel(
    nflverse_datasets: frozenset[str] | set[str] | list[str] | None = None,
    include_gm: bool = False,
    seasons: int | list[int] | bool | None = None,
    max_workers: int | None = None,
    base_dir: Path | None = None,
    ui: Optional["ConsoleUI"] = None
) -> dict[str, Any]:
    """Download multiple datasets in parallel for faster setup.

    Unified parallel downloader for nflverse datasets and GM/executive data.
    Useful for setup tasks that need to download multiple datasets at once.

    :param nflverse_datasets: Set/list of nflverse dataset names (e.g., ESSENTIAL_DATASETS)
    :param include_gm: Include GM/executive data download (default: False)
    :param seasons: Season(s) to load for nflverse (True=all, None=current, int/list=specific)
    :param max_workers: Max concurrent workers (default: None = one per task)
    :param base_dir: Base directory for nflverse caching (default: data/nflverse)
    :param ui: Optional ConsoleUI instance for fancy display (default: None = verbose logging)
    :return: Summary dict with download statistics

    Example:
        from gridiron_yampylytics.config import ESSENTIAL_DATASETS
        from gridiron_yampylytics.loaders.parallel_loader import download_datasets_parallel

        # Download essential datasets + GM data in parallel
        result = download_datasets_parallel(
            nflverse_datasets=ESSENTIAL_DATASETS,
            include_gm=True,
            seasons=True
        )
    """
    # Configure logging for thread-safe output (if no UI or UI is in verbose mode)
    use_verbose = ui is None or (ui is not None and ui.mode == DisplayMode.VERBOSE)
    if use_verbose:
        logging.basicConfig(
            level=logging.INFO,
            format='[%(threadName)s] %(message)s',
            force=True
        )

    # Setup cache directories for nflverse
    cache_dirs = setup_cache_dirs(base_dir)

    # Show what we're downloading (verbose mode only)
    download_items = []
    if nflverse_datasets:
        download_items.append(f"NFLverse: {', '.join(sorted(nflverse_datasets))}")
    if include_gm:
        download_items.append("GM/Executive data")

    if not download_items:
        if use_verbose:
            logger.info("No datasets specified!")
        return {'successful': [], 'failed': [], 'total_tasks': 0}

    # Verbose logging (only if no UI or UI in verbose mode)
    if use_verbose:
        logger.info("="*80)
        logger.info("PARALLEL DATA DOWNLOAD")
        logger.info("="*80)

        for item in download_items:
            logger.info(f"  • {item}")

        if nflverse_datasets and seasons is not None:
            logger.info(f"  • Seasons: {seasons if seasons is not True else 'all available'}")

        logger.info(f"Cache location: {list(cache_dirs.values())[0]}")
        logger.info("="*80)
        logger.info("")

    # Build task list
    tasks = []

    # Add nflverse datasets
    if nflverse_datasets:
        for dataset in nflverse_datasets:
            if dataset in SEASON_DATASETS:
                # Season-based dataset
                tasks.append(Task(
                    dataset,
                    SEASON_DATASETS[dataset],
                    (seasons, cache_dirs[dataset])
                ))
            elif dataset in NO_SEASON_DATASETS:
                # Non-season dataset
                tasks.append(Task(
                    dataset,
                    NO_SEASON_DATASETS[dataset],
                    (cache_dirs[dataset],)
                ))
            else:
                logger.info(f"Warning: Unknown dataset '{dataset}', skipping")

    # Add GM data download if requested
    if include_gm:
        tasks.append(Task('gm_data', download_gm_data, ()))

    # Initialize UI status for all datasets (if UI provided and in fancy mode)
    if ui is not None and ui.mode != DisplayMode.VERBOSE:
        from gridiron_yampylytics.ui import TaskStatus
        for task in tasks:
            ui.update_dataset(task.name, TaskStatus.RUNNING, progress=0.0)

    # Execute all downloads in parallel
    if use_verbose:
        logger.info(f"Starting parallel download of {len(tasks)} datasets...\n")
    results = run_tasks_parallel(tasks, max_workers=max_workers)

    # Update UI status based on results (if UI provided and in fancy mode)
    if ui is not None and ui.mode != DisplayMode.VERBOSE:
        from gridiron_yampylytics.ui import TaskStatus
        for name in results['successful']:
            ui.update_dataset(name, TaskStatus.COMPLETE, progress=1.0)
        for name, error in results['failed']:
            ui.update_dataset(name, TaskStatus.FAILED, progress=0.0)

    # Print summary (verbose mode only)
    if use_verbose:
        logger.info("\n" + "="*80)
        logger.info("DOWNLOAD SUMMARY")
        logger.info("="*80)

        if results['successful']:
            logger.info(f"\n✅ Successfully downloaded {len(results['successful'])} dataset(s):")
            for name in results['successful']:
                logger.info(f"   • {name}")

        if results['failed']:
            logger.info(f"\n⚠️  Failed to download {len(results['failed'])} dataset(s):")
            for name, error in results['failed']:
                logger.info(f"   • {name}: {error[:80]}...")

        logger.info("\n" + "="*80)

    # Update manifest for successful nflverse datasets (not GM)
    nflverse_successful = [name for name in results['successful'] if name != 'gm_data']
    if nflverse_successful:
        if use_verbose:
            logger.info("Updating manifest...")
        for dataset_name in nflverse_successful:
            try:
                dataset_dir = cache_dirs[dataset_name]
                files = list(dataset_dir.glob(f"{dataset_name}.*"))

                if files:
                    total_size = sum(f.stat().st_size for f in files)
                    update_dataset(dataset_name, {
                        "last_downloaded": datetime.now().strftime("%Y-%m-%d"),
                        "file_size_bytes": total_size,
                        "files": len(files)
                    })
            except Exception as e:
                if use_verbose:
                    logger.info(f"  ⚠️  Warning: Could not update manifest for {dataset_name}: {e}")

        if use_verbose:
            logger.info("  ✓ Manifest updated")

    return {
        'successful': results['successful'],
        'failed': results['failed'],
        'total_tasks': len(tasks),
    }
