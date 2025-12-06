"""Calculate Yampy Athletic Scores (YAS) for NFL draft prospects.

YAS is gridiron-yampylytics' implementation of Relative Athletic Scores (RAS),
calculated from NFL Combine data. Our version differs from official RAS due to:
- Using combine-only data (no pro day measurements)
- Missing 2 of 10 metrics (10-yard split, 20-yard split)
- Different normalization pools (see versions below)

This script creates two versions:
1. yas_2025.csv - Normalized against ALL years (2000-2025)
2. yas_historical.csv - Normalized against PRIOR years only (historical perspective)

Methodology:
- Calculate percentile rank (0-100) for each metric within position group
- Convert to 0-10 score (percentile / 10)
- Average all metric scores to get raw YAS
- Re-normalize raw YAS to 0-10 scale within position (ensures 5.0 = median)

Usage:
    uv run python -m scripts.calculate_yas

Output:
    data/yas/yas_2025.csv
    data/yas/yas_historical.csv
"""
import sys
import heapq
from pathlib import Path
from typing import Any
from dataclasses import dataclass, field
import pandas as pd
import numpy as np


@dataclass
class PlayerMetric:
    """Single player's metric value for heap sorting.

    :param value: Metric value (e.g., 40-yard dash time)
    :param player_id: Unique identifier for the player
    :param season: Year of combine
    :param row_data: Full row data for later retrieval
    """
    value: float
    player_id: str
    season: int
    row_data: dict[str, Any] = field(repr=False)

    def __lt__(self, other: 'PlayerMetric') -> bool:
        """Compare by value for heap sorting."""
        return self.value < other.value


class PercentileCalculator:
    """Manages incremental percentile calculation using heaps.

    Tracks metrics across years, calculating percentiles based on all prior data.
    Uses blue-green heap swapping to avoid re-sorting.

    :param metric_name: Name of the metric (e.g., 'forty', 'vertical')
    :param lower_is_better: If True, use max heap (negative values)
    """

    def __init__(self, metric_name: str, lower_is_better: bool = False):
        self.metric_name = metric_name
        self.lower_is_better = lower_is_better
        self.heaps_by_position: dict[str, list[PlayerMetric]] = {}

    def add_players(self, players: list[PlayerMetric], position: str) -> None:
        """Add players to position-specific heap.

        :param players: List of PlayerMetric objects
        :param position: Position group (e.g., 'QB', 'WR')
        """
        if position not in self.heaps_by_position:
            self.heaps_by_position[position] = []

        heap = self.heaps_by_position[position]
        for player in players:
            # For lower_is_better metrics, negate for max heap behavior
            if self.lower_is_better:
                player.value = -player.value
            heapq.heappush(heap, player)

    def calculate_percentiles(self, position: str, season: int) -> dict[str, float]:
        """Calculate percentiles for all players in position heap.

        Pops all players, calculates percentiles, pushes to new heap.

        :param position: Position group
        :param season: Current season being processed
        :return: Dict mapping player_id to percentile score (0-10)
        """
        if position not in self.heaps_by_position:
            return {}

        old_heap = self.heaps_by_position[position]
        heap_length = len(old_heap)

        if heap_length == 0:
            return {}

        # Pop all players in sorted order
        sorted_players = []
        while old_heap:
            sorted_players.append(heapq.heappop(old_heap))

        # Calculate percentiles (position / total)
        percentiles = {}
        for rank, player in enumerate(sorted_players):
            percentile = (rank / heap_length) * 10  # Convert to 0-10 scale
            percentiles[player.player_id] = percentile

        # Push back to heap (blue-green swap)
        for player in sorted_players:
            heapq.heappush(old_heap, player)

        return percentiles


