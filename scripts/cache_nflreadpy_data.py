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

Available datasets (currently implemented):
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

Additional datasets available from nflreadr (not yet implemented):
    - qbr: ESPN Quarterback Ratings
    - nextgen_stats: Next Gen Stats (player tracking, speed, separation, etc.)
    - snap_counts: Player snap count statistics
    - participation: Player game participation records
    - ftn_charting: Film charting analysis data
    - trades: Player trade transactions
    - players: Player profile information
    - team_stats: Aggregate team performance data
    - pfr_passing: Pro Football Reference passing statistics
    - roster_status: Practice squad, IR, active roster designations
    - ff_opportunity: Fantasy football opportunity metrics
    - ff_rankings: Fantasy football player rankings

To add these datasets:
    1. Add caching function (e.g., cache_nextgen_stats)
    2. Add to SEASON_DATASETS or NO_SEASON_DATASETS dict
    3. Test with: uv run python -m scripts.cache_nflreadpy_data --dataset nextgen_stats --all
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
    base_dir = Path(__file__).parent.parent / "data" / "nflverse"
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
    print(f"Loading play-by-play data (seasons={seasons})...")
    df = nfl.load_pbp(seasons=seasons)

    output_file = cache_dir / "pbp.csv" if seasons is True else cache_dir / f"pbp_{seasons}.csv"
    df.write_csv(output_file)
    print(f"  ✓ Saved {len(df):,} rows to {output_file}")


def cache_player_stats(seasons: int | list[int] | bool, cache_dir: Path) -> None:
    """Cache player statistics.

    :param seasons: Season(s) to load
    :param cache_dir: Directory to save cached files
    """
    print(f"Loading player stats (seasons={seasons})...")
    df = nfl.load_player_stats(seasons=seasons)

    output_file = cache_dir / "player_stats.csv" if seasons is True else cache_dir / f"player_stats_{seasons}.csv"
    df.write_csv(output_file)
    print(f"  ✓ Saved {len(df):,} rows to {output_file}")


def cache_rosters(seasons: int | list[int] | bool, cache_dir: Path) -> None:
    """Cache weekly rosters.

    :param seasons: Season(s) to load
    :param cache_dir: Directory to save cached files
    """
    print(f"Loading rosters (seasons={seasons})...")
    df = nfl.load_rosters(seasons=seasons)

    output_file = cache_dir / "rosters.csv" if seasons is True else cache_dir / f"rosters_{seasons}.csv"
    df.write_csv(output_file)
    print(f"  ✓ Saved {len(df):,} rows to {output_file}")


def cache_draft_picks(cache_dir: Path) -> None:
    """Cache draft picks (no season filter - loads all).

    :param cache_dir: Directory to save cached files
    """
    print("Loading draft picks (all years)...")
    df = nfl.load_draft_picks()

    output_file = cache_dir / "draft_picks.csv"
    df.write_csv(output_file)
    print(f"  ✓ Saved {len(df):,} rows to {output_file}")


def cache_combine(cache_dir: Path) -> None:
    """Cache NFL Combine results (no season filter - loads all).

    :param cache_dir: Directory to save cached files
    """
    print("Loading combine results (all years)...")
    df = nfl.load_combine()

    output_file = cache_dir / "combine.csv"
    df.write_csv(output_file)
    print(f"  ✓ Saved {len(df):,} rows to {output_file}")


def cache_contracts(cache_dir: Path) -> None:
    """Cache player contracts (no season filter - loads all).

    Saved as Parquet because contracts contain nested year-by-year data.

    :param cache_dir: Directory to save cached files
    """
    print("Loading player contracts (all years)...")
    df = nfl.load_contracts()

    output_file = cache_dir / "contracts.parquet"
    df.write_parquet(output_file)
    print(f"  ✓ Saved {len(df):,} rows to {output_file} (Parquet format - includes nested year-by-year contract details)")


def cache_ids(cache_dir: Path) -> None:
    """Cache player ID mappings (no season filter - loads all).

    Uses load_ff_playerids (fantasy football player IDs) for cross-platform ID mapping.

    :param cache_dir: Directory to save cached files
    """
    print("Loading player ID mappings...")
    df = nfl.load_ff_playerids()

    output_file = cache_dir / "player_ids.csv"
    df.write_csv(output_file)
    print(f"  ✓ Saved {len(df):,} rows to {output_file}")


def cache_schedules(seasons: int | list[int] | bool, cache_dir: Path) -> None:
    """Cache game schedules.

    :param seasons: Season(s) to load
    :param cache_dir: Directory to save cached files
    """
    print(f"Loading schedules (seasons={seasons})...")
    df = nfl.load_schedules(seasons=seasons)

    output_file = cache_dir / "schedules.csv" if seasons is True else cache_dir / f"schedules_{seasons}.csv"
    df.write_csv(output_file)
    print(f"  ✓ Saved {len(df):,} rows to {output_file}")


