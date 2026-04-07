"""Generate unified yamplayer_id for all NFL datasets.

This module creates a deduplicated unified_players table using SQL-based entity
resolution, then generates yamplayer_id hashes and applies them back to all datasets.

Strategy:
1. Build unified_players table — foundation: players.csv (100% gsis_id coverage),
   enriched with combine.csv (combine-only players) and draft_picks.csv (historical picks)
2. Use UPDATE-then-INSERT to enrich and deduplicate
3. Only update VARCHAR-safe fields (skip type-mismatched fields)
4. Generate yamplayer_id from available IDs
5. Apply back to all datasets via LEFT JOIN
"""
import duckdb
import hashlib
import re
import pandas as pd
from pathlib import Path
from datetime import datetime
from typing import Any
from gridiron_yampylytics.manifest import update_transformation_script


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


def _normalize_college_python(college: str) -> str:
    """Normalize a college name string in Python (mirrors normalize_college_sql).

    Used in generate_yamplayer_id_hash() where SQL expressions cannot be applied.

    :param college: Raw college name string
    :return: Normalized college name
    """
    college = re.sub(r' St\.?$', ' State', college, flags=re.IGNORECASE)
    college = re.sub(r' Col\.?$', ' College', college, flags=re.IGNORECASE)
    return college


def generate_yamplayer_id_hash(row: dict) -> str:
    """Generate yamplayer_id hash from available identifiers.

    Uses gsis_id, pfr_id, name, birthdate, and normalized college as hash inputs.
    mfl_id is intentionally excluded — it is not present in players.csv and was
    never used as a hydration join key.

    :param row: Dictionary containing player data
    :return: yamplayer_id in format YAMP_<12-char-hash>
    """
    id_components = [
        str(row.get('gsis_id', '')),
        str(row.get('pfr_id', '')),
        str(row.get('name', '')),
        str(row.get('birthdate', '')),
        _normalize_college_python(str(row.get('college', '') or '')),
    ]
    id_string = '|'.join([c for c in id_components if c])
    hash_str = hashlib.md5(id_string.encode()).hexdigest()
    return f'YAMP_{hash_str[:12]}'


