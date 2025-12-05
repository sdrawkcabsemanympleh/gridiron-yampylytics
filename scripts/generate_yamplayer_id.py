

"""Generate unified yamplayer_id for all NFL datasets.

This script creates a deduplicated unified_players table using SQL-based entity
resolution, then generates yamplayer_id hashes and applies them back to all datasets.

Strategy:
1. Build unified_players table from 5 source datasets
2. Use UPDATE-then-INSERT to enrich and deduplicate
3. Only update VARCHAR-safe fields (skip type-mismatched fields)
4. Generate yamplayer_id from available IDs
5. Apply back to all datasets via LEFT JOIN

TODO:  Change docstring style to reST
TODO:  Handle duplicate rows (use left join right now, can that cause dups on fuzzy matches?)
"""

import argparse
import hashlib
import sys
from pathlib import Path

import duckdb

# Configure UTF-8 output for Windows console
# NOTE: Commenting out reconfigure - it was causing the script to hang/break stdout
# print("DEBUG: Configuring UTF-8...")
# if sys.platform == 'win32':
#     sys.stdout.reconfigure(encoding='utf-8')
print("DEBUG: Skipped UTF-8 reconfigure to avoid stdout issues")


def normalize_name_sql() -> str:
    """Return SQL expression to normalize player names."""
    return "LOWER(REGEXP_REPLACE(TRIM(name), ' (jr\\.?|sr\\.?|ii|iii|iv|v)$', '', 'i'))"


def normalize_college_sql(college_field: str) -> str:
    """Return SQL expression to normalize college names.

    Args:
        college_field: Name of the college column to normalize

    Returns:
        SQL expression that normalizes college names
    """
    return f"""
        REGEXP_REPLACE(
            REGEXP_REPLACE({college_field}, ' St\\.?$', ' State', 'i'),
            ' Col\\.?$', ' College', 'i'
        )
    """


def generate_yamplayer_id(row: dict) -> str:
    """Generate yamplayer_id hash from available identifiers.

    Args:
        row: Dictionary containing player data

    Returns:
        yamplayer_id in format YAMP_<12-char-hash>
    """
    id_components = [
        str(row.get('gsis_id', '')),
        str(row.get('pfr_id', '')),
        str(row.get('mfl_id', '')),
        str(row.get('name', '')),
        str(row.get('birthdate', '')),
        normalize_college_sql(row.get('college', '')),
    ]
    id_string = '|'.join([c for c in id_components if c])
    hash_str = hashlib.md5(id_string.encode()).hexdigest()
    return f'YAMP_{hash_str[:12]}'


