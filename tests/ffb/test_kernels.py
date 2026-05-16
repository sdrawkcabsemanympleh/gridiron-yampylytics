"""Tests for ffb/simulation/kernels.py — vectorized pick sampling and lineup scoring."""
import numpy as np
import pytest
from gridiron_yampylytics.ffb.models.draft import DraftState
from gridiron_yampylytics.ffb.models.league import League, RosterConfig
from gridiron_yampylytics.ffb.models.manager import Manager
from gridiron_yampylytics.ffb.models.player import NFLPlayer, Position
from gridiron_yampylytics.ffb.simulation.kernels import (
    STRATEGY_ADP,
    STRATEGY_GREEDY_VOR,
    STRATEGY_NEED_WEIGHTED_ADP,
    STRATEGY_WEIGHTED_SCORER,
    _compute_weighted_scores,
    _sample_pick,
    _score_lineup,
    simulate_batch,
)
from gridiron_yampylytics.ffb.simulation.snapshot import POSITION_INDEX, SimSnapshot


def _p(pid: str, pos: str, pts: float, adp: float, std: float = 2.0) -> NFLPlayer:
    return NFLPlayer(player_id=pid, name=pid, position=Position(pos), team="KC",
                     projected_points=pts, adp=adp, adp_std=std)


def _state(available: list[NFLPlayer]) -> DraftState:
    rc = RosterConfig(qb=1, rb=1, wr=0, te=0, flex=0, k=0, def_=0, bench=1)
    league = League(team_count=2, roster=rc)
    managers = [
        Manager(manager_id="user", name="User", draft_slot=1, is_user=True),
        Manager(manager_id="opp", name="Opp", draft_slot=2, is_user=False),
    ]
    return DraftState.new(league=league, managers=managers, available_players=available)


def _repl() -> dict[Position, float]:
    return {Position.QB: 50.0, Position.RB: 100.0, Position.WR: 80.0,
            Position.TE: 60.0, Position.K: 30.0, Position.DEF: 20.0}


