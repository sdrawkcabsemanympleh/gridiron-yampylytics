"""Player pool loader for YampGM fantasy draft tool.

Hydrates ``NFLPlayer`` Pydantic models from gridiron-yampylytics DuckDB data.

Two load paths:
- Skill players (QB/RB/WR/TE/K): joined from ``nflverse.players``,
  ``nflverse.ff_rankings``, ``nflverse.ff_playerids``, ``nflverse.player_stats``,
  ``nflverse.schedules``, and ``nflverse.injuries``. ``yamplayer_id`` is the
  universal join key throughout.
- DST: sourced directly from ``nflverse.ff_rankings`` (pos='DST'). DST entities
  are teams, not persons, so they have no ``yamplayer_id``. A deterministic
  synthetic ``player_id`` of the form ``"DST_{team}"`` is used instead
  (e.g. ``"DST_KC"``).

Projected points use FantasyPros pre-draft PPR season totals from
``nflverse.ff_projections`` when available (run ``uv run download-fp-projections``
to populate).  Falls back to prior-season PPR actuals from ``nflverse.player_stats``
if the projections table does not exist.
"""
import logging
from pathlib import Path
import duckdb
from gridiron_yampylytics.ffb.data.db import connect
from gridiron_yampylytics.ffb.models.player import NFLPlayer, Position

logger = logging.getLogger(__name__)

# Positions that map to the Position enum. DST is handled separately.
_SKILL_POSITIONS: frozenset[str] = frozenset({"QB", "RB", "WR", "TE", "K"})

# ff_rankings ecr_type value for standard/PPR redraft leagues.
_DEFAULT_ECR_TYPE: str = "ro"

# ff_rankings pos value for team defenses.
_DST_POS: str = "DST"

_SKILL_PLAYER_QUERY = """
WITH bye_weeks AS (
    SELECT t.team, w.week AS bye_week
    FROM (
        SELECT DISTINCT home_team AS team FROM nflverse.schedules
        WHERE season = {season} AND game_type = 'REG'
        UNION
        SELECT DISTINCT away_team FROM nflverse.schedules
        WHERE season = {season} AND game_type = 'REG'
    ) t
    CROSS JOIN (
        SELECT DISTINCT week FROM nflverse.schedules
        WHERE season = {season} AND game_type = 'REG'
    ) w
    WHERE NOT EXISTS (
        SELECT 1 FROM nflverse.schedules s
        WHERE s.season = {season} AND s.game_type = 'REG'
          AND (s.home_team = t.team OR s.away_team = t.team)
          AND s.week = w.week
    )
),
latest_injury AS (
    SELECT DISTINCT ON (yamplayer_id)
        yamplayer_id,
        report_status AS injury_status
    FROM nflverse.injuries
    WHERE report_status IS NOT NULL
    ORDER BY yamplayer_id, date_modified DESC
),
season_ppr AS (
    SELECT yamplayer_id,
        SUM(fantasy_points_ppr) AS projected_points
    FROM nflverse.player_stats
    WHERE season = {season} AND season_type = 'REG'
    GROUP BY yamplayer_id
),
fp_projections AS (
    SELECT fp.yamplayer_id, pr.fpts_ppr AS projected_points
    FROM nflverse.ff_projections pr
    JOIN nflverse.ff_playerids fp ON LOWER(TRIM(pr.player_name)) = LOWER(TRIM(fp.name))
    WHERE pr.position != 'DEF'
),
rankings AS (
    SELECT
        fp.yamplayer_id,
        fp.sleeper_id,
        r.ecr AS ecr_rank,
        r.sd AS adp_std,
        ROW_NUMBER() OVER (PARTITION BY fp.yamplayer_id ORDER BY r.ecr) AS rn
    FROM nflverse.ff_rankings r
    JOIN nflverse.ff_playerids fp ON r.id = fp.fantasypros_id
    WHERE r.ecr_type = '{ecr_type}'
)
SELECT
    p.yamplayer_id          AS player_id,
    p.display_name          AS name,
    p.position,
    p.latest_team           AS team,
    COALESCE(fpp.projected_points, sp.projected_points) AS projected_points,
    CAST(rk.ecr_rank AS DOUBLE) AS adp,
    rk.adp_std,
    bw.bye_week,
    CAST(rk.ecr_rank AS BIGINT) AS ecr_rank,
    li.injury_status,
    rk.sleeper_id
FROM nflverse.players p
JOIN rankings rk ON p.yamplayer_id = rk.yamplayer_id AND rk.rn = 1
LEFT JOIN fp_projections fpp ON p.yamplayer_id = fpp.yamplayer_id
LEFT JOIN season_ppr sp      ON p.yamplayer_id = sp.yamplayer_id
LEFT JOIN bye_weeks bw        ON p.latest_team = bw.team
LEFT JOIN latest_injury li   ON p.yamplayer_id = li.yamplayer_id
WHERE p.position IN ('QB', 'RB', 'WR', 'TE', 'K')
ORDER BY rk.ecr_rank
"""

