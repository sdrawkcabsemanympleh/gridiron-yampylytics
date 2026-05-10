"""Tests for scoring components: vor.py, vona.py, scarcity.py, scorer.py."""
import pytest
from gridiron_yampylytics.ffb.models.draft import DraftState, Roster
from gridiron_yampylytics.ffb.models.league import League, RosterConfig
from gridiron_yampylytics.ffb.models.manager import Manager
from gridiron_yampylytics.ffb.models.player import NFLPlayer, Position
from gridiron_yampylytics.ffb.scoring.scarcity import (
    GradientScarcityAnalyzer,
    ScarcityAnalyzer,
    TierScarcityAnalyzer,
)
from gridiron_yampylytics.ffb.scoring.scorer import PlayerScore, ScorerWeights, WeightedLinearScorer
from gridiron_yampylytics.ffb.scoring.vona import AdpVonaApproximation, MonteCarloVona, VonaCalculator
from gridiron_yampylytics.ffb.scoring.vor import (
    DEFAULT_FLEX_SHARES,
    PlayerVor,
    annotate_vor,
    compute_replacement_levels,
    compute_vor,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _p(pid: str, pos: str, pts: float, adp: float = 10.0) -> NFLPlayer:
    return NFLPlayer(player_id=pid, name=pid, position=Position(pos), team="KC", projected_points=pts, adp=adp)


def _state(available: list[NFLPlayer]) -> DraftState:
    """Draft at pick 1, user at slot 1 (user's turn), no flex."""
    rc = RosterConfig(qb=1, rb=1, wr=1, te=0, flex=0, k=0, def_=0, bench=1)
    league = League(team_count=2, roster=rc)
    managers = [
        Manager(manager_id="user", name="User", draft_slot=1, is_user=True),
        Manager(manager_id="opp", name="Opp", draft_slot=2, is_user=False),
    ]
    return DraftState.new(league=league, managers=managers, available_players=available)


def _state_with_roster(available: list[NFLPlayer], user_players: list[NFLPlayer]) -> DraftState:
    """Draft state with given players already on the user's roster."""
    rc = RosterConfig(qb=1, rb=1, wr=1, te=0, flex=0, k=0, def_=0, bench=1)
    league = League(team_count=2, roster=rc)
    user_mgr = Manager(manager_id="user", name="User", draft_slot=1, is_user=True)
    opp_mgr = Manager(manager_id="opp", name="Opp", draft_slot=2, is_user=False)
    user_roster = Roster(manager=user_mgr, players=user_players)
    opp_roster = Roster(manager=opp_mgr)
    return DraftState(
        league=league,
        managers=[user_mgr, opp_mgr],
        rosters={"user": user_roster, "opp": opp_roster},
        available_players=available,
        current_pick=len(user_players) * 2 + 1,
    )

# ---------------------------------------------------------------------------
# vor.py — compute_replacement_levels
# ---------------------------------------------------------------------------

class TestComputeReplacementLevels:
    """Tests for replacement-level derivation."""

    def test_no_flex_depth_equals_team_count_times_starters(self) -> None:
        """Without FLEX, effective depth = team_count × dedicated starters.

        2 teams, qb=1, no flex → effective_depth(QB) = 2.
        4 QBs sorted: pool[2] is the replacement.
        """
        rc = RosterConfig(qb=1, rb=0, wr=0, te=0, flex=0, k=0, def_=0, bench=0)
        players = [_p("q1", "QB", 300.0), _p("q2", "QB", 250.0), _p("q3", "QB", 200.0), _p("q4", "QB", 150.0)]
        levels = compute_replacement_levels(players, rc, team_count=2)
        assert levels[Position.QB] == pytest.approx(200.0)

    def test_flex_contribution_increases_rb_depth(self) -> None:
        """FLEX shifts extend effective RB depth beyond dedicated slots.

        2 teams, rb=1, flex=1, default rb_share=0.50:
        flex_contrib = round(1 × 2 × 0.5) = 1 → effective_depth(RB) = 3.
        """
        rc = RosterConfig(qb=0, rb=1, wr=0, te=0, flex=1, k=0, def_=0, bench=0)
        players = [_p(f"r{i}", "RB", float(200 - i * 20), float(i + 1)) for i in range(5)]
        levels = compute_replacement_levels(players, rc, team_count=2)
        assert levels[Position.RB] == pytest.approx(140.0)

    def test_position_absent_from_pool_returns_zero(self) -> None:
        """Positions with no players in the pool get replacement level 0.0."""
        rc = RosterConfig(qb=1, rb=0, wr=0, te=0, flex=0, k=0, def_=0, bench=0)
        players = [_p("q1", "QB", 300.0)]
        levels = compute_replacement_levels(players, rc, team_count=2)
        assert levels[Position.DEF] == pytest.approx(0.0)

    def test_pool_smaller_than_depth_returns_zero(self) -> None:
        """When fewer players exist than the effective depth, replacement level is 0.0."""
        rc = RosterConfig(qb=1, rb=0, wr=0, te=0, flex=0, k=0, def_=0, bench=0)
        players = [_p("q1", "QB", 300.0)]  # depth=2, pool size=1
        levels = compute_replacement_levels(players, rc, team_count=2)
        assert levels[Position.QB] == pytest.approx(0.0)

    def test_custom_flex_shares_override_default(self) -> None:
        """Custom flex_shares override the default PPR heuristic.

        RB share=1.0 → all flex slots go to RB:
        effective_depth(RB) = 2 × 1 + round(1 × 2 × 1.0) = 4.
        """
        rc = RosterConfig(qb=0, rb=1, wr=0, te=0, flex=1, k=0, def_=0, bench=0)
        players = [_p(f"r{i}", "RB", float(200 - i * 10), float(i + 1)) for i in range(6)]
        levels = compute_replacement_levels(players, rc, team_count=2, flex_shares={Position.RB: 1.0})
        assert levels[Position.RB] == pytest.approx(160.0)

    def test_replacement_level_sorted_descending_internally(self) -> None:
        """Pool is sorted descending before indexing; input order does not matter."""
        rc = RosterConfig(qb=1, rb=0, wr=0, te=0, flex=0, k=0, def_=0, bench=0)
        players = [_p("q3", "QB", 100.0), _p("q1", "QB", 300.0), _p("q2", "QB", 200.0)]
        levels = compute_replacement_levels(players, rc, team_count=2)
        assert levels[Position.QB] == pytest.approx(100.0)  # pool[2] of [300, 200, 100]

# ---------------------------------------------------------------------------
# vor.py — compute_vor / annotate_vor
# ---------------------------------------------------------------------------

class TestComputeVor:
    """Tests for VOR computation."""

    def test_above_replacement_is_positive(self) -> None:
        """VOR is positive for players above replacement level."""
        assert compute_vor(_p("q1", "QB", 300.0), {Position.QB: 200.0}) == pytest.approx(100.0)

    def test_at_replacement_is_zero(self) -> None:
        """VOR is exactly zero for a player at replacement level."""
        assert compute_vor(_p("q1", "QB", 200.0), {Position.QB: 200.0}) == pytest.approx(0.0)

    def test_below_replacement_is_negative(self) -> None:
        """VOR is negative for players below replacement level."""
        assert compute_vor(_p("q1", "QB", 150.0), {Position.QB: 200.0}) == pytest.approx(-50.0)

    def test_missing_position_uses_zero_replacement(self) -> None:
        """VOR equals projected_points when position is absent from replacement_levels."""
        assert compute_vor(_p("q1", "QB", 300.0), {}) == pytest.approx(300.0)


class TestAnnotateVor:
    """Tests for annotate_vor."""

    def test_sorted_descending_by_vor(self) -> None:
        """annotate_vor returns players sorted by VOR descending."""
        players = [_p("q2", "QB", 200.0), _p("q1", "QB", 350.0), _p("q3", "QB", 100.0)]
        result = annotate_vor(players, {Position.QB: 200.0})
        vors = [r.vor for r in result]
        assert vors == sorted(vors, reverse=True)

    def test_replacement_level_populated(self) -> None:
        """Each PlayerVor carries the correct replacement_level for its position."""
        players = [_p("q1", "QB", 300.0)]
        result = annotate_vor(players, {Position.QB: 200.0})
        assert result[0].replacement_level == pytest.approx(200.0)

    def test_returns_all_players(self) -> None:
        """annotate_vor returns one result per input player."""
        players = [_p(f"q{i}", "QB", float(i * 10)) for i in range(5)]
        assert len(annotate_vor(players, {Position.QB: 20.0})) == 5

# ---------------------------------------------------------------------------
# vona.py — AdpVonaApproximation
# ---------------------------------------------------------------------------

class TestAdpVonaApproximation:
    """Tests for the ADP-based VONA approximation."""

    def setup_method(self) -> None:
        """Create a shared calculator instance."""
        self.vona = AdpVonaApproximation()

    def test_zero_picks_no_players_taken(self) -> None:
        """When picks_until_user=0, no players are assumed taken yet.

        VONA = player.pts - best remaining competitor at same position.
        """
        players = [_p("q1", "QB", 300.0, 1.0), _p("q2", "QB", 250.0, 5.0), _p("r1", "RB", 280.0, 2.0)]
        result = self.vona.compute_vona(players[0], players, picks_until_user=0)
        assert result == pytest.approx(300.0 - 250.0)

    def test_likely_taken_players_excluded(self) -> None:
        """Players with the lowest ADP are removed from the survivor pool."""
        players = [
            _p("r1", "RB", 300.0, 1.0),
            _p("q1", "QB", 280.0, 2.0),  # likely taken (adp=2, within top-2)
            _p("q2", "QB", 200.0, 5.0),  # survives
        ]
        result = self.vona.compute_vona(players[1], players, picks_until_user=2)
        assert result == pytest.approx(280.0 - 200.0)

    def test_no_competition_returns_projected_points(self) -> None:
        """Returns player.projected_points when no position competitors survive."""
        players = [_p("q1", "QB", 300.0, 1.0)]
        result = self.vona.compute_vona(players[0], players, picks_until_user=0)
        assert result == pytest.approx(300.0)

    def test_player_excluded_from_own_comparison(self) -> None:
        """The evaluated player does not count as its own competitor."""
        players = [_p("q1", "QB", 300.0, 1.0), _p("q2", "QB", 300.0, 2.0)]
        result = self.vona.compute_vona(players[0], players, picks_until_user=0)
        assert result == pytest.approx(0.0)  # 300 - 300

    def test_cross_position_players_not_included(self) -> None:
        """Players at other positions do not affect VONA baseline."""
        players = [
            _p("q1", "QB", 300.0, 1.0),
            _p("r1", "RB", 400.0, 2.0),  # different position, ignored
            _p("q2", "QB", 200.0, 3.0),
        ]
        result = self.vona.compute_vona(players[0], players, picks_until_user=0)
        assert result == pytest.approx(300.0 - 200.0)


class TestMonteCarloVona:
    """Tests for the Monte Carlo VONA stub."""

    def test_raises_not_implemented(self) -> None:
        """compute_vona raises NotImplementedError — simulation module not built yet."""
        player = _p("q1", "QB", 300.0)
        with pytest.raises(NotImplementedError):
            MonteCarloVona().compute_vona(player, [player], 0)


class TestVonaCalculatorProtocol:
    """Both VONA implementations satisfy the VonaCalculator protocol."""

    def test_adp_satisfies_protocol(self) -> None:
        assert isinstance(AdpVonaApproximation(), VonaCalculator)

    def test_monte_carlo_satisfies_protocol(self) -> None:
        assert isinstance(MonteCarloVona(), VonaCalculator)

# ---------------------------------------------------------------------------
# scarcity.py — TierScarcityAnalyzer
# ---------------------------------------------------------------------------

class TestTierScarcityAnalyzer:
    """Tests for gap-based tier scarcity."""

    def test_empty_position_returns_empty_list(self) -> None:
        """Returns [] when no players at the requested position are available."""
        players = [_p("r1", "RB", 200.0)]
        assert TierScarcityAnalyzer().analyze(players, Position.QB) == []

    def test_player_before_cliff_gets_highest_scarcity(self) -> None:
        """The player just above a large drop gets scarcity_score=1.0.

        Pool: [300, 290, 200, 190], gap_threshold=30 → cliff between 290 and 200.
        Drops: [10, 90, 10, 0], max_drop=90 → player at 290 gets 90/90=1.0.
        """
        players = [_p("p1", "RB", 300.0), _p("p2", "RB", 290.0), _p("p3", "RB", 200.0), _p("p4", "RB", 190.0)]
        results = TierScarcityAnalyzer(gap_threshold=30.0).analyze(players, Position.RB)
        scores = {r.player.player_id: r.scarcity_score for r in results}
        assert scores["p2"] == pytest.approx(1.0)

    def test_tiers_assigned_correctly(self) -> None:
        """Tier boundaries open exactly where drops exceed gap_threshold.

        Pool: [300, 290, 200, 190], gap_threshold=30:
        - p1 and p2: tier 1 (drop between them = 10 < 30)
        - p3 and p4: tier 2 (cliff of 90 before p3)
        """
        players = [_p("p1", "RB", 300.0), _p("p2", "RB", 290.0), _p("p3", "RB", 200.0), _p("p4", "RB", 190.0)]
        results = TierScarcityAnalyzer(gap_threshold=30.0).analyze(players, Position.RB)
        tiers = {r.player.player_id: r.tier for r in results}
        assert tiers["p1"] == 1
        assert tiers["p2"] == 1
        assert tiers["p3"] == 2
        assert tiers["p4"] == 2

    def test_scores_normalized_to_unit_interval(self) -> None:
        """All scarcity_scores are in [0.0, 1.0]."""
        players = [_p(f"p{i}", "RB", float(200 - i * 20)) for i in range(5)]
        results = TierScarcityAnalyzer().analyze(players, Position.RB)
        for r in results:
            assert 0.0 <= r.scarcity_score <= 1.0

    def test_last_player_gets_zero_scarcity(self) -> None:
        """The lowest-ranked player has no one below them — drop=0, score=0.0."""
        players = [_p("p1", "RB", 300.0), _p("p2", "RB", 200.0), _p("p3", "RB", 100.0)]
        results = TierScarcityAnalyzer().analyze(players, Position.RB)
        assert results[-1].scarcity_score == pytest.approx(0.0)
        assert results[-1].player.player_id == "p3"

    def test_rank_in_position_assigned_correctly(self) -> None:
        """rank_in_position is 1-indexed within the sorted position pool."""
        players = [_p("p1", "RB", 300.0), _p("p2", "RB", 200.0), _p("p3", "RB", 100.0)]
        results = TierScarcityAnalyzer().analyze(players, Position.RB)
        assert [r.rank_in_position for r in results] == [1, 2, 3]

    def test_results_sorted_by_projected_points_desc(self) -> None:
        """Results are sorted descending by projected_points regardless of input order."""
        players = [_p("p3", "RB", 100.0), _p("p1", "RB", 300.0), _p("p2", "RB", 200.0)]
        results = TierScarcityAnalyzer().analyze(players, Position.RB)
        pts = [r.player.projected_points for r in results]
        assert pts == sorted(pts, reverse=True)

# ---------------------------------------------------------------------------
# scarcity.py — GradientScarcityAnalyzer
# ---------------------------------------------------------------------------

class TestGradientScarcityAnalyzer:
    """Tests for slope/curvature-based scarcity."""

    def test_empty_position_returns_empty_list(self) -> None:
        """Returns [] when no players at the requested position are available."""
        players = [_p("r1", "RB", 200.0)]
        assert GradientScarcityAnalyzer().analyze(players, Position.QB) == []

    def test_scores_in_unit_interval(self) -> None:
        """All scarcity_scores are in [0.0, 1.0]."""
        players = [_p(f"p{i}", "RB", float(200 - i * 20)) for i in range(6)]
        results = GradientScarcityAnalyzer().analyze(players, Position.RB)
        for r in results:
            assert 0.0 <= r.scarcity_score <= 1.0

    def test_single_player_gets_zero_scarcity(self) -> None:
        """A position pool with one player has no slope or curvature — score=0.0."""
        players = [_p("p1", "QB", 300.0)]
        results = GradientScarcityAnalyzer().analyze(players, Position.QB)
        assert len(results) == 1
        assert results[0].scarcity_score == pytest.approx(0.0)

    def test_cliff_player_scores_higher_than_top_player(self) -> None:
        """The player just before a large cliff scores higher than the player above the flat region.

        Pool: [300, 280, 100, 90] — cliff between 280 and 100.
        Central difference gives p2 (280) high slope and high curvature.
        """
        players = [_p("p1", "RB", 300.0), _p("p2", "RB", 280.0), _p("p3", "RB", 100.0), _p("p4", "RB", 90.0)]
        results = GradientScarcityAnalyzer().analyze(players, Position.RB)
        scores = {r.player.player_id: r.scarcity_score for r in results}
        assert scores["p2"] > scores["p1"]

    def test_results_sorted_by_projected_points_desc(self) -> None:
        """Results are sorted descending by projected_points regardless of input order."""
        players = [_p("p3", "RB", 100.0), _p("p1", "RB", 300.0), _p("p2", "RB", 200.0)]
        results = GradientScarcityAnalyzer().analyze(players, Position.RB)
        pts = [r.player.projected_points for r in results]
        assert pts == sorted(pts, reverse=True)


class TestScarcityAnalyzerProtocol:
    """Both scarcity implementations satisfy the ScarcityAnalyzer protocol."""

    def test_tier_analyzer_satisfies_protocol(self) -> None:
        assert isinstance(TierScarcityAnalyzer(), ScarcityAnalyzer)

    def test_gradient_analyzer_satisfies_protocol(self) -> None:
        assert isinstance(GradientScarcityAnalyzer(), ScarcityAnalyzer)

# ---------------------------------------------------------------------------
# scorer.py — ScorerWeights / WeightedLinearScorer
# ---------------------------------------------------------------------------

class TestScorerWeights:
    """Tests for default weight values."""

    def test_default_weights(self) -> None:
        """Default weights sum to 1.0 with the expected allocation."""
        w = ScorerWeights()
        assert w.vor == pytest.approx(0.40)
        assert w.vona == pytest.approx(0.30)
        assert w.scarcity == pytest.approx(0.20)
        assert w.roster_need == pytest.approx(0.10)


class TestWeightedLinearScorer:
    """Tests for the composite scorer."""

    def test_empty_available_returns_empty_list(self) -> None:
        """No available players → empty recommendation list."""
        state = _state([])
        assert WeightedLinearScorer().score(state, {}) == []

    def test_returns_all_available_players(self) -> None:
        """One PlayerScore is returned for each available player."""
        players = [_p(f"q{i}", "QB", float(i * 10 + 50), float(i + 1)) for i in range(5)]
        state = _state(players)
        results = WeightedLinearScorer().score(state, {Position.QB: 50.0})
        assert len(results) == 5

    def test_results_sorted_descending(self) -> None:
        """Results are in descending total_score order."""
        players = [_p(f"q{i}", "QB", float(i * 50 + 50), float(i + 1)) for i in range(5)]
        state = _state(players)
        results = WeightedLinearScorer().score(state, {Position.QB: 50.0})
        scores = [r.total_score for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_player_score_fields_populated(self) -> None:
        """Every PlayerScore field is non-None and in a valid range."""
        players = [_p("q1", "QB", 300.0, 1.0), _p("q2", "QB", 200.0, 2.0)]
        state = _state(players)
        results = WeightedLinearScorer().score(state, {Position.QB: 150.0})
        for r in results:
            assert isinstance(r, PlayerScore)
            assert isinstance(r.player, NFLPlayer)
            assert isinstance(r.total_score, float)
            assert isinstance(r.vor, float)
            assert isinstance(r.vona, float)
            assert 0.0 <= r.scarcity_score <= 1.0
            assert 0.0 <= r.roster_need_score <= 1.0

    def test_gradient_analyzer_accepted(self) -> None:
        """WeightedLinearScorer accepts GradientScarcityAnalyzer via protocol."""
        players = [_p("q1", "QB", 300.0, 1.0), _p("r1", "RB", 200.0, 2.0)]
        state = _state(players)
        levels = {Position.QB: 200.0, Position.RB: 100.0}
        scorer = WeightedLinearScorer(scarcity_analyzer=GradientScarcityAnalyzer())
        assert len(scorer.score(state, levels)) == 2

    def test_roster_need_one_for_empty_roster(self) -> None:
        """roster_need_score is 1.0 when the dedicated slot for a position is unfilled."""
        players = [_p("q1", "QB", 300.0, 1.0)]
        state = _state(players)
        results = WeightedLinearScorer().score(state, {Position.QB: 200.0})
        assert results[0].roster_need_score == pytest.approx(1.0)

    def test_roster_need_partial_after_dedicated_filled(self) -> None:
        """roster_need_score is 0.5 for QB once the dedicated slot is filled.

        QB gets one depth slot beyond its dedicated count (backup QB pressure),
        so need decreases from 1.0 → 0.5 → 0.0 rather than binary 1.0 → 0.0.
        """
        qb_on_roster = _p("q_drafted", "QB", 350.0, 1.0)
        available = [_p("q1", "QB", 300.0, 3.0), _p("r1", "RB", 250.0, 5.0)]
        state = _state_with_roster(available, [qb_on_roster])
        levels = {Position.QB: 200.0, Position.RB: 150.0}
        results = WeightedLinearScorer().score(state, levels)
        qb_score = next(r for r in results if r.player.position == Position.QB)
        rb_score = next(r for r in results if r.player.position == Position.RB)
        assert qb_score.roster_need_score == pytest.approx(0.5)
        assert rb_score.roster_need_score == pytest.approx(1.0)