def _mock_arrays(n: int = 4) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Return (adps, adp_stds, points, positions, available) for n players."""
    adps = np.array([1.0, 2.0, 3.0, 4.0][:n], dtype=np.float64)
    stds = np.full(n, 2.0, dtype=np.float64)
    pts = np.array([300.0, 250.0, 200.0, 150.0][:n], dtype=np.float64)
    # 0=QB, 1=RB, 1=RB, 0=QB
    pos = np.array([0, 1, 1, 0][:n], dtype=np.int32)
    avail = np.ones(n, dtype=bool)
    return adps, stds, pts, pos, avail


def _mock_repl() -> np.ndarray:
    r = np.zeros(len(Position), dtype=np.float64)
    r[POSITION_INDEX[Position.QB]] = 50.0
    r[POSITION_INDEX[Position.RB]] = 100.0
    return r


def _mock_slots() -> np.ndarray:
    s = np.zeros(len(Position), dtype=np.int32)
    s[POSITION_INDEX[Position.QB]] = 1
    s[POSITION_INDEX[Position.RB]] = 1
    return s


# ---------------------------------------------------------------------------
# _sample_pick — ADP strategy
# ---------------------------------------------------------------------------

class TestSamplePickADP:
    def test_returns_index_in_range(self) -> None:
        adps, stds, pts, pos, avail = _mock_arrays()
        rng = np.random.default_rng(0)
        idx = _sample_pick(STRATEGY_ADP, np.empty(0), adps, stds, pts, pos,
                           np.zeros(len(Position), dtype=np.int32), _mock_slots(),
                           _mock_repl(), avail, 1, 8,
                           np.array([], dtype=np.int32), 0, rng)
        assert 0 <= idx < 4

    def test_skips_unavailable_players(self) -> None:
        adps, stds, pts, pos, avail = _mock_arrays()
        avail[0] = False  # make player 0 unavailable
        rng = np.random.default_rng(42)
        for _ in range(50):
            idx = _sample_pick(STRATEGY_ADP, np.empty(0), adps, stds, pts, pos,
                               np.zeros(len(Position), dtype=np.int32), _mock_slots(),
                               _mock_repl(), avail, 1, 8,
                               np.array([], dtype=np.int32), 0, rng)
            assert idx != 0

    def test_dominant_adp_player_selected_most_often(self) -> None:
        adps = np.array([1.0, 50.0, 50.0, 50.0], dtype=np.float64)
        stds = np.full(4, 0.5, dtype=np.float64)  # tight stds → strong peak
        pts = np.array([300.0, 10.0, 10.0, 10.0], dtype=np.float64)
        pos = np.zeros(4, dtype=np.int32)
        avail = np.ones(4, dtype=bool)
        repl = _mock_repl()
        slots = _mock_slots()
        rng = np.random.default_rng(0)
        picks = [_sample_pick(STRATEGY_ADP, np.empty(0), adps, stds, pts, pos,
                              np.zeros(len(Position), dtype=np.int32), slots, repl, avail, 1, 8,
                              np.array([], dtype=np.int32), 0, rng)
                 for _ in range(100)]
        assert picks.count(0) > 80


# ---------------------------------------------------------------------------
# _sample_pick — NeedWeightedADP strategy
# ---------------------------------------------------------------------------

class TestSamplePickNeedWeighted:
    def test_suppresses_overstocked_position(self) -> None:
        """With need_weight=1.0, min_need_factor=0.0: fully stocked QB should never pick."""
        adps = np.array([1.0, 2.0], dtype=np.float64)
        stds = np.full(2, 2.0, dtype=np.float64)
        pts = np.array([300.0, 200.0], dtype=np.float64)
        pos = np.array([0, 1], dtype=np.int32)  # QB, RB
        avail = np.ones(2, dtype=bool)
        slots = _mock_slots()
        repl = _mock_repl()
        # User already has 1 QB (slot is full), 0 RB
        mgr_counts = np.zeros(len(Position), dtype=np.int32)
        mgr_counts[POSITION_INDEX[Position.QB]] = 1
        params = np.array([1.0, 0.0, 0.0])  # need_weight=1.0, min=0, no fade
        rng = np.random.default_rng(0)
        picks = [_sample_pick(STRATEGY_NEED_WEIGHTED_ADP, params, adps, stds, pts, pos,
                              mgr_counts, slots, repl, avail, 1, 8,
                           np.array([], dtype=np.int32), 0, rng)
                 for _ in range(50)]
        assert all(p == 1 for p in picks)  # always picks RB

    def test_falls_back_to_adp_with_no_need_weight(self) -> None:
        """need_weight=0.0 should behave identically to pure ADP."""
        adps, stds, pts, pos, avail = _mock_arrays()
        slots = _mock_slots()
        repl = _mock_repl()
        mgr_counts = np.zeros(len(Position), dtype=np.int32)
        params_zero_need = np.array([0.0, 0.15, 0.7])
        params_adp = np.empty(0)
        rng_a = np.random.default_rng(7)
        rng_b = np.random.default_rng(7)
        for _ in range(30):
            idx_need = _sample_pick(STRATEGY_NEED_WEIGHTED_ADP, params_zero_need, adps, stds, pts, pos,
                                    mgr_counts, slots, repl, avail, 1, 8,
                                    np.array([], dtype=np.int32), 0, rng_a)
            idx_adp = _sample_pick(STRATEGY_ADP, params_adp, adps, stds, pts, pos,
                                   mgr_counts, slots, repl, avail, 1, 8,
                                   np.array([], dtype=np.int32), 0, rng_b)
            assert idx_need == idx_adp


# ---------------------------------------------------------------------------
# _sample_pick — GreedyVOR strategy
# ---------------------------------------------------------------------------

class TestSamplePickGreedyVor:
    def test_selects_highest_vor_available(self) -> None:
        adps = np.array([1.0, 2.0, 3.0], dtype=np.float64)
        stds = np.full(3, 2.0, dtype=np.float64)
        # QB:300 VOR=250, RB:200 VOR=100, RB:150 VOR=50
        pts = np.array([300.0, 200.0, 150.0], dtype=np.float64)
        pos = np.array([0, 1, 1], dtype=np.int32)
        avail = np.ones(3, dtype=bool)
        mgr_counts = np.zeros(len(Position), dtype=np.int32)
        slots = _mock_slots()
        repl = _mock_repl()
        rng = np.random.default_rng(0)
        idx = _sample_pick(STRATEGY_GREEDY_VOR, np.empty(0), adps, stds, pts, pos,
                           mgr_counts, slots, repl, avail, 1, 8,
                           np.array([], dtype=np.int32), 0, rng)
        assert idx == 0  # QB has highest VOR

    def test_prioritises_unfilled_position_over_higher_vor(self) -> None:
        adps = np.array([1.0, 2.0], dtype=np.float64)
        stds = np.full(2, 2.0, dtype=np.float64)
        # QB:300 VOR=250 (slot full), RB:200 VOR=100 (slot needed)
        pts = np.array([300.0, 200.0], dtype=np.float64)
        pos = np.array([0, 1], dtype=np.int32)
        avail = np.ones(2, dtype=bool)
        mgr_counts = np.zeros(len(Position), dtype=np.int32)
        mgr_counts[POSITION_INDEX[Position.QB]] = 1  # QB slot full
        slots = _mock_slots()
        repl = _mock_repl()
        rng = np.random.default_rng(0)
        idx = _sample_pick(STRATEGY_GREEDY_VOR, np.empty(0), adps, stds, pts, pos,
                           mgr_counts, slots, repl, avail, 1, 8,
                           np.array([], dtype=np.int32), 0, rng)
        assert idx == 1  # RB because QB slot is full


# ---------------------------------------------------------------------------
# _score_lineup
# ---------------------------------------------------------------------------

class TestScoreLineup:
    def _make_arrays(self, players: list[tuple[str, float]]) -> tuple[np.ndarray, np.ndarray]:
        """Return (points, positions) for (pos_str, pts) tuples."""
        pts = np.array([p for _, p in players], dtype=np.float64)
        pos = np.array([POSITION_INDEX[Position(s)] for s, _ in players], dtype=np.int32)
        return pts, pos

    def test_selects_best_starting_lineup(self) -> None:
        # 2 RBs available, 1 RB slot; should pick the higher one
        pts = np.array([200.0, 150.0], dtype=np.float64)
        pos = np.array([POSITION_INDEX[Position.RB]] * 2, dtype=np.int32)
        user_mask = np.ones(2, dtype=bool)
        slots = np.zeros(len(Position), dtype=np.int32)
        slots[POSITION_INDEX[Position.RB]] = 1
        score = _score_lineup(user_mask, pts, pos, slots, np.array([], dtype=np.int32), 0)
        assert score == pytest.approx(200.0)

    def test_fills_dedicated_before_flex(self) -> None:
        # QB(300), RB(200), RB(150); 1 QB + 1 RB dedicated + 1 FLEX(RB eligible)
        pts = np.array([300.0, 200.0, 150.0], dtype=np.float64)
        pos = np.array([
            POSITION_INDEX[Position.QB],
            POSITION_INDEX[Position.RB],
            POSITION_INDEX[Position.RB],
        ], dtype=np.int32)
        user_mask = np.ones(3, dtype=bool)
        slots = np.zeros(len(Position), dtype=np.int32)
        slots[POSITION_INDEX[Position.QB]] = 1
        slots[POSITION_INDEX[Position.RB]] = 1
        flex_pos = np.array([POSITION_INDEX[Position.RB]], dtype=np.int32)
        score = _score_lineup(user_mask, pts, pos, slots, flex_pos, 1)
        # QB(300) + RB1(200) dedicated; RB2(150) in FLEX
        assert score == pytest.approx(650.0)

    def test_zero_for_empty_roster(self) -> None:
        pts = np.array([300.0, 200.0], dtype=np.float64)
        pos = np.array([POSITION_INDEX[Position.QB], POSITION_INDEX[Position.RB]], dtype=np.int32)
        user_mask = np.zeros(2, dtype=bool)
        slots = np.zeros(len(Position), dtype=np.int32)
        slots[POSITION_INDEX[Position.QB]] = 1
        assert _score_lineup(user_mask, pts, pos, slots, np.array([], dtype=np.int32), 0) == pytest.approx(0.0)

    def test_matches_optimize_lineup_output(self) -> None:
        """End-to-end: _score_lineup must agree with the OO roster_evaluator."""
        from gridiron_yampylytics.ffb.evaluation.roster_evaluator import score_roster
        players = [
            _p("q1", "QB", 320, 1.0),
            _p("r1", "RB", 230, 2.0),
            _p("r2", "RB", 190, 3.0),
            _p("w1", "WR", 250, 4.0),
        ]
        rc = RosterConfig(qb=1, rb=1, wr=1, te=0, flex=1, k=0, def_=0, bench=1)
        expected = score_roster(players, rc)
        # Build arrays over all 4 players
        pts = np.array([p.projected_points for p in players], dtype=np.float64)
        pos = np.array([POSITION_INDEX[p.position] for p in players], dtype=np.int32)
        user_mask = np.ones(4, dtype=bool)
        slots = np.zeros(len(Position), dtype=np.int32)
        slots[POSITION_INDEX[Position.QB]] = rc.qb
        slots[POSITION_INDEX[Position.RB]] = rc.rb
        slots[POSITION_INDEX[Position.WR]] = rc.wr
        flex_pos = np.array([POSITION_INDEX[p] for p in rc.flex_eligible], dtype=np.int32)
        result = _score_lineup(user_mask, pts, pos, slots, flex_pos, rc.flex)
        assert result == pytest.approx(expected)


# ---------------------------------------------------------------------------
# simulate_batch — integration
# ---------------------------------------------------------------------------

class TestSimulateBatch:
    def _make_snapshot(self) -> tuple[SimSnapshot, dict]:
        players = [
            _p("q1", "QB", 400, 1.0),
            _p("r1", "RB", 300, 2.0),
            _p("r2", "RB", 270, 3.0),
            _p("q2", "QB", 50, 4.0),
            _p("r3", "RB", 200, 5.0),
            _p("r4", "RB", 150, 6.0),
        ]
        state = _state(players)
        repl = _repl()
        snap = SimSnapshot.from_draft_state(state, players[0], repl)
        return snap, repl

    def test_returns_positive_mean_score(self) -> None:
        snap, _ = self._make_snapshot()
        rng = np.random.default_rng(0)
        params = np.array([0.3, 0.15, 0.7])
        mean, std = simulate_batch(snap, STRATEGY_NEED_WEIGHTED_ADP, params,
                                   STRATEGY_GREEDY_VOR, np.empty(0), 10, rng)
        assert mean > 0.0

    def test_std_is_nonnegative(self) -> None:
        snap, _ = self._make_snapshot()
        rng = np.random.default_rng(1)
        params = np.array([0.3, 0.15, 0.7])
        _, std = simulate_batch(snap, STRATEGY_NEED_WEIGHTED_ADP, params,
                                STRATEGY_GREEDY_VOR, np.empty(0), 10, rng)
        assert std >= 0.0

    def test_dominant_candidate_scores_higher(self) -> None:
        """Candidate with 400pts QB should outscore 50pts QB candidate."""
        players = [
            _p("q1", "QB", 400, 1.0),
            _p("r1", "RB", 300, 2.0),
            _p("r2", "RB", 270, 3.0),
            _p("q2", "QB", 50, 4.0),
            _p("r3", "RB", 200, 5.0),
            _p("r4", "RB", 150, 6.0),
        ]
        state = _state(players)
        repl = _repl()
        snap_q1 = SimSnapshot.from_draft_state(state, players[0], repl)
        snap_q2 = SimSnapshot.from_draft_state(state, players[3], repl)
        params = np.array([0.3, 0.15, 0.7])
        mean_q1, _ = simulate_batch(snap_q1, STRATEGY_NEED_WEIGHTED_ADP, params,
                                    STRATEGY_GREEDY_VOR, np.empty(0), 50,
                                    np.random.default_rng(0))
        mean_q2, _ = simulate_batch(snap_q2, STRATEGY_NEED_WEIGHTED_ADP, params,
                                    STRATEGY_GREEDY_VOR, np.empty(0), 50,
                                    np.random.default_rng(0))
        assert mean_q1 > mean_q2

    def test_seeded_simulation_is_reproducible(self) -> None:
        snap, _ = self._make_snapshot()
        params = np.array([0.3, 0.15, 0.7])
        m1, s1 = simulate_batch(snap, STRATEGY_NEED_WEIGHTED_ADP, params,
                                 STRATEGY_GREEDY_VOR, np.empty(0), 20,
                                 np.random.default_rng(42))
        m2, s2 = simulate_batch(snap, STRATEGY_NEED_WEIGHTED_ADP, params,
                                 STRATEGY_GREEDY_VOR, np.empty(0), 20,
                                 np.random.default_rng(42))
        assert m1 == pytest.approx(m2)
        assert s1 == pytest.approx(s2)

    def test_weighted_scorer_strategy_produces_positive_mean(self) -> None:
        snap, _ = self._make_snapshot()
        user_params = np.array([0.40, 0.30, 0.20, 0.10, 1.0])
        opp_params = np.array([0.3, 0.15, 0.7])
        mean, std = simulate_batch(snap, STRATEGY_NEED_WEIGHTED_ADP, opp_params,
                                   STRATEGY_WEIGHTED_SCORER, user_params, 20,
                                   np.random.default_rng(0))
        assert mean > 0.0
        assert std >= 0.0

    def test_weighted_scorer_is_reproducible(self) -> None:
        snap, _ = self._make_snapshot()
        user_params = np.array([0.40, 0.30, 0.20, 0.10, 1.0])
        opp_params = np.array([0.3, 0.15, 0.7])
        m1, s1 = simulate_batch(snap, STRATEGY_NEED_WEIGHTED_ADP, opp_params,
                                 STRATEGY_WEIGHTED_SCORER, user_params, 20,
                                 np.random.default_rng(99))
        m2, s2 = simulate_batch(snap, STRATEGY_NEED_WEIGHTED_ADP, opp_params,
                                 STRATEGY_WEIGHTED_SCORER, user_params, 20,
                                 np.random.default_rng(99))
        assert m1 == pytest.approx(m2)
        assert s1 == pytest.approx(s2)


# ---------------------------------------------------------------------------
# _compute_weighted_scores
# ---------------------------------------------------------------------------

class TestComputeWeightedScores:
    def _make_inputs(self) -> tuple:
        """4 players: QB(300), RB(200), RB(150), QB(50). QB slot full, RB slot open."""
        pts = np.array([300.0, 200.0, 150.0, 50.0], dtype=np.float64)
        adps = np.array([1.0, 2.0, 3.0, 4.0], dtype=np.float64)
        pos = np.array([0, 1, 1, 0], dtype=np.int32)  # QB=0, RB=1
        avail = np.ones(4, dtype=bool)
        repl = _mock_repl()
        slots = _mock_slots()
        mgr_counts = np.zeros(len(Position), dtype=np.int32)
        mgr_counts[POSITION_INDEX[Position.QB]] = 1  # QB slot full
        flex_pos = np.array([], dtype=np.int32)
        return pts, adps, pos, avail, repl, slots, mgr_counts, flex_pos

    def test_returns_array_of_correct_shape(self) -> None:
        pts, adps, pos, avail, repl, slots, mgr_counts, flex_pos = self._make_inputs()
        scores = _compute_weighted_scores(
            adps, pts, pos, mgr_counts, slots, repl, flex_pos, avail, 0,
            0.40, 0.30, 0.20, 0.10,
        )
        assert scores.shape == (4,)

    def test_unavailable_players_score_zero(self) -> None:
        pts, adps, pos, avail, repl, slots, mgr_counts, flex_pos = self._make_inputs()
        avail[2] = False
        scores = _compute_weighted_scores(
            adps, pts, pos, mgr_counts, slots, repl, flex_pos, avail, 0,
            0.40, 0.30, 0.20, 0.10,
        )
        assert scores[2] == pytest.approx(0.0)

    def test_high_vor_player_scores_above_low_vor(self) -> None:
        """RB(200) has higher VOR than QB(50) when QB slot is full (need=0 for QB)."""
        pts, adps, pos, avail, repl, slots, mgr_counts, flex_pos = self._make_inputs()
        scores = _compute_weighted_scores(
            adps, pts, pos, mgr_counts, slots, repl, flex_pos, avail, 0,
            0.40, 0.30, 0.20, 0.10,
        )
        rb_idx = 1  # RB(200), slot needed
        qb_low_idx = 3  # QB(50), slot full
        assert scores[rb_idx] > scores[qb_low_idx]

    def test_vona_reduces_score_of_redundant_players(self) -> None:
        """When two similar RBs exist, the lower one has lower VONA (less urgency)."""
        pts, adps, pos, avail, repl, slots, mgr_counts, flex_pos = self._make_inputs()
        scores = _compute_weighted_scores(
            adps, pts, pos, mgr_counts, slots, repl, flex_pos, avail, 0,
            0.00, 1.00, 0.00, 0.00,  # VONA-only
        )
        rb_high_idx = 1  # RB(200) — the "scarce" one at top of its position
        rb_low_idx = 2   # RB(150) — less urgent because RB(200) is better
        assert scores[rb_high_idx] >= scores[rb_low_idx]


# ---------------------------------------------------------------------------
# _sample_pick — WeightedScorer strategy
# ---------------------------------------------------------------------------

class TestSamplePickWeightedScorer:
    def _weighted_params(self, temperature: float = 1.0) -> np.ndarray:
        return np.array([0.40, 0.30, 0.20, 0.10, temperature], dtype=np.float64)

    def test_returns_index_in_range(self) -> None:
        adps, stds, pts, pos, avail = _mock_arrays()
        rng = np.random.default_rng(0)
        idx = _sample_pick(STRATEGY_WEIGHTED_SCORER, self._weighted_params(), adps, stds, pts, pos,
                           np.zeros(len(Position), dtype=np.int32), _mock_slots(),
                           _mock_repl(), avail, 1, 8,
                           np.array([], dtype=np.int32), 0, rng)
        assert 0 <= idx < 4

    def test_skips_unavailable_players(self) -> None:
        adps, stds, pts, pos, avail = _mock_arrays()
        avail[0] = False
        rng = np.random.default_rng(7)
        for _ in range(30):
            idx = _sample_pick(STRATEGY_WEIGHTED_SCORER, self._weighted_params(), adps, stds, pts, pos,
                               np.zeros(len(Position), dtype=np.int32), _mock_slots(),
                               _mock_repl(), avail, 1, 8,
                               np.array([], dtype=np.int32), 0, rng)
            assert idx != 0

    def test_low_temperature_favours_top_scorer(self) -> None:
        """Very low temperature → near-deterministic; best VOR player picked most often."""
        adps = np.array([1.0, 2.0, 3.0, 4.0], dtype=np.float64)
        stds = np.full(4, 2.0, dtype=np.float64)
        pts = np.array([400.0, 10.0, 10.0, 10.0], dtype=np.float64)  # player 0 dominant
        pos = np.array([0, 1, 1, 0], dtype=np.int32)
        avail = np.ones(4, dtype=bool)
        rng = np.random.default_rng(0)
        picks = [
            _sample_pick(STRATEGY_WEIGHTED_SCORER, self._weighted_params(temperature=0.01),
                         adps, stds, pts, pos,
                         np.zeros(len(Position), dtype=np.int32), _mock_slots(),
                         _mock_repl(), avail, 1, 8,
                         np.array([], dtype=np.int32), 0, rng)
            for _ in range(50)
        ]
        assert picks.count(0) > 40  # near-deterministic at very low temperature