def cache_injuries(seasons: int | list[int] | bool, cache_dir: Path) -> None:
    """Cache injury reports.

    Walks forward from 2009 until hitting a 404, loading all available years.

    :param seasons: Season(s) to load (if True, auto-detects available years)
    :param cache_dir: Directory to save cached files
    """
    if seasons is True:
        # Walk forward from 2009 until we hit a year that doesn't exist
        print("Loading injuries (auto-detecting available years)...")
        from datetime import datetime
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

        print(f"  Found injury data for {len(available_seasons)} seasons ({min(available_seasons)}-{max(available_seasons)})")
        df = nfl.load_injuries(seasons=available_seasons)
        output_file = cache_dir / "injuries.csv"
    else:
        print(f"Loading injuries (seasons={seasons})...")
        df = nfl.load_injuries(seasons=seasons)
        output_file = cache_dir / f"injuries_{seasons}.csv"

    df.write_csv(output_file)
    print(f"  ✓ Saved {len(df):,} rows to {output_file}")


def cache_depth_charts(seasons: int | list[int] | bool, cache_dir: Path) -> None:
    """Cache team depth charts.

    :param seasons: Season(s) to load
    :param cache_dir: Directory to save cached files
    """
    print(f"Loading depth charts (seasons={seasons})...")
    df = nfl.load_depth_charts(seasons=seasons)

    output_file = cache_dir / "depth_charts.csv" if seasons is True else cache_dir / f"depth_charts_{seasons}.csv"
    df.write_csv(output_file)
    print(f"  ✓ Saved {len(df):,} rows to {output_file}")


# ============================================================================
# ADDITIONAL DATASETS (not yet implemented)
# ============================================================================
# To add new datasets, follow this pattern:
#
# def cache_nextgen_stats(seasons: int | list[int] | bool, cache_dir: Path) -> None:
#     """Cache Next Gen Stats (player tracking data)."""
#     print(f"Loading Next Gen Stats (seasons={seasons})...")
#     df = nfl.load_nextgen_stats(seasons=seasons)
#     output_file = cache_dir / "nextgen_stats.csv" if seasons is True else cache_dir / f"nextgen_stats_{seasons}.csv"
#     df.write_csv(output_file)
#     print(f"  ✓ Saved {len(df):,} rows to {output_file}")
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
    print(f"Cache location: data/nflverse/")
    print("="*80)
    print()

    # Track successes and failures
    successful = []
    failed = []

    if args.dataset == "all":
        # Cache all datasets
        print("Caching all datasets...\n")

        # Cache season-based datasets
        for name, func in SEASON_DATASETS.items():
            try:
                func(seasons, cache_dirs[name])
                successful.append(name)
            except Exception as e:
                print(f"  ⚠️  Failed: {e}")
                failed.append((name, str(e)))

        # Cache non-season datasets
        for name, func in NO_SEASON_DATASETS.items():
            try:
                func(cache_dirs[name])
                successful.append(name)
            except Exception as e:
                print(f"  ⚠️  Failed: {e}")
                failed.append((name, str(e)))

    elif args.dataset in SEASON_DATASETS:
        # Cache specific season-based dataset
        try:
            SEASON_DATASETS[args.dataset](seasons, cache_dirs[args.dataset])
            successful.append(args.dataset)
        except Exception as e:
            print(f"\n❌ Error: {e}")
            failed.append((args.dataset, str(e)))

    elif args.dataset in NO_SEASON_DATASETS:
        # Cache specific non-season dataset
        if args.seasons:
            print(f"Warning: {args.dataset} doesn't support season filtering. Ignoring --seasons.")
        try:
            NO_SEASON_DATASETS[args.dataset](cache_dirs[args.dataset])
            successful.append(args.dataset)
        except Exception as e:
            print(f"\n❌ Error: {e}")
            failed.append((args.dataset, str(e)))

    # Print summary
    print("\n" + "="*80)
    print("CACHING SUMMARY")
    print("="*80)

    if successful:
        print(f"\n✅ Successfully cached {len(successful)} dataset(s):")
        for name in successful:
            print(f"   • {name}")

    if failed:
        print(f"\n⚠️  Failed to cache {len(failed)} dataset(s):")
        for name, error in failed:
            print(f"   • {name}: {error[:80]}...")

    print("\n" + "="*80)
    print(f"Data cached in: data/nflverse/")
    print("You can now import these CSVs into your SQL tool of choice.")

    if failed and not successful:
        sys.exit(1)  # Exit with error if everything failed
    elif failed:
        sys.exit(0)  # Exit successfully if some succeeded (warnings only)


if __name__ == "__main__":
    main()