class IncrementalYASCalculator:
    """Calculates YAS scores incrementally year-by-year.

    Maintains separate PercentileCalculator for each metric.
    """

    def __init__(self):
        self.metrics = [
            ('ht_inches', True, 'ht'),
            ('wt', True, 'wt'),
            ('forty', False, 'forty'),
            ('bench', True, 'bench'),
            ('vertical', True, 'vertical'),
            ('broad_jump', True, 'broad_jump'),
            ('cone', False, 'cone'),
            ('shuttle', False, 'shuttle')
        ]

        # Create calculator for each metric
        self.calculators = {}
        for metric_col, higher_is_better, name in self.metrics:
            lower_is_better = not higher_is_better
            self.calculators[metric_col] = PercentileCalculator(name, lower_is_better)

    def add_year_data(self, df_year: pd.DataFrame) -> None:
        """Add one year's worth of combine data to all heaps.

        :param df_year: DataFrame for single season
        """
        for metric_col, _, _ in self.metrics:
            calculator = self.calculators[metric_col]

            # Group by position
            for position, group in df_year.groupby('calculated_position'):
                players = []

                # Extract values using vectorized operations
                values = group[metric_col]
                pfr_ids = group['pfr_id']
                seasons = group['season']

                for idx in range(len(group)):
                    value = values.iloc[idx]
                    if pd.notna(value):
                        player = PlayerMetric(
                            value=float(value),
                            player_id=f"{pfr_ids.iloc[idx]}_{position}",
                            season=int(seasons.iloc[idx]),
                            row_data=group.iloc[idx].to_dict()
                        )
                        players.append(player)

                if players:
                    calculator.add_players(players, position)

    def calculate_year_scores(self, df_year: pd.DataFrame) -> pd.DataFrame:
        """Calculate scores for current year based on accumulated data.

        :param df_year: DataFrame for single season
        :return: DataFrame with score columns added
        """
        df_result = df_year.copy()

        # Calculate percentiles for each metric
        for metric_col, _, _ in self.metrics:
            calculator = self.calculators[metric_col]
            score_col = metric_col.replace('_inches', '') + '_score'

            # Calculate percentiles for each position
            df_result[score_col] = np.nan
            for position in df_result['calculated_position'].unique():
                percentiles = calculator.calculate_percentiles(position, df_year['season'].iloc[0])

                # Map percentiles to DataFrame using vectorized mask
                mask = df_result['calculated_position'] == position
                position_rows = df_result[mask]

                for idx in position_rows.index:
                    player_id = f"{df_result.at[idx, 'pfr_id']}_{position}"
                    if player_id in percentiles:
                        df_result.at[idx, score_col] = percentiles[player_id]

        return df_result


def parse_height(ht_str: str) -> float | None:
    """Parse height from '6-4' format to inches.

    :param ht_str: Height string in format 'feet-inches'
    :return: Height in inches, or None if invalid
    """
    if pd.isna(ht_str) or not isinstance(ht_str, str):
        return None

    try:
        parts = ht_str.strip().split('-')
        if len(parts) != 2:
            return None
        feet, inches = int(parts[0]), int(parts[1])
        return (feet * 12) + inches
    except (ValueError, AttributeError):
        return None


def create_position_mapping() -> dict[str, set[str]]:
    """Create mapping of position codes to normalized groups.

    :return: Dict mapping normalized position to set of variant codes
    """
    # TODO: Expand this as we discover more position variants in depth charts
    mapping = {
        'QB': {'QB'},
        'RB': {'RB', 'HB', 'FB'},
        'WR': {'WR', 'FL', 'SE'},
        'TE': {'TE'},
        'OT': {'OT', 'LT', 'RT'},
        'OG': {'OG', 'LG', 'RG', 'OL'},
        'C': {'C'},
        'DT': {'DT', 'NT', 'LDT', 'RDT', 'DL'},
        'DE': {'DE', 'LDE', 'RDE', 'EDGE'},
        'LB': {'LB', 'OLB', 'ILB', 'MLB', 'WLB', 'SLB'},
        'CB': {'CB', 'LCB', 'RCB', 'CB/WR'},  # Calculate Travis Hunter as CB
        'S': {'S', 'SS', 'FS', 'SAF'},
        'K': {'K', 'PK'},
        'P': {'P'},
        'LS': {'LS'}
    }
    return mapping