_SKILL_PLAYER_QUERY_FALLBACK = """
WITH bye_weeks AS (
    SELECT t.team, w.week AS bye_week
    FROM (
        SELECT DISTINCT home_team AS team FROM nflverse.schedules
        WHERE season = {season} AND game_type = 'REG'
        UNION
        SELECT DISTINCT away_team FROM nflverse.schedules
        WHERE season = {season} AND game_type = 'REG'
    ) t
    CROSS JOIN (
        SELECT DISTINCT week FROM nflverse.schedules
        WHERE season = {season} AND game_type = 'REG'
    ) w
    WHERE NOT EXISTS (
        SELECT 1 FROM nflverse.schedules s
        WHERE s.season = {season} AND s.game_type = 'REG'
          AND (s.home_team = t.team OR s.away_team = t.team)
          AND s.week = w.week
    )
),
latest_injury AS (
    SELECT DISTINCT ON (yamplayer_id)
        yamplayer_id,
        report_status AS injury_status
    FROM nflverse.injuries
    WHERE report_status IS NOT NULL
    ORDER BY yamplayer_id, date_modified DESC
),
season_ppr AS (
    SELECT yamplayer_id,
        SUM(fantasy_points_ppr) AS projected_points
    FROM nflverse.player_stats
    WHERE season = {season} AND season_type = 'REG'
    GROUP BY yamplayer_id
),
rankings AS (
    SELECT
        fp.yamplayer_id,
        fp.sleeper_id,
        r.ecr AS ecr_rank,
        r.sd AS adp_std,
        ROW_NUMBER() OVER (PARTITION BY fp.yamplayer_id ORDER BY r.ecr) AS rn
    FROM nflverse.ff_rankings r
    JOIN nflverse.ff_playerids fp ON r.id = fp.fantasypros_id
    WHERE r.ecr_type = '{ecr_type}'
)
SELECT
    p.yamplayer_id          AS player_id,
    p.display_name          AS name,
    p.position,
    p.latest_team           AS team,
    sp.projected_points,
    CAST(rk.ecr_rank AS DOUBLE) AS adp,
    rk.adp_std,
    bw.bye_week,
    CAST(rk.ecr_rank AS BIGINT) AS ecr_rank,
    li.injury_status,
    rk.sleeper_id
FROM nflverse.players p
JOIN rankings rk ON p.yamplayer_id = rk.yamplayer_id AND rk.rn = 1
LEFT JOIN season_ppr sp     ON p.yamplayer_id = sp.yamplayer_id
LEFT JOIN bye_weeks bw       ON p.latest_team = bw.team
LEFT JOIN latest_injury li   ON p.yamplayer_id = li.yamplayer_id
WHERE p.position IN ('QB', 'RB', 'WR', 'TE', 'K')
ORDER BY rk.ecr_rank
"""

