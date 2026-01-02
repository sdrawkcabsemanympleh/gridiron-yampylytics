"""YAS (Yampylytics Athletic Score) calculator.

This module calculates athletic scores similar to RAS (Relative Athletic Score)
for NFL prospects based on combine measurables. Provides both historical
(year-by-year) and current (all-time) percentile rankings.

For programmatic use:
    from gridiron_yampylytics.processors.yas import calculate_yas
    result = calculate_yas()

The calculation process:
1. Loads combine data into pandas DataFrame
2. Uses vectorized groupby operations to calculate percentiles by position group
3. Averages percentiles to create YAS scores
4. Generates both historical (draft class) and current (all-time) scores
"""
import datetime
import pandas as pd
import time
from enum import Enum
from pathlib import Path
from typing import Any

from gridiron_yampylytics.manifest import update_transformation_script


# For each position we calculate, we may need to include others, due to it being a superset, naming, nomenclature
# Ideally a player which contributes to more than one of these will have an entry for where they lie in each.
contributing_positions = {
    'QB': {'QB'},
    'RB': {'RB'},
    'FB': {'FB'},
    'OT': {'OT', 'LT', 'RT', 'T'},
    'OG': {'OG', 'LG', 'RG', 'G'},
    'C': {'C'},
    'OL': {'OT', 'LT', 'RT', 'OG', 'LG', 'RG', 'C'},
    'TE': {'TE'},
    'WR': {'WR', 'CB/WR'},  # Hunter gotta go make our lives harder...
    'CB': {'CB', 'CB/WR'},
    'S': {'S', 'SAF'},
    'DB': {'CB', 'CB/WR', 'S', 'SAF'},
    'LB': {'LB', 'ILB'},  # Standardize off-ball-ish linebackers here
    'EDGE': {'EDGE', 'OLB'},  # Edge didn't exist prior to 2018; most would have been OLB, some DE
    'DT': {'DT'},
    'DE': {'DE'},
    'DL': {'DL', 'DT', 'DE'},
    'K': {'K'},
    'P': {'P'},
    'LS': {'LS'}
}


class YasCalcType(Enum):
    """Denotes the calculation, whether including all players (current), or only previous ones (historical)"""
    HISTORICAL = 'historical'
    CURRENT = 'current'


class CombineMeasurables(Enum):
    """Various Combine drills and measurments included in the data, mirroring table column names"""
    BENCH = 'bench'
    BROAD_JUMP = 'broad_jump'
    CONE = 'cone'
    FORTY = 'forty'
    HEIGHT = 'ht'
    SHUTTLE = 'shuttle'
    VERTICAL = 'vertical'
    WEIGHT = 'wt'


def higher_is_better(measurable: CombineMeasurables) -> bool:
    """For some measurables, like height, a big number is good.  Some it is not.  This tells you if big number gud.

    :param measurable: A combine measurable
    :returns: True if the measurable is better, False otherwise
    """
    return measurable.value in {'ht', 'wt', 'bench', 'vertical', 'broad_jump'}


def standardize_position(position: str) -> str:
    """Standardizes the position codes for players.  Trying to be light handed, but still ensure the data has value
    by ensuring there are enough peers to calculate against and we get rid of oddballs like SAF

    :param str position: position code to standardize
    :return: standardized position code
    """
    if position in {'T', 'LT', 'RT'}:
        return 'OT'
    if position in {'LG', 'RG', 'G'}:
        return 'OG'
    if position == 'SAF':
        return 'S'
    if position in {'LB', 'ILB'}:
        return 'LB'
    if position in {'EDGE', 'OLB'}:
        return 'EDGE'
    return position