def build_unified_players_table(con: duckdb.DuckDBPyConnection, base_dir: Path) -> None:
    """Build deduplicated unified_players table from source datasets.

    Args:
        con: DuckDB connection
        base_dir: Base directory containing data/ folder
    """
    nflverse_dir = base_dir / 'data' / 'nflverse'

    print("\n" + "="*80)
    print("STEP 1: BUILDING UNIFIED PLAYERS TABLE")
    print("="*80)

    # Phase 1: Load player_ids.csv as foundation (minimal schema, VARCHAR-only)
    print("\nLoading player_ids.csv as foundation...")
    player_ids_file = nflverse_dir / 'player_ids.csv'

    con.execute(f"""
        CREATE TABLE unified_players AS
        SELECT DISTINCT
            gsis_id,
            pfr_id,
            mfl_id,
            name,
            {normalize_name_sql()} as merge_name,
            CAST(birthdate AS VARCHAR) as birthdate,
            {normalize_college_sql('college')} as college
        FROM read_csv_auto('{player_ids_file}', strict_mode=false, quote='"')
        WHERE name IS NOT NULL
    """)

    count = con.execute("SELECT COUNT(*) FROM unified_players").fetchone()[0]
    print(f"  [OK] Loaded {count:,} players from player_ids.csv")

    # Phase 2: Process combine.csv
    print("\nProcessing combine.csv...")
    combine_file = nflverse_dir / 'combine.csv'

    # UPDATE: Enrich existing players with pfr_id from combine
    con.execute(f"""
        UPDATE unified_players
        SET
            pfr_id = COALESCE(unified_players.pfr_id, c.pfr_id),
            college = COALESCE(unified_players.college, {normalize_college_sql('c.school')})
        FROM read_csv_auto('{combine_file}', strict_mode=false, quote='"') c
        WHERE c.pfr_id IS NOT NULL
          AND c.player_name IS NOT NULL
          AND (
              (c.pfr_id IS NOT NULL AND unified_players.pfr_id = c.pfr_id)
           OR ({normalize_name_sql()} = LOWER(REGEXP_REPLACE(TRIM(c.player_name), ' (jr\\.?|sr\\.?|ii|iii|iv|v)$', '', 'i'))
               AND unified_players.college IS NOT NULL
               AND unified_players.college = {normalize_college_sql('c.school')})
          )
    """)
    print("  [OK] Enriched existing players with combine data")

    # INSERT: Add new players from combine
    con.execute(f"""
        INSERT INTO unified_players (pfr_id, name, merge_name, college)
        SELECT DISTINCT
            c.pfr_id,
            c.player_name as name,
            LOWER(REGEXP_REPLACE(TRIM(c.player_name), ' (jr\\.?|sr\\.?|ii|iii|iv|v)$', '', 'i')) as merge_name,
            {normalize_college_sql('c.school')} as college
        FROM read_csv_auto('{combine_file}', strict_mode=false, quote='"') c
        WHERE c.player_name IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM unified_players u
              WHERE
                  -- TIER 1: ID match
                  (c.pfr_id IS NOT NULL AND u.pfr_id = c.pfr_id)
                  -- TIER 2: name + college (combine doesn't have birthdate)
               OR (u.merge_name = LOWER(REGEXP_REPLACE(TRIM(c.player_name), ' (jr\\.?|sr\\.?|ii|iii|iv|v)$', '', 'i'))
                   AND u.college IS NOT NULL
                   AND u.college = {normalize_college_sql('c.school')})
          )
    """)

    count = con.execute("SELECT COUNT(*) FROM unified_players").fetchone()[0]
    print(f"  [OK] Total after combine: {count:,}")

    # Phase 3: Process rosters.csv
    print("\nProcessing rosters.csv...")
    rosters_file = nflverse_dir / 'rosters.csv'

    # UPDATE: Enrich with gsis_id and birthdate
    con.execute(f"""
        UPDATE unified_players
        SET
            gsis_id = COALESCE(unified_players.gsis_id, r.gsis_id),
            pfr_id = COALESCE(unified_players.pfr_id, r.pfr_id),
            birthdate = COALESCE(unified_players.birthdate, CAST(r.birth_date AS VARCHAR))
        FROM read_csv_auto('{rosters_file}', strict_mode=false, quote='"') r
        WHERE r.full_name IS NOT NULL
          AND (
              (r.gsis_id IS NOT NULL AND unified_players.gsis_id = r.gsis_id)
           OR (r.pfr_id IS NOT NULL AND unified_players.pfr_id = r.pfr_id)
           OR (r.birth_date IS NOT NULL
               AND unified_players.birthdate = CAST(r.birth_date AS VARCHAR)
               AND unified_players.merge_name = LOWER(REGEXP_REPLACE(TRIM(r.full_name), ' (jr\\.?|sr\\.?|ii|iii|iv|v)$', '', 'i')))
          )
    """)
    print("  [OK] Enriched existing players with roster data")

    # INSERT: Add new players from rosters
    con.execute(f"""
        INSERT INTO unified_players (gsis_id, pfr_id, name, merge_name, birthdate)
        SELECT DISTINCT
            r.gsis_id,
            r.pfr_id,
            r.full_name as name,
            LOWER(REGEXP_REPLACE(TRIM(r.full_name), ' (jr\\.?|sr\\.?|ii|iii|iv|v)$', '', 'i')) as merge_name,
            CAST(r.birth_date AS VARCHAR) as birthdate
        FROM read_csv_auto('{rosters_file}', strict_mode=false, quote='"') r
        WHERE r.full_name IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM unified_players u
              WHERE
                  (r.gsis_id IS NOT NULL AND u.gsis_id = r.gsis_id)
               OR (r.pfr_id IS NOT NULL AND u.pfr_id = r.pfr_id)
               OR (r.birth_date IS NOT NULL
                   AND u.birthdate = CAST(r.birth_date AS VARCHAR)
                   AND u.merge_name = LOWER(REGEXP_REPLACE(TRIM(r.full_name), ' (jr\\.?|sr\\.?|ii|iii|iv|v)$', '', 'i')))
          )
    """)

    count = con.execute("SELECT COUNT(*) FROM unified_players").fetchone()[0]
    print(f"  [OK] Total after rosters: {count:,}")

    # Phase 4: Process draft_picks.csv
    print("\nProcessing draft_picks.csv...")
    draft_file = nflverse_dir / 'draft_picks.csv'

    # UPDATE: Enrich with pfr_id
    con.execute(f"""
        UPDATE unified_players
        SET
            pfr_id = COALESCE(unified_players.pfr_id, d.pfr_player_id),
            college = COALESCE(unified_players.college, {normalize_college_sql('d.college')})
        FROM read_csv_auto('{draft_file}', strict_mode=false, quote='"') d
        WHERE d.pfr_player_name IS NOT NULL
          AND d.pfr_player_id IS NOT NULL
          AND (
              (d.pfr_player_id IS NOT NULL AND unified_players.pfr_id = d.pfr_player_id)
           OR (unified_players.merge_name = LOWER(REGEXP_REPLACE(TRIM(d.pfr_player_name), ' (jr\\.?|sr\\.?|ii|iii|iv|v)$', '', 'i'))
               AND unified_players.college IS NOT NULL
               AND unified_players.college = {normalize_college_sql('d.college')})
          )
    """)
    print("  [OK] Enriched existing players with draft data")

    # INSERT: Add new players from draft
    con.execute(f"""
        INSERT INTO unified_players (pfr_id, name, merge_name, college)
        SELECT DISTINCT
            d.pfr_player_id as pfr_id,
            d.pfr_player_name as name,
            LOWER(REGEXP_REPLACE(TRIM(d.pfr_player_name), ' (jr\\.?|sr\\.?|ii|iii|iv|v)$', '', 'i')) as merge_name,
            d.college
        FROM read_csv_auto('{draft_file}', strict_mode=false, quote='"') d
        WHERE d.pfr_player_name IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM unified_players u
              WHERE
                  -- TIER 1: ID match
                  (d.pfr_player_id IS NOT NULL AND u.pfr_id = d.pfr_player_id)
                  -- TIER 2: name + college (draft doesn't have birthdate)
               OR (u.merge_name = LOWER(REGEXP_REPLACE(TRIM(d.pfr_player_name), ' (jr\\.?|sr\\.?|ii|iii|iv|v)$', '', 'i'))
                   AND u.college IS NOT NULL
                   AND u.college = {normalize_college_sql('d.college')})
          )
    """)

    count = con.execute("SELECT COUNT(*) FROM unified_players").fetchone()[0]
    print(f"  [OK] Total after draft_picks: {count:,}")

    print(f"\n[OK] Unified players table complete: {count:,} unique players")