def normalize_position(pos: str, mapping: dict[str, set[str]]) -> str:
    """Normalize a position code to standard group.

    :param pos: Position code to normalize
    :param mapping: Position mapping dictionary
    :return: Normalized position code, or original if no mapping found
    """
    if pd.isna(pos):
        return None

    pos = str(pos).strip().upper()

    # Check if already normalized
    if pos in mapping:
        return pos

    # Find which group this position belongs to
    for normalized, variants in mapping.items():
        if pos in {v.upper() for v in variants}:
            return normalized

    # Return original if no mapping found
    return pos


def extract_positions_played() -> dict[str, list[str]]:
    """Extract all positions each player played from depth charts.

    :return: Dict mapping gsis_id to list of positions played
    """
    print("Extracting positions played from depth charts...")

    base_dir = Path(__file__).parent.parent / "data" / "nflverse"
    pos_mapping = create_position_mapping()
    positions_by_player = {}

    # Load legacy depth charts (2001-2024)
    legacy_file = base_dir / "depth_charts_legacy.csv"
    if legacy_file.exists():
        df_legacy = pd.read_csv(legacy_file)
        for gsis_id, group in df_legacy.groupby('gsis_id'):
            positions = group['position'].unique()
            normalized = [normalize_position(p, pos_mapping) for p in positions if p]
            positions_by_player[gsis_id] = list(set(normalized))

    # Load modern depth charts (2025)
    modern_file = base_dir / "depth_charts_modern.csv"
    if modern_file.exists():
        df_modern = pd.read_csv(modern_file)
        for gsis_id, group in df_modern.groupby('gsis_id'):
            # Modern uses pos_abb field
            positions = group['pos_abb'].unique() if 'pos_abb' in df_modern.columns else []
            normalized = [normalize_position(p, pos_mapping) for p in positions if p]

            if gsis_id in positions_by_player:
                # Merge with legacy positions
                positions_by_player[gsis_id] = list(set(positions_by_player[gsis_id] + normalized))
            else:
                positions_by_player[gsis_id] = list(set(normalized))

    print(f"  ✓ Found positions for {len(positions_by_player):,} players")
    return positions_by_player


def map_combine_to_gsis() -> pd.DataFrame:
    """Load combine data and map pfr_id to gsis_id.

    :return: DataFrame with combine data + gsis_id mapping
    """
    print("Loading combine data...")

    base_dir = Path(__file__).parent.parent / "data" / "nflverse"

    # Load combine data
    combine_file = base_dir / "combine.csv"
    df = pd.read_csv(combine_file)
    print(f"  ✓ Loaded {len(df):,} combine records")

    # Parse height to inches
    print("  Converting heights to inches...")
    df['ht_inches'] = df['ht'].apply(parse_height)

    # Load player ID crosswalk
    ids_file = base_dir / "player_ids.csv"
    df_ids = pd.read_csv(ids_file)

    # Filter to only non-null pfr_ids (avoid empty string matches)
    df_ids_filtered = df_ids[df_ids['pfr_id'].notna() & (df_ids['pfr_id'] != '')]

    # Deduplicate player IDs (one row per player, not per season)
    df_ids_unique = df_ids_filtered[['pfr_id', 'gsis_id']].drop_duplicates(subset=['pfr_id'])

    # Map pfr_id to gsis_id (only for non-null pfr_ids)
    print("  Mapping pfr_id to gsis_id...")
    df_with_pfr = df[df['pfr_id'].notna() & (df['pfr_id'] != '')].copy()
    df_without_pfr = df[~(df['pfr_id'].notna() & (df['pfr_id'] != ''))].copy()

    df_with_pfr = df_with_pfr.merge(
        df_ids_unique,
        on='pfr_id',
        how='left'
    )

    # Concatenate back together
    df = pd.concat([df_with_pfr, df_without_pfr], ignore_index=True)

    mapped_count = df['gsis_id'].notna().sum()
    print(f"  ✓ Mapped {mapped_count:,} of {len(df):,} records to gsis_id ({mapped_count/len(df)*100:.1f}%)")
    print(f"  ✓ {len(df_without_pfr):,} records have no pfr_id (cannot be mapped)")

    return df


