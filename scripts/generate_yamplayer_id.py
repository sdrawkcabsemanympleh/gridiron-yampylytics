"""Generate unified yamplayer_id for all NFL datasets.

This script creates a deduplicated unified_players table using SQL-based entity
resolution, then generates yamplayer_id hashes and applies them back to all datasets.

Strategy:
1. Build unified_players table from 5 source datasets
2. Use UPDATE-then-INSERT to enrich and deduplicate
3. Only update VARCHAR-safe fields (skip type-mismatched fields)
4. Generate yamplayer_id from available IDs
5. Apply back to all datasets via LEFT JOIN
"""

import argparse
import hashlib
import sys
from pathlib import Path

import duckdb

# Configure UTF-8 output for Windows console
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')


def normalize_name_sql() -> str:
    """Return SQL expression to normalize player names."""
    return "LOWER(REGEXP_REPLACE(TRIM(name), ' (jr\\.?|sr\\.?|ii|iii|iv|v)$', '', 'i'))"


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
        str(row.get('birthdate', ''))
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
    yas_dir = base_dir / 'data' / 'yas'

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
            position,
            college
        FROM read_csv_auto('{player_ids_file}', strict_mode=false)
        WHERE name IS NOT NULL
    """)

    count = con.execute("SELECT COUNT(*) FROM unified_players").fetchone()[0]
    print(f"  ✓ Loaded {count:,} players from player_ids.csv")

    # Phase 2: Process combine.csv
    print("\nProcessing combine.csv...")
    combine_file = nflverse_dir / 'combine.csv'

    # UPDATE: Enrich existing players with pfr_id from combine
    con.execute(f"""
        UPDATE unified_players
        SET pfr_id = COALESCE(unified_players.pfr_id, c.pfr_id)
        FROM read_csv_auto('{combine_file}', strict_mode=false) c
        WHERE c.pfr_id IS NOT NULL
          AND c.player_name IS NOT NULL
          AND (
              (c.pfr_id IS NOT NULL AND unified_players.pfr_id = c.pfr_id)
           OR ({normalize_name_sql()} = LOWER(REGEXP_REPLACE(TRIM(c.player_name), ' (jr\\.?|sr\\.?|ii|iii|iv|v)$', '', 'i'))
               AND unified_players.college = c.school
               AND unified_players.position = c.pos)
          )
    """)
    print("  ✓ Enriched existing players with combine data")

    # INSERT: Add new players from combine
    con.execute(f"""
        INSERT INTO unified_players (pfr_id, name, merge_name, position, college)
        SELECT DISTINCT
            c.pfr_id,
            c.player_name as name,
            LOWER(REGEXP_REPLACE(TRIM(c.player_name), ' (jr\\.?|sr\\.?|ii|iii|iv|v)$', '', 'i')) as merge_name,
            c.pos as position,
            c.school as college
        FROM read_csv_auto('{combine_file}', strict_mode=false) c
        WHERE c.player_name IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM unified_players u
              WHERE
                  (c.pfr_id IS NOT NULL AND u.pfr_id = c.pfr_id)
               OR (u.merge_name = LOWER(REGEXP_REPLACE(TRIM(c.player_name), ' (jr\\.?|sr\\.?|ii|iii|iv|v)$', '', 'i'))
                   AND u.college = c.school
                   AND u.position = c.pos)
          )
    """)

    count = con.execute("SELECT COUNT(*) FROM unified_players").fetchone()[0]
    print(f"  ✓ Total after combine: {count:,}")

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
        FROM read_csv_auto('{rosters_file}', strict_mode=false) r
        WHERE r.full_name IS NOT NULL
          AND (
              (r.gsis_id IS NOT NULL AND unified_players.gsis_id = r.gsis_id)
           OR (r.pfr_id IS NOT NULL AND unified_players.pfr_id = r.pfr_id)
           OR (r.birth_date IS NOT NULL
               AND unified_players.birthdate = CAST(r.birth_date AS VARCHAR)
               AND unified_players.merge_name = LOWER(REGEXP_REPLACE(TRIM(r.full_name), ' (jr\\.?|sr\\.?|ii|iii|iv|v)$', '', 'i')))
          )
    """)
    print("  ✓ Enriched existing players with roster data")

    # INSERT: Add new players from rosters
    con.execute(f"""
        INSERT INTO unified_players (gsis_id, pfr_id, name, merge_name, birthdate, position)
        SELECT DISTINCT
            r.gsis_id,
            r.pfr_id,
            r.full_name as name,
            LOWER(REGEXP_REPLACE(TRIM(r.full_name), ' (jr\\.?|sr\\.?|ii|iii|iv|v)$', '', 'i')) as merge_name,
            CAST(r.birth_date AS VARCHAR) as birthdate,
            r.position
        FROM read_csv_auto('{rosters_file}', strict_mode=false) r
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
    print(f"  ✓ Total after rosters: {count:,}")

    # Phase 4: Process draft_picks.csv
    print("\nProcessing draft_picks.csv...")
    draft_file = nflverse_dir / 'draft_picks.csv'

    # UPDATE: Enrich with pfr_id
    con.execute(f"""
        UPDATE unified_players
        SET pfr_id = COALESCE(unified_players.pfr_id, d.pfr_player_id)
        FROM read_csv_auto('{draft_file}', strict_mode=false) d
        WHERE d.pfr_player_name IS NOT NULL
          AND d.pfr_player_id IS NOT NULL
          AND (
              (d.pfr_player_id IS NOT NULL AND unified_players.pfr_id = d.pfr_player_id)
           OR (unified_players.merge_name = LOWER(REGEXP_REPLACE(TRIM(d.pfr_player_name), ' (jr\\.?|sr\\.?|ii|iii|iv|v)$', '', 'i'))
               AND unified_players.position = d.position
               AND unified_players.college = d.college)
          )
    """)
    print("  ✓ Enriched existing players with draft data")

    # INSERT: Add new players from draft
    con.execute(f"""
        INSERT INTO unified_players (pfr_id, name, merge_name, position, college)
        SELECT DISTINCT
            d.pfr_player_id as pfr_id,
            d.pfr_player_name as name,
            LOWER(REGEXP_REPLACE(TRIM(d.pfr_player_name), ' (jr\\.?|sr\\.?|ii|iii|iv|v)$', '', 'i')) as merge_name,
            d.position,
            d.college
        FROM read_csv_auto('{draft_file}', strict_mode=false) d
        WHERE d.pfr_player_name IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM unified_players u
              WHERE
                  (d.pfr_player_id IS NOT NULL AND u.pfr_id = d.pfr_player_id)
               OR (u.merge_name = LOWER(REGEXP_REPLACE(TRIM(d.pfr_player_name), ' (jr\\.?|sr\\.?|ii|iii|iv|v)$', '', 'i'))
                   AND u.position = d.position
                   AND u.college = d.college)
          )
    """)

    count = con.execute("SELECT COUNT(*) FROM unified_players").fetchone()[0]
    print(f"  ✓ Total after draft_picks: {count:,}")

    # Phase 5: Process YAS data
    print("\nProcessing yas_2025.csv...")
    yas_file = yas_dir / 'yas_2025.csv'

    if yas_file.exists():
        # UPDATE: Enrich with IDs from YAS
        con.execute(f"""
            UPDATE unified_players
            SET
                gsis_id = COALESCE(unified_players.gsis_id, y.gsis_id),
                pfr_id = COALESCE(unified_players.pfr_id, y.pfr_id)
            FROM read_csv_auto('{yas_file}', strict_mode=false) y
            WHERE y.player_name IS NOT NULL
              AND (
                  (y.gsis_id IS NOT NULL AND unified_players.gsis_id = y.gsis_id)
               OR (y.pfr_id IS NOT NULL AND unified_players.pfr_id = y.pfr_id)
               OR (unified_players.merge_name = LOWER(REGEXP_REPLACE(TRIM(y.player_name), ' (jr\\.?|sr\\.?|ii|iii|iv|v)$', '', 'i')))
              )
        """)
        print("  ✓ Enriched existing players with YAS data")

        # INSERT: Add new players from YAS
        con.execute(f"""
            INSERT INTO unified_players (gsis_id, pfr_id, name, merge_name, position)
            SELECT DISTINCT
                y.gsis_id,
                y.pfr_id,
                y.player_name as name,
                LOWER(REGEXP_REPLACE(TRIM(y.player_name), ' (jr\\.?|sr\\.?|ii|iii|iv|v)$', '', 'i')) as merge_name,
                y.pos as position
            FROM read_csv_auto('{yas_file}', strict_mode=false) y
            WHERE y.player_name IS NOT NULL
              AND NOT EXISTS (
                  SELECT 1 FROM unified_players u
                  WHERE
                      (y.gsis_id IS NOT NULL AND u.gsis_id = y.gsis_id)
                   OR (y.pfr_id IS NOT NULL AND u.pfr_id = y.pfr_id)
                   OR (u.merge_name = LOWER(REGEXP_REPLACE(TRIM(y.player_name), ' (jr\\.?|sr\\.?|ii|iii|iv|v)$', '', 'i')))
              )
        """)

        count = con.execute("SELECT COUNT(*) FROM unified_players").fetchone()[0]
        print(f"  ✓ Total after YAS: {count:,}")
    else:
        print("  ⚠ YAS file not found, skipping")

    print(f"\n✅ Unified players table complete: {count:,} unique players")


def generate_yamplayer_ids(con: duckdb.DuckDBPyConnection) -> None:
    """Generate yamplayer_id for each player in unified table.

    Args:
        con: DuckDB connection
    """
    print("\n" + "="*80)
    print("STEP 2: GENERATING YAMPLAYER_IDS")
    print("="*80)

    # Export to pandas, generate IDs, reimport
    df = con.execute("SELECT * FROM unified_players").df()
    print(f"\nGenerating yamplayer_id for {len(df):,} players...")

    df['yamplayer_id'] = df.apply(generate_yamplayer_id, axis=1)

    # Check for duplicates
    duplicates = df['yamplayer_id'].duplicated().sum()
    if duplicates > 0:
        print(f"  ⚠ WARNING: {duplicates} duplicate yamplayer_ids detected!")

    # Replace table with version containing yamplayer_id
    con.execute("DROP TABLE unified_players")
    con.execute("CREATE TABLE unified_players AS SELECT * FROM df")

    print(f"  ✓ Generated {len(df):,} yamplayer_ids")


def apply_yamplayer_ids_to_datasets(
    con: duckdb.DuckDBPyConnection,
    base_dir: Path,
    dry_run: bool = False
) -> None:
    """Apply yamplayer_id back to all source datasets.

    Args:
        con: DuckDB connection
        base_dir: Base directory containing data/ folder
        dry_run: If True, only show what would be done
    """
    print("\n" + "="*80)
    print("STEP 3: APPLYING YAMPLAYER_IDS TO DATASETS")
    print("="*80)

    nflverse_dir = base_dir / 'data' / 'nflverse'
    yas_dir = base_dir / 'data' / 'yas'

    # Dataset configurations: (file, join_column, name_column_for_fallback)
    datasets = [
        (nflverse_dir / 'combine.csv', 'pfr_id', 'player_name'),
        (nflverse_dir / 'rosters.csv', 'gsis_id', 'full_name'),
        (nflverse_dir / 'draft_picks.csv', 'pfr_player_id', 'pfr_player_name'),
        (nflverse_dir / 'player_stats.csv', 'player_id', 'player_display_name'),
        (nflverse_dir / 'injuries.csv', 'gsis_id', 'full_name'),
        (nflverse_dir / 'depth_charts.csv', 'gsis_id', 'full_name'),
        (yas_dir / 'yas_2025.csv', 'gsis_id', 'player_name'),
        (yas_dir / 'yas_historical.csv', 'gsis_id', 'player_name'),
    ]

    for file_path, join_col, name_col in datasets:
        if not file_path.exists():
            print(f"\n⚠ Skipping {file_path.name} (not found)")
            continue

        print(f"\nProcessing {file_path.name}...")

        # Load dataset
        df = con.execute(f"SELECT * FROM read_csv_auto('{file_path}', strict_mode=false)").df()
        original_count = len(df)

        # Determine actual join column (gsis_id might be aliased as player_id)
        if join_col == 'player_id' and 'player_id' not in df.columns and 'gsis_id' in df.columns:
            actual_join_col = 'gsis_id'
        else:
            actual_join_col = join_col

        # Map dataset column to unified_players column
        if join_col == 'pfr_player_id':
            unified_join_col = 'pfr_id'
        elif join_col == 'player_id':
            unified_join_col = 'gsis_id'
        else:
            unified_join_col = join_col

        # Join to get yamplayer_id
        if actual_join_col in df.columns:
            result = con.execute(f"""
                SELECT
                    d.*,
                    u.yamplayer_id
                FROM df d
                LEFT JOIN unified_players u ON d.{actual_join_col} = u.{unified_join_col}
            """).df()
        else:
            print(f"  ⚠ Column '{actual_join_col}' not found, skipping")
            continue

        matched = result['yamplayer_id'].notna().sum()
        coverage = (matched / original_count * 100) if original_count > 0 else 0

        print(f"  Matched: {matched:,}/{original_count:,} ({coverage:.1f}%)")

        if not dry_run:
            # Write back to CSV
            result.to_csv(file_path, index=False)
            print(f"  ✓ Updated {file_path.name}")
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

    output_file = base_dir / 'data' / 'yamplayer_mapping.csv'

    df = con.execute("SELECT * FROM unified_players ORDER BY yamplayer_id").df()

    if not dry_run:
        df.to_csv(output_file, index=False)
        print(f"\n✅ Saved {len(df):,} player mappings to: {output_file}")
    else:
        print(f"\n[DRY RUN] Would save {len(df):,} mappings to: {output_file}")


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(description='Generate yamplayer_id for all datasets')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be done without modifying files')
    args = parser.parse_args()

    base_dir = Path(__file__).parent.parent

    print("="*80)
    print("YAMPLAYER_ID GENERATOR - SQL-BASED APPROACH")
    print("="*80)

    if args.dry_run:
        print("\n🔍 DRY RUN MODE - No files will be modified")

    # Create DuckDB connection
    con = duckdb.connect(':memory:')

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
        print("✅ COMPLETE!")
        print("="*80)

    finally:
        con.close()


if __name__ == '__main__':
    main()
