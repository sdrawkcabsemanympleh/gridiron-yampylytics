import datetime
import duckdb
import pandas as pd
from dataclasses import dataclass
from enum import Enum


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


def get_percentiles(connection: duckdb.DuckDBPyConnection, position: str, measurable: CombineMeasurables,
                    calculation_year: int,  return_previous_classes: bool = False):
    """Queries DuckDB to get the percentile rank for a given position and measurable.  Uses the contributing_positions
    mapping to map to all positions to be queried for.

    :param str position: position code the calculation will be made for
    :param measurable: measureable to get data for
    :param calculation_year: calculates the percentile based on all players in this draft class or before
    :param return_previous_classes: returns players of previous draft classes for calculating current YAS
    """
    ordering = 'DESC' if higher_is_better(measurable) else 'ASC'
    positions_list = ', '.join(f"'{p}'" for p in contributing_positions[position])
    query_string = f"""
        SELECT
            yamplayer_id
            , player_name
            , pos as drafted_position
            , '{position}' as calculation_position
            --, '{standardize_position(position)}' as yas_position
            , draft_year as draft_year
            , {calculation_year} as calculation_year
            , {measurable.value}
        FROM
            nflverse.combine
        WHERE
            pos IN ({positions_list})
            AND draft_year <= {calculation_year}
        """
    if not return_previous_classes:
        query_string = f'SELECT * FROM ({query_string}) WHERE draft_year = {calculation_year}'
    df = connection.execute(query_string).df()
    df[f'{measurable.value}_percentile'] = df[measurable.value].rank(
        pct=True, ascending=higher_is_better(measurable)) * 10
    df['yas_position'] = df['drafted_position'].apply(standardize_position)
    return df


def calculate_position_yas_scores(connection: duckdb.DuckDBPyConnection, position: str, calculation_year: int,
                                  return_previous_classes: bool = True):
    """Queries DuckDB to get the percentile rank for a given position.  Uses the contributing_positions mapping to
    map to all positions to be queried for.

    :param str position: position code the calculation will be made for
    :param calculation_year: calculates the percentile based on all players in this draft class or before
    :param return_previous_classes: returns players of previous draft classes for calculating current YAS
    """
    columns_to_average = [f'{measurable.value}_percentile' for measurable in CombineMeasurables]
    yas_merged = None
    for measurable in CombineMeasurables:
        percentiles_df = get_percentiles(connection, position, measurable, calculation_year, return_previous_classes)
        percentiles_df = percentiles_df.set_index(['yamplayer_id', 'calculation_position', 'calculation_year'])
        if yas_merged is None:
            yas_merged = percentiles_df
        else:
            cols_to_drop = ['player_name', 'drafted_position', 'yas_position', 'draft_year']
            percentiles_df = percentiles_df.drop(columns=cols_to_drop)
            yas_merged = pd.merge(
                yas_merged,
                percentiles_df,
                left_index=True,
                right_index=True,
                how='outer'
            )
    yas_merged['yas_score_unnormallized'] = yas_merged[columns_to_average].mean(axis=1)
    yas_merged['measurables_present'] = yas_merged[columns_to_average].count(axis=1)
    yas_merged['yas_score'] = yas_merged['yas_score_unnormallized'].rank(pct=True) * 10
    return yas_merged


def calculate_year_yas(connection: duckdb.DuckDBPyConnection, calculation_year: int | None = None,
                              yas_calc_type: YasCalcType = YasCalcType.HISTORICAL):
    """Calculates YAS for a given year for all positions.  If historical is requested, only the players in the draft
    for that year are included, yielding the score compared to all players that year and before, like RAS.  If current,
    scores are calculated for all players in that year and before.  Defaults to this year so current need not have
    a year supplied.

    :param calculation_year: calculates the percentile based on all players in this draft class or before
    :param yas_calc_type: determines whether players of previous draft classes should be returned or not
    :return: Dataframe of the draft class YAS scores
    """
    if calculation_year is None:
        calculation_year = datetime.datetime.now().year
    yas_merged = None
    for position in contributing_positions.keys():
        position_yas = calculate_position_yas_scores(
            connection=connection,
            position=position,
            calculation_year=calculation_year,
            return_previous_classes=True if yas_calc_type == YasCalcType.CURRENT else False,
        )
        if yas_merged is None:
            yas_merged = position_yas
        else:
            yas_merged = pd.concat([yas_merged, position_yas])
    yas_merged['calculation_type'] = yas_calc_type.value
    yas_merged = yas_merged.set_index('calculation_type', append=True)
    return yas_merged


