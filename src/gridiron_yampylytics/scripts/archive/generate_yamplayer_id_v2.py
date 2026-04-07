"""Generate yamplayer_id V2 - uses players.csv as foundation instead of player_ids.csv.

V2 DIFFERENCES FROM V1:
- Foundation: players.csv (24,356 NFL players, 100% gsis_id coverage)
- Enrichment: player_ids.csv (adds fantasy IDs: mfl_id, sleeper_id, etc.)
- Hash prefix: YAMP_V2_{hash} instead of YAMP_{hash}
- Output: yamplayer_mapping_v2.csv (V1 mapping untouched)
- Hydration: SKIPPED (validation only - don't modify datasets yet)

This script is for VALIDATION - compare V1 vs V2 mappings before deciding to hydrate.

Usage:
    uv run python -m scripts.generate_yamplayer_id_v2
    uv run python -m scripts.generate_yamplayer_id_v2 --dry-run
"""
import sys
import argparse
import duckdb
import hashlib
import pandas as pd
from pathlib import Path
from datetime import datetime
from typing import Any


def normalize_name_sql() -> str:
    """Return SQL expression to normalize player names.

    :return: SQL expression for name normalization
    """
    return "LOWER(REGEXP_REPLACE(TRIM(name), ' (jr\\.?|sr\\.?|ii|iii|iv|v)$', '', 'i'))"


def normalize_college_sql(college_field: str) -> str:
    """Return SQL expression to normalize college names.

    :param college_field: Name of the college column to normalize
    :return: SQL expression that normalizes college names
    """
    return f"""
        REGEXP_REPLACE(
            REGEXP_REPLACE({college_field}, ' St\\.?$', ' State', 'i'),
            ' Col\\.?$', ' College', 'i'
        )
    """