def expand_for_positions(
    combine_df: pd.DataFrame,
    positions_dict: dict[str, list[str]]
) -> pd.DataFrame:
    """Create one row per (player, position) combination.

    :param combine_df: Combine data with gsis_id
    :param positions_dict: Dict of gsis_id -> positions played
    :return: Expanded DataFrame with calculated_position column
    """
    print("Expanding rows for multi-position players...")

    pos_mapping = create_position_mapping()

    # Normalize combine positions for all rows at once
    combine_df['combine_position'] = combine_df['pos'].apply(
        lambda x: normalize_position(x, pos_mapping)
    )

    # Build expansion data structure
    expanded_data = []

    for idx in range(len(combine_df)):
        row = combine_df.iloc[idx]
        gsis_id = row.get('gsis_id')
        combine_pos = row['combine_position']

        # Get positions this player played in NFL
        positions_played = positions_dict.get(gsis_id, []) if pd.notna(gsis_id) else []

        # If we have NFL positions, create row for each position
        if positions_played:
            all_positions = set(positions_played)
            if combine_pos:
                all_positions.add(combine_pos)
            positions_str = ','.join(sorted(all_positions))

            for calc_pos in all_positions:
                expanded_data.append({
                    'idx': idx,
                    'calculated_position': calc_pos,
                    'positions_played': positions_str
                })
        else:
            # No NFL data - just use combine position
            expanded_data.append({
                'idx': idx,
                'calculated_position': combine_pos,
                'positions_played': combine_pos if combine_pos else ''
            })

    # Create expansion DataFrame
    df_expansion = pd.DataFrame(expanded_data)

    # Merge back with original data using iloc indexing
    df_expanded = combine_df.iloc[df_expansion['idx'].values].reset_index(drop=True)
    df_expanded['calculated_position'] = df_expansion['calculated_position'].values
    df_expanded['positions_played'] = df_expansion['positions_played'].values

    print(f"  ✓ Expanded to {len(df_expanded):,} rows ({len(combine_df):,} → {len(df_expanded):,})")

    return df_expanded


def calculate_metric_scores(
    df: pd.DataFrame,
    position_col: str = 'calculated_position'
) -> pd.DataFrame:
    """Calculate 0-10 percentile scores for each metric within position groups.

    :param df: DataFrame with combine metrics
    :param position_col: Column name for position grouping
    :return: DataFrame with *_score columns added
    """
    print("Calculating metric scores within position groups...")

    # Metrics configuration: (column_name, higher_is_better)
    metrics = [
        ('ht_inches', True),
        ('wt', True),
        ('forty', False),  # Lower time = better
        ('bench', True),
        ('vertical', True),
        ('broad_jump', True),
        ('cone', False),  # Lower time = better
        ('shuttle', False)  # Lower time = better
    ]

    df = df.copy()

    for metric, higher_is_better in metrics:
        score_col = metric.replace('_inches', '') + '_score'

        # Calculate percentile within each position group
        df[score_col] = df.groupby(position_col)[metric].transform(
            lambda x: x.rank(pct=True, method='average') * 10 if higher_is_better
            else (1 - x.rank(pct=True, method='average')) * 10
        )

    # Count metrics present
    score_cols = [m[0].replace('_inches', '') + '_score' for m in metrics]
    df['metrics_present'] = df[score_cols].notna().sum(axis=1)
    df['is_partial'] = df['metrics_present'] < 6

    print(f"  ✓ Calculated scores for 8 metrics")
    print(f"  ✓ {(~df['is_partial']).sum():,} complete records (≥6 metrics)")
    print(f"  ✓ {df['is_partial'].sum():,} partial records (<6 metrics)")

    return df