_DST_QUERY = """
WITH bye_weeks AS (
    SELECT t.team, w.week AS bye_week
    FROM (
        SELECT DISTINCT home_team AS team FROM nflverse.schedules
        WHERE season = {season} AND game_type = 'REG'
        UNION
        SELECT DISTINCT away_team FROM nflverse.schedules
        WHERE season = {season} AND game_type = 'REG'
    ) t
    CROSS JOIN (
        SELECT DISTINCT week FROM nflverse.schedules
        WHERE season = {season} AND game_type = 'REG'
    ) w
    WHERE NOT EXISTS (
        SELECT 1 FROM nflverse.schedules s
        WHERE s.season = {season} AND s.game_type = 'REG'
          AND (s.home_team = t.team OR s.away_team = t.team)
          AND s.week = w.week
    )
),
dst_rankings AS (
    SELECT
        team,
        player AS dst_name,
        CAST(ecr AS DOUBLE) AS adp,
        sd AS adp_std,
        CAST(ecr AS BIGINT) AS ecr_rank,
        ROW_NUMBER() OVER (PARTITION BY team ORDER BY ecr) AS rn
    FROM nflverse.ff_rankings
    WHERE ecr_type = '{ecr_type}' AND pos = 'DST'
)
SELECT
    'DST_' || r.team            AS player_id,
    r.dst_name                  AS name,
    'DEF'                       AS position,
    r.team                      AS team,
    proj.fpts_ppr               AS projected_points,
    r.adp,
    r.adp_std,
    bw.bye_week,
    r.ecr_rank,
    NULL::VARCHAR               AS injury_status,
    NULL::VARCHAR               AS sleeper_id
FROM dst_rankings r
LEFT JOIN bye_weeks bw ON r.team = bw.team
LEFT JOIN nflverse.ff_projections proj ON proj.team = r.team AND proj.position = 'DEF'
WHERE r.rn = 1
ORDER BY r.ecr_rank
"""

_DST_QUERY_FALLBACK = """
WITH bye_weeks AS (
    SELECT t.team, w.week AS bye_week
    FROM (
        SELECT DISTINCT home_team AS team FROM nflverse.schedules
        WHERE season = {season} AND game_type = 'REG'
        UNION
        SELECT DISTINCT away_team FROM nflverse.schedules
        WHERE season = {season} AND game_type = 'REG'
    ) t
    CROSS JOIN (
        SELECT DISTINCT week FROM nflverse.schedules
        WHERE season = {season} AND game_type = 'REG'
    ) w
    WHERE NOT EXISTS (
        SELECT 1 FROM nflverse.schedules s
        WHERE s.season = {season} AND s.game_type = 'REG'
          AND (s.home_team = t.team OR s.away_team = t.team)
          AND s.week = w.week
    )
),
dst_rankings AS (
    SELECT
        team,
        player AS dst_name,
        CAST(ecr AS DOUBLE) AS adp,
        sd AS adp_std,
        CAST(ecr AS BIGINT) AS ecr_rank,
        ROW_NUMBER() OVER (PARTITION BY team ORDER BY ecr) AS rn
    FROM nflverse.ff_rankings
    WHERE ecr_type = '{ecr_type}' AND pos = 'DST'
)
SELECT
    'DST_' || r.team        AS player_id,
    r.dst_name              AS name,
    'DEF'                   AS position,
    r.team                  AS team,
    NULL::DOUBLE            AS projected_points,
    r.adp,
    r.adp_std,
    bw.bye_week,
    r.ecr_rank,
    NULL::VARCHAR           AS injury_status,
    NULL::VARCHAR           AS sleeper_id
FROM dst_rankings r
LEFT JOIN bye_weeks bw ON r.team = bw.team
WHERE r.rn = 1
ORDER BY r.ecr_rank
"""


def _has_table(con: duckdb.DuckDBPyConnection, schema: str, table: str) -> bool:
    """Return True if ``schema.table`` exists in the connected DuckDB database.

    :param con: Open DuckDB connection.
    :param schema: Schema name.
    :param table: Table name.
    :return: True if the table exists, False otherwise.
    """
    try:
        con.execute(f"SELECT 1 FROM {schema}.{table} LIMIT 0")
        return True
    except Exception:
        return False


def _row_to_nfl_player(row: tuple) -> NFLPlayer:
    """Convert a single query result row to an ``NFLPlayer``.

    :param row: Tuple of (player_id, name, position, team, projected_points,
        adp, adp_std, bye_week, ecr_rank, injury_status, sleeper_id).
    :return: Hydrated ``NFLPlayer`` instance.
    """
    player_id, name, position, team, projected_points, adp, adp_std, bye_week, ecr_rank, injury_status, sleeper_id = row
    return NFLPlayer(
        player_id=str(player_id),
        name=str(name),
        position=Position(position),
        team=str(team) if team else "FA",
        projected_points=float(projected_points) if projected_points is not None else 0.0,
        adp=float(adp),
        adp_std=float(adp_std) if adp_std is not None else 5.0,
        bye_week=int(bye_week) if bye_week is not None else None,
        ecr_rank=int(ecr_rank) if ecr_rank is not None else None,
        injury_status=str(injury_status) if injury_status is not None else None,
        sleeper_id=str(sleeper_id) if sleeper_id is not None else None,
    )


