"""DuckDB table creation module with materialized tables and indexes.

This module creates a high-performance DuckDB database with:
- Materialized tables (not views) for fast query performance
- Strategic indexes on foreign keys and common query patterns
- Optional play-by-play data (large dataset)

For programmatic use:
    from gridiron_yampylytics.database.tables import create_duckdb_tables
    result = create_duckdb_tables(include_pbp=False)

Database size: ~580 MB (default) | ~3.2 GB (with pbp)

Tables are faster than views but use disk space and require rebuilding
when CSVs change. For always-current data, use views instead (see database/views.py).
"""
import os
from pathlib import Path
from typing import Any
import duckdb


def create_table_with_indexes(
    con: duckdb.DuckDBPyConnection,
    schema: str,
    table_name: str,
    csv_path: Path,
    primary_key: str | None = None,
    indexes: list[tuple[str, str]] | None = None,
) -> None:
    """Create a materialized table from CSV with indexes.

    :param con: DuckDB connection
    :param schema: Schema name (e.g., 'nflverse', 'reference')
    :param table_name: Table name
    :param csv_path: Path to CSV file
    :param primary_key: Unused (kept for compatibility)
    :param indexes: List of (index_name, column_spec) tuples
    """
    full_name = f"{schema}.{table_name}"

    # Create materialized table from CSV
    print(f"Creating table: {full_name}...")
    con.execute(f"""
        CREATE TABLE {full_name} AS
        SELECT * FROM read_csv_auto(
            '{csv_path}',
            union_by_name=true,
            auto_detect=true,
            null_padding=true,
            quote='"',
            sample_size=-1,
            parallel=false
        )
    """)

    row_count = con.execute(f"SELECT COUNT(*) FROM {full_name}").fetchone()[0]
    print(f"  ✓ Loaded {row_count:,} rows")

    # Create indexes
    if indexes:
        for idx_name, columns in indexes:
            try:
                con.execute(f"CREATE INDEX {idx_name} ON {full_name}({columns})")
                print(f"  ✓ INDEX: {idx_name} ({columns})")
            except Exception as e:
                print(f"  ⚠ Could not create index {idx_name}: {e}")

    print()


def create_seasonal_table_with_indexes(
    con: duckdb.DuckDBPyConnection,
    schema: str,
    table_name: str,
    glob_pattern: str,
    indexes: list[tuple[str, str]] | None = None,
) -> bool:
    """Create a combined seasonal table from all CSV files matching a glob pattern.

    Uses union_by_name to merge columns across files that may differ slightly
    between seasons. Skips creation silently if no matching files are found.

    :param con: DuckDB connection
    :param schema: Schema name
    :param table_name: Table name
    :param glob_pattern: Glob pattern string (e.g. '/path/to/nextgen_stats_*.csv')
    :param indexes: List of (index_name, column_spec) tuples
    :return: True if table was created, False if no files matched
    """
    from glob import glob
    files = sorted(glob(glob_pattern))
    if not files:
        print(f"  ⚠ Skipping {schema}.{table_name} — no files matched: {glob_pattern}\n")
        return False

    full_name = f"{schema}.{table_name}"
    # Build DuckDB list literal with forward-slash paths (required on Windows)
    quoted = ", ".join(f"'{f.replace(chr(92), '/')}'" for f in files)
    file_list = f"[{quoted}]"
    print(f"Creating table: {full_name} ({len(files)} season file(s))...")

    con.execute(f"""
        CREATE TABLE {full_name} AS
        SELECT * FROM read_csv_auto(
            {file_list},
            union_by_name=true,
            auto_detect=true,
            null_padding=true,
            quote='"',
            sample_size=-1,
            parallel=false
        )
    """)

    row_count = con.execute(f"SELECT COUNT(*) FROM {full_name}").fetchone()[0]
    print(f"  ✓ Loaded {row_count:,} rows")

    if indexes:
        for idx_name, columns in indexes:
            try:
                con.execute(f"CREATE INDEX {idx_name} ON {full_name}({columns})")
                print(f"  ✓ INDEX: {idx_name} ({columns})")
            except Exception as e:
                print(f"  ⚠ Could not create index {idx_name}: {e}")

    print()
    return True