def calculate_raw_yas(df: pd.DataFrame) -> pd.DataFrame:
    """Average metric scores to get raw YAS.

    :param df: DataFrame with *_score columns
    :return: DataFrame with yas_raw column
    """
    print("Calculating raw YAS scores...")

    score_cols = ['ht_score', 'wt_score', 'forty_score', 'bench_score',
                  'vertical_score', 'broad_jump_score', 'cone_score', 'shuttle_score']

    df = df.copy()
    df['yas_raw'] = df[score_cols].mean(axis=1, skipna=True)

    print(f"  ✓ Calculated raw YAS (mean of metric scores)")

    return df


def normalize_yas(
    df: pd.DataFrame,
    position_col: str = 'calculated_position'
) -> pd.DataFrame:
    """Re-normalize raw YAS to final 0-10 scale within position groups.

    :param df: DataFrame with yas_raw column
    :param position_col: Column name for position grouping
    :return: DataFrame with yas_score column
    """
    print("Re-normalizing YAS to 0-10 scale within positions...")

    df = df.copy()

    # Calculate percentile of raw YAS within each position
    df['yas_score'] = df.groupby(position_col)['yas_raw'].transform(
        lambda x: x.rank(pct=True, method='average') * 10
    )

    print(f"  ✓ Final YAS scores calculated")

    return df


def calculate_yas_all_years() -> pd.DataFrame:
    """Generate YAS normalized against all years (2000-2025).

    :return: DataFrame with YAS scores
    """
    print("\n" + "=" * 80)
    print("CALCULATING YAS - ALL YEARS NORMALIZATION")
    print("=" * 80)
    print()

    # Load combine data
    df = map_combine_to_gsis()
    print()

    # Normalize combine positions
    print("Normalizing combine positions...")
    pos_mapping = create_position_mapping()
    df['calculated_position'] = df['pos'].apply(lambda x: normalize_position(x, pos_mapping))
    print(f"  ✓ Using combine position only (no multi-position expansion)")
    print()

    # Calculate scores
    df = calculate_metric_scores(df)
    print()
    df = calculate_raw_yas(df)
    print()
    df = normalize_yas(df)
    print()

    # Add normalization method
    df['normalization_method'] = 'all_years'

    return df


def calculate_yas_prior_years() -> pd.DataFrame:
    """Generate YAS normalized against only prior years (historical perspective).

    Uses incremental heap-based calculation for performance.

    :return: DataFrame with YAS scores
    """
    print("\n" + "=" * 80)
    print("CALCULATING YAS - PRIOR YEARS ONLY NORMALIZATION (HEAP-BASED)")
    print("=" * 80)
    print()

    # Load combine data
    df_all = map_combine_to_gsis()
    print()

    # Normalize combine positions
    print("Normalizing combine positions...")
    pos_mapping = create_position_mapping()
    df_all['calculated_position'] = df_all['pos'].apply(lambda x: normalize_position(x, pos_mapping))
    print(f"  ✓ Using combine position only (no multi-position expansion)")
    print(f"  ✓ Total players: {len(df_all):,}")
    print()

    # Initialize incremental calculator
    print("Initializing heap-based calculator...")
    calculator = IncrementalYASCalculator()
    print("  ✓ Created 8 metric calculators (ht, wt, forty, bench, vertical, broad_jump, cone, shuttle)")
    print()

    # Process year by year using heaps
    print("Processing year-by-year (incremental heap approach)...")
    all_years = []

    seasons = sorted(df_all['season'].dropna().unique())
    total_seasons = len(seasons)

    for i, year in enumerate(seasons, 1):
        print(f"  [{i}/{total_seasons}] Processing {year}...", flush=True)

        # Get current year's data
        df_year = df_all[df_all['season'] == year].copy()
        year_players = len(df_year)

        # Add this year's players to heaps
        print(f"    Adding {year_players} players to heaps...", end='', flush=True)
        calculator.add_year_data(df_year)
        print(" ✓")

        # Calculate percentiles for this year (based on accumulated data)
        print(f"    Calculating percentiles (using all data up to {year})...", end='', flush=True)
        df_year_scored = calculator.calculate_year_scores(df_year)
        print(" ✓")

        # Calculate raw YAS and normalize
        print(f"    Computing raw YAS and final normalization...", end='', flush=True)
        df_year_scored = calculate_raw_yas(df_year_scored)
        df_year_scored = normalize_yas(df_year_scored)
        print(" ✓")

        all_years.append(df_year_scored)
        print(f"    ✓ Year {year} complete: {len(df_year_scored)} rows saved")
        print()

    df = pd.concat(all_years, ignore_index=True)
    print(f"✅ Processed {total_seasons} seasons successfully")
    print(f"   Total output rows: {len(df):,}")
    print()

    # Add normalization method
    df['normalization_method'] = 'prior_years_only'

    return df