def _load_skill_players(
    con: duckdb.DuckDBPyConnection,
    season: int,
    ecr_type: str,
) -> list[NFLPlayer]:
    """Load QB/RB/WR/TE/K players from DuckDB.

    Uses ``yamplayer_id`` as the universal join key across all source tables.
    Uses FantasyPros pre-draft PPR projections (``nflverse.ff_projections``) when
    available; falls back to prior-season PPR actuals from ``nflverse.player_stats``.

    :param con: Open DuckDB connection.
    :param season: Season year for player_stats fallback and schedules lookups.
    :param ecr_type: ``ff_rankings.ecr_type`` filter (e.g. ``"ro"`` for
        standard/PPR redraft overall).
    :return: List of ``NFLPlayer`` instances, ordered by ECR rank ascending.
    """
    has_proj = _has_table(con, "nflverse", "ff_projections")
    source = "ff_projections" if has_proj else f"player_stats season {season} (ff_projections not found)"
    logger.info("Projected points source: %s", source)
    template = _SKILL_PLAYER_QUERY if has_proj else _SKILL_PLAYER_QUERY_FALLBACK
    rows = con.execute(template.format(season=season, ecr_type=ecr_type)).fetchall()
    return [_row_to_nfl_player(row) for row in rows]


def _load_dst(
    con: duckdb.DuckDBPyConnection,
    season: int,
    ecr_type: str,
) -> list[NFLPlayer]:
    """Load team DST entries from DuckDB.

    DST is a team concept with no ``yamplayer_id``. A synthetic
    ``player_id`` of the form ``"DST_{team}"`` is assigned (e.g. ``"DST_KC"``).
    Uses FantasyPros pre-draft PPR projections when available; otherwise
    ``projected_points`` is ``None``.

    :param con: Open DuckDB connection.
    :param season: Season year for schedules bye week lookup.
    :param ecr_type: ``ff_rankings.ecr_type`` filter.
    :return: List of ``NFLPlayer`` instances for all ranked DSTs,
        ordered by ECR rank ascending.
    """
    template = _DST_QUERY if _has_table(con, "nflverse", "ff_projections") else _DST_QUERY_FALLBACK
    rows = con.execute(template.format(season=season, ecr_type=ecr_type)).fetchall()
    return [_row_to_nfl_player(row) for row in rows]


def load_player_pool(
    db_path: Path | str | None = None,
    season: int = 2024,
    ecr_type: str = _DEFAULT_ECR_TYPE,
    include_dst: bool = True,
) -> list[NFLPlayer]:
    """Load the full draftable player pool from gridiron-yampylytics DuckDB.

    Combines skill players (QB/RB/WR/TE/K) and optionally DST into a single
    list, sorted by ECR rank ascending (best player first).

    :param db_path: Path to the DuckDB database file. Defaults to
        ``gridiron_yampylytics.db`` in the current working directory.
    :param season: Season year used for ``player_stats`` projected points and
        ``schedules`` bye week derivation. Defaults to 2024 (last complete
        season). Switch to 2025 once 2025 final stats are in the DB.
    :param ecr_type: ``ff_rankings.ecr_type`` filter. ``"ro"`` = redraft
        overall (standard/PPR), ``"rsf"`` = superflex, ``"bo"`` = best ball.
        Defaults to ``"ro"``.
    :param include_dst: Whether to include team DST entries. Defaults to
        ``True``. Pass ``False`` for leagues with no DEF slot.
    :return: Combined list of ``NFLPlayer`` instances, sorted by ECR rank.
        DST players appear after skill players (DST ECR ranks are inherently
        higher numbers in the overall pool).
    :raises FileNotFoundError: If the database file does not exist.
    """
    with connect(db_path) as con:
        skill_players = _load_skill_players(con, season, ecr_type)
        dst_players = _load_dst(con, season, ecr_type) if include_dst else []
    all_players = skill_players + dst_players
    all_players.sort(key=lambda p: p.adp)
    with_proj = sum(1 for p in all_players if p.projected_points > 0)
    logger.info(
        "Player pool: %d total (%d skill + %d DST); %d/%d have projected_points > 0",
        len(all_players), len(skill_players), len(dst_players), with_proj, len(all_players),
    )
    return all_players