def generate_yamplayer_id_v2_hash(row: dict) -> str:
    """Generate yamplayer_id V2 hash from available identifiers.

    V2 uses YAMP_V2_ prefix to differentiate from V1 hashes.

    :param row: Dictionary containing player data
    :return: yamplayer_id in format YAMP_V2_<12-char-hash>
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
    return f'YAMP_V2_{hash_str[:12]}'


def build_unified_players_table_v2(con: duckdb.DuckDBPyConnection, base_dir: Path) -> None:
    """Build deduplicated unified_players table from source datasets - V2 approach.

    V2 STRATEGY:
    - Start with players.csv (24,356 NFL players, perfect gsis_id coverage)
    - Merge in player_ids.csv to add fantasy IDs (mfl_id, sleeper_id, etc.)
    - Then merge combine, rosters, draft_picks (same as V1)

    :param con: DuckDB connection
    :param base_dir: Base directory containing data/ folder
    """
    nflverse_dir = base_dir / 'data' / 'nflverse'

    print("\n" + "="*80)
    print("STEP 1: BUILDING UNIFIED PLAYERS TABLE (V2 - players.csv foundation)")
    print("="*80)

    # Phase 1: Load players.csv as foundation (normalize field names to match V1 schema)
    print("\nLoading players.csv as foundation...")
    players_file = nflverse_dir / 'players.csv'

    con.execute(f"""
        CREATE TABLE unified_players AS
        SELECT DISTINCT
            gsis_id,
            pfr_id,
            NULL::VARCHAR as mfl_id,  -- Will enrich from player_ids.csv
            display_name as name,
            LOWER(REGEXP_REPLACE(TRIM(display_name), ' (jr\\.?|sr\\.?|ii|iii|iv|v)$', '', 'i')) as merge_name,
            CAST(birth_date AS VARCHAR) as birthdate,
            {normalize_college_sql('college_name')} as college
        FROM read_csv_auto('{players_file}', strict_mode=false, quote='"')
        WHERE display_name IS NOT NULL
    """)

    count = con.execute("SELECT COUNT(*) FROM unified_players").fetchone()[0]
    print(f"  [OK] Loaded {count:,} players from players.csv")

    # Phase 2: Merge in player_ids.csv to add fantasy platform IDs
    print("\nMerging player_ids.csv (adding fantasy IDs)...")
    player_ids_file = nflverse_dir / 'player_ids.csv'

    # UPDATE: Enrich existing players with mfl_id and other fantasy IDs
    con.execute(f"""
        UPDATE unified_players
        SET
            mfl_id = COALESCE(unified_players.mfl_id, p.mfl_id)
        FROM read_csv_auto('{player_ids_file}', strict_mode=false, quote='"') p
        WHERE p.name IS NOT NULL
          AND (
              (p.gsis_id IS NOT NULL AND unified_players.gsis_id = p.gsis_id)
           OR (p.pfr_id IS NOT NULL AND unified_players.pfr_id = p.pfr_id)
           OR (p.birthdate IS NOT NULL
               AND unified_players.birthdate = CAST(p.birthdate AS VARCHAR)
               AND unified_players.merge_name = LOWER(REGEXP_REPLACE(TRIM(p.name), ' (jr\\.?|sr\\.?|ii|iii|iv|v)$', '', 'i')))
          )
    """)
    print("  [OK] Enriched existing players with fantasy IDs from player_ids.csv")

    # INSERT: Add new players from player_ids (those not in players.csv)
    con.execute(f"""
        INSERT INTO unified_players (gsis_id, pfr_id, mfl_id, name, merge_name, birthdate, college)
        SELECT DISTINCT
            p.gsis_id,
            p.pfr_id,
            p.mfl_id,
            p.name,
            LOWER(REGEXP_REPLACE(TRIM(p.name), ' (jr\\.?|sr\\.?|ii|iii|iv|v)$', '', 'i')) as merge_name,
            CAST(p.birthdate AS VARCHAR) as birthdate,
            {normalize_college_sql('p.college')} as college
        FROM read_csv_auto('{player_ids_file}', strict_mode=false, quote='"') p
        WHERE p.name IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM unified_players u
              WHERE
                  (p.gsis_id IS NOT NULL AND u.gsis_id = p.gsis_id)
               OR (p.pfr_id IS NOT NULL AND u.pfr_id = p.pfr_id)
               OR (p.birthdate IS NOT NULL
                   AND u.birthdate = CAST(p.birthdate AS VARCHAR)
                   AND u.merge_name = LOWER(REGEXP_REPLACE(TRIM(p.name), ' (jr\\.?|sr\\.?|ii|iii|iv|v)$', '', 'i')))
          )
    """)

    count = con.execute("SELECT COUNT(*) FROM unified_players").fetchone()[0]
    print(f"  [OK] Total after player_ids: {count:,}")

    # Phase 3: Process combine.csv (same as V1)
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
                  (c.pfr_id IS NOT NULL AND u.pfr_id = c.pfr_id)
               OR (u.merge_name = LOWER(REGEXP_REPLACE(TRIM(c.player_name), ' (jr\\.?|sr\\.?|ii|iii|iv|v)$', '', 'i'))
                   AND u.college IS NOT NULL
                   AND u.college = {normalize_college_sql('c.school')})
          )
    """)

    count = con.execute("SELECT COUNT(*) FROM unified_players").fetchone()[0]
    print(f"  [OK] Total after combine: {count:,}")

    # Phase 4: Process rosters.csv (same as V1)
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

    # Phase 5: Process draft_picks.csv (same as V1)
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
                  (d.pfr_player_id IS NOT NULL AND u.pfr_id = d.pfr_player_id)
               OR (u.merge_name = LOWER(REGEXP_REPLACE(TRIM(d.pfr_player_name), ' (jr\\.?|sr\\.?|ii|iii|iv|v)$', '', 'i'))
                   AND u.college IS NOT NULL
                   AND u.college = {normalize_college_sql('d.college')})
          )
    """)

    count = con.execute("SELECT COUNT(*) FROM unified_players").fetchone()[0]
    print(f"  [OK] Total after draft_picks: {count:,}")

    print(f"\n[OK] Unified players table complete: {count:,} unique players")


def generate_yamplayer_ids_v2(con: duckdb.DuckDBPyConnection) -> None:
    """Generate yamplayer_id V2 for each player in unified table.

    Uses YAMP_V2_ prefix to differentiate from V1.

    :param con: DuckDB connection
    """
    print("\n" + "="*80)
    print("STEP 2: GENERATING YAMPLAYER_IDS V2")
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
    print(f"\nGenerating yamplayer_id V2 for {len(df):,} players...")

    df['yamplayer_id'] = df.apply(generate_yamplayer_id_v2_hash, axis=1)

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

    print(f"  [OK] Generated {len(df):,} yamplayer_ids V2")


def save_mapping_file_v2(con: duckdb.DuckDBPyConnection, base_dir: Path, dry_run: bool = False) -> None:
    """Save V2 unified player mapping to CSV for validation.

    Saves to yamplayer_mapping_v2.csv (V1 mapping remains at yamplayer_mapping.csv)

    :param con: DuckDB connection
    :param base_dir: Base directory containing data/ folder
    :param dry_run: If True, only show what would be done
    """
    print("\n" + "="*80)
    print("SAVING V2 MAPPING FILE")
    print("="*80)

    output_file = base_dir / 'data' / 'reference' / 'yamplayer_mapping_v2.csv'

    df = con.execute("SELECT * FROM unified_players ORDER BY yamplayer_id").df()

    if not dry_run:
        df.to_csv(output_file, index=False)
        print(f"\n[OK] Saved {len(df):,} V2 player mappings to: {output_file}")
    else:
        print(f"\n[DRY RUN] Would save {len(df):,} V2 mappings to: {output_file}")


def generate_yamplayer_id_v2(base_dir: Path | None = None, dry_run: bool = False) -> dict[str, Any]:
    """Generate yamplayer_id V2 mapping file (validation only - no hydration).

    V2 CHANGES:
    - Foundation: players.csv (24,356 NFL players) instead of player_ids.csv (7,693)
    - Adds fantasy IDs from player_ids.csv via merge
    - Hash prefix: YAMP_V2_{hash}
    - Output: yamplayer_mapping_v2.csv
    - SKIPS HYDRATION (for validation)

    :param base_dir: Base directory containing data/ folder (default: current working directory)
    :param dry_run: If True, only show what would be done without modifying files
    :return: Summary dict with counts and statistics
    """
    if base_dir is None:
        base_dir = Path.cwd()

    print("\n" + "="*80)
    print("YAMPLAYER_ID V2 GENERATOR - VALIDATION MODE")
    print("="*80)
    print("\nV2 uses players.csv as foundation (not player_ids.csv)")
    print("Output: yamplayer_mapping_v2.csv (V1 remains untouched)")
    print("Hydration: SKIPPED (validation only)")

    if dry_run:
        print("\n[DRY RUN] DRY RUN MODE - No files will be modified")

    # Create DuckDB connection
    print("\nInitializing DuckDB connection...")
    con = duckdb.connect(':memory:')
    print("[OK] DuckDB connection established")

    try:
        # Step 1: Build unified players table (V2 approach)
        build_unified_players_table_v2(con, base_dir)

        # Step 2: Generate yamplayer_ids V2
        generate_yamplayer_ids_v2(con)

        # Step 3: SKIP hydration (validation mode)
        print("\n" + "="*80)
        print("STEP 3: HYDRATION - SKIPPED (VALIDATION MODE)")
        print("="*80)
        print("\nNOTE: Datasets NOT modified - V2 mapping for validation only")
        print("After validation, use separate script to hydrate datasets with V2")

        # Step 4: Save mapping file V2
        save_mapping_file_v2(con, base_dir, dry_run=dry_run)

        # Get stats
        unique_players = con.execute("SELECT COUNT(*) FROM unified_players").fetchone()[0]
        gsis_coverage = con.execute("SELECT COUNT(*) FROM unified_players WHERE gsis_id IS NOT NULL").fetchone()[0]
        gsis_pct = (gsis_coverage / unique_players * 100) if unique_players > 0 else 0

        # Get file info
        mapping_file = base_dir / 'data' / 'reference' / 'yamplayer_mapping_v2.csv'
        file_size = mapping_file.stat().st_size if mapping_file.exists() else 0

        print("\n" + "="*80)
        print("[OK] V2 MAPPING GENERATION COMPLETE!")
        print("="*80)
        print(f"\nV2 Statistics:")
        print(f"  • Total players: {unique_players:,}")
        print(f"  • gsis_id coverage: {gsis_coverage:,} ({gsis_pct:.1f}%)")
        print(f"  • Mapping file: {mapping_file}")
        print(f"\nNext steps:")
        print(f"  1. Compare V1 vs V2 mappings")
        print(f"  2. Validate no duplicates or missing players")
        print(f"  3. If validation passes, decide on hydration strategy")

        return {
            'unique_players': unique_players,
            'gsis_coverage': gsis_coverage,
            'gsis_coverage_pct': gsis_pct,
            'mapping_file': mapping_file,
            'file_size_bytes': file_size,
        }

    finally:
        con.close()


def main() -> None:
    """CLI entry point for yamplayer_id V2 generation."""
    sys.stdout.reconfigure(encoding='utf-8')

    parser = argparse.ArgumentParser(description='Generate yamplayer_id V2 (validation mode)')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be done without modifying files')
    args = parser.parse_args()

    base_dir = Path.cwd()
    generate_yamplayer_id_v2(base_dir=base_dir, dry_run=args.dry_run)


if __name__ == '__main__':
    main()