class YasCalculator:
    """Calculator for Yampylytics Athletic Score (YAS).

    Provides methods to calculate athletic scores similar to RAS (Relative Athletic Score)
    for NFL prospects based on combine measurables. Uses pure pandas operations instead of
    DuckDB for improved performance. Caches combine data and results for reusability.

    Usage:
        calculator = YasCalculator()
        combine_df = YasCalculator.get_combine_data(path_to_csv)
        yas_df = calculator.calculate_all_yas(combine_df)
    """
    _combine_data: pd.DataFrame | None = None
    _yas_historical: pd.DataFrame | None = None
    _yas_current: pd.DataFrame | None = None

    @classmethod
    def get_combine_data(cls, csv_path: Path | None = None, refresh: bool = False) -> pd.DataFrame:
        """Get combine data DataFrame with lazy loading and caching.

        Loads combine CSV on first call and caches for subsequent calls. Returns a copy
        for thread safety. Use refresh=True to force reload from disk.

        :param csv_path: Path to combine.csv file (required on first call or when refresh=True)
        :param refresh: Force reload from CSV even if already cached
        :return: Copy of combine DataFrame (thread-safe)
        :raises ValueError: If csv_path is None and data not already loaded
        """
        if cls._combine_data is None or refresh:
            if csv_path is None:
                raise ValueError("csv_path required for initial load or refresh")
            cls._combine_data = pd.read_csv(csv_path)
        return cls._combine_data.copy()

    @classmethod
    def refresh_combine_data(cls, csv_path: Path) -> None:
        """Force reload combine data from CSV and clear cached results.

        :param csv_path: Path to combine.csv file
        """
        cls._combine_data = pd.read_csv(csv_path)
        cls._yas_historical = None
        cls._yas_current = None

    @classmethod
    def calculate_year_yas(
        cls,
        calculation_year: int | None = None,
        yas_calc_type: YasCalcType = YasCalcType.HISTORICAL
    ) -> pd.DataFrame:
        """Calculate YAS for a given year for all positions using vectorized groupby operations.

        If historical is requested, only the players in the draft for that year are included,
        yielding the score compared to all players that year and before, like RAS. If current,
        scores are calculated for all players in that year and before.

        :param calculation_year: Calculate percentiles based on players in this year and prior
        :param yas_calc_type: Determines whether players of previous draft classes should be returned
        :return: DataFrame of the draft class YAS scores
        """
        combine_df = cls.get_combine_data()
        if calculation_year is None:
            calculation_year = datetime.datetime.now().year
        mask = (combine_df['draft_year'] <= calculation_year)
        if yas_calc_type == YasCalcType.HISTORICAL:
            mask &= (combine_df['draft_year'] == calculation_year)
        df = combine_df[mask].copy()
        # Expand rows: each player appears once per calculation_position they contribute to
        # (e.g., 'CB/WR' contributes to both 'CB' and 'WR' calculations)
        rows_to_add = []
        for calc_pos, raw_positions in contributing_positions.items():
            # Filter for positions that contribute to this calc_pos
            pos_mask = df['pos'].isin(raw_positions)
            pos_df = df[pos_mask].copy()
            pos_df['calculation_position'] = calc_pos
            pos_df['calculation_year'] = calculation_year
            pos_df['yas_position'] = pos_df['pos'].apply(standardize_position)
            rows_to_add.append(pos_df)
        df_expanded = pd.concat(rows_to_add, ignore_index=True)
        percentile_cols = []
        for measurable in CombineMeasurables:
            col_name = f'{measurable.value}_percentile'
            percentile_cols.append(col_name)
            df_expanded[col_name] = (
                df_expanded.groupby('calculation_position')[measurable.value]
                .rank(pct=True, ascending=higher_is_better(measurable)) * 10
            )
        df_expanded['yas_score_unnormallized'] = df_expanded[percentile_cols].mean(axis=1)
        df_expanded['measurables_present'] = df_expanded[percentile_cols].count(axis=1)
        df_expanded['yas_score'] = (
            df_expanded.groupby('calculation_position')['yas_score_unnormallized']
            .rank(pct=True) * 10
        )
        df_expanded['calculation_type'] = yas_calc_type.value
        df_expanded = df_expanded.set_index(['yamplayer_id', 'calculation_position', 'calculation_year', 'calculation_type'])
        return df_expanded

    @classmethod
    def calculate_all_yas(cls) -> pd.DataFrame:
        """Generate all historical YAS data for all years from 2000 forward to now plus current.

        :return: DataFrame with all YAS scores (historical + current)
        """
        calculation_year = datetime.datetime.now().year
        historical_years = list(range(2000, calculation_year + 1))
        total_years = len(historical_years)
        yas_merged = None
        total_time = 0

        print(f"Processing {total_years} historical years (2000-{calculation_year})...")
        print()

        for i, year in enumerate(historical_years, 1):
            print(f"  [{i}/{total_years}] Calculating historical YAS for {year}...", end='', flush=True)

            year_start = time.time()
            yas_scores = cls.calculate_year_yas(calculation_year=year)
            year_elapsed = time.time() - year_start
            total_time += year_elapsed

            if yas_merged is None:
                yas_merged = yas_scores
            else:
                yas_merged = pd.concat([yas_merged, yas_scores])
            print(f" ✓ ({len(yas_scores):,} rows, {year_elapsed:.2f}s)")

        cls._yas_historical = yas_merged

        print(f"\nCalculating current YAS for {calculation_year} (all players)...", end='', flush=True)
        current_start = time.time()
        cls._yas_current = cls.calculate_year_yas(
            calculation_year=calculation_year,
            yas_calc_type=YasCalcType.CURRENT
        )
        current_elapsed = time.time() - current_start
        total_time += current_elapsed
        yas_merged = pd.concat([yas_merged, cls._yas_current])
        print(f" ✓ ({len(cls._yas_current):,} rows, {current_elapsed:.2f}s)")

        print(f"\n✅ Total processing time: {total_time:.2f}s")
        print()

        return yas_merged



