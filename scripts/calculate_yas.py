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
from pathlib import Path
from typing import Any
import pandas as pd
import numpy as np


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
        'OG': {'OG', 'LG', 'RG'},
        'C': {'C'},
        'DT': {'DT', 'NT', 'LDT', 'RDT'},
        'DE': {'DE', 'LDE', 'RDE'},
        'LB': {'LB', 'OLB', 'ILB', 'MLB', 'WLB', 'SLB'},
        'CB': {'CB', 'LCB', 'RCB'},
        'S': {'S', 'SS', 'FS'},
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

    # Map pfr_id to gsis_id
    print("  Mapping pfr_id to gsis_id...")
    df = df.merge(
        df_ids[['pfr_id', 'gsis_id']],
        on='pfr_id',
        how='left'
    )

    mapped_count = df['gsis_id'].notna().sum()
    print(f"  ✓ Mapped {mapped_count:,} of {len(df):,} records to gsis_id ({mapped_count/len(df)*100:.1f}%)")

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
    expanded_rows = []

    for idx, row in combine_df.iterrows():
        gsis_id = row.get('gsis_id')
        combine_pos = normalize_position(row.get('pos'), pos_mapping)

        # Get positions this player played in NFL
        positions_played = positions_dict.get(gsis_id, []) if pd.notna(gsis_id) else []

        # If we have NFL positions, create row for each position
        # Also include combine position if not already in the list
        if positions_played:
            all_positions = set(positions_played)
            if combine_pos:
                all_positions.add(combine_pos)

            for calc_pos in all_positions:
                new_row = row.copy()
                new_row['combine_position'] = combine_pos
                new_row['calculated_position'] = calc_pos
                new_row['positions_played'] = ','.join(sorted(all_positions))
                expanded_rows.append(new_row)
        else:
            # No NFL data - just use combine position
            new_row = row.copy()
            new_row['combine_position'] = combine_pos
            new_row['calculated_position'] = combine_pos
            new_row['positions_played'] = combine_pos if combine_pos else ''
            expanded_rows.append(new_row)

    df_expanded = pd.DataFrame(expanded_rows)
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

    # Step 1: Extract positions played
    positions_dict = extract_positions_played()
    print()

    # Step 2: Map combine to gsis_id
    df = map_combine_to_gsis()
    print()

    # Step 3: Expand for multi-position players
    df = expand_for_positions(df, positions_dict)
    print()

    # Step 4-6: Calculate scores
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

    :return: DataFrame with YAS scores
    """
    print("\n" + "=" * 80)
    print("CALCULATING YAS - PRIOR YEARS ONLY NORMALIZATION")
    print("=" * 80)
    print()

    # Step 1: Extract positions played
    positions_dict = extract_positions_played()
    print()

    # Step 2: Map combine to gsis_id
    df_all = map_combine_to_gsis()
    print()

    # Step 3: Expand for multi-position players
    df_all = expand_for_positions(df_all, positions_dict)
    print()

    # Process year by year
    print("Processing by year (prior-years-only normalization)...")
    all_years = []

    seasons = sorted(df_all['season'].dropna().unique())
    for year in seasons:
        # Filter to only include current year and earlier
        df_subset = df_all[df_all['season'] <= year].copy()

        # Calculate scores using ALL data up to this year
        df_subset_scored = calculate_metric_scores(df_subset)
        df_subset_scored = calculate_raw_yas(df_subset_scored)
        df_subset_scored = normalize_yas(df_subset_scored)

        # Extract only current year's results
        df_year = df_subset_scored[df_subset_scored['season'] == year].copy()
        all_years.append(df_year)

    df = pd.concat(all_years, ignore_index=True)
    print(f"  ✓ Processed {len(seasons)} seasons")
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
        # Positions
        'combine_position', 'calculated_position', 'positions_played',
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
