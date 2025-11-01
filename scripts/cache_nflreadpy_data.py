"""Cache nflreadpy data locally for SQL exploration and offline analysis.

This script downloads data from nflreadpy (nflverse) and caches it locally as CSV files.
Useful for SQL exploration in DataGrip, DBeaver, or other SQL tools.

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
from pathlib import Path
from typing import Any
import nflreadpy as nfl


def setup_cache_dirs() -> dict[str, Path]:
    """Create cache directory structure.

    :return: Dictionary mapping dataset names to their cache directories
    """
    base_dir = Path(__file__).parent.parent / "data" / "cached" / "nflreadpy"

    dirs = {
        "pbp": base_dir / "play_by_play",
        "player_stats": base_dir / "player_stats",
        "rosters": base_dir / "rosters",
        "draft_picks": base_dir / "draft_picks",
        "combine": base_dir / "combine",
        "contracts": base_dir / "contracts",
        "ids": base_dir / "player_ids",
        "schedules": base_dir / "schedules",
        "injuries": base_dir / "injuries",
        "depth_charts": base_dir / "depth_charts",
    }

    for dir_path in dirs.values():
        dir_path.mkdir(parents=True, exist_ok=True)

    return dirs


def cache_pbp(seasons: int | list[int] | bool, cache_dir: Path) -> None:
    """Cache play-by-play data.

    :param seasons: Season(s) to load (True for all, None for current, int/list for specific)
    :param cache_dir: Directory to save cached files
    """
    print(f"Loading play-by-play data (seasons={seasons})...")
    df = nfl.load_pbp(seasons=seasons)

    output_file = cache_dir / "pbp_all.csv" if seasons is True else cache_dir / f"pbp_{seasons}.csv"
    df.write_csv(output_file)
    print(f"  ✓ Saved {len(df):,} rows to {output_file}")


def cache_player_stats(seasons: int | list[int] | bool, cache_dir: Path) -> None:
    """Cache player statistics.

    :param seasons: Season(s) to load
    :param cache_dir: Directory to save cached files
    """
    print(f"Loading player stats (seasons={seasons})...")
    df = nfl.load_player_stats(seasons=seasons)

    output_file = cache_dir / "player_stats_all.csv" if seasons is True else cache_dir / f"player_stats_{seasons}.csv"
    df.write_csv(output_file)
    print(f"  ✓ Saved {len(df):,} rows to {output_file}")


def cache_rosters(seasons: int | list[int] | bool, cache_dir: Path) -> None:
    """Cache weekly rosters.

    :param seasons: Season(s) to load
    :param cache_dir: Directory to save cached files
    """
    print(f"Loading rosters (seasons={seasons})...")
    df = nfl.load_rosters(seasons=seasons)

    output_file = cache_dir / "rosters_all.csv" if seasons is True else cache_dir / f"rosters_{seasons}.csv"
    df.write_csv(output_file)
    print(f"  ✓ Saved {len(df):,} rows to {output_file}")


def cache_draft_picks(cache_dir: Path) -> None:
    """Cache draft picks (no season filter - loads all).

    :param cache_dir: Directory to save cached files
    """
    print("Loading draft picks (all years)...")
    df = nfl.load_draft_picks()

    output_file = cache_dir / "draft_picks_all.csv"
    df.write_csv(output_file)
    print(f"  ✓ Saved {len(df):,} rows to {output_file}")


def cache_combine(cache_dir: Path) -> None:
    """Cache NFL Combine results (no season filter - loads all).

    :param cache_dir: Directory to save cached files
    """
    print("Loading combine results (all years)...")
    df = nfl.load_combine()

    output_file = cache_dir / "combine_all.csv"
    df.write_csv(output_file)
    print(f"  ✓ Saved {len(df):,} rows to {output_file}")


def cache_contracts(cache_dir: Path) -> None:
    """Cache player contracts (no season filter - loads all).

    :param cache_dir: Directory to save cached files
    """
    print("Loading player contracts (all years)...")
    df = nfl.load_contracts()

    output_file = cache_dir / "contracts_all.csv"
    df.write_csv(output_file)
    print(f"  ✓ Saved {len(df):,} rows to {output_file}")


def cache_ids(cache_dir: Path) -> None:
    """Cache player ID mappings (no season filter - loads all).

    :param cache_dir: Directory to save cached files
    """
    print("Loading player ID mappings...")
    df = nfl.load_ids()

    output_file = cache_dir / "player_ids_all.csv"
    df.write_csv(output_file)
    print(f"  ✓ Saved {len(df):,} rows to {output_file}")


def cache_schedules(seasons: int | list[int] | bool, cache_dir: Path) -> None:
    """Cache game schedules.

    :param seasons: Season(s) to load
    :param cache_dir: Directory to save cached files
    """
    print(f"Loading schedules (seasons={seasons})...")
    df = nfl.load_schedules(seasons=seasons)

    output_file = cache_dir / "schedules_all.csv" if seasons is True else cache_dir / f"schedules_{seasons}.csv"
    df.write_csv(output_file)
    print(f"  ✓ Saved {len(df):,} rows to {output_file}")


def cache_injuries(seasons: int | list[int] | bool, cache_dir: Path) -> None:
    """Cache injury reports.

    :param seasons: Season(s) to load
    :param cache_dir: Directory to save cached files
    """
    print(f"Loading injuries (seasons={seasons})...")
    df = nfl.load_injuries(seasons=seasons)

    output_file = cache_dir / "injuries_all.csv" if seasons is True else cache_dir / f"injuries_{seasons}.csv"
    df.write_csv(output_file)
    print(f"  ✓ Saved {len(df):,} rows to {output_file}")


def cache_depth_charts(seasons: int | list[int] | bool, cache_dir: Path) -> None:
    """Cache team depth charts.

    :param seasons: Season(s) to load
    :param cache_dir: Directory to save cached files
    """
    print(f"Loading depth charts (seasons={seasons})...")
    df = nfl.load_depth_charts(seasons=seasons)

    output_file = cache_dir / "depth_charts_all.csv" if seasons is True else cache_dir / f"depth_charts_{seasons}.csv"
    df.write_csv(output_file)
    print(f"  ✓ Saved {len(df):,} rows to {output_file}")


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


def main() -> None:
    """Main entry point for caching nflreadpy data."""
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

    # Setup cache directories
    cache_dirs = setup_cache_dirs()

    print("="*80)
    print("NFLREADPY DATA CACHING")
    print("="*80)
    print(f"Dataset: {args.dataset}")
    print(f"Seasons: {seasons if seasons is not None else 'current season'}")
    print(f"Cache location: data/cached/nflreadpy/")
    print("="*80)
    print()

    try:
        if args.dataset == "all":
            # Cache all datasets
            print("Caching all datasets...\n")

            # Cache season-based datasets
            for name, func in SEASON_DATASETS.items():
                func(seasons, cache_dirs[name])

            # Cache non-season datasets
            for name, func in NO_SEASON_DATASETS.items():
                func(cache_dirs[name])

        elif args.dataset in SEASON_DATASETS:
            # Cache specific season-based dataset
            SEASON_DATASETS[args.dataset](seasons, cache_dirs[args.dataset])

        elif args.dataset in NO_SEASON_DATASETS:
            # Cache specific non-season dataset
            if args.seasons:
                print(f"Warning: {args.dataset} doesn't support season filtering. Ignoring --seasons.")
            NO_SEASON_DATASETS[args.dataset](cache_dirs[args.dataset])

        print("\n" + "="*80)
        print("✓ Caching complete!")
        print("="*80)
        print(f"\nData cached in: data/cached/nflreadpy/")
        print("You can now import these CSVs into your SQL tool of choice.")

    except Exception as e:
        print(f"\n❌ Error during caching: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