def build_unified_players_table(con: duckdb.DuckDBPyConnection, base_dir: Path) -> None:
    """Build deduplicated unified_players table from source datasets.

    Foundation: players.csv (all known NFL players, 100% gsis_id, 91% pfr_id).
    Enriched with combine.csv (combine-only invitees who never signed to a roster)
    and draft_picks.csv (historical drafted players not in players.csv).
    rosters.csv is intentionally omitted — players.csv already covers all rostered players.

    :param con: DuckDB connection
    :param base_dir: Base directory containing data/ folder
    """
    nflverse_dir = base_dir / 'data' / 'nflverse'

    print("\n" + "="*80)
    print("STEP 1: BUILDING UNIFIED PLAYERS TABLE")
    print("="*80)

    # Phase 1: Load players.csv as foundation
    print("\nLoading players.csv as foundation...")
    players_file = nflverse_dir / 'players.csv'

    con.execute(f"""
        CREATE TABLE unified_players AS
        SELECT DISTINCT
            gsis_id,
            pfr_id,
            display_name AS name,
            LOWER(REGEXP_REPLACE(TRIM(display_name), ' (jr\\.?|sr\\.?|ii|iii|iv|v)$', '', 'i')) AS merge_name,
            CAST(birth_date AS VARCHAR) AS birthdate,
            {normalize_college_sql('college_name')} AS college
        FROM read_csv_auto('{players_file}', strict_mode=false, quote='"')
        WHERE display_name IS NOT NULL
    """)

    count = con.execute("SELECT COUNT(*) FROM unified_players").fetchone()[0]
    print(f"  [OK] Loaded {count:,} players from players.csv")

    # Phase 2: Process combine.csv
    print("\nProcessing combine.csv...")
    combine_file = nflverse_dir / 'combine.csv'

    # UPDATE: Enrich existing players with pfr_id/college from combine
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

    # INSERT: Add combine-only players (invited but never signed to an NFL roster)
    con.execute(f"""
        INSERT INTO unified_players (pfr_id, name, merge_name, college)
        SELECT DISTINCT
            c.pfr_id,
            c.player_name AS name,
            LOWER(REGEXP_REPLACE(TRIM(c.player_name), ' (jr\\.?|sr\\.?|ii|iii|iv|v)$', '', 'i')) AS merge_name,
            {normalize_college_sql('c.school')} AS college
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

    # Phase 3: Process draft_picks.csv
    print("\nProcessing draft_picks.csv...")
    draft_file = nflverse_dir / 'draft_picks.csv'

    # UPDATE: Enrich existing players with pfr_id/college from draft data
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

    # INSERT: Add historical draft picks not in players.csv
    con.execute(f"""
        INSERT INTO unified_players (pfr_id, name, merge_name, college)
        SELECT DISTINCT
            d.pfr_player_id AS pfr_id,
            d.pfr_player_name AS name,
            LOWER(REGEXP_REPLACE(TRIM(d.pfr_player_name), ' (jr\\.?|sr\\.?|ii|iii|iv|v)$', '', 'i')) AS merge_name,
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


def generate_yamplayer_ids(con: duckdb.DuckDBPyConnection) -> None:
    """Generate yamplayer_id for each player in unified table.

    :param con: DuckDB connection
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

    df['yamplayer_id'] = df.apply(generate_yamplayer_id_hash, axis=1)

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

    Uses ROW_NUMBER() tie-breaking to ensure 1:1 mapping (no row explosion).

    :param con: DuckDB connection with unified_players table loaded
    :param df: Polars/Pandas DataFrame of combine.csv data
    :return: DataFrame with yamplayer_id column added
    """
    # Add explicit row ID for partitioning
    df['_row_id'] = range(len(df))

    result = con.execute(f"""
        WITH ranked_matches AS (
            SELECT
                d.*,
                u.yamplayer_id,
                ROW_NUMBER() OVER (
                    PARTITION BY d._row_id
                    ORDER BY
                        CASE WHEN d.pfr_id IS NOT NULL AND d.pfr_id != '' AND u.pfr_id = d.pfr_id THEN 1 ELSE 2 END,
                        CASE WHEN d.school IS NOT NULL AND u.college = {normalize_college_sql('d.school')} THEN 1 ELSE 2 END
                ) as rn
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
        )
        SELECT * EXCLUDE (rn, _row_id)
        FROM ranked_matches
        WHERE rn = 1
    """).df()
    return result


def hydrate_rosters(con: duckdb.DuckDBPyConnection, df) -> 'pd.DataFrame':
    """Hydrate rosters.csv with yamplayer_ids using roster-specific matching logic.

    Matching strategy (mirrors Step 1 rosters.csv logic):
    - TIER 1: gsis_id match (when gsis_id IS NOT NULL AND gsis_id != '')
    - TIER 2: pfr_id match (when pfr_id IS NOT NULL AND pfr_id != '')
    - TIER 3: birthdate + normalized name match

    Uses ROW_NUMBER() tie-breaking to ensure 1:1 mapping (no row explosion).

    :param con: DuckDB connection with unified_players table loaded
    :param df: Polars/Pandas DataFrame of rosters.csv data
    :return: DataFrame with yamplayer_id column added
    """
    # Add explicit row ID for partitioning
    df['_row_id'] = range(len(df))

    result = con.execute("""
        WITH ranked_matches AS (
            SELECT
                d.*,
                u.yamplayer_id,
                ROW_NUMBER() OVER (
                    PARTITION BY d._row_id
                    ORDER BY
                        CASE WHEN d.gsis_id IS NOT NULL AND d.gsis_id != '' AND u.gsis_id = d.gsis_id THEN 1
                             WHEN d.pfr_id IS NOT NULL AND d.pfr_id != '' AND u.pfr_id = d.pfr_id THEN 2
                             WHEN d.birth_date IS NOT NULL AND u.birthdate = CAST(d.birth_date AS VARCHAR) THEN 3
                             ELSE 4 END
                ) as rn
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
        )
        SELECT * EXCLUDE (rn, _row_id)
        FROM ranked_matches
        WHERE rn = 1
    """).df()
    return result


def hydrate_draft_picks(con: duckdb.DuckDBPyConnection, df) -> 'pd.DataFrame':
    """Hydrate draft_picks.csv with yamplayer_ids using draft-specific matching logic.

    Matching strategy (mirrors Step 1 draft_picks.csv logic):
    - TIER 1: pfr_player_id match (when pfr_player_id IS NOT NULL AND pfr_player_id != '')
    - TIER 2: Normalized name + normalized college match

    Note: Maps pfr_player_id -> pfr_id in unified_players
    Uses ROW_NUMBER() tie-breaking to ensure 1:1 mapping (no row explosion).

    :param con: DuckDB connection with unified_players table loaded
    :param df: Polars/Pandas DataFrame of draft_picks.csv data
    :return: DataFrame with yamplayer_id column added
    """
    # Add explicit row ID for partitioning
    df['_row_id'] = range(len(df))

    result = con.execute(f"""
        WITH ranked_matches AS (
            SELECT
                d.*,
                u.yamplayer_id,
                ROW_NUMBER() OVER (
                    PARTITION BY d._row_id
                    ORDER BY
                        CASE WHEN d.pfr_player_id IS NOT NULL AND d.pfr_player_id != '' AND u.pfr_id = d.pfr_player_id THEN 1 ELSE 2 END,
                        CASE WHEN d.college IS NOT NULL AND u.college = {normalize_college_sql('d.college')} THEN 1 ELSE 2 END
                ) as rn
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
        )
        SELECT * EXCLUDE (rn, _row_id)
        FROM ranked_matches
        WHERE rn = 1
    """).df()
    return result


def hydrate_player_stats(con: duckdb.DuckDBPyConnection, df) -> 'pd.DataFrame':
    """Hydrate player_stats.csv with yamplayer_ids using fast Python dict lookups.

    Matching strategy:
    - TIER 1: player_id match (maps to gsis_id in unified_players) - ALWAYS prefer
    - TIER 2: Normalized name match (no college available) - Only if unique match

    Note: Uses Python dict lookups instead of SQL JOIN for performance (O(n) vs O(n*m))

    :param con: DuckDB connection with unified_players table loaded
    :param df: Polars/Pandas DataFrame of player_stats.csv data
    :return: DataFrame with yamplayer_id column added
    """
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

    :param con: DuckDB connection with unified_players table loaded
    :param df: Polars/Pandas DataFrame of injuries.csv data
    :return: DataFrame with yamplayer_id column added
    """

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


def hydrate_depth_charts(con: duckdb.DuckDBPyConnection, df) -> 'pd.DataFrame':
    """Hydrate depth_charts (legacy/modern) with yamplayer_ids using strict gsis_id-only matching.

    Matching strategy (STRICT - ID only):
    - ONLY match on gsis_id
    - No name fallback (conservative approach for depth charts)

    Note: Uses Python dict lookups for performance (O(n))
    Works for both depth_charts_legacy.csv and depth_charts_modern.csv

    :param con: DuckDB connection with unified_players table loaded
    :param df: Polars/Pandas DataFrame of depth_charts data
    :return: DataFrame with yamplayer_id column added
    """
    # Build lookup dict from unified_players (gsis_id only)
    unified = con.execute("SELECT gsis_id, yamplayer_id FROM unified_players WHERE gsis_id IS NOT NULL").df()
    gsis_lookup = unified.set_index('gsis_id')['yamplayer_id'].to_dict()

    def get_yamplayer_id(row):
        """Get yamplayer_id - gsis_id match ONLY (strict)."""
        gsis_id = row.get('gsis_id')
        if pd.notna(gsis_id) and gsis_id != '':
            return gsis_lookup.get(gsis_id)
        return None

    # Apply lookup to all rows
    df['yamplayer_id'] = df.apply(get_yamplayer_id, axis=1)
    return df


def hydrate_players(con: duckdb.DuckDBPyConnection, df) -> 'pd.DataFrame':
    """Hydrate players.csv with yamplayer_ids via gsis_id lookup.

    Matching strategy:
    - TIER 1: gsis_id match (players.csv has 100% gsis_id coverage)

    :param con: DuckDB connection with unified_players table loaded
    :param df: Pandas DataFrame of players.csv data
    :return: DataFrame with yamplayer_id column added
    """
    unified = con.execute("SELECT gsis_id, yamplayer_id FROM unified_players WHERE gsis_id IS NOT NULL").df()
    gsis_lookup = unified.set_index('gsis_id')['yamplayer_id'].to_dict()
    df['yamplayer_id'] = df['gsis_id'].map(gsis_lookup)
    return df


def hydrate_nextgen_stats(con: duckdb.DuckDBPyConnection, df) -> 'pd.DataFrame':
    """Hydrate nextgen_stats with yamplayer_ids via player_gsis_id lookup.

    Matching strategy:
    - TIER 1: player_gsis_id match (maps to gsis_id in unified_players)

    :param con: DuckDB connection with unified_players table loaded
    :param df: Pandas DataFrame of nextgen_stats data
    :return: DataFrame with yamplayer_id column added
    """
    unified = con.execute("SELECT gsis_id, yamplayer_id FROM unified_players WHERE gsis_id IS NOT NULL").df()
    gsis_lookup = unified.set_index('gsis_id')['yamplayer_id'].to_dict()
    df['yamplayer_id'] = df['player_gsis_id'].map(gsis_lookup)
    return df


def hydrate_rosters_weekly(con: duckdb.DuckDBPyConnection, df) -> 'pd.DataFrame':
    """Hydrate rosters_weekly with yamplayer_ids via gsis_id then pfr_id fallback.

    Matching strategy:
    - TIER 1: gsis_id match
    - TIER 2: pfr_id match

    :param con: DuckDB connection with unified_players table loaded
    :param df: Pandas DataFrame of rosters_weekly data
    :return: DataFrame with yamplayer_id column added
    """
    unified = con.execute("SELECT gsis_id, pfr_id, yamplayer_id FROM unified_players").df()
    gsis_lookup = unified[unified['gsis_id'].notna()].set_index('gsis_id')['yamplayer_id'].to_dict()
    pfr_lookup = unified[unified['pfr_id'].notna()].set_index('pfr_id')['yamplayer_id'].to_dict()

    def get_yamplayer_id(row):
        """Get yamplayer_id: gsis_id first, pfr_id fallback."""
        gsis_id = row.get('gsis_id')
        if pd.notna(gsis_id) and gsis_id != '':
            result = gsis_lookup.get(gsis_id)
            if result:
                return result
        pfr_id = row.get('pfr_id')
        if pd.notna(pfr_id) and pfr_id != '':
            return pfr_lookup.get(pfr_id)
        return None

    df['yamplayer_id'] = df.apply(get_yamplayer_id, axis=1)
    return df


def hydrate_ff_opportunity(con: duckdb.DuckDBPyConnection, df) -> 'pd.DataFrame':
    """Hydrate ff_opportunity with yamplayer_ids via player_id (gsis_id) lookup.

    Matching strategy:
    - TIER 1: player_id match (maps to gsis_id in unified_players)

    :param con: DuckDB connection with unified_players table loaded
    :param df: Pandas DataFrame of ff_opportunity data
    :return: DataFrame with yamplayer_id column added
    """
    unified = con.execute("SELECT gsis_id, yamplayer_id FROM unified_players WHERE gsis_id IS NOT NULL").df()
    gsis_lookup = unified.set_index('gsis_id')['yamplayer_id'].to_dict()
    df['yamplayer_id'] = df['player_id'].map(gsis_lookup)
    return df


def hydrate_ff_playerids(con: duckdb.DuckDBPyConnection, df) -> 'pd.DataFrame':
    """Hydrate ff_playerids with yamplayer_ids via gsis_id then pfr_id fallback.

    Matching strategy:
    - TIER 1: gsis_id match
    - TIER 2: pfr_id match

    :param con: DuckDB connection with unified_players table loaded
    :param df: Pandas DataFrame of ff_playerids data
    :return: DataFrame with yamplayer_id column added
    """
    unified = con.execute("SELECT gsis_id, pfr_id, yamplayer_id FROM unified_players").df()
    gsis_lookup = unified[unified['gsis_id'].notna()].set_index('gsis_id')['yamplayer_id'].to_dict()
    pfr_lookup = unified[unified['pfr_id'].notna()].set_index('pfr_id')['yamplayer_id'].to_dict()

    def get_yamplayer_id(row):
        """Get yamplayer_id: gsis_id first, pfr_id fallback."""
        gsis_id = row.get('gsis_id')
        if pd.notna(gsis_id) and gsis_id != '':
            result = gsis_lookup.get(gsis_id)
            if result:
                return result
        pfr_id = row.get('pfr_id')
        if pd.notna(pfr_id) and pfr_id != '':
            return pfr_lookup.get(pfr_id)
        return None

    df['yamplayer_id'] = df.apply(get_yamplayer_id, axis=1)
    return df


def hydrate_snap_counts(con: duckdb.DuckDBPyConnection, df) -> 'pd.DataFrame':
    """Hydrate snap_counts with yamplayer_ids via pfr_player_id lookup.

    Matching strategy:
    - TIER 1: pfr_player_id match (maps to pfr_id in unified_players)

    :param con: DuckDB connection with unified_players table loaded
    :param df: Pandas DataFrame of snap_counts data
    :return: DataFrame with yamplayer_id column added
    """
    unified = con.execute("SELECT pfr_id, yamplayer_id FROM unified_players WHERE pfr_id IS NOT NULL").df()
    pfr_lookup = unified.set_index('pfr_id')['yamplayer_id'].to_dict()
    df['yamplayer_id'] = df['pfr_player_id'].map(pfr_lookup)
    return df


def hydrate_trades(con: duckdb.DuckDBPyConnection, df) -> 'pd.DataFrame':
    """Hydrate trades with yamplayer_ids via pfr_id lookup.

    Matching strategy:
    - TIER 1: pfr_id match

    :param con: DuckDB connection with unified_players table loaded
    :param df: Pandas DataFrame of trades data
    :return: DataFrame with yamplayer_id column added
    """
    unified = con.execute("SELECT pfr_id, yamplayer_id FROM unified_players WHERE pfr_id IS NOT NULL").df()
    pfr_lookup = unified.set_index('pfr_id')['yamplayer_id'].to_dict()
    df['yamplayer_id'] = df['pfr_id'].map(pfr_lookup)
    return df


def apply_yamplayer_ids_to_datasets(
    con: duckdb.DuckDBPyConnection,
    base_dir: Path,
    dry_run: bool = False
) -> None:
    """Apply yamplayer_id back to all source datasets using per-dataset hydration functions.

    :param con: DuckDB connection
    :param base_dir: Base directory containing data/ folder
    :param dry_run: If True, only show what would be done
    """
    print("\n" + "="*80)
    print("STEP 3: APPLYING YAMPLAYER_IDS TO DATASETS")
    print("="*80)

    nflverse_dir = base_dir / 'data' / 'nflverse'

    # Mapping: filename stem pattern -> hydration function
    # Seasonal datasets match by stem prefix (e.g. 'nextgen_stats_' matches nextgen_stats_2024.csv)
    # Non-seasonal datasets match exact filename
    HYDRATORS = {
        'combine.csv': hydrate_combine,
        'rosters.csv': hydrate_rosters,
        'draft_picks.csv': hydrate_draft_picks,
        'player_stats.csv': hydrate_player_stats,
        'injuries.csv': hydrate_injuries,
        'depth_charts_legacy.csv': hydrate_depth_charts,
        'depth_charts_modern.csv': hydrate_depth_charts,
        'ff_playerids.csv': hydrate_ff_playerids,
        'trades.csv': hydrate_trades,
        'players.csv': hydrate_players,
    }

    # Seasonal hydrators: pattern prefix -> function (matches all season files)
    SEASONAL_HYDRATORS = {
        'nextgen_stats_': hydrate_nextgen_stats,
        'rosters_weekly_': hydrate_rosters_weekly,
        'ff_opportunity_': hydrate_ff_opportunity,
        'snap_counts_': hydrate_snap_counts,
    }

    # Non-seasonal datasets (exact filenames)
    static_datasets = [
        nflverse_dir / 'combine.csv',
        nflverse_dir / 'rosters.csv',
        nflverse_dir / 'draft_picks.csv',
        nflverse_dir / 'player_stats.csv',
        nflverse_dir / 'injuries.csv',
        nflverse_dir / 'depth_charts_legacy.csv',
        nflverse_dir / 'depth_charts_modern.csv',
        nflverse_dir / 'ff_playerids.csv',
        nflverse_dir / 'trades.csv',
        nflverse_dir / 'players.csv',
    ]

    # Seasonal datasets (glob all matching season files)
    seasonal_datasets = []
    for prefix in SEASONAL_HYDRATORS:
        seasonal_datasets.extend(sorted(nflverse_dir.glob(f'{prefix}*.csv')))

    datasets = static_datasets + seasonal_datasets

    for file_path in datasets:
        if not file_path.exists():
            print(f"\n[WARNING] Skipping {file_path.name} (not found)")
            continue

        # Get the appropriate hydrator function (exact match first, then seasonal prefix)
        hydrator = HYDRATORS.get(file_path.name)
        if not hydrator:
            hydrator = next(
                (fn for prefix, fn in SEASONAL_HYDRATORS.items() if file_path.name.startswith(prefix)),
                None,
            )
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

    :param con: DuckDB connection
    :param base_dir: Base directory containing data/ folder
    :param dry_run: If True, only show what would be done
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


def generate_yamplayer_id(
    base_dir: Path | None = None,
    dry_run: bool = False
) -> dict[str, Any]:
    """Generate unified yamplayer_id for all NFL datasets.

    :param base_dir: Base directory containing data/ folder (default: current working directory parent)
    :param dry_run: If True, only show what would be done without modifying files
    :return: Summary dict with counts and statistics
    """
    # Set default path if not provided
    if base_dir is None:
        base_dir = Path.cwd()

    print("\n" + "="*80)
    print("YAMPLAYER_ID GENERATOR - SQL-BASED APPROACH")
    print("="*80)

    if dry_run:
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
        apply_yamplayer_ids_to_datasets(con, base_dir, dry_run=dry_run)

        # Step 4: Save mapping file
        save_mapping_file(con, base_dir, dry_run=dry_run)

        # Get stats from unified_players table
        unique_players = con.execute("SELECT COUNT(*) FROM unified_players").fetchone()[0]

        # Get file info
        mapping_file = base_dir / 'data' / 'reference' / 'yamplayer_mapping.csv'
        file_size = mapping_file.stat().st_size if mapping_file.exists() else 0

        # Get row count from saved file
        total_rows = con.execute(f"SELECT COUNT(*) FROM read_csv_auto('{mapping_file}')").fetchone()[0] if mapping_file.exists() else 0

        # Calculate duplicate rate
        duplicate_rate_value = ((total_rows - unique_players) / total_rows * 100) if total_rows > 0 else 0.0
        duplicate_rate = f"{duplicate_rate_value:.1f}%"

        # Step 5: Update manifest with processing metadata
        if not dry_run:
            print("\n" + "="*80)
            print("UPDATING MANIFEST")
            print("="*80)
            try:
                # Update manifest
                update_transformation_script("generate_yamplayer_id", {
                    "last_processed": datetime.now().strftime("%Y-%m-%d"),
                    "file_size_bytes": file_size,
                    "unique_players": unique_players,
                    "total_rows": total_rows,
                    "duplicate_rate": duplicate_rate
                })
                print(f"\n[OK] Manifest updated with processing metadata:")
                print(f"  • Last processed: {datetime.now().strftime('%Y-%m-%d')}")
                print(f"  • Unique players: {unique_players:,}")
                print(f"  • Total rows: {total_rows:,}")
                print(f"  • Duplicate rate: {duplicate_rate}")
            except Exception as e:
                # Don't fail the whole function if manifest update fails
                print(f"\n[WARNING] Could not update manifest: {e}")

        print("\n" + "="*80)
        print("[OK] COMPLETE!")
        print("="*80)

        # Return structured data
        return {
            'unique_players': unique_players,
            'total_rows': total_rows,
            'duplicate_rate': duplicate_rate,
            'duplicate_rate_value': duplicate_rate_value,
            'mapping_file': mapping_file,
            'file_size_bytes': file_size,
        }

    finally:
        con.close()
