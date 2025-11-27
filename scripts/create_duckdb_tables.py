"""Creates a DuckDB database with materialized tables and optimized indexes.

This script creates a high-performance DuckDB database with:
- Materialized tables (not views) for fast query performance
- PRIMARY KEY constraints for data quality
- Strategic indexes on foreign keys and common query patterns
- Optional play-by-play data (2.6 GB - use --include-pbp flag)

Database size: ~580 MB (default) | ~3.2 GB (with pbp)
"""

import argparse
import os
from pathlib import Path

import duckdb


def create_table_with_indexes(
    con: duckdb.DuckDBPyConnection,
    schema: str,
    table_name: str,
    csv_path: Path,
    primary_key: str | None = None,
    indexes: list[tuple[str, str]] | None = None,
) -> None:
    """Create a materialized table from CSV with PRIMARY KEY and indexes.

    Args:
        con: DuckDB connection
        schema: Schema name (e.g., 'nflverse', 'reference')
        table_name: Table name
        csv_path: Path to CSV file
        primary_key: PRIMARY KEY definition (e.g., 'yamplayer_id' or '(gsis_id, season)')
        indexes: List of (index_name, column_spec) tuples
    """
    full_name = f"{schema}.{table_name}"

    # Create materialized table from CSV
    pk_clause = f"PRIMARY KEY ({primary_key})" if primary_key else ""

    print(f"Creating table: {full_name}...")
    con.execute(f"""
        CREATE TABLE {full_name} AS
        SELECT * FROM read_csv_auto(
            '{csv_path}',
            union_by_name=true,
            auto_detect=true,
            null_padding=true
        )
    """)

    # Add PRIMARY KEY constraint if specified
    if primary_key:
        try:
            # DuckDB doesn't support ALTER TABLE ADD PRIMARY KEY directly on existing table
            # So we recreate with constraint
            con.execute(f"""
                CREATE TABLE {full_name}_temp AS
                SELECT * FROM {full_name}
            """)
            con.execute(f"DROP TABLE {full_name}")
            con.execute(f"""
                CREATE TABLE {full_name} (
                    PRIMARY KEY ({primary_key})
                ) AS SELECT * FROM {full_name}_temp
            """)
            con.execute(f"DROP TABLE {full_name}_temp")
            print(f"  ✓ PRIMARY KEY: {primary_key}")
        except Exception as e:
            print(f"  ⚠ Could not add PRIMARY KEY ({primary_key}): {e}")
            print(f"    Continuing without PRIMARY KEY constraint...")

    # Create indexes
    if indexes:
        for idx_name, columns in indexes:
            try:
                con.execute(f"CREATE INDEX {idx_name} ON {full_name}({columns})")
                print(f"  ✓ INDEX: {idx_name} ({columns})")
            except Exception as e:
                print(f"  ⚠ Could not create index {idx_name}: {e}")

    row_count = con.execute(f"SELECT COUNT(*) FROM {full_name}").fetchone()[0]
    print(f"  ✓ Loaded {row_count:,} rows\n")