def generate_yamplayer_ids(con: duckdb.DuckDBPyConnection) -> None:
    """Generate yamplayer_id for each player in unified table.

    Args:
        con: DuckDB connection
    """
    print("\n" + "="*80)
    print("STEP 2: GENERATING YAMPLAYER_IDS")
    print("="*80)

    # Deduplicate unified_players before generating IDs
    print("\nDeduplicating unified_players table...")
    con.execute("""
        CREATE TEMP TABLE unified_deduped AS
        SELECT DISTINCT * FROM unified_players
    """)
    con.execute("DROP TABLE unified_players")
    con.execute("ALTER TABLE unified_deduped RENAME TO unified_players")
    count = con.execute("SELECT COUNT(*) FROM unified_players").fetchone()[0]
    print(f"  [OK] Deduplicated to {count:,} unique players")

    # Export to pandas, generate IDs, reimport
    df = con.execute("SELECT * FROM unified_players").df()
    print(f"\nGenerating yamplayer_id for {len(df):,} players...")

    df['yamplayer_id'] = df.apply(generate_yamplayer_id, axis=1)

    # Check for duplicates
    duplicates = df['yamplayer_id'].duplicated().sum()
    if duplicates > 0:
        print(f"  [WARNING] WARNING: {duplicates} duplicate yamplayer_ids detected!")
        print(f"\nDuplicate yamplayer_ids (showing details):")
        print("="*80)

        # Find which yamplayer_ids are duplicated
        dup_ids = df[df['yamplayer_id'].duplicated(keep=False)].sort_values('yamplayer_id')

        # Group by yamplayer_id and show each group
        for yamp_id, group in dup_ids.groupby('yamplayer_id'):
            print(f"\nyamplayer_id: {yamp_id} ({len(group)} occurrences)")
            for idx, row in group.iterrows():
                print(f"  - {row['name']:30s} | gsis:{str(row['gsis_id']):15s} | pfr:{str(row['pfr_id']):15s} | college:{str(row['college']):20s} | birthdate:{str(row['birthdate'])}")

        print("="*80)

    # Replace table with version containing yamplayer_id
    con.execute("DROP TABLE unified_players")
    con.execute("CREATE TABLE unified_players AS SELECT * FROM df")

    print(f"  [OK] Generated {len(df):,} yamplayer_ids")