def create_duckdb_tables(
    db_path: Path | str | None = None,
    data_dir: Path | str | None = None,
    include_pbp: bool = False,
    overwrite: bool = False
) -> dict[str, Any]:
    """Create DuckDB database with materialized tables and indexes.

    Creates a high-performance DuckDB database with materialized tables
    (stored data, not views) and strategic indexes for fast queries.

    :param db_path: Path to DuckDB database file (default: gridiron_yampylytics.db)
    :param data_dir: Path to data directory (default: ./data)
    :param include_pbp: Include play-by-play data (adds ~2.6 GB)
    :param overwrite: Overwrite existing database without prompting
    :return: Summary dict with database creation statistics
    """
    # Set default paths
    if db_path is None:
        db_path = Path.cwd() / "gridiron_yampylytics.db"
    else:
        db_path = Path(db_path)

    if data_dir is None:
        data_dir = Path.cwd() / "data"
    else:
        data_dir = Path(data_dir)

    # Set environment variable to avoid tzdata download issues on Windows
    os.environ['DUCKDB_NO_DOWNLOAD_TZDATA'] = '1'

    # Check if database exists
    if db_path.exists():
        if not overwrite:
            print(f"⚠ Database already exists: {db_path}")
            response = input("Overwrite? [y/N]: ")
            if response.lower() != 'y':
                print("Aborted.")
                return {'aborted': True, 'db_path': db_path}
        db_path.unlink()

    print("=" * 80)
    print("CREATING DUCKDB DATABASE WITH MATERIALIZED TABLES")
    print("=" * 80)
    print(f"\nDatabase: {db_path}")
    print(f"Include PBP: {include_pbp}\n")

    con = duckdb.connect(str(db_path))

    # Create schemas
    print("Creating schemas...")
    con.execute("CREATE SCHEMA IF NOT EXISTS nflverse")
    con.execute("CREATE SCHEMA IF NOT EXISTS reference")
    con.execute("CREATE SCHEMA IF NOT EXISTS yas")
    con.execute("CREATE SCHEMA IF NOT EXISTS raw_executives")
    print("  ✓ Created schemas: nflverse, reference, yas, raw_executives\n")

    tables_created = 0

    print("=" * 80)
    print("REFERENCE TABLES")
    print("=" * 80)

    # reference.yamplayer_mapping (PRIMARY KEY: yamplayer_id)
    if (data_dir / "reference" / "yamplayer_mapping.csv").exists():
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
        tables_created += 1

    # reference.gm_tenures (PRIMARY KEY: nflverse_code, From)
    if (data_dir / "reference" / "gm_tenures.csv").exists():
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
        tables_created += 1

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
            tables_created += 1

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
        tables_created += 1

    print("=" * 80)
    print("NFLVERSE PLAYER DIMENSION TABLES")
    print("=" * 80)

    # nflverse.player_ids (PRIMARY KEY: gsis_id) — fantasy platform ID crosswalk (not hydrated)
    if (data_dir / "nflverse" / "player_ids.csv").exists():
        create_table_with_indexes(
            con,
            "nflverse",
            "player_ids",
            data_dir / "nflverse" / "player_ids.csv",
            primary_key="gsis_id",
            indexes=[
                ("idx_playerids_pfr", "pfr_id"),
                ("idx_playerids_espn", "espn_id"),
                ("idx_playerids_name", "name"),
            ],
        )
        tables_created += 1

    print("=" * 80)
    print("NFLVERSE PLAYER FACT TABLES")
    print("=" * 80)

    # nflverse.rosters (PRIMARY KEY: gsis_id, season, week)
    if (data_dir / "nflverse" / "rosters.csv").exists():
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
        tables_created += 1

    # nflverse.player_stats (PRIMARY KEY: player_id, season, week, season_type)
    if (data_dir / "nflverse" / "player_stats.csv").exists():
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
        tables_created += 1

    # nflverse.combine (PRIMARY KEY: pfr_id)
    if (data_dir / "nflverse" / "combine.csv").exists():
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
        tables_created += 1

    # nflverse.draft_picks (PRIMARY KEY: season, pick)
    if (data_dir / "nflverse" / "draft_picks.csv").exists():
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
        tables_created += 1

    print("=" * 80)
    print("NFLVERSE GAME/EVENT TABLES")
    print("=" * 80)

    # nflverse.schedules (PRIMARY KEY: game_id)
    if (data_dir / "nflverse" / "schedules.csv").exists():
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
        tables_created += 1

    # nflverse.injuries (NO PRIMARY KEY - event log)
    if (data_dir / "nflverse" / "injuries.csv").exists():
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
        tables_created += 1

    # nflverse.pbp (OPTIONAL - 2.6 GB)
    if include_pbp:
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
            tables_created += 1
        else:
            print(f"  ⚠ PBP file not found: {pbp_file}")
    else:
        print("\n⏭  Skipping play-by-play data (use include_pbp=True to include)")

    print("\n" + "=" * 80)
    print("NFLVERSE PLAYER DIMENSION TABLES (NEW)")
    print("=" * 80)

    # nflverse.players (PRIMARY KEY: gsis_id) — full nflverse player registry
    if (data_dir / "nflverse" / "players.csv").exists():
        create_table_with_indexes(
            con,
            "nflverse",
            "players",
            data_dir / "nflverse" / "players.csv",
            primary_key="gsis_id",
            indexes=[
                ("idx_players_yamplayer", "yamplayer_id"),
                ("idx_players_pfr", "pfr_id"),
                ("idx_players_espn", "espn_id"),
                ("idx_players_name", "display_name"),
                ("idx_players_status", "status"),
                ("idx_players_position", "position"),
            ],
        )
        tables_created += 1

    # nflverse.ff_playerids (PRIMARY KEY: gsis_id) — fantasy platform ID crosswalk
    if (data_dir / "nflverse" / "ff_playerids.csv").exists():
        create_table_with_indexes(
            con,
            "nflverse",
            "ff_playerids",
            data_dir / "nflverse" / "ff_playerids.csv",
            primary_key="gsis_id",
            indexes=[
                ("idx_ffpids_yamplayer", "yamplayer_id"),
                ("idx_ffpids_pfr", "pfr_id"),
                ("idx_ffpids_espn", "espn_id"),
            ],
        )
        tables_created += 1

    # nflverse.trades (no natural key — one row per player per trade)
    if (data_dir / "nflverse" / "trades.csv").exists():
        create_table_with_indexes(
            con,
            "nflverse",
            "trades",
            data_dir / "nflverse" / "trades.csv",
            primary_key=None,
            indexes=[
                ("idx_trades_yamplayer", "yamplayer_id"),
                ("idx_trades_pfr", "pfr_id"),
            ],
        )
        tables_created += 1

    # nflverse.ff_rankings (no natural single key — rankings snapshot)
    if (data_dir / "nflverse" / "ff_rankings.csv").exists():
        create_table_with_indexes(
            con,
            "nflverse",
            "ff_rankings",
            data_dir / "nflverse" / "ff_rankings.csv",
            primary_key=None,
            indexes=[
                ("idx_ffrank_ecr_type", "ecr_type"),
                ("idx_ffrank_player", "player"),
            ],
        )
        tables_created += 1

    print("\n" + "=" * 80)
    print("NFLVERSE SEASONAL TABLES (NEW)")
    print("=" * 80)

    nflverse_glob = str(data_dir / "nflverse").replace("\\", "/")

    # nflverse.nextgen_stats (all seasons, PRIMARY KEY: player_gsis_id + season + week + season_type)
    if create_seasonal_table_with_indexes(
        con,
        "nflverse",
        "nextgen_stats",
        f"{nflverse_glob}/nextgen_stats_*.csv",
        indexes=[
            ("idx_ngs_yamplayer", "yamplayer_id"),
            ("idx_ngs_gsis", "player_gsis_id"),
            ("idx_ngs_season_week", "season, week"),
            ("idx_ngs_position", "player_position"),
            ("idx_ngs_team", "team_abbr"),
        ],
    ):
        tables_created += 1

    # nflverse.rosters_weekly (all seasons, PRIMARY KEY: gsis_id + season + week)
    if create_seasonal_table_with_indexes(
        con,
        "nflverse",
        "rosters_weekly",
        f"{nflverse_glob}/rosters_weekly_*.csv",
        indexes=[
            ("idx_rostersw_yamplayer", "yamplayer_id"),
            ("idx_rostersw_gsis", "gsis_id"),
            ("idx_rostersw_pfr", "pfr_id"),
            ("idx_rostersw_team_season", "team, season"),
            ("idx_rostersw_season", "season"),
        ],
    ):
        tables_created += 1

    # nflverse.ff_opportunity (all seasons, PRIMARY KEY: player_id + season + week + season_type)
    if create_seasonal_table_with_indexes(
        con,
        "nflverse",
        "ff_opportunity",
        f"{nflverse_glob}/ff_opportunity_*.csv",
        indexes=[
            ("idx_ffopp_yamplayer", "yamplayer_id"),
            ("idx_ffopps_gsis", "player_id"),
            ("idx_ffopps_season_week", "season, week"),
            ("idx_ffopps_position", "position"),
            ("idx_ffopps_team", "posteam"),
        ],
    ):
        tables_created += 1

    # nflverse.snap_counts (all seasons, PRIMARY KEY: pfr_player_id + season + week)
    if create_seasonal_table_with_indexes(
        con,
        "nflverse",
        "snap_counts",
        f"{nflverse_glob}/snap_counts_*.csv",
        indexes=[
            ("idx_snap_yamplayer", "yamplayer_id"),
            ("idx_snap_pfr", "pfr_player_id"),
            ("idx_snap_season_week", "season, week"),
            ("idx_snap_team", "team"),
            ("idx_snap_position", "position"),
        ],
    ):
        tables_created += 1

    # nflverse.officials (all seasons, PRIMARY KEY: game_id + official_id)
    if create_seasonal_table_with_indexes(
        con,
        "nflverse",
        "officials",
        f"{nflverse_glob}/officials_*.csv",
        indexes=[
            ("idx_officials_game", "game_id"),
            ("idx_officials_season_week", "season, week"),
            ("idx_officials_name", "official_name"),
            ("idx_officials_position", "position"),
        ],
    ):
        tables_created += 1

    # nflverse.team_stats (all seasons, PRIMARY KEY: season + week + team + season_type)
    if create_seasonal_table_with_indexes(
        con,
        "nflverse",
        "team_stats",
        f"{nflverse_glob}/team_stats_*.csv",
        indexes=[
            ("idx_teamstats_team_season", "team, season"),
            ("idx_teamstats_season_week", "season, week"),
            ("idx_teamstats_opponent", "opponent_team"),
        ],
    ):
        tables_created += 1

    # nflverse.ftn_charting (all seasons, PRIMARY KEY: nflverse_game_id + nflverse_play_id)
    if create_seasonal_table_with_indexes(
        con,
        "nflverse",
        "ftn_charting",
        f"{nflverse_glob}/ftn_charting_*.csv",
        indexes=[
            ("idx_ftn_game", "nflverse_game_id"),
            ("idx_ftn_season_week", "season, week"),
        ],
    ):
        tables_created += 1

    # nflverse.participation (all seasons, PRIMARY KEY: nflverse_game_id + play_id)
    # Note: no season column at play level — game-keyed only
    if create_seasonal_table_with_indexes(
        con,
        "nflverse",
        "participation",
        f"{nflverse_glob}/participation_*.csv",
        indexes=[
            ("idx_participation_game", "nflverse_game_id"),
            ("idx_participation_team", "possession_team"),
        ],
    ):
        tables_created += 1

    print("\n" + "=" * 80)
    print("YAS (ATHLETIC SCORES)")
    print("=" * 80)

    # yas.yas_complete (PRIMARY KEY: yamplayer_id, calculation_position, calculation_type)
    yas_complete_file = data_dir / "yas" / "yas_complete.csv"
    if yas_complete_file.exists():
        create_table_with_indexes(
            con,
            "yas",
            "yas_complete",
            yas_complete_file,
            primary_key="yamplayer_id, calculation_position, calculation_type",
            indexes=[
                ("idx_yascomplete_yamplayer", "yamplayer_id"),
                ("idx_yascomplete_yas_position", "yas_position"),
                ("idx_yascomplete_calculation_position", "calculation_position"),
                ("idx_yascomplete_draft_year", "draft_year"),
                ("idx_yascomplete_score", "yas_score"),
            ],
        )
        tables_created += 1

    # Get final database size
    db_size_mb = db_path.stat().st_size / (1024 * 1024)

    print("\n" + "=" * 80)
    print("DATABASE CREATED SUCCESSFULLY!")
    print("=" * 80)
    print(f"\n📊 Database: {db_path}")
    print(f"💾 Size: {db_size_mb:.1f} MB")
    print(f"📋 Tables: {tables_created}")
    print(f"\n🚀 Launch interactive SQL explorer:")
    print(f"   uv run harlequin {db_path}")
    if os.name == 'nt':  # Windows
        print(f"   uv run harlequin {db_path} --no-download-tzdata")
    print(f"\n📖 Query examples:")
    print(f"   SELECT * FROM reference.yamplayer_mapping LIMIT 10;")
    print(f"   SELECT * FROM nflverse.player_stats WHERE season = 2023;")
    print(f"   SELECT * FROM yas.yas_complete ORDER BY yas_score DESC LIMIT 10;")

    con.close()

    # Return structured data for programmatic use
    return {
        'db_path': db_path,
        'db_size_mb': db_size_mb,
        'tables_created': tables_created,
        'include_pbp': include_pbp,
    }