def calculate_yas(
    combine_csv: Path | None = None,
    output_file: Path | None = None,
    base_dir: Path | None = None
) -> dict[str, Any]:
    """Calculate YAS scores for all combine data and save to CSV.

    Uses DataFrame-based approach for improved performance (no DuckDB queries).
    Calculates YAS scores for all historical years (2000-present) plus current
    all-time scores, and saves results to CSV.

    :param combine_csv: Path to combine.csv file (default: data/nflverse/combine.csv)
    :param output_file: Path for output CSV (default: data/yas/yas_complete.csv)
    :param base_dir: Base directory for relative paths (default: current working directory)
    :return: Summary dict with statistics and file info
    """

    # Set default paths if not provided
    if base_dir is None:
        base_dir = Path.cwd()
    if combine_csv is None:
        combine_csv = base_dir / "data" / "nflverse" / "combine.csv"
    if output_file is None:
        output_file = base_dir / "data" / "yas" / "yas_complete.csv"

    print("=" * 80)
    print("YAS CALCULATOR - DataFrame-Based (Optimized)")
    print("=" * 80)
    print()

    # Verify combine CSV exists
    if not combine_csv.exists():
        raise FileNotFoundError(f"Combine CSV not found at {combine_csv}")

    print(f"📂 Loading combine data from: {combine_csv}")

    # Load combine CSV into class cache
    print("📥 Loading combine.csv into DataFrame...")
    combine_df = YasCalculator.get_combine_data(csv_path=combine_csv, refresh=True)
    print(f"   ✓ Loaded {len(combine_df):,} combine records")
    print()

    # Calculate YAS scores using static class methods
    print("🧮 Calculating YAS scores (all historical + current)...")
    print("   This will process years 2000-2025 with progress updates")
    print()

    yas_df = YasCalculator.calculate_all_yas()

    print()
    print(f"✅ Calculation complete! Generated {len(yas_df):,} rows")
    print()

    # Save to CSV
    print(f"💾 Saving results to: {output_file}")
    output_file.parent.mkdir(parents=True, exist_ok=True)
    yas_df.to_csv(output_file, index=True)  # index=True to preserve the multi-index
    print(f"   ✓ Saved {len(yas_df):,} records")
    print()

    # Summary stats
    unique_players = yas_df.index.get_level_values('yamplayer_id').nunique()
    num_positions = yas_df.index.get_level_values('calculation_position').nunique()
    num_years = yas_df.index.get_level_values('calculation_year').nunique()

    print("📊 Summary:")
    print(f"   Total rows: {len(yas_df):,}")
    print(f"   Unique players: {unique_players:,}")
    print(f"   Positions: {num_positions}")
    print(f"   Years: {num_years}")
    print()

    print("=" * 80)
    print("✅ YAS CALCULATION COMPLETE")
    print("=" * 80)

    # Update manifest with processing metadata
    print()
    print("=" * 80)
    print("UPDATING MANIFEST")
    print("=" * 80)
    try:
        # Get file size
        file_size = output_file.stat().st_size if output_file.exists() else 0

        # Calculate stats from the YAS dataframe
        total_rows = len(yas_df)
        year_range_start = yas_df.index.get_level_values('calculation_year').min()
        year_range_end = yas_df.index.get_level_values('calculation_year').max()

        # Update manifest
        update_transformation_script("calculate_yas", {
            "last_processed": datetime.datetime.now().strftime("%Y-%m-%d"),
            "file_size_bytes": file_size,
            "total_rows": total_rows,
            "unique_players": unique_players,
            "positions_covered": num_positions,
            "year_range": f"{year_range_start}-{year_range_end}"
        })
        print(f"\n[OK] Manifest updated with processing metadata:")
        print(f"  • Last processed: {datetime.datetime.now().strftime('%Y-%m-%d')}")
        print(f"  • Total rows: {total_rows:,}")
        print(f"  • Unique players: {unique_players:,}")
        print(f"  • Positions covered: {num_positions}")
        print(f"  • Year range: {year_range_start}-{year_range_end}")
    except Exception as e:
        # Don't fail the whole script if manifest update fails
        print(f"\n[WARNING] Could not update manifest: {e}")

    print()
    print(f"Output: {output_file}")

    # Return structured data for programmatic use
    return {
        'total_rows': len(yas_df),
        'unique_players': unique_players,
        'positions_covered': num_positions,
        'years_covered': num_years,
        'year_range': f"{year_range_start}-{year_range_end}",
        'output_file': output_file,
        'file_size_bytes': file_size,
    }
