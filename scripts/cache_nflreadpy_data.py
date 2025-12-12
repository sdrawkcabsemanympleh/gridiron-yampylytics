"""CLI wrapper for nflverse data caching.

This script is a thin wrapper around the cache_nflverse_data function.
For programmatic use, import and call the function directly:

    from src.gridiron_yampylytics.loaders.nflverse import cache_nflverse_data
    result = cache_nflverse_data(dataset="all", seasons=True)

Usage:
    # Cache all available data
    uv run python -m scripts.cache_nflreadpy_data --all

    # Cache specific seasons
    uv run python -m scripts.cache_nflreadpy_data --seasons 2023 2024

    # Cache specific dataset
    uv run python -m scripts.cache_nflreadpy_data --dataset pbp --seasons 2024

    # Cache current season only
    uv run python -m scripts.cache_nflreadpy_data

Available datasets:
    - pbp: Play-by-play data (1999-2025)
    - player_stats: Weekly/seasonal player statistics (2012-2025)
    - rosters: Weekly rosters (2006-2025)
    - draft_picks: Draft history (1967-2025)
    - combine: NFL Combine results (2000-2024)
    - contracts: Player contracts (2000s-2025)
    - ids: Player ID mappings (all)
    - schedules: Game schedules (1999-2025)
    - injuries: Injury reports (recent)
    - depth_charts: Team depth charts (2017-2025)
"""
import sys
import argparse
from src.gridiron_yampylytics.loaders.nflverse import (
    cache_nflverse_data,
    SEASON_DATASETS,
    NO_SEASON_DATASETS
)


def main() -> None:
    """CLI entry point for nflverse data caching."""
    sys.stdout.reconfigure(encoding='utf-8')

    parser = argparse.ArgumentParser(
        description="Cache nflreadpy data locally for SQL exploration",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument(
        "--dataset",
        choices=list(SEASON_DATASETS.keys()) + list(NO_SEASON_DATASETS.keys()) + ["all"],
        default="all",
        help="Which dataset to cache (default: all)"
    )
    parser.add_argument(
        "--seasons",
        nargs="+",
        type=int,
        help="Specific season(s) to cache (e.g., 2023 2024). Omit for current season."
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Cache all available seasons for the dataset"
    )

    args = parser.parse_args()

    # Determine season argument
    if args.all:
        seasons = True
    elif args.seasons:
        seasons = args.seasons if len(args.seasons) > 1 else args.seasons[0]
    else:
        seasons = None  # Current season

    # Call the caching function
    result = cache_nflverse_data(dataset=args.dataset, seasons=seasons)

    # Exit with error if everything failed
    if result['failed'] and not result['successful']:
        sys.exit(1)


if __name__ == "__main__":
    main()
