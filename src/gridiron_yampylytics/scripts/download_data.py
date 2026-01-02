"""Unified data download script for all data sources.

This script replaces the individual cache_nflreadpy_data.py and download_gm_data.py
scripts with a single, flexible parallel downloader.

For programmatic use, import and call the function directly:
    from gridiron_yampylytics.loaders.parallel_loader import download_datasets_parallel
    from gridiron_yampylytics.config import ESSENTIAL_DATASETS

    result = download_datasets_parallel(
        nflverse_datasets=ESSENTIAL_DATASETS,
        include_gm=True,
        seasons=True
    )

Usage:
    # Download essential datasets + GM data (parallel)
    uv run python -m scripts.download_data --essential --gm --all-seasons

    # Download analysis datasets (current season)
    uv run python -m scripts.download_data --analysis

    # Download specific datasets
    uv run python -m scripts.download_data --datasets combine draft_picks --gm

    # Limit parallel workers
    uv run python -m scripts.download_data --essential --max-workers=4

    # Sequential execution (debugging)
    uv run python -m scripts.download_data --essential --sequential
"""
import sys
import argparse
from gridiron_yampylytics.loaders.parallel_loader import download_datasets_parallel
from gridiron_yampylytics.loaders.nflverse import (
    SEASON_DATASETS,
    NO_SEASON_DATASETS,
    cache_nflverse_data
)
from gridiron_yampylytics.loaders.gm_data import download_gm_data
from gridiron_yampylytics.config import (
    ESSENTIAL_DATASETS,
    ANALYSIS_DATASETS,
    YAMPY_DATASETS
)
from gridiron_yampylytics.ui import ConsoleUI, DisplayMode


def main() -> None:
    """CLI entry point for unified data download."""
    # Note: UTF-8 reconfigure is done later, only for verbose mode
    # Rich Console handles encoding automatically for fancy mode

    parser = argparse.ArgumentParser(
        description="Download NFL data from multiple sources in parallel",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    # Dataset selection (mutually exclusive groups)
    dataset_group = parser.add_mutually_exclusive_group()
    dataset_group.add_argument(
        "--essential",
        action="store_true",
        help="Download essential datasets (combine, draft_picks, rosters)"
    )
    dataset_group.add_argument(
        "--analysis",
        action="store_true",
        help="Download analysis datasets (all except pbp)"
    )
    dataset_group.add_argument(
        "--yampy",
        action="store_true",
        help="Download YAMPY datasets (currently same as --all, may diverge)"
    )
    dataset_group.add_argument(
        "--all",
        action="store_true",
        help="Download ALL available datasets"
    )
    dataset_group.add_argument(
        "--datasets",
        nargs="+",
        choices=list(SEASON_DATASETS.keys()) + list(NO_SEASON_DATASETS.keys()),
        help="Specific dataset(s) to download"
    )

    # Additional options
    parser.add_argument(
        "--gm",
        action="store_true",
        help="Include GM/executive data download"
    )
    parser.add_argument(
        "--seasons",
        nargs="+",
        type=int,
        help="Specific season(s) to cache (e.g., 2023 2024). Omit for current season."
    )
    parser.add_argument(
        "--all-seasons",
        action="store_true",
        help="Download all available seasons"
    )
    parser.add_argument(
        "--sequential",
        action="store_true",
        help="Use sequential execution instead of parallel (for debugging)"
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=None,
        help="Maximum number of parallel workers (default: unlimited)"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Verbose mode with detailed logging (instead of fancy UI)"
    )

    args = parser.parse_args()

    # Determine which datasets to download
    if args.essential:
        nflverse_datasets = ESSENTIAL_DATASETS
    elif args.analysis:
        nflverse_datasets = ANALYSIS_DATASETS
    elif args.yampy:
        nflverse_datasets = YAMPY_DATASETS
    elif args.all:
        nflverse_datasets = list(SEASON_DATASETS.keys()) + list(NO_SEASON_DATASETS.keys())
    elif args.datasets:
        nflverse_datasets = set(args.datasets)
    else:
        # Default to essential if nothing specified
        nflverse_datasets = ESSENTIAL_DATASETS

    # Determine season argument
    if args.all_seasons:
        seasons = True
    elif args.seasons:
        seasons = args.seasons if len(args.seasons) > 1 else args.seasons[0]
    else:
        seasons = None  # Current season

    # Execute download
    if args.sequential:
        # Sequential execution for debugging
        print("Running in SEQUENTIAL mode (for debugging)")
        print()

        successful = []
        failed = []

        # Download nflverse datasets sequentially
        for dataset in nflverse_datasets:
            try:
                cache_nflverse_data(dataset=dataset, seasons=seasons, parallel=False)
                successful.append(dataset)
            except Exception as e:
                failed.append((dataset, str(e)))

        # Download GM data if requested
        if args.gm:
            try:
                download_gm_data()
                successful.append('gm_data')
            except Exception as e:
                failed.append(('gm_data', str(e)))

        result = {
            'successful': successful,
            'failed': failed,
        }
    else:
        # Parallel execution (default)
        # Determine display mode
        mode = DisplayMode.VERBOSE if args.verbose else DisplayMode.FANCY

        # Configure UTF-8 output for verbose mode (Rich handles it automatically for fancy mode)
        if mode == DisplayMode.VERBOSE:
            sys.stdout.reconfigure(encoding='utf-8')

        # Build config for UI header
        config = {
            "datasets": nflverse_datasets,
            "seasons": seasons,
            "gm": args.gm,
            "workers": args.max_workers,
        }

        # Create UI and run download with context manager
        with ConsoleUI(mode=mode, config=config) as ui:
            result = download_datasets_parallel(
                nflverse_datasets=nflverse_datasets,
                include_gm=args.gm,
                seasons=seasons,
                max_workers=args.max_workers,
                ui=ui
            )

    # Exit with error if everything failed
    if result['failed'] and not result['successful']:
        sys.exit(1)


if __name__ == "__main__":
    main()
