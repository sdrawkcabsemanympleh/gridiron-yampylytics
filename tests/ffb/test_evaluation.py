"""Tests for ffb/evaluation/roster_evaluator.py."""
import pytest
from gridiron_yampylytics.ffb.evaluation.roster_evaluator import LineupResult, optimize_lineup, score_roster
from gridiron_yampylytics.ffb.models.league import RosterConfig
from gridiron_yampylytics.ffb.models.player import NFLPlayer, Position

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _p(pid: str, pos: str, pts: float) -> NFLPlayer:
    return NFLPlayer(player_id=pid, name=pid, position=Position(pos), team="KC", projected_points=pts, adp=10.0)

# ---------------------------------------------------------------------------
# optimize_lineup
# ---------------------------------------------------------------------------

class TestOptimizeLineup:
    """Tests for lineup optimization logic."""

    def test_empty_pool_returns_empty_result(self) -> None:
        """optimize_lineup on an empty pool returns an empty LineupResult."""
        rc = RosterConfig(qb=1, rb=1, wr=0, te=0, flex=0, k=0, def_=0, bench=0)
        result = optimize_lineup([], rc)
        assert result.starters == []
        assert result.bench == []
        assert result.total_projected_points == pytest.approx(0.0)

    def test_assigns_top_players_to_dedicated_slots(self) -> None:
        """Top-N by projected_points fill dedicated slots; others go to bench."""
        rc = RosterConfig(qb=1, rb=0, wr=0, te=0, flex=0, k=0, def_=0, bench=1)
        players = [_p("q1", "QB", 300.0), _p("q2", "QB", 200.0)]
        result = optimize_lineup(players, rc)
        starter_ids = {p.player_id for p in result.starters}
        bench_ids = {p.player_id for p in result.bench}
        assert "q1" in starter_ids
        assert "q2" in bench_ids

    def test_flex_slot_filled_by_best_surplus_player(self) -> None:
        """FLEX slot is filled by the highest-projected-points surplus flex-eligible player."""
        rc = RosterConfig(qb=0, rb=2, wr=0, te=0, flex=1, k=0, def_=0, bench=0)
        players = [_p("r1", "RB", 300.0), _p("r2", "RB", 250.0), _p("r3", "RB", 200.0)]
        result = optimize_lineup(players, rc)
        starter_ids = {p.player_id for p in result.starters}
        assert "r1" in starter_ids
        assert "r2" in starter_ids
        assert "r3" in starter_ids  # fills FLEX slot

    def test_non_flex_eligible_player_not_in_flex(self) -> None:
        """Players at positions excluded from flex_eligible cannot fill the FLEX slot."""
        rc = RosterConfig(qb=1, rb=1, wr=0, te=0, flex=1, k=0, def_=0, bench=0,
                          flex_eligible=[Position.RB])
        players = [_p("q1", "QB", 400.0), _p("r1", "RB", 300.0), _p("q2", "QB", 250.0)]
        result = optimize_lineup(players, rc)
        starter_ids = {p.player_id for p in result.starters}
        # q2 is QB, not in flex_eligible=[RB], so it goes to bench
        assert "q1" in starter_ids
        assert "r1" in starter_ids
        assert "q2" not in starter_ids

    def test_total_projected_points_is_sum_of_starters(self) -> None:
        """total_projected_points equals the sum of starters' projected_points."""
        rc = RosterConfig(qb=1, rb=1, wr=0, te=0, flex=0, k=0, def_=0, bench=1)
        players = [_p("q1", "QB", 300.0), _p("r1", "RB", 250.0), _p("r2", "RB", 100.0)]
        result = optimize_lineup(players, rc)
        expected = sum(p.projected_points for p in result.starters)
        assert result.total_projected_points == pytest.approx(expected)

    def test_no_players_beyond_dedicated_slots_are_starters(self) -> None:
        """Players at positions with zero dedicated slots are not starters."""
        rc = RosterConfig(qb=1, rb=0, wr=0, te=0, flex=0, k=0, def_=0, bench=2)
        players = [_p("q1", "QB", 300.0), _p("r1", "RB", 400.0), _p("r2", "RB", 350.0)]
        result = optimize_lineup(players, rc)
        starter_ids = {p.player_id for p in result.starters}
        assert "q1" in starter_ids
        assert "r1" not in starter_ids  # rb=0, so no RB starter slots

    def test_fewer_players_than_dedicated_slots_assigns_all_available(self) -> None:
        """If fewer players exist than a position's slots, all are assigned as starters."""
        rc = RosterConfig(qb=0, rb=2, wr=0, te=0, flex=0, k=0, def_=0, bench=0)
        players = [_p("r1", "RB", 300.0)]  # only 1 RB, but 2 rb slots
        result = optimize_lineup(players, rc)
        assert len(result.starters) == 1
        assert result.starters[0].player_id == "r1"

    def test_best_flex_chosen_when_multiple_eligible(self) -> None:
        """Among multiple flex-eligible surplus players, the highest-pts fills FLEX."""
        rc = RosterConfig(qb=0, rb=1, wr=1, te=0, flex=1, k=0, def_=0, bench=0)
        players = [
            _p("r1", "RB", 300.0), _p("r2", "RB", 200.0),  # r2 is surplus RB
            _p("w1", "WR", 280.0), _p("w2", "WR", 150.0),  # w2 is surplus WR
        ]
        result = optimize_lineup(players, rc)
        starter_ids = {p.player_id for p in result.starters}
        # FLEX candidates: r2(200), w2(150) → r2 wins
        assert "r2" in starter_ids
        assert "w2" not in starter_ids

# ---------------------------------------------------------------------------
# score_roster
# ---------------------------------------------------------------------------

class TestScoreRoster:
    """Tests for the score_roster shorthand."""

    def test_returns_total_projected_points(self) -> None:
        """score_roster returns the same value as optimize_lineup.total_projected_points."""
        rc = RosterConfig(qb=1, rb=1, wr=0, te=0, flex=0, k=0, def_=0, bench=0)
        players = [_p("q1", "QB", 300.0), _p("r1", "RB", 250.0)]
        assert score_roster(players, rc) == pytest.approx(550.0)

    def test_empty_roster_returns_zero(self) -> None:
        """score_roster returns 0.0 for an empty player list."""
        rc = RosterConfig(qb=1, rb=1, wr=0, te=0, flex=0, k=0, def_=0, bench=0)
        assert score_roster([], rc) == pytest.approx(0.0)