def hydrate_combine(con: duckdb.DuckDBPyConnection, df) -> 'pd.DataFrame':
    """Hydrate combine.csv with yamplayer_ids using combine-specific matching logic.

    Matching strategy (mirrors Step 1 combine.csv logic):
    - TIER 1: pfr_id match (when pfr_id IS NOT NULL AND pfr_id != '')
    - TIER 2: Normalized name + normalized college match

    Args:
        con: DuckDB connection with unified_players table loaded
        df: Polars/Pandas DataFrame of combine.csv data

    Returns:
        DataFrame with yamplayer_id column added
    """
    result = con.execute(f"""
        SELECT DISTINCT
            d.*,
            u.yamplayer_id
        FROM df d
        LEFT JOIN unified_players u ON (
            -- TIER 1: ID match
            (d.pfr_id IS NOT NULL AND d.pfr_id != '' AND u.pfr_id = d.pfr_id)
            -- TIER 2: Name + college match
            OR (
                LOWER(REGEXP_REPLACE(TRIM(d.player_name), ' (jr\\.?|sr\\.?|ii|iii|iv|v)$', '', 'i')) = u.merge_name
                AND d.school IS NOT NULL AND d.school != ''
                AND u.college IS NOT NULL
                AND u.college = {normalize_college_sql('d.school')}
            )
        )
    """).df()
    return result


def hydrate_rosters(con: duckdb.DuckDBPyConnection, df) -> 'pd.DataFrame':
    """Hydrate rosters.csv with yamplayer_ids using roster-specific matching logic.

    Matching strategy (mirrors Step 1 rosters.csv logic):
    - TIER 1: gsis_id match (when gsis_id IS NOT NULL AND gsis_id != '')
    - TIER 2: pfr_id match (when pfr_id IS NOT NULL AND pfr_id != '')
    - TIER 3: birthdate + normalized name match

    Args:
        con: DuckDB connection with unified_players table loaded
        df: Polars/Pandas DataFrame of rosters.csv data

    Returns:
        DataFrame with yamplayer_id column added
    """
    result = con.execute("""
        SELECT DISTINCT
            d.*,
            u.yamplayer_id
        FROM df d
        LEFT JOIN unified_players u ON (
            -- TIER 1: gsis_id match
            (d.gsis_id IS NOT NULL AND d.gsis_id != '' AND u.gsis_id = d.gsis_id)
            -- TIER 2: pfr_id match
            OR (d.pfr_id IS NOT NULL AND d.pfr_id != '' AND u.pfr_id = d.pfr_id)
            -- TIER 3: birthdate + name match
            OR (
                d.birth_date IS NOT NULL AND d.birth_date != ''
                AND u.birthdate = CAST(d.birth_date AS VARCHAR)
                AND LOWER(REGEXP_REPLACE(TRIM(d.full_name), ' (jr\\.?|sr\\.?|ii|iii|iv|v)$', '', 'i')) = u.merge_name
            )
        )
    """).df()
    return result