def main() -> None:
    """Create DuckDB database with materialized tables and indexes."""
    parser = argparse.ArgumentParser(
        description="Create DuckDB database with materialized tables and indexes"
    )
    parser.add_argument(
        "--include-pbp",
        action="store_true",
        help="Include play-by-play data (adds ~2.6 GB to database)",
    )
    args = parser.parse_args()

    base_dir = Path(__file__).parent.parent
    data_dir = base_dir / "data"

    # Set environment variable to avoid tzdata download issues on Windows
    os.environ['DUCKDB_NO_DOWNLOAD_TZDATA'] = '1'

    db_path = base_dir / "gridiron_yampylytics.db"
    if db_path.exists():
        print(f"⚠ Database already exists: {db_path}")
        response = input("Overwrite? [y/N]: ")
        if response.lower() != 'y':
            print("Aborted.")
            return
        db_path.unlink()

    print("=" * 80)
    print("CREATING DUCKDB DATABASE WITH MATERIALIZED TABLES")
    print("=" * 80)
    print(f"\nDatabase: {db_path}")
    print(f"Include PBP: {args.include_pbp}\n")

    con = duckdb.connect(str(db_path))

    # Create schemas
    print("Creating schemas...")
    con.execute("CREATE SCHEMA IF NOT EXISTS nflverse")
    con.execute("CREATE SCHEMA IF NOT EXISTS reference")
    con.execute("CREATE SCHEMA IF NOT EXISTS yas")
    con.execute("CREATE SCHEMA IF NOT EXISTS raw_executives")
    print("  ✓ Created schemas: nflverse, reference, yas, raw_executives\n")

    print("=" * 80)
    print("REFERENCE TABLES")
    print("=" * 80)

    # reference.yamplayer_mapping (PRIMARY KEY: yamplayer_id)
    create_table_with_indexes(
        con,
        "reference",
        "yamplayer_mapping",
        data_dir / "reference" / "yamplayer_mapping.csv",
        primary_key="yamplayer_id",
        indexes=[
            ("idx_yamplayer_gsis", "gsis_id"),
            ("idx_yamplayer_pfr", "pfr_id"),
            ("idx_yamplayer_name", "name"),
        ],
    )

    # reference.gm_tenures (PRIMARY KEY: nflverse_code, From)
    create_table_with_indexes(
        con,
        "reference",
        "gm_tenures",
        data_dir / "reference" / "gm_tenures.csv",
        primary_key="nflverse_code, \"From\"",
        indexes=[
            ("idx_gm_team", "nflverse_code"),
            ("idx_gm_person", "Person"),
            ("idx_gm_tenure", "\"From\", \"To\""),
        ],
    )

    # Draft value charts (tiny lookup tables, PRIMARY KEY only)
    for chart in ["jimmy_johnson", "rich_hill", "fitzgerald_spielberger", "harvard"]:
        csv_file = data_dir / "reference" / f"draft_values_{chart}.csv"
        if csv_file.exists():
            create_table_with_indexes(
                con,
                "reference",
                f"draft_values_{chart}",
                csv_file,
                primary_key="pick",
                indexes=None,
            )

    # reference.team_code_mapping
    team_code_file = data_dir / "reference" / "team_code_mapping.csv"
    if team_code_file.exists():
        create_table_with_indexes(
            con,
            "reference",
            "team_code_mapping",
            team_code_file,
            primary_key="nflverse_code",
            indexes=None,
        )

    print("=" * 80)
    print("NFLVERSE PLAYER DIMENSION TABLES")
    print("=" * 80)

    # nflverse.player_ids (PRIMARY KEY: gsis_id)
    create_table_with_indexes(
        con,
        "nflverse",
        "player_ids",
        data_dir / "nflverse" / "player_ids.csv",
        primary_key="gsis_id",
        indexes=[
            ("idx_playerids_pfr", "pfr_id"),
            ("idx_playerids_espn", "espn_id"),
            ("idx_playerids_yamplayer", "yamplayer_id"),
            ("idx_playerids_name", "name"),
        ],
    )

    print("=" * 80)
    print("NFLVERSE PLAYER FACT TABLES")
    print("=" * 80)

    # nflverse.rosters (PRIMARY KEY: gsis_id, season, week)
    create_table_with_indexes(
        con,
        "nflverse",
        "rosters",
        data_dir / "nflverse" / "rosters.csv",
        primary_key="gsis_id, season, week",
        indexes=[
            ("idx_rosters_gsis", "gsis_id"),
            ("idx_rosters_pfr", "pfr_id"),
            ("idx_rosters_yamplayer", "yamplayer_id"),
            ("idx_rosters_team_season", "team, season"),
            ("idx_rosters_season", "season"),
        ],
    )

    # nflverse.player_stats (PRIMARY KEY: player_id, season, week, season_type)
    create_table_with_indexes(
        con,
        "nflverse",
        "player_stats",
        data_dir / "nflverse" / "player_stats.csv",
        primary_key="player_id, season, week, season_type",
        indexes=[
            ("idx_stats_player", "player_id"),
            ("idx_stats_yamplayer", "yamplayer_id"),
            ("idx_stats_season_week", "season, week"),
            ("idx_stats_position", "position"),
            ("idx_stats_team", "team"),
        ],
    )

    # nflverse.combine (PRIMARY KEY: pfr_id)
    create_table_with_indexes(
        con,
        "nflverse",
        "combine",
        data_dir / "nflverse" / "combine.csv",
        primary_key="pfr_id",
        indexes=[
            ("idx_combine_yamplayer", "yamplayer_id"),
            ("idx_combine_season", "season"),
            ("idx_combine_pos", "pos"),
            ("idx_combine_season_pos", "season, pos"),
        ],
    )

    # nflverse.draft_picks (PRIMARY KEY: season, pick)
    create_table_with_indexes(
        con,
        "nflverse",
        "draft_picks",
        data_dir / "nflverse" / "draft_picks.csv",
        primary_key="season, pick",
        indexes=[
            ("idx_draft_gsis", "gsis_id"),
            ("idx_draft_pfr", "pfr_player_id"),
            ("idx_draft_yamplayer", "yamplayer_id"),
            ("idx_draft_season_round", "season, round"),
            ("idx_draft_team", "team"),
            ("idx_draft_college", "college"),
        ],
    )

    print("=" * 80)
    print("NFLVERSE GAME/EVENT TABLES")
    print("=" * 80)

    # nflverse.schedules (PRIMARY KEY: game_id)
    create_table_with_indexes(
        con,
        "nflverse",
        "schedules",
        data_dir / "nflverse" / "schedules.csv",
        primary_key="game_id",
        indexes=[
            ("idx_sched_season_week", "season, week"),
            ("idx_sched_season_type", "season, game_type"),
            ("idx_sched_home", "home_team"),
            ("idx_sched_away", "away_team"),
            ("idx_sched_away_qb", "away_qb_id"),
            ("idx_sched_home_qb", "home_qb_id"),
        ],
    )

    # nflverse.injuries (NO PRIMARY KEY - event log)
    create_table_with_indexes(
        con,
        "nflverse",
        "injuries",
        data_dir / "nflverse" / "injuries.csv",
        primary_key=None,  # Event log - no natural key
        indexes=[
            ("idx_injuries_gsis", "gsis_id"),
            ("idx_injuries_yamplayer", "yamplayer_id"),
            ("idx_injuries_season_week", "season, week"),
            ("idx_injuries_team", "team"),
            ("idx_injuries_date", "date_modified"),
        ],
    )

    # nflverse.pbp (OPTIONAL - 2.6 GB)
    if args.include_pbp:
        print("\n⚠ INCLUDING PLAY-BY-PLAY DATA (this will take several minutes)...")
        pbp_file = data_dir / "nflverse" / "pbp.csv"
        if pbp_file.exists():
            create_table_with_indexes(
                con,
                "nflverse",
                "pbp",
                pbp_file,
                primary_key="game_id, play_id",
                indexes=[
                    ("idx_pbp_game", "game_id"),
                    ("idx_pbp_season_week", "season, week"),
                    ("idx_pbp_posteam", "posteam"),
                    ("idx_pbp_passer", "passer_id"),
                    ("idx_pbp_rusher", "rusher_id"),
                    ("idx_pbp_receiver", "receiver_id"),
                    ("idx_pbp_down_dist", "down, ydstogo"),
                ],
            )
        else:
            print(f"  ⚠ PBP file not found: {pbp_file}")
    else:
        print("\n⏭  Skipping play-by-play data (use --include-pbp to include)")

    print("\n" + "=" * 80)
    print("YAS (ATHLETIC SCORES)")
    print("=" * 80)

    # yas.yas_2025 (PRIMARY KEY: yamplayer_id, season)
    yas_2025_file = data_dir / "yas" / "yas_2025.csv"
    if yas_2025_file.exists():
        create_table_with_indexes(
            con,
            "yas",
            "yas_2025",
            yas_2025_file,
            primary_key="yamplayer_id, season",
            indexes=[
                ("idx_yas2025_yamplayer", "yamplayer_id"),
                ("idx_yas2025_gsis", "gsis_id"),
                ("idx_yas2025_pfr", "pfr_id"),
                ("idx_yas2025_season_pos", "season, calculated_position"),
                ("idx_yas2025_score", "yas_score"),
            ],
        )

    # yas.yas_historical (PRIMARY KEY: yamplayer_id, season)
    yas_hist_file = data_dir / "yas" / "yas_historical.csv"
    if yas_hist_file.exists():
        create_table_with_indexes(
            con,
            "yas",
            "yas_historical",
            yas_hist_file,
            primary_key="yamplayer_id, season",
            indexes=[
                ("idx_yashist_yamplayer", "yamplayer_id"),
                ("idx_yashist_gsis", "gsis_id"),
                ("idx_yashist_pfr", "pfr_id"),
                ("idx_yashist_season_pos", "season, calculated_position"),
                ("idx_yashist_score", "yas_score"),
            ],
        )

    print("\n" + "=" * 80)
    print("RAW EXECUTIVE DATA")
    print("=" * 80)

    # Load all team executive CSV files
    exec_dir = data_dir / "raw" / "executives"
    if exec_dir.exists():
        exec_files = sorted(exec_dir.glob("*_executives.csv"))
        print(f"Loading {len(exec_files)} team executive files...")
        for exec_file in exec_files:
            team_code = exec_file.stem.replace("_executives", "")
            create_table_with_indexes(
                con,
                "raw_executives",
                f"{team_code}_executives",
                exec_file,
                primary_key=None,
                indexes=None,
            )

    con.close()

    # Get final database size
    db_size_mb = db_path.stat().st_size / (1024 * 1024)

    print("\n" + "=" * 80)
    print("DATABASE CREATED SUCCESSFULLY!")
    print("=" * 80)
    print(f"\n📊 Database: {db_path}")
    print(f"💾 Size: {db_size_mb:.1f} MB")
    print(f"\n🚀 Launch interactive SQL explorer:")
    print(f"   uv run harlequin {db_path}")
    if os.name == 'nt':  # Windows
        print(f"   uv run harlequin {db_path} --no-download-tzdata")
    print(f"\n📖 Query examples:")
    print(f"   SELECT * FROM reference.yamplayer_mapping LIMIT 10;")
    print(f"   SELECT * FROM nflverse.player_stats WHERE season = 2023;")
    print(f"   SELECT * FROM yas.yas_2025 ORDER BY yas_score DESC LIMIT 10;")


if __name__ == "__main__":
    main()