def save_output(df: pd.DataFrame, filename: str) -> None:
    """Save YAS data to CSV.

    :param df: DataFrame to save
    :param filename: Output filename
    """
    output_dir = Path(__file__).parent.parent / "data" / "yas"
    output_dir.mkdir(parents=True, exist_ok=True)

    output_file = output_dir / filename

    # Select and order columns
    columns = [
        # Identifiers
        'gsis_id', 'pfr_id', 'player_name', 'season',
        # Position
        'pos', 'calculated_position',
        # Metric scores
        'ht_score', 'wt_score', 'forty_score', 'bench_score',
        'vertical_score', 'broad_jump_score', 'cone_score', 'shuttle_score',
        # Raw metrics
        'ht_inches', 'wt', 'forty', 'bench', 'vertical', 'broad_jump', 'cone', 'shuttle',
        # YAS
        'yas_score', 'metrics_present', 'is_partial', 'normalization_method'
    ]

    # Only include columns that exist
    columns = [c for c in columns if c in df.columns]

    df[columns].to_csv(output_file, index=False)
    print(f"  ✓ Saved to {output_file}")
    print(f"  ✓ {len(df):,} records")


def main() -> None:
    """Main entry point for YAS calculation."""
    sys.stdout.reconfigure(encoding='utf-8')

    print("=" * 80)
    print("YAMPY ATHLETIC SCORE (YAS) CALCULATOR")
    print("=" * 80)
    print()
    print("Calculating YAS from NFL Combine data...")
    print()
    print("Metrics used (8 of 10):")
    print("  Physical: height, weight")
    print("  Performance: 40-yard dash, bench press, vertical jump,")
    print("               broad jump, 3-cone drill, 20-yard shuttle")
    print()
    print("Missing metrics: 10-yard split, 20-yard split")
    print()
    print("This script generates two versions:")
    print("  1. yas_2025.csv - Normalized against ALL years")
    print("  2. yas_historical.csv - Normalized against PRIOR years only")
    print()

    try:
        # Version 1: All years normalization
        df_all_years = calculate_yas_all_years()
        save_output(df_all_years, 'yas_2025.csv')
        print()

        # Version 2: Prior years only normalization
        df_historical = calculate_yas_prior_years()
        save_output(df_historical, 'yas_historical.csv')
        print()

        print("=" * 80)
        print("✅ YAS CALCULATION COMPLETE")
        print("=" * 80)
        print()
        print("Output files:")
        print("  data/yas/yas_2025.csv")
        print("  data/yas/yas_historical.csv")
        print()
        print("DuckDB usage:")
        print("  SELECT * FROM yas.yas_2025;")
        print("  SELECT * FROM yas.yas_historical;")

    except Exception as e:
        print()
        print("=" * 80)
        print("❌ ERROR")
        print("=" * 80)
        print(f"Failed to calculate YAS: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