def hydrate_draft_picks(con: duckdb.DuckDBPyConnection, df) -> 'pd.DataFrame':
    """Hydrate draft_picks.csv with yamplayer_ids using draft-specific matching logic.

    Matching strategy (mirrors Step 1 draft_picks.csv logic):
    - TIER 1: pfr_player_id match (when pfr_player_id IS NOT NULL AND pfr_player_id != '')
    - TIER 2: Normalized name + normalized college match

    Note: Maps pfr_player_id -> pfr_id in unified_players

    Args:
        con: DuckDB connection with unified_players table loaded
        df: Polars/Pandas DataFrame of draft_picks.csv data

    Returns:
        DataFrame with yamplayer_id column added
    """
    result = con.execute(f"""
        SELECT DISTINCT
            d.*,
            u.yamplayer_id
        FROM df d
        LEFT JOIN unified_players u ON (
            -- TIER 1: pfr_player_id match (maps to pfr_id in unified_players)
            (d.pfr_player_id IS NOT NULL AND d.pfr_player_id != '' AND u.pfr_id = d.pfr_player_id)
            -- TIER 2: Name + college match
            OR (
                LOWER(REGEXP_REPLACE(TRIM(d.pfr_player_name), ' (jr\\.?|sr\\.?|ii|iii|iv|v)$', '', 'i')) = u.merge_name
                AND d.college IS NOT NULL AND d.college != ''
                AND u.college IS NOT NULL
                AND u.college = {normalize_college_sql('d.college')}
            )
        )
    """).df()
    return result


def hydrate_player_stats(con: duckdb.DuckDBPyConnection, df) -> 'pd.DataFrame':
    """Hydrate player_stats.csv with yamplayer_ids using fast Python dict lookups.

    Matching strategy:
    - TIER 1: player_id match (maps to gsis_id in unified_players) - ALWAYS prefer
    - TIER 2: Normalized name match (no college available) - Only if unique match

    Note: Uses Python dict lookups instead of SQL JOIN for performance (O(n) vs O(n*m))

    Args:
        con: DuckDB connection with unified_players table loaded
        df: Polars/Pandas DataFrame of player_stats.csv data

    Returns:
        DataFrame with yamplayer_id column added
    """
    import pandas as pd

    # Build lookup dicts from unified_players
    unified = con.execute("SELECT gsis_id, merge_name, yamplayer_id FROM unified_players").df()

    # TIER 1: gsis_id -> yamplayer_id (1-to-1 mapping)
    gsis_lookup = unified[unified['gsis_id'].notna()].set_index('gsis_id')['yamplayer_id'].to_dict()

    # TIER 2: merge_name -> yamplayer_id (but only for unique names to avoid ambiguity)
    name_counts = unified['merge_name'].value_counts()
    unique_names = name_counts[name_counts == 1].index
    name_lookup = unified[unified['merge_name'].isin(unique_names)].set_index('merge_name')['yamplayer_id'].to_dict()

    def normalize_name(name):
        """Normalize name to match unified_players.merge_name format."""
        if pd.isna(name) or name == '':
            return None
        import re
        name = str(name).strip()
        name = re.sub(r' (jr\.?|sr\.?|ii|iii|iv|v)$', '', name, flags=re.IGNORECASE)
        return name.lower()

    def get_yamplayer_id(row):
        """Get yamplayer_id with tie-breaking: ID first, then unique name match."""
        # TIER 1: Try gsis_id (player_id) first
        player_id = row.get('player_id')
        if pd.notna(player_id) and player_id != '':
            yamplayer_id = gsis_lookup.get(player_id)
            if yamplayer_id:
                return yamplayer_id

        # TIER 2: Try normalized name (only if unique)
        normalized_name = normalize_name(row.get('player_display_name'))
        if normalized_name:
            return name_lookup.get(normalized_name)

        return None

    # Apply lookup to all rows
    df['yamplayer_id'] = df.apply(get_yamplayer_id, axis=1)
    return df


def hydrate_injuries(con: duckdb.DuckDBPyConnection, df) -> 'pd.DataFrame':
    """Hydrate injuries.csv with yamplayer_ids using fast Python dict lookups.

    Matching strategy:
    - TIER 1: gsis_id match - ALWAYS prefer
    - TIER 2: Normalized name match (no college available) - Only if unique match

    Note: Uses Python dict lookups instead of SQL JOIN for performance (O(n) vs O(n*m))

    Args:
        con: DuckDB connection with unified_players table loaded
        df: Polars/Pandas DataFrame of injuries.csv data

    Returns:
        DataFrame with yamplayer_id column added
    """
    import pandas as pd

    # Build lookup dicts from unified_players
    unified = con.execute("SELECT gsis_id, merge_name, yamplayer_id FROM unified_players").df()

    # TIER 1: gsis_id -> yamplayer_id (1-to-1 mapping)
    gsis_lookup = unified[unified['gsis_id'].notna()].set_index('gsis_id')['yamplayer_id'].to_dict()

    # TIER 2: merge_name -> yamplayer_id (but only for unique names to avoid ambiguity)
    name_counts = unified['merge_name'].value_counts()
    unique_names = name_counts[name_counts == 1].index
    name_lookup = unified[unified['merge_name'].isin(unique_names)].set_index('merge_name')['yamplayer_id'].to_dict()

    def normalize_name(name):
        """Normalize name to match unified_players.merge_name format."""
        if pd.isna(name) or name == '':
            return None
        import re
        name = str(name).strip()
        name = re.sub(r' (jr\.?|sr\.?|ii|iii|iv|v)$', '', name, flags=re.IGNORECASE)
        return name.lower()

    def get_yamplayer_id(row):
        """Get yamplayer_id with tie-breaking: ID first, then unique name match."""
        # TIER 1: Try gsis_id first
        gsis_id = row.get('gsis_id')
        if pd.notna(gsis_id) and gsis_id != '':
            yamplayer_id = gsis_lookup.get(gsis_id)
            if yamplayer_id:
                return yamplayer_id

        # TIER 2: Try normalized name (only if unique)
        normalized_name = normalize_name(row.get('full_name'))
        if normalized_name:
            return name_lookup.get(normalized_name)

        return None

    # Apply lookup to all rows
    df['yamplayer_id'] = df.apply(get_yamplayer_id, axis=1)
    return df


