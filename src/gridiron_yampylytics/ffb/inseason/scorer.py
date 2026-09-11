"""Global free agent pool scorer for YampGM in-season tool.

Scores every available NFL player across six quality dimensions, normalizes
each component within position, then combines them into a weighted composite.

The scorer is **league-agnostic** — it produces global scores for all players
regardless of which league they're rostered in.  Filtering to a specific
league's available players happens in
:mod:`~gridiron_yampylytics.ffb.inseason.roster_fit`.

Typical usage::

    scorer = FaPoolScorer(db_path=Path("gridiron_yampylytics.db"))
    scores = scorer.score(season=2025, current_week=8, scoring_type="ppr")
    top_adds = scores[:20]
"""
import logging
from dataclasses import dataclass, field
from pathlib import Path
import pandas as pd
from gridiron_yampylytics.ffb.data.db import connect
from gridiron_yampylytics.ffb.data.sleeper import SleeperTrendingPlayer
from gridiron_yampylytics.ffb.inseason.config import (
    LOOKBACK_WEEKS,
    SCHEDULE_LOOKAHEAD_WEEKS,
    SCORED_POSITIONS,
)

logger = logging.getLogger(__name__)

_MIN_WEEKS_FOR_CV: int = 2  # fewer weeks → CV undefined; use position mean instead
_POSITIONS_SQL: str = ", ".join(f"'{p}'" for p in SCORED_POSITIONS)


@dataclass
class FaPoolScorerWeights:
    """Component weights for the FA pool scorer.

    Weights need not sum to 1.0 — they are applied to normalized [0, 1]
    component scores.  The defaults emphasize recent performance and
    consistency over forward-looking signals, which tend to be noisier
    mid-season.

    :param recent_performance: Weight for average points over the lookback
        window. Default 0.30.
    :param consistency: Weight for inverse coefficient of variation (lower
        boom/bust variance = higher score). Default 0.25.
    :param vs_expectation: Weight for average actual-minus-expected points
        from ``ff_opportunity``. Default 0.20.
    :param opportunity: Weight for snap share and target/rush share composite.
        Default 0.10.
    :param trend: Weight for linear trend slope over recent weeks (positive =
        improving). Default 0.10.
    :param schedule_quality: Weight for average difficulty of upcoming
        opponents' defenses at this position. Default 0.05.
    """
    recent_performance: float = 0.30
    consistency: float = 0.25
    vs_expectation: float = 0.20
    opportunity: float = 0.10
    trend: float = 0.10
    schedule_quality: float = 0.05


@dataclass
class FaPoolScore:
    """Scored result for a single player from the FA pool scorer.

    Stores both raw component values (for display and audit) and their
    [0, 1] normalized counterparts (used in the composite calculation).
    Normalization is within-position, so all scores are relative to peers
    at the same position.

    :param player_id: nflverse ``gsis_id`` (primary join key across DuckDB tables).
    :param sleeper_id: Sleeper platform player ID. ``None`` for players not in
        ``ff_playerids`` (e.g. obscure backups, some DSTs).
    :param player_name: Display name.
    :param position: Fantasy position (QB / RB / WR / TE / K / DEF).
    :param team: NFL team abbreviation.
    :param mean_points: Average fantasy points over the lookback window.
    :param std_points: Standard deviation of weekly fantasy points.
    :param consistency_cv: Coefficient of variation (std / mean). Lower = more
        consistent. ``None`` when fewer than :data:`_MIN_WEEKS_FOR_CV` games
        are available.
    :param trend_slope: Linear regression slope of weekly points vs. week number.
        Positive = trending up.
    :param mean_opportunity: Composite opportunity score: average of snap share
        and the most relevant volume stat for this position (target share for
        pass-catchers, rush attempt share for RBs).
    :param mean_vs_expectation: Average actual-minus-expected fantasy points
        from ``ff_opportunity``. Positive = consistently outperforming model.
    :param schedule_score_raw: Average fantasy points allowed by upcoming
        opponents to this position. Higher = easier schedule.
    :param weeks_analyzed: Number of weeks of data used. May be less than
        the lookback window if the player missed games or the season just
        started.
    :param recent_performance_norm: Normalized recent performance in [0, 1].
    :param consistency_norm: Normalized consistency in [0, 1] (inverted CV).
    :param vs_expectation_norm: Normalized vs-expectation in [0, 1].
    :param opportunity_norm: Normalized opportunity in [0, 1].
    :param trend_norm: Normalized trend in [0, 1].
    :param schedule_quality_norm: Normalized schedule quality in [0, 1].
    :param composite_score: Weighted sum of normalized components.
    :param injury_status: Most recent Sleeper/nflverse injury designation.
        ``None`` means no active designation (healthy).
    :param ecr_rank: Expert consensus rank from ``ff_rankings`` (PPR).
        ``None`` if not ranked.
    :param trending_add_count: Sleeper platform add count in the trending
        window. Not included in the composite score — provided as context
        to indicate waiver urgency.
    """
    player_id: str
    sleeper_id: str | None
    player_name: str
    position: str
    team: str
    mean_points: float
    std_points: float
    consistency_cv: float | None
    trend_slope: float
    mean_opportunity: float
    mean_vs_expectation: float
    schedule_score_raw: float
    weeks_analyzed: int
    recent_performance_norm: float
    consistency_norm: float
    vs_expectation_norm: float
    opportunity_norm: float
    trend_norm: float
    schedule_quality_norm: float
    composite_score: float
    injury_status: str | None
    ecr_rank: int | None
    trending_add_count: int = field(default=0)