def calculate_all_yas(connection: duckdb.DuckDBPyConnection):
    """Generates all historical YAS data for all years from 2000 forward to now as well as the current years'.  It
    does have the inefficiency of querying for all combine data from 2000 to the calculation year at each iteration,
    which we can optimize by querying only for the new data each iteration and more integration of dataframe indexing.

    :param connection: duckdb.DuckDB connection object
    """
    calculation_year = datetime.datetime.now().year
    historical_years = list(range(2000, calculation_year + 1))
    total_years = len(historical_years)
    yas_merged = None
    print(f"Processing {total_years} historical years (2000-{calculation_year})...")
    for i, year in enumerate(historical_years, 1):
        print(f"  [{i}/{total_years}] Calculating historical YAS for {year}...", end='', flush=True)
        yas_scores = calculate_year_yas(connection=connection, calculation_year=year)
        if yas_merged is None:
            yas_merged = yas_scores
        else:
            yas_merged = pd.concat([yas_merged, yas_scores])
        print(f" ✓ ({len(yas_scores):,} rows)")
    print(f"\nCalculating current YAS for {calculation_year} (all players)...", end='', flush=True)
    current_yas = calculate_year_yas(connection=connection, calculation_year=calculation_year,
                                yas_calc_type=YasCalcType.CURRENT)
    yas_merged = pd.concat([yas_merged, current_yas])
    print(f" ✓ ({len(current_yas):,} rows)")
    return yas_merged


@dataclass
class YasPlayerScore:  # TODO:  Expand this for all combine attributes and make script to generate these
    """Will eventually change to pydantic model and move out, but can be used for fun coding bidness"""
    yamplayer_id: str
    draft_position: str
    draft_year: int
    calculated_position: str
    calculated_year: int
    combine_test: str
    combine_value: float
    yas_overall_current: float
    yas_overall_historical: float


def main() -> None:
    """Main entry point for YAS calculation.

    Loads combine data from CSV into in-memory DuckDB, calculates YAS scores,
    and saves to data/yas/yas_complete.csv
    """
    import sys
    from pathlib import Path

    # Configure UTF-8 output
    sys.stdout.reconfigure(encoding='utf-8')

    print("=" * 80)
    print("YAS CALCULATOR - yamplayer_id Version")
    print("=" * 80)
    print()

    # Setup paths
    base_dir = Path(__file__).parent.parent
    nflverse_dir = base_dir / "data" / "nflverse"
    combine_csv = nflverse_dir / "combine.csv"
    output_dir = base_dir / "data" / "yas"
    output_file = output_dir / "yas_complete.csv"

    # Verify combine CSV exists
    if not combine_csv.exists():
        print(f"❌ ERROR: Combine CSV not found at {combine_csv}")
        sys.exit(1)

    print(f"📂 Loading combine data from: {combine_csv}")

    # Create in-memory DuckDB connection
    print("🔧 Creating DuckDB in-memory connection...")
    con = duckdb.connect(":memory:")

    # Load combine CSV into DuckDB
    print("📥 Loading combine.csv into DuckDB...")
    combine_df = pd.read_csv(combine_csv)
    print(f"   ✓ Loaded {len(combine_df):,} combine records")

    # Register as table in nflverse schema
    con.execute("CREATE SCHEMA IF NOT EXISTS nflverse")
    con.execute("CREATE TABLE nflverse.combine AS SELECT * FROM combine_df")
    print(f"   ✓ Registered as nflverse.combine table")
    print()

    # Calculate YAS scores
    print("🧮 Calculating YAS scores (all historical + current)...")
    print("   This will process years 2000-2025 with progress updates")
    print()

    yas_df = calculate_all_yas(con)

    print()
    print(f"✅ Calculation complete! Generated {len(yas_df):,} rows")
    print()

    # Save to CSV
    print(f"💾 Saving results to: {output_file}")
    output_dir.mkdir(parents=True, exist_ok=True)
    yas_df.to_csv(output_file, index=True)  # index=True to preserve the multi-index
    print(f"   ✓ Saved {len(yas_df):,} records")
    print()

    # Summary stats
    print("📊 Summary:")
    print(f"   Total rows: {len(yas_df):,}")
    print(f"   Unique players: {yas_df.index.get_level_values('yamplayer_id').nunique():,}")
    print(f"   Positions: {yas_df.index.get_level_values('calculation_position').nunique()}")
    print(f"   Years: {yas_df.index.get_level_values('calculation_year').nunique()}")
    print()

    print("=" * 80)
    print("✅ YAS CALCULATION COMPLETE")
    print("=" * 80)
    print()
    print(f"Output: {output_file}")

    con.close()


if __name__ == "__main__":
    main()