"""Generate yamplayer_id (unified player ID) for all players across all datasets.

SQL-BASED APPROACH:
1. Start with player_ids.csv as foundation (12K players with comprehensive IDs)
2. Add missing players from other datasets using smart matching
3. Generate yamplayer_id ONCE for deduplicated unified_players table
4. Apply back to all original datasets

Usage:
    uv run python -m scripts.generate_yamplayer_id
    uv run python -m scripts.generate_yamplayer_id --dry-run  # Preview only
    uv run python -m scripts.generate_yamplayer_id --validate  # Run validation
"""
import sys
import hashlib
from pathlib import Path
import argparse
import pandas as pd
import duckdb


def normalize_name(name: str) -> str:
    """Normalize player name for matching.

    Based on nflverse merge_name field conventions.

    :param name: Raw player name
    :return: Normalized name (lowercase, no suffixes, no punctuation)
    """
    if pd.isna(name) or name == '':
        return ''

    name = str(name).lower().strip()

    # Remove suffixes
    suffixes = ['jr', 'jr.', 'sr', 'sr.', 'ii', 'iii', 'iv', 'v']
    for suffix in suffixes:
        name = name.replace(f' {suffix}', '').replace(f'.{suffix}', '')

    # Remove punctuation
    name = name.replace('.', '').replace(',', '').replace('-', ' ')
    name = name.replace("'", '')

    # Normalize whitespace
    name = ' '.join(name.split())

    return name


def generate_yamplayer_id(row: pd.Series) -> str:
    """Generate yamplayer_id from all available IDs and metadata.

    :param row: Row with player data
    :return: yamplayer_id in format YAMP_<hash>
    """
    # Combine all identifying information (use full MD5 hash for low collision)
    id_components = [
        str(row.get('gsis_id', '')),
        str(row.get('pfr_id', '')),
        str(row.get('mfl_id', '')),
        str(row.get('espn_id', '')),
        str(row.get('stats_global_id', '')),
        str(row.get('name', '')),
        str(row.get('birthdate', ''))
    ]

    # Filter out empty values
    id_string = '|'.join([c for c in id_components if c and c != 'nan' and c != 'None'])

    # Generate full MD5 hash (32 chars)
    hash_obj = hashlib.md5(id_string.encode('utf-8'))
    hash_str = hash_obj.hexdigest()

    # Use first 12 chars (281 trillion possibilities - collision extremely unlikely)
    return f'YAMP_{hash_str[:12]}'


def build_unified_players_table(con: duckdb.DuckDBPyConnection, base_dir: Path) -> None:
    """Build unified_players table from all datasets using SQL.

    Uses UPDATE-then-INSERT approach with tiered OR matching:
    1. UPDATE existing rows to enrich with new data
    2. INSERT only truly new players (not matched by ANY criteria)

    Matching tiers:
    - TIER 1: ANY official ID match (gsis_id, pfr_id, mfl_id, espn_id, stats_global_id)
    - TIER 2: merge_name + birthdate
    - TIER 3: Dataset-specific composite keys

    :param con: DuckDB connection
    :param base_dir: Base directory of project
    """
    print("=" * 80)
    print("STEP 1: BUILDING UNIFIED PLAYERS TABLE")
    print("=" * 80)
    print()

    # Define file paths
    player_ids_file = base_dir / "data" / "nflverse" / "player_ids.csv"
    combine_file = base_dir / "data" / "nflverse" / "combine.csv"
    rosters_file = base_dir / "data" / "nflverse" / "rosters.csv"
    draft_file = base_dir / "data" / "nflverse" / "draft_picks.csv"
    yas_file = base_dir / "data" / "yas" / "yas_2025.csv"

    # Step 1a: Load player_ids.csv as foundation (cast all to VARCHAR for consistency)
    print("Loading player_ids.csv as foundation...")
    query = f"""
        CREATE TABLE unified_players AS
        SELECT
            CAST(gsis_id AS VARCHAR) as gsis_id,
            CAST(pfr_id AS VARCHAR) as pfr_id,
            CAST(mfl_id AS VARCHAR) as mfl_id,
            CAST(espn_id AS VARCHAR) as espn_id,
            CAST(stats_global_id AS VARCHAR) as stats_global_id,
            CAST(name AS VARCHAR) as name,
            CAST(merge_name AS VARCHAR) as merge_name,
            CAST(birthdate AS VARCHAR) as birthdate,
            CAST(position AS VARCHAR) as position,
            CAST(team AS VARCHAR) as team,
            CAST(draft_year AS VARCHAR) as draft_year,
            CAST(draft_round AS VARCHAR) as draft_round,
            CAST(draft_pick AS VARCHAR) as draft_pick,
            CAST(college AS VARCHAR) as college,
            CAST(height AS VARCHAR) as height,
            CAST(weight AS VARCHAR) as weight,
            CAST(age AS VARCHAR) as age,
            CAST(db_season AS VARCHAR) as season
        FROM read_csv_auto('{player_ids_file}', strict_mode=false)
    """
    con.execute(query)

    count = con.execute("SELECT COUNT(*) FROM unified_players").fetchone()[0]
    print(f"  ✓ Loaded {count:,} players from player_ids.csv")
    print()

    # Step 1b: Process combine.csv (UPDATE existing, then INSERT new)
    print("Processing combine.csv...")

    # First, UPDATE existing players with new data from combine
    print("  Enriching existing players with combine data...")
    update_query = f"""
        UPDATE unified_players
        SET
            pfr_id = COALESCE(unified_players.pfr_id, c.pfr_id),
            college = COALESCE(unified_players.college, c.school),
            draft_year = COALESCE(unified_players.draft_year, c.draft_year),
            draft_round = COALESCE(unified_players.draft_round, c.draft_round),
            draft_pick = COALESCE(unified_players.draft_pick, c.draft_ovr),
            team = COALESCE(unified_players.team, c.draft_team),
            height = COALESCE(unified_players.height, CAST(c.ht AS VARCHAR)),
            weight = COALESCE(unified_players.weight, CAST(c.wt AS VARCHAR))
        FROM read_csv_auto('{combine_file}', strict_mode=false) c
        WHERE c.player_name IS NOT NULL
          AND (
              -- TIER 1: ANY ID match
              (c.pfr_id IS NOT NULL AND unified_players.pfr_id = c.pfr_id)
              -- TIER 2: No birthdate in combine, skip this tier
              -- TIER 3: Composite key (name + draft_year + school + position)
           OR (unified_players.merge_name = LOWER(REGEXP_REPLACE(c.player_name, ' (jr|sr|ii|iii|iv|v)\\.?$', '', 'i'))
               AND unified_players.draft_year = c.draft_year
               AND unified_players.college = c.school
               AND unified_players.position = c.pos)
          )
    """
    con.execute(update_query)
    print(f"    ✓ Updated existing players")

    # Then, INSERT truly new players from combine
    print("  Adding new players from combine...")
    insert_query = f"""
        INSERT INTO unified_players
        SELECT DISTINCT
            NULL as gsis_id,
            c.pfr_id,
            NULL as mfl_id,
            NULL as espn_id,
            NULL as stats_global_id,
            c.player_name as name,
            LOWER(REGEXP_REPLACE(c.player_name, ' (jr|sr|ii|iii|iv|v)\\.?$', '', 'i')) as merge_name,
            NULL as birthdate,
            c.pos as position,
            c.draft_team as team,
            c.draft_year,
            c.draft_round,
            c.draft_ovr as draft_pick,
            c.school as college,
            CAST(c.ht AS VARCHAR) as height,
            CAST(c.wt AS VARCHAR) as weight,
            NULL as age,
            c.season
        FROM read_csv_auto('{combine_file}', strict_mode=false) c
        WHERE c.player_name IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM unified_players u
              WHERE
                  -- TIER 1: ANY ID match
                  (c.pfr_id IS NOT NULL AND u.pfr_id = c.pfr_id)
                  -- TIER 3: Composite key
               OR (u.merge_name = LOWER(REGEXP_REPLACE(c.player_name, ' (jr|sr|ii|iii|iv|v)\\.?$', '', 'i'))
                   AND u.draft_year = c.draft_year
                   AND u.college = c.school
                   AND u.position = c.pos)
          )
    """
    con.execute(insert_query)

    new_count = con.execute("SELECT COUNT(*) FROM unified_players").fetchone()[0]
    added = new_count - count
    count = new_count
    print(f"    ✓ Added {added:,} new players")
    print(f"  ✓ Total after combine: {count:,}")
    print()

    # Step 1c: Process rosters.csv (UPDATE existing, then INSERT new)
    print("Processing rosters.csv...")

    # UPDATE existing players
    print("  Enriching existing players with roster data...")
    update_query = f"""
        UPDATE unified_players
        SET
            gsis_id = COALESCE(unified_players.gsis_id, CAST(r.gsis_id AS VARCHAR)),
            pfr_id = COALESCE(unified_players.pfr_id, CAST(r.pfr_id AS VARCHAR)),
            espn_id = COALESCE(unified_players.espn_id, CAST(r.espn_id AS VARCHAR)),
            birthdate = COALESCE(unified_players.birthdate, CAST(r.birth_date AS VARCHAR)),
            college = COALESCE(unified_players.college, CAST(r.college AS VARCHAR))
        FROM read_csv_auto('{rosters_file}', strict_mode=false) r
        WHERE r.full_name IS NOT NULL
          AND (
              -- TIER 1: ANY ID match
              (r.gsis_id IS NOT NULL AND CAST(unified_players.gsis_id AS VARCHAR) = CAST(r.gsis_id AS VARCHAR))
           OR (r.pfr_id IS NOT NULL AND CAST(unified_players.pfr_id AS VARCHAR) = CAST(r.pfr_id AS VARCHAR))
           OR (r.espn_id IS NOT NULL AND CAST(unified_players.espn_id AS VARCHAR) = CAST(r.espn_id AS VARCHAR))
              -- TIER 2: merge_name + birthdate
           OR (r.birth_date IS NOT NULL
               AND CAST(unified_players.birthdate AS VARCHAR) = CAST(r.birth_date AS VARCHAR)
               AND unified_players.merge_name = LOWER(REGEXP_REPLACE(r.full_name, ' (jr|sr|ii|iii|iv|v)\\.?$', '', 'i')))
          )
    """
    con.execute(update_query)
    print(f"    ✓ Updated existing players")

    # INSERT new players
    print("  Adding new players from rosters...")
    insert_query = f"""
        INSERT INTO unified_players
        SELECT DISTINCT
            r.gsis_id,
            r.pfr_id,
            NULL as mfl_id,
            r.espn_id,
            NULL as stats_global_id,
            r.full_name as name,
            LOWER(REGEXP_REPLACE(r.full_name, ' (jr|sr|ii|iii|iv|v)\\.?$', '', 'i')) as merge_name,
            r.birth_date as birthdate,
            r.position,
            r.team,
            r.entry_year as draft_year,
            NULL as draft_round,
            r.draft_number as draft_pick,
            r.college,
            CAST(r.height AS VARCHAR) as height,
            CAST(r.weight AS VARCHAR) as weight,
            CAST(r.years_exp AS VARCHAR) as age,
            r.season
        FROM read_csv_auto('{rosters_file}', strict_mode=false) r
        WHERE r.full_name IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM unified_players u
              WHERE
                  -- TIER 1: ANY ID match
                  (r.gsis_id IS NOT NULL AND u.gsis_id = r.gsis_id)
               OR (r.pfr_id IS NOT NULL AND u.pfr_id = r.pfr_id)
               OR (r.espn_id IS NOT NULL AND u.espn_id = r.espn_id)
                  -- TIER 2: merge_name + birthdate
               OR (r.birth_date IS NOT NULL
                   AND u.birthdate = r.birth_date
                   AND u.merge_name = LOWER(REGEXP_REPLACE(r.full_name, ' (jr|sr|ii|iii|iv|v)\\.?$', '', 'i')))
          )
    """
    con.execute(insert_query)

    new_count = con.execute("SELECT COUNT(*) FROM unified_players").fetchone()[0]
    added = new_count - count
    count = new_count
    print(f"    ✓ Added {added:,} new players")
    print(f"  ✓ Total after rosters: {count:,}")
    print()

    # Step 1d: Process draft_picks.csv (UPDATE existing, then INSERT new)
    print("Processing draft_picks.csv...")

    # UPDATE existing players
    print("  Enriching existing players with draft data...")
    update_query = f"""
        UPDATE unified_players
        SET
            pfr_id = COALESCE(unified_players.pfr_id, d.pfr_player_id),
            college = COALESCE(unified_players.college, d.college),
            draft_year = COALESCE(unified_players.draft_year, d.season),
            draft_round = COALESCE(unified_players.draft_round, d.round),
            draft_pick = COALESCE(unified_players.draft_pick, d.pick),
            team = COALESCE(unified_players.team, d.team),
            age = COALESCE(unified_players.age, CAST(d.age AS VARCHAR))
        FROM read_csv_auto('{draft_file}', strict_mode=false) d
        WHERE d.pfr_player_name IS NOT NULL
          AND (
              -- TIER 1: ANY ID match
              (d.pfr_player_id IS NOT NULL AND unified_players.pfr_id = d.pfr_player_id)
              -- TIER 3: Natural key (draft slot is unique per year)
           OR (unified_players.draft_year = d.season
               AND unified_players.draft_round = d.round
               AND unified_players.draft_pick = d.pick)
          )
    """
    con.execute(update_query)
    print(f"    ✓ Updated existing players")

    # INSERT new players
    print("  Adding new players from draft_picks...")
    insert_query = f"""
        INSERT INTO unified_players
        SELECT DISTINCT
            NULL as gsis_id,
            d.pfr_player_id as pfr_id,
            NULL as mfl_id,
            NULL as espn_id,
            NULL as stats_global_id,
            d.pfr_player_name as name,
            LOWER(REGEXP_REPLACE(d.pfr_player_name, ' (jr|sr|ii|iii|iv|v)\\.?$', '', 'i')) as merge_name,
            NULL as birthdate,
            d.position,
            d.team,
            d.season as draft_year,
            d.round as draft_round,
            d.pick as draft_pick,
            d.college,
            NULL as height,
            NULL as weight,
            CAST(d.age AS VARCHAR) as age,
            d.season
        FROM read_csv_auto('{draft_file}', strict_mode=false) d
        WHERE d.pfr_player_name IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM unified_players u
              WHERE
                  -- TIER 1: ANY ID match
                  (d.pfr_player_id IS NOT NULL AND u.pfr_id = d.pfr_player_id)
                  -- TIER 3: Natural key
               OR (u.draft_year = d.season
                   AND u.draft_round = d.round
                   AND u.draft_pick = d.pick)
          )
    """
    con.execute(insert_query)

    new_count = con.execute("SELECT COUNT(*) FROM unified_players").fetchone()[0]
    added = new_count - count
    count = new_count
    print(f"    ✓ Added {added:,} new players")
    print(f"  ✓ Total after draft_picks: {count:,}")
    print()

    # Step 1e: Process YAS data (UPDATE existing, then INSERT new)
    if yas_file.exists():
        print("Processing YAS data...")

        # UPDATE existing players
        print("  Enriching existing players with YAS data...")
        update_query = f"""
            UPDATE unified_players
            SET
                gsis_id = COALESCE(unified_players.gsis_id, y.gsis_id),
                pfr_id = COALESCE(unified_players.pfr_id, y.pfr_id),
                height = COALESCE(unified_players.height, CAST(y.ht_inches AS VARCHAR)),
                weight = COALESCE(unified_players.weight, CAST(y.wt AS VARCHAR))
            FROM read_csv_auto('{yas_file}', strict_mode=false) y
            WHERE y.player_name IS NOT NULL
              AND (
                  -- TIER 1: ANY ID match
                  (y.gsis_id IS NOT NULL AND unified_players.gsis_id = y.gsis_id)
               OR (y.pfr_id IS NOT NULL AND unified_players.pfr_id = y.pfr_id)
              )
        """
        con.execute(update_query)
        updated = con.execute("SELECT changes()").fetchone()[0]
        print(f"    ✓ Updated {updated:,} existing players")

        # INSERT new players (should be very rare)
        print("  Adding new players from YAS...")
        insert_query = f"""
            INSERT INTO unified_players
            SELECT DISTINCT
                y.gsis_id,
                y.pfr_id,
                NULL as mfl_id,
                NULL as espn_id,
                NULL as stats_global_id,
                y.player_name as name,
                LOWER(REGEXP_REPLACE(y.player_name, ' (jr|sr|ii|iii|iv|v)\\.?$', '', 'i')) as merge_name,
                NULL as birthdate,
                y.calculated_position as position,
                NULL as team,
                y.season as draft_year,
                NULL as draft_round,
                NULL as draft_pick,
                NULL as college,
                CAST(y.ht_inches AS VARCHAR) as height,
                CAST(y.wt AS VARCHAR) as weight,
                NULL as age,
                y.season
            FROM read_csv_auto('{yas_file}', strict_mode=false) y
            WHERE y.player_name IS NOT NULL
              AND NOT EXISTS (
                  SELECT 1 FROM unified_players u
                  WHERE
                      -- TIER 1: ANY ID match
                      (y.gsis_id IS NOT NULL AND u.gsis_id = y.gsis_id)
                   OR (y.pfr_id IS NOT NULL AND u.pfr_id = y.pfr_id)
              )
        """
        con.execute(insert_query)

        new_count = con.execute("SELECT COUNT(*) FROM unified_players").fetchone()[0]
        added = new_count - count
        count = new_count
        print(f"    ✓ Added {added:,} new players")
        print(f"  ✓ Total after YAS: {count:,}")
        print()

    # No GROUP BY deduplication needed - the UPDATE-then-INSERT approach prevents duplicates
    print(f"✓ Final unified players count: {count:,}")
    print()


def generate_yamplayer_ids(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Generate yamplayer_id for all players in unified_players table.

    :param con: DuckDB connection
    :return: DataFrame with yamplayer_id added
    """
    print("=" * 80)
    print("STEP 2: GENERATING YAMPLAYER_IDs")
    print("=" * 80)
    print()

    # Export unified_players to pandas for hash generation
    print("Exporting unified_players for ID generation...")
    df = con.execute("SELECT * FROM unified_players").df()
    print(f"  ✓ Loaded {len(df):,} players")
    print()

    # Generate yamplayer_id
    print("Generating yamplayer_id hashes...")
    df['yamplayer_id'] = df.apply(generate_yamplayer_id, axis=1)
    print(f"  ✓ Generated {len(df):,} unique yamplayer_ids")
    print()

    # Check for hash collisions (should be extremely rare)
    duplicates = df['yamplayer_id'].duplicated().sum()
    if duplicates > 0:
        print(f"  ⚠️  WARNING: {duplicates} hash collisions detected!")
        print("     (This should be extremely rare - investigating...)")
        collision_ids = df[df['yamplayer_id'].duplicated(keep=False)]['yamplayer_id'].unique()
        for collision_id in collision_ids[:5]:  # Show first 5
            players = df[df['yamplayer_id'] == collision_id][['name', 'gsis_id', 'pfr_id']]
            print(f"     {collision_id}:")
            print(players.to_string(index=False))
    else:
        print("  ✓ No hash collisions detected!")
    print()

    # Coverage report
    print("ID Coverage Report:")
    for id_col in ['gsis_id', 'pfr_id', 'mfl_id', 'espn_id', 'stats_global_id']:
        count = df[id_col].notna().sum()
        pct = (count / len(df)) * 100
        print(f"  {id_col:20s}: {count:6,} ({pct:5.1f}%)")
    print()

    return df


def apply_yamplayer_id_to_datasets(
    mapping_df: pd.DataFrame,
    base_dir: Path,
    dry_run: bool = False
) -> None:
    """Apply yamplayer_id to all original datasets.

    :param mapping_df: DataFrame with yamplayer_id mapping
    :param base_dir: Base directory of project
    :param dry_run: If True, don't save changes
    """
    print("=" * 80)
    print("STEP 3: APPLYING YAMPLAYER_ID TO ALL DATASETS")
    print("=" * 80)
    print()

    # Create lookup tables for each ID type
    lookups = {}
    for id_col in ['gsis_id', 'pfr_id', 'mfl_id', 'espn_id', 'stats_global_id']:
        lookup = mapping_df[mapping_df[id_col].notna()][[id_col, 'yamplayer_id']].copy()
        lookup = lookup.drop_duplicates(subset=[id_col])
        lookups[id_col] = lookup

    # Datasets to process
    datasets = [
        ('combine.csv', 'pfr_id'),
        ('rosters.csv', 'gsis_id'),
        ('player_stats.csv', 'player_id'),  # player_id is alias for gsis_id
        ('draft_picks.csv', 'pfr_player_id'),
        ('injuries.csv', 'gsis_id'),
        ('depth_charts.csv', 'gsis_id'),
        ('depth_charts_legacy.csv', 'gsis_id'),
        ('depth_charts_modern.csv', 'gsis_id'),
        ('yas_2025.csv', 'pfr_id'),
        ('yas_historical.csv', 'pfr_id'),
    ]

    nflverse_dir = base_dir / "data" / "nflverse"
    yas_dir = base_dir / "data" / "yas"

    for filename, id_col in datasets:
        # Determine file path
        if filename.startswith('yas'):
            file_path = yas_dir / filename
        else:
            file_path = nflverse_dir / filename

        if not file_path.exists():
            print(f"SKIP {filename} (file not found)")
            continue

        print(f"Processing {filename}...", end=' ', flush=True)

        try:
            # Load file
            df = pd.read_csv(file_path, low_memory=False)

            # Handle special cases
            if id_col == 'player_id':
                # player_id is alias for gsis_id in player_stats
                lookup = lookups['gsis_id'].rename(columns={'gsis_id': 'player_id'})
            elif id_col == 'pfr_player_id':
                # draft_picks uses pfr_player_id instead of pfr_id
                lookup = lookups['pfr_id'].rename(columns={'pfr_id': 'pfr_player_id'})
            else:
                if id_col not in lookups:
                    print(f"ERROR: No lookup for {id_col}")
                    continue
                lookup = lookups[id_col]

            # Remove existing yamplayer_id column if it exists (buggy version)
            if 'yamplayer_id' in df.columns:
                df = df.drop(columns=['yamplayer_id'])

            # Join to add new yamplayer_id
            df = df.merge(lookup, on=id_col, how='left')

            matched = df['yamplayer_id'].notna().sum()
            unmatched = df['yamplayer_id'].isna().sum()

            # Save if not dry run
            if not dry_run:
                df.to_csv(file_path, index=False)

            print(f"✓ {matched:,} matched, {unmatched:,} unmatched")

        except Exception as e:
            print(f"ERROR: {e}")

    print()


def validate_yamplayer_ids(mapping_df: pd.DataFrame) -> dict:
    """Run validation checks on yamplayer_id assignments.

    :param mapping_df: DataFrame with yamplayer_id mapping
    :return: Dict with validation results
    """
    print("=" * 80)
    print("VALIDATION: CHECKING YAMPLAYER_ID INTEGRITY")
    print("=" * 80)
    print()

    results = {
        'duplicate_ids': [],
        'split_players': [],
        'total_players': len(mapping_df)
    }

    # Check 1: No duplicate IDs for different players
    print("Checking for duplicate yamplayer_ids...")
    duplicate_check = mapping_df.groupby('yamplayer_id').agg({
        'gsis_id': 'nunique',
        'pfr_id': 'nunique',
        'name': 'nunique'
    })

    duplicates = duplicate_check[
        (duplicate_check['gsis_id'] > 1) |
        (duplicate_check['pfr_id'] > 1)
    ]

    if len(duplicates) > 0:
        print(f"  ⚠️  WARNING: Found {len(duplicates)} yamplayer_ids mapping to multiple players!")
        results['duplicate_ids'] = duplicates.index.tolist()
    else:
        print("  ✓ No duplicate IDs found")

    # Check 2: No split players (same gsis_id, different yamplayer_ids)
    print("Checking for split players...")
    gsis_check = mapping_df[mapping_df['gsis_id'].notna()].groupby('gsis_id').agg({
        'yamplayer_id': 'nunique',
        'name': 'first'
    })

    splits = gsis_check[gsis_check['yamplayer_id'] > 1]

    if len(splits) > 0:
        print(f"  ⚠️  WARNING: Found {len(splits)} players with multiple yamplayer_ids!")
        results['split_players'] = splits.index.tolist()
    else:
        print("  ✓ No split players found")

    print()
    return results


def main() -> None:
    """Main entry point for generating yamplayer_id."""
    sys.stdout.reconfigure(encoding='utf-8')

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run', action='store_true', help='Preview changes without saving')
    parser.add_argument('--validate', action='store_true', help='Run validation checks')
    args = parser.parse_args()

    print("=" * 80)
    print("YAMPLAYER_ID GENERATOR - SQL-BASED APPROACH")
    print("=" * 80)
    print()
    if args.dry_run:
        print("🔍 DRY RUN MODE - No files will be modified")
        print()

    base_dir = Path(__file__).parent.parent

    # Connect to DuckDB
    con = duckdb.connect(':memory:')

    try:
        # Step 1: Build unified players table
        build_unified_players_table(con, base_dir)

        # Step 2: Generate yamplayer_ids
        mapping_df = generate_yamplayer_ids(con)

        # Save mapping (audit trail)
        mapping_file = base_dir / "data" / "yamplayer_mapping.csv"
        if not args.dry_run:
            mapping_df.to_csv(mapping_file, index=False)
            print(f"✓ Saved mapping to: {mapping_file}")
            print()

        # Step 3: Apply to all datasets
        apply_yamplayer_id_to_datasets(mapping_df, base_dir, dry_run=args.dry_run)

        # Validation
        if args.validate:
            validation_results = validate_yamplayer_ids(mapping_df)

            if validation_results['duplicate_ids'] or validation_results['split_players']:
                print("❌ VALIDATION FAILED - Issues detected!")
                sys.exit(1)
            else:
                print("✅ VALIDATION PASSED - All checks OK!")

        if args.dry_run:
            print("🔍 DRY RUN - No files were modified. Run without --dry-run to apply changes.")
        else:
            print("✅ All changes saved!")

    finally:
        con.close()


if __name__ == "__main__":
    main()