def apply_yamplayer_ids_to_datasets(
    con: duckdb.DuckDBPyConnection,
    base_dir: Path,
    dry_run: bool = False
) -> None:
    """Apply yamplayer_id back to all source datasets using per-dataset hydration functions.

    Args:
        con: DuckDB connection
        base_dir: Base directory containing data/ folder
        dry_run: If True, only show what would be done
    """
    print("\n" + "="*80)
    print("STEP 3: APPLYING YAMPLAYER_IDS TO DATASETS")
    print("="*80)

    nflverse_dir = base_dir / 'data' / 'nflverse'

    # Mapping: filename -> hydration function
    # Each hydrator mirrors the matching logic used in Step 1 for that dataset
    HYDRATORS = {
        'combine.csv': hydrate_combine,
        'rosters.csv': hydrate_rosters,
        'draft_picks.csv': hydrate_draft_picks,
        'player_stats.csv': hydrate_player_stats,
        'injuries.csv': hydrate_injuries,
        # 'depth_charts.csv': hydrate_depth_charts,  # TODO: Add after splitting depth_charts
    }

    # List of datasets to process
    datasets = [
        nflverse_dir / 'combine.csv',
        nflverse_dir / 'rosters.csv',
        nflverse_dir / 'draft_picks.csv',
        nflverse_dir / 'player_stats.csv',
        nflverse_dir / 'injuries.csv',
        # nflverse_dir / 'depth_charts.csv',  # TODO: Add after splitting
    ]

    for file_path in datasets:
        if not file_path.exists():
            print(f"\n[WARNING] Skipping {file_path.name} (not found)")
            continue

        # Get the appropriate hydrator function
        hydrator = HYDRATORS.get(file_path.name)
        if not hydrator:
            print(f"\n[WARNING] No hydrator defined for {file_path.name}, skipping")
            continue

        print(f"\nProcessing {file_path.name}...")

        # Load dataset
        df = con.execute(f"SELECT * FROM read_csv_auto('{file_path}', strict_mode=false, null_padding=true, parallel=false, all_varchar=true, quote='\"')").df()
        original_count = len(df)

        # Drop any existing yamplayer_id column(s) to avoid duplication
        yamplayer_cols = [col for col in df.columns if col == 'yamplayer_id' or col.startswith('yamplayer_id')]
        if yamplayer_cols:
            print(f"  [WARNING] Removing {len(yamplayer_cols)} existing yamplayer_id column(s): {yamplayer_cols}")
            df = df.drop(columns=yamplayer_cols)

        # Call dataset-specific hydrator function
        result = hydrator(con, df)

        # Report match statistics
        matched = result['yamplayer_id'].notna().sum()
        coverage = (matched / original_count * 100) if original_count > 0 else 0
        print(f"  Matched: {matched:,}/{original_count:,} ({coverage:.1f}%)")

        # Write back to CSV
        if not dry_run:
            result.to_csv(file_path, index=False)
            print(f"  [OK] Updated {file_path.name}")
        else:
            print(f"  [DRY RUN] Would update {file_path.name}")


def save_mapping_file(con: duckdb.DuckDBPyConnection, base_dir: Path, dry_run: bool = False) -> None:
    """Save unified player mapping to CSV for audit trail.

    Args:
        con: DuckDB connection
        base_dir: Base directory containing data/ folder
        dry_run: If True, only show what would be done
    """
    print("\n" + "="*80)
    print("SAVING MAPPING FILE")
    print("="*80)

    output_file = base_dir / 'data' / 'reference' / 'yamplayer_mapping.csv'

    df = con.execute("SELECT * FROM unified_players ORDER BY yamplayer_id").df()

    if not dry_run:
        df.to_csv(output_file, index=False)
        print(f"\n[OK] Saved {len(df):,} player mappings to: {output_file}")
    else:
        print(f"\n[DRY RUN] Would save {len(df):,} mappings to: {output_file}")


def main() -> None:
    """Main entry point."""
    print("Starting yamplayer_id generator...")
    print("Parsing arguments...")
    parser = argparse.ArgumentParser(description='Generate yamplayer_id for all datasets')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be done without modifying files')
    args = parser.parse_args()

    print("Resolving paths...")
    base_dir = Path(__file__).parent.parent
    print(f"Base directory: {base_dir}")

    print("\n" + "="*80)
    print("YAMPLAYER_ID GENERATOR - SQL-BASED APPROACH")
    print("="*80)

    if args.dry_run:
        print("\n[DRY RUN] DRY RUN MODE - No files will be modified")

    # Create DuckDB connection
    print("\nInitializing DuckDB connection...")
    con = duckdb.connect(':memory:')
    print("[OK] DuckDB connection established")

    try:
        # Step 1: Build unified players table
        build_unified_players_table(con, base_dir)

        # Step 2: Generate yamplayer_ids
        generate_yamplayer_ids(con)

        # Step 3: Apply to all datasets
        apply_yamplayer_ids_to_datasets(con, base_dir, dry_run=args.dry_run)

        # Step 4: Save mapping file
        save_mapping_file(con, base_dir, dry_run=args.dry_run)

        print("\n" + "="*80)
        print("[OK] COMPLETE!")
        print("="*80)

    finally:
        con.close()


if __name__ == '__main__':
    main()