class FaPoolScorer:
    """Scores all NFL skill-position players on six quality dimensions.

    All computation runs against the local DuckDB analytics database.  Each
    call to :meth:`score` opens a short-lived read-only connection.

    :param db_path: Path to ``gridiron_yampylytics.db``. Defaults to the
        file in the current working directory (same convention as
        :func:`~gridiron_yampylytics.ffb.data.db.connect`).
    :param weights: Component weights. ``None`` uses :class:`FaPoolScorerWeights`
        defaults.
    :param lookback_weeks: Number of recent weeks to include in performance
        and consistency calculations. Default from config.
    :param schedule_lookahead: Number of upcoming weeks to evaluate for
        schedule quality. Default from config.
    """

    def __init__(
        self,
        db_path: Path | str | None = None,
        weights: FaPoolScorerWeights | None = None,
        lookback_weeks: int = LOOKBACK_WEEKS,
        schedule_lookahead: int = SCHEDULE_LOOKAHEAD_WEEKS,
    ) -> None:
        """Initialise the scorer.

        :param db_path: Path to ``gridiron_yampylytics.db``. ``None`` uses cwd.
        :param weights: Component weights. ``None`` uses defaults.
        :param lookback_weeks: Weeks of history for performance/consistency.
        :param schedule_lookahead: Upcoming weeks for schedule quality.
        """
        self._db_path = db_path
        self.weights = weights or FaPoolScorerWeights()
        self.lookback_weeks = lookback_weeks
        self.schedule_lookahead = schedule_lookahead

    def score(
        self,
        season: int,
        current_week: int,
        scoring_type: str = "ppr",
        sleeper_id_filter: set[str] | None = None,
        trending_adds: list[SleeperTrendingPlayer] | None = None,
    ) -> list[FaPoolScore]:
        """Score all players (or a filtered subset) for the given week.

        :param season: NFL season year (e.g. ``2025``).
        :param current_week: Current NFL week (1-18). Lookback window covers
            ``[current_week - lookback_weeks, current_week - 1]``.
        :param scoring_type: ``"ppr"``, ``"half_ppr"``, or ``"standard"``.
            Controls which fantasy points column is used.
        :param sleeper_id_filter: When provided, only players whose
            ``sleeper_id`` is in this set are included in the output. Pass the
            result of :meth:`~LeagueContext.available_player_ids` to filter to
            free agents in a specific league.
        :param trending_adds: Optional list of Sleeper trending adds to annotate
            results with :attr:`FaPoolScore.trending_add_count`. Not included
            in the composite score.
        :return: :class:`FaPoolScore` list sorted by ``composite_score``
            descending.
        """
        week_start = max(1, current_week - self.lookback_weeks)
        week_end = current_week - 1
        if week_end < week_start:
            logger.warning(
                "current_week=%d leaves no completed weeks in lookback window — "
                "returning empty results.",
                current_week,
            )
            return []
        fpts_expr = self._scoring_expr(scoring_type)
        with connect(self._db_path) as con:
            stats_df = self._fetch_recent_stats(con, season, week_start, week_end, fpts_expr)
            opp_df = self._fetch_vs_expectation(con, season, week_start, week_end)
            ids_df = self._fetch_player_ids(con)
            injury_df = self._fetch_injury_status(con, season)
            sched_map = self._fetch_schedule_quality(con, season, current_week, scoring_type)
        if stats_df.empty:
            logger.warning("No player_stats rows found for season=%d weeks %d-%d.", season, week_start, week_end)
            return []
        df = stats_df.merge(opp_df, on="player_id", how="left")
        df = df.merge(ids_df, on="player_id", how="left")
        df = df.merge(injury_df, on="player_id", how="left")
        df["mean_vs_expectation"] = df["mean_vs_expectation"].fillna(0.0)
        df["schedule_score_raw"] = df["team"].map(
            lambda t: sched_map.get((t, df.loc[df["team"] == t, "position"].iloc[0] if (df["team"] == t).any() else ""), 0.0)
        )
        df["schedule_score_raw"] = df.apply(
            lambda row: sched_map.get((row["team"], row["position"]), 0.0), axis=1
        )
        if sleeper_id_filter is not None:
            df = df[df["sleeper_id"].isin(sleeper_id_filter)]
        df = self._normalize_components(df)
        df["composite_score"] = (
            self.weights.recent_performance * df["recent_performance_norm"]
            + self.weights.consistency * df["consistency_norm"]
            + self.weights.vs_expectation * df["vs_expectation_norm"]
            + self.weights.opportunity * df["opportunity_norm"]
            + self.weights.trend * df["trend_norm"]
            + self.weights.schedule_quality * df["schedule_quality_norm"]
        )
        trending_map: dict[str, int] = {}
        if trending_adds:
            trending_map = {t.player_id: t.count for t in trending_adds}
        results: list[FaPoolScore] = []
        for _, row in df.iterrows():
            results.append(FaPoolScore(
                player_id=str(row["player_id"]),
                sleeper_id=str(row["sleeper_id"]) if pd.notna(row.get("sleeper_id")) else None,
                player_name=str(row["player_name"]),
                position=str(row["position"]),
                team=str(row["team"]),
                mean_points=float(row["mean_points"]),
                std_points=float(row["std_points"]),
                consistency_cv=float(row["consistency_cv"]) if pd.notna(row.get("consistency_cv")) else None,
                trend_slope=float(row["trend_slope"]) if pd.notna(row.get("trend_slope")) else 0.0,
                mean_opportunity=float(row["mean_opportunity"]),
                mean_vs_expectation=float(row["mean_vs_expectation"]),
                schedule_score_raw=float(row["schedule_score_raw"]),
                weeks_analyzed=int(row["weeks_analyzed"]),
                recent_performance_norm=float(row["recent_performance_norm"]),
                consistency_norm=float(row["consistency_norm"]),
                vs_expectation_norm=float(row["vs_expectation_norm"]),
                opportunity_norm=float(row["opportunity_norm"]),
                trend_norm=float(row["trend_norm"]),
                schedule_quality_norm=float(row["schedule_quality_norm"]),
                composite_score=float(row["composite_score"]),
                injury_status=str(row["injury_status"]) if pd.notna(row.get("injury_status")) else None,
                ecr_rank=int(row["ecr_rank"]) if pd.notna(row.get("ecr_rank")) else None,
                trending_add_count=trending_map.get(
                    str(row["sleeper_id"]) if pd.notna(row.get("sleeper_id")) else "", 0
                ),
            ))
        results.sort(key=lambda s: s.composite_score, reverse=True)
        return results

    # ------------------------------------------------------------------
    # Private data-fetch methods
    # ------------------------------------------------------------------

    def _fetch_recent_stats(
        self,
        con: object,
        season: int,
        week_start: int,
        week_end: int,
        fpts_expr: str,
    ) -> pd.DataFrame:
        """Fetch per-player aggregated stats for the lookback window.

        Returns one row per player with mean/std points, trend slope,
        opportunity composite, and weeks analyzed.

        :param con: Open DuckDB connection.
        :param season: NFL season year.
        :param week_start: First week of the lookback window.
        :param week_end: Last week of the lookback window (inclusive).
        :param fpts_expr: SQL expression for the fantasy points column to use.
        :return: DataFrame with columns: player_id, player_name, position, team,
            weeks_analyzed, mean_points, std_points, consistency_cv, trend_slope,
            mean_opportunity, yamplayer_id.
        """
        query = f"""
            WITH raw AS (
                SELECT
                    player_id,
                    MAX(player_display_name)                       AS player_name,
                    MAX(position)                                   AS position,
                    MAX(team)                                       AS team,
                    week,
                    COALESCE({fpts_expr}, 0.0)                     AS fpts,
                    COALESCE(target_share, 0.0)                    AS target_share,
                    COALESCE(carries / NULLIF(carries + receptions + passing_yards / 10, 0), 0.0)
                                                                    AS rush_share_proxy,
                    MAX(yamplayer_id)                               AS yamplayer_id
                FROM nflverse.player_stats
                WHERE season        = {season}
                  AND season_type   = 'REG'
                  AND week          BETWEEN {week_start} AND {week_end}
                  AND position      IN ({_POSITIONS_SQL})
                  AND {fpts_expr}   IS NOT NULL
                GROUP BY player_id, week
            ),
            snaps AS (
                SELECT yamplayer_id, AVG(offense_pct) AS mean_snap_pct
                FROM   nflverse.snap_counts
                WHERE  season = {season}
                  AND  week   BETWEEN {week_start} AND {week_end}
                GROUP BY yamplayer_id
            ),
            agg AS (
                SELECT
                    player_id,
                    MAX(player_name)                                AS player_name,
                    MAX(position)                                   AS position,
                    MAX(team)                                       AS team,
                    COUNT(*)                                        AS weeks_analyzed,
                    AVG(fpts)                                       AS mean_points,
                    STDDEV(fpts)                                    AS std_points,
                    CASE
                        WHEN COUNT(*) >= {_MIN_WEEKS_FOR_CV} AND AVG(fpts) > 0
                        THEN STDDEV(fpts) / AVG(fpts)
                        ELSE NULL
                    END                                             AS consistency_cv,
                    REGR_SLOPE(fpts, week)                         AS trend_slope,
                    AVG(target_share)                               AS mean_target_share,
                    AVG(rush_share_proxy)                           AS mean_rush_share,
                    MAX(yamplayer_id)                               AS yamplayer_id
                FROM raw
                GROUP BY player_id
            )
            SELECT
                a.player_id,
                a.player_name,
                a.position,
                a.team,
                a.weeks_analyzed,
                a.mean_points,
                COALESCE(a.std_points, 0.0)                        AS std_points,
                a.consistency_cv,
                COALESCE(a.trend_slope, 0.0)                       AS trend_slope,
                -- opportunity: snap share + position-appropriate volume stat
                COALESCE(s.mean_snap_pct, 0.0) * 0.5
                    + CASE a.position
                        WHEN 'RB'  THEN a.mean_rush_share  * 0.5
                        WHEN 'QB'  THEN a.mean_target_share * 0.5  -- completion pct proxy
                        ELSE            a.mean_target_share * 0.5
                      END                                           AS mean_opportunity,
                a.yamplayer_id
            FROM agg a
            LEFT JOIN snaps s ON a.yamplayer_id = s.yamplayer_id
        """
        return con.execute(query).df()

    def _fetch_vs_expectation(
        self,
        con: object,
        season: int,
        week_start: int,
        week_end: int,
    ) -> pd.DataFrame:
        """Fetch average actual-minus-expected fantasy points per player.

        Uses ``ff_opportunity.total_fantasy_points_diff``.

        :param con: Open DuckDB connection.
        :param season: NFL season year.
        :param week_start: First week of the lookback window.
        :param week_end: Last week of the lookback window.
        :return: DataFrame with columns: player_id, mean_vs_expectation.
        """
        query = f"""
            SELECT
                player_id,
                AVG(total_fantasy_points_diff) AS mean_vs_expectation
            FROM nflverse.ff_opportunity
            WHERE season = {season}
              AND week   BETWEEN {week_start} AND {week_end}
            GROUP BY player_id
        """
        return con.execute(query).df()

    def _fetch_player_ids(self, con: object) -> pd.DataFrame:
        """Fetch Sleeper ID and ECR rank for all players in the ID crosswalk.

        Joins ``ff_playerids`` and ``ff_rankings`` (PPR ECR only).

        :param con: Open DuckDB connection.
        :return: DataFrame with columns: player_id (gsis_id), sleeper_id, ecr_rank.
        """
        query = """
            SELECT
                fpi.gsis_id          AS player_id,
                fpi.sleeper_id,
                fr.rank              AS ecr_rank
            FROM nflverse.ff_playerids fpi
            LEFT JOIN nflverse.ff_rankings fr
                ON  fpi.fantasypros_id = fr.fantasypros_id
                AND fr.ecr_type        = 'ro'
            WHERE fpi.sleeper_id IS NOT NULL
        """
        return con.execute(query).df()

    def _fetch_injury_status(self, con: object, season: int) -> pd.DataFrame:
        """Fetch the most recent injury designation per player.

        Returns only the latest record per player (most recent ``date_modified``).

        :param con: Open DuckDB connection.
        :param season: NFL season year.
        :return: DataFrame with columns: player_id (gsis_id), injury_status.
        """
        query = f"""
            SELECT player_id, report_status AS injury_status
            FROM (
                SELECT
                    gsis_id                                                          AS player_id,
                    report_status,
                    ROW_NUMBER() OVER (PARTITION BY gsis_id ORDER BY date_modified DESC)
                                                                                     AS rn
                FROM nflverse.injuries
                WHERE season = {season}
                  AND report_status IS NOT NULL
            )
            WHERE rn = 1
        """
        return con.execute(query).df()

    def _fetch_schedule_quality(
        self,
        con: object,
        season: int,
        current_week: int,
        scoring_type: str,
    ) -> dict[tuple[str, str], float]:
        """Build a (team, position) → avg pts allowed lookup for upcoming games.

        Step 1 — defensive strength: average fantasy points allowed by each
        team's defense to each position in completed weeks this season.
        Step 2 — upcoming schedule: look up each team's opponents over the
        next ``schedule_lookahead`` weeks.
        Step 3 — combine: for each (team, position) pair, return the average
        defensive strength of upcoming opponents.

        :param con: Open DuckDB connection.
        :param season: NFL season year.
        :param current_week: Current NFL week. Completed weeks are ``< current_week``.
        :param scoring_type: Scoring type string for the fantasy points expression.
        :return: Dict mapping ``(team, position)`` → average pts allowed by
            upcoming opponents.  Missing pairs fall back to 0.0 at call site.
        """
        fpts_expr = self._scoring_expr(scoring_type)
        week_end_sched = current_week + self.schedule_lookahead
        def_query = f"""
            SELECT
                opponent_team        AS defense_team,
                position,
                AVG({fpts_expr})     AS avg_pts_allowed
            FROM nflverse.player_stats
            WHERE season      = {season}
              AND season_type  = 'REG'
              AND week         < {current_week}
              AND position     IN ({_POSITIONS_SQL})
              AND {fpts_expr}  IS NOT NULL
              AND opponent_team IS NOT NULL
            GROUP BY opponent_team, position
        """
        sched_query = f"""
            SELECT home_team, away_team, week
            FROM nflverse.schedules
            WHERE season    = {season}
              AND game_type  = 'REG'
              AND week       BETWEEN {current_week} AND {week_end_sched}
        """
        def_df = con.execute(def_query).df()
        sched_df = con.execute(sched_query).df()
        if def_df.empty or sched_df.empty:
            return {}
        def_map: dict[tuple[str, str], float] = {
            (str(r["defense_team"]), str(r["position"])): float(r["avg_pts_allowed"])
            for _, r in def_df.iterrows()
        }
        team_upcoming_opps: dict[str, list[str]] = {}
        for _, row in sched_df.iterrows():
            home, away = str(row["home_team"]), str(row["away_team"])
            team_upcoming_opps.setdefault(home, []).append(away)
            team_upcoming_opps.setdefault(away, []).append(home)
        positions = def_df["position"].unique().tolist()
        result: dict[tuple[str, str], float] = {}
        for team, opponents in team_upcoming_opps.items():
            for pos in positions:
                opp_strengths = [def_map.get((opp, pos), 0.0) for opp in opponents]
                if opp_strengths:
                    result[(team, pos)] = sum(opp_strengths) / len(opp_strengths)
        return result

    # ------------------------------------------------------------------
    # Private normalization helpers
    # ------------------------------------------------------------------

    def _normalize_components(self, df: pd.DataFrame) -> pd.DataFrame:
        """Normalize all six scoring components to [0, 1] within position.

        Consistency uses inverted normalization (lower CV = better).  All
        others use standard min-max within each position group.

        :param df: Merged player DataFrame from ``score()``.
        :return: Same DataFrame with ``*_norm`` columns added in-place.
        """
        df = df.copy()
        df["recent_performance_norm"] = self._minmax_within_position(df, "mean_points")
        df["consistency_norm"] = self._minmax_within_position(df, "consistency_cv", invert=True, fill_na_with_mid=True)
        df["vs_expectation_norm"] = self._minmax_within_position(df, "mean_vs_expectation")
        df["opportunity_norm"] = self._minmax_within_position(df, "mean_opportunity")
        df["trend_norm"] = self._minmax_within_position(df, "trend_slope")
        df["schedule_quality_norm"] = self._minmax_within_position(df, "schedule_score_raw")
        return df

    @staticmethod
    def _minmax_within_position(
        df: pd.DataFrame,
        column: str,
        invert: bool = False,
        fill_na_with_mid: bool = False,
    ) -> pd.Series:
        """Apply min-max normalization grouped by position.

        :param df: Player DataFrame containing ``position`` and ``column``.
        :param column: Column to normalize.
        :param invert: If ``True``, flips the normalized value so that lower
            raw values become higher scores (used for consistency_cv).
        :param fill_na_with_mid: If ``True``, fills NaN entries with 0.5
            (neutral score) rather than 0.0. Used for consistency_cv when a
            player has fewer than :data:`_MIN_WEEKS_FOR_CV` games.
        :return: Series of normalized values aligned with ``df``'s index.
        """
        result = pd.Series(index=df.index, dtype=float)
        for pos, group in df.groupby("position"):
            vals = group[column]
            lo, hi = vals.min(), vals.max()
            denom = (hi - lo) if hi != lo else 1.0
            normed = (vals - lo) / denom
            if invert:
                normed = 1.0 - normed
            if fill_na_with_mid:
                normed = normed.fillna(0.5)
            else:
                normed = normed.fillna(0.0)
            result.loc[group.index] = normed
        return result

    @staticmethod
    def _scoring_expr(scoring_type: str) -> str:
        """Return the SQL expression for fantasy points given a scoring type.

        :param scoring_type: ``"ppr"``, ``"half_ppr"``, or ``"standard"``.
        :return: SQL column reference or calculated expression string.
        :raises ValueError: If ``scoring_type`` is not one of the three
            supported values.
        """
        if scoring_type == "ppr":
            return "fantasy_points_ppr"
        if scoring_type == "standard":
            return "fantasy_points"
        if scoring_type == "half_ppr":
            return "COALESCE(fantasy_points, 0.0) + 0.5 * COALESCE(receptions, 0.0)"
        raise ValueError(
            f"Unknown scoring_type {scoring_type!r}. "
            "Expected 'ppr', 'half_ppr', or 'standard'."
        )
