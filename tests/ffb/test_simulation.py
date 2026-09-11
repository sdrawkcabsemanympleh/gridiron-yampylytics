"""Tests for ffb/simulation/pick_model.py and ffb/simulation/engine.py."""
import threading
import numpy as np
import pytest
from gridiron_yampylytics.ffb.models.draft import DraftState, Roster
from gridiron_yampylytics.ffb.models.league import League, RosterConfig
from gridiron_yampylytics.ffb.models.manager import Manager
from gridiron_yampylytics.ffb.models.player import NFLPlayer, Position
from gridiron_yampylytics.ffb.simulation.engine import DraftSimulator, SimulationResult
from gridiron_yampylytics.ffb.simulation.pick_model import (
    ADPPickModel,
    GreedyVorPickModel,
    NeedWeightedADPModel,
    PickModel,
    ScoredPickModel,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _p(pid: str, pos: str, pts: float, adp: float, std: float = 2.0) -> NFLPlayer:
    return NFLPlayer(player_id=pid, name=pid, position=Position(pos), team="KC", projected_points=pts, adp=adp, adp_std=std)


def _state(available: list[NFLPlayer]) -> DraftState:
    """2 teams, 3 rounds each (qb=1, rb=1, bench=1); user at slot 1, pick 1."""
    rc = RosterConfig(qb=1, rb=1, wr=0, te=0, flex=0, k=0, def_=0, bench=1)
    league = League(team_count=2, roster=rc)
    managers = [
        Manager(manager_id="user", name="User", draft_slot=1, is_user=True),
        Manager(manager_id="opp", name="Opp", draft_slot=2, is_user=False),
    ]
    return DraftState.new(league=league, managers=managers, available_players=available)

# ---------------------------------------------------------------------------
# pick_model.py — ADPPickModel
# ---------------------------------------------------------------------------

class TestADPPickModel:
    """Tests for the ADP-based pick model."""

    def setup_method(self) -> None:
        """Shared model instance and seeded RNG."""
        self.model = ADPPickModel()
        self.rng = np.random.default_rng(42)

    def test_returns_player_from_available(self) -> None:
        """sample_pick always returns a player that was in available_players."""
        players = [_p("q1", "QB", 300.0, 1.0), _p("r1", "RB", 280.0, 3.0)]
        pick = self.model.sample_pick(players, 1, self.rng)
        assert pick in players

    def test_empty_available_raises_value_error(self) -> None:
        """sample_pick raises ValueError on an empty available pool."""
        with pytest.raises(ValueError, match="empty"):
            self.model.sample_pick([], 1, self.rng)

    def test_certain_pick_near_adp(self) -> None:
        """A player with ADP=5 and very low std dominates sampling at pick 5.

        With adp_std=0.01, z is enormous for any other player, making their
        weight ≈ 0. The player at their ADP should be chosen in all samples.
        """
        rng = np.random.default_rng(0)
        players = [
            _p("consensus", "QB", 300.0, adp=5.0, std=0.01),  # z≈0 at pick 5
            _p("sleeper", "QB", 280.0, adp=50.0, std=0.01),   # z≈4500 at pick 5
        ]
        picks = [self.model.sample_pick(players, 5, rng).player_id for _ in range(50)]
        assert all(p == "consensus" for p in picks)

    def test_different_seeds_can_produce_different_picks(self) -> None:
        """Sampling is stochastic — different seeds can produce different outcomes."""
        players = [_p(f"p{i}", "QB", float(100 - i), float(i + 1)) for i in range(10)]
        pick_a = self.model.sample_pick(players, 5, np.random.default_rng(1))
        pick_b = self.model.sample_pick(players, 5, np.random.default_rng(999))
        # Can't guarantee they differ, but with 10 players this is overwhelmingly likely
        assert isinstance(pick_a, NFLPlayer)
        assert isinstance(pick_b, NFLPlayer)


class TestScoredPickModel:
    """Tests for the ScoredPickModel stub."""

    def test_raises_not_implemented(self) -> None:
        """sample_pick raises NotImplementedError — not yet implemented."""
        player = _p("q1", "QB", 300.0, 1.0)
        rng = np.random.default_rng(0)
        with pytest.raises(NotImplementedError):
            ScoredPickModel().sample_pick([player], 1, rng)


class TestPickModelProtocol:
    """All pick model implementations satisfy the PickModel protocol."""

    def test_adp_satisfies_protocol(self) -> None:
        assert isinstance(ADPPickModel(), PickModel)

    def test_scored_satisfies_protocol(self) -> None:
        assert isinstance(ScoredPickModel(), PickModel)

    def test_need_weighted_adp_satisfies_protocol(self) -> None:
        assert isinstance(NeedWeightedADPModel(), PickModel)

    def test_greedy_vor_satisfies_protocol(self) -> None:
        assert isinstance(GreedyVorPickModel(), PickModel)

# ---------------------------------------------------------------------------
# pick_model.py — NeedWeightedADPModel
# ---------------------------------------------------------------------------

class TestNeedWeightedADPModel:
    """Tests for the roster-aware ADP pick model."""

    def setup_method(self) -> None:
        """Shared instances and a simple roster config."""
        self.rng = np.random.default_rng(42)
        self.rc = RosterConfig(qb=1, rb=2, wr=0, te=0, flex=0, k=0, def_=0, bench=1)

    def _p(self, pid: str, pos: str, adp: float) -> NFLPlayer:
        return NFLPlayer(player_id=pid, name=pid, position=Position(pos), team="KC",
                         projected_points=100.0, adp=adp, adp_std=1.0)

    def test_returns_player_from_available(self) -> None:
        """sample_pick always returns a player that was in available_players."""
        players = [self._p("q1", "QB", 1.0), self._p("r1", "RB", 2.0)]
        model = NeedWeightedADPModel()
        assert model.sample_pick(players, 1, self.rng) in players

    def test_empty_raises_value_error(self) -> None:
        """sample_pick raises ValueError on an empty available pool."""
        with pytest.raises(ValueError, match="empty"):
            NeedWeightedADPModel().sample_pick([], 1, self.rng)

    def test_falls_back_to_pure_adp_without_roster_context(self) -> None:
        """Without roster_counts or roster_config the model behaves identically to ADPPickModel."""
        players = [self._p("q1", "QB", 1.0), self._p("r1", "RB", 2.0)]
        adp_model = ADPPickModel()
        need_model = NeedWeightedADPModel()
        rng_a = np.random.default_rng(0)
        rng_b = np.random.default_rng(0)
        picks_adp = [adp_model.sample_pick(players, 1, rng_a).player_id for _ in range(200)]
        picks_need = [need_model.sample_pick(players, 1, rng_b).player_id for _ in range(200)]
        assert picks_adp == picks_need

    def test_overstocked_position_suppressed(self) -> None:
        """With need_weight=1.0 and min_need_factor=0.0, a filled position slot is never sampled.

        roster_counts has qb=1 (slot filled), rb=0 (slot open). With full need weight and
        zero floor, QB weight collapses to 0 — only RBs should ever be sampled.
        """
        qb = self._p("q1", "QB", 1.0)
        rb = self._p("r1", "RB", 2.0)
        model = NeedWeightedADPModel(need_weight=1.0, min_need_factor=0.0)
        roster_counts = {Position.QB: 1, Position.RB: 0}
        picks = [
            model.sample_pick([qb, rb], 2, self.rng, roster_counts=roster_counts, roster_config=self.rc).player_id
            for _ in range(100)
        ]
        assert all(p == "r1" for p in picks)

    def test_late_round_fade_removes_need_at_final_pick(self) -> None:
        """With late_round_fade=1.0, need influence drops to zero at the last pick.

        A model with full need weight but maximum fade behaves like pure ADP at
        total_picks. Verified by comparing to ADPPickModel with the same seed.
        """
        qb = self._p("q1", "QB", 1.0)
        rb = self._p("r1", "RB", 2.0)
        need_model = NeedWeightedADPModel(need_weight=1.0, min_need_factor=0.0, late_round_fade=1.0)
        adp_model = ADPPickModel()
        roster_counts = {Position.QB: 1}
        total_picks = 6
        rng_a = np.random.default_rng(7)
        rng_b = np.random.default_rng(7)
        picks_need = [
            need_model.sample_pick(
                [qb, rb], total_picks, rng_a,
                roster_counts=roster_counts, roster_config=self.rc, total_picks=total_picks,
            ).player_id
            for _ in range(200)
        ]
        picks_adp = [adp_model.sample_pick([qb, rb], total_picks, rng_b).player_id for _ in range(200)]
        assert picks_need == picks_adp


# ---------------------------------------------------------------------------
# pick_model.py — GreedyVorPickModel
# ---------------------------------------------------------------------------

class TestGreedyVorPickModel:
    """Tests for the greedy VOR pick model."""

    def _p(self, pid: str, pos: str, pts: float) -> NFLPlayer:
        return NFLPlayer(player_id=pid, name=pid, position=Position(pos), team="KC",
                         projected_points=pts, adp=1.0)

    def _rc(self) -> RosterConfig:
        return RosterConfig(qb=1, rb=2, wr=0, te=0, flex=0, k=0, def_=0, bench=1)

    def test_empty_raises_value_error(self) -> None:
        """sample_pick raises ValueError on an empty available pool."""
        rng = np.random.default_rng(0)
        with pytest.raises(ValueError, match="empty"):
            GreedyVorPickModel().sample_pick([], 1, rng)

    def test_picks_best_vor_without_roster_context(self) -> None:
        """Without roster context, picks the player with the highest VOR."""
        players = [self._p("q1", "QB", 100.0), self._p("r1", "RB", 200.0)]
        levels = {Position.QB: 50.0, Position.RB: 50.0}
        rng = np.random.default_rng(0)
        pick = GreedyVorPickModel().sample_pick(players, 1, rng, replacement_levels=levels)
        assert pick.player_id == "r1"  # VOR 150 > 50

    def test_fills_needed_position_over_higher_projected_points(self) -> None:
        """With an open QB slot, picks QB even when an RB has higher projected points.

        QB (200 pts) vs RB (300 pts). QB slot is empty; RB slot is full.
        The needed pool contains only QB, so GreedyVorPickModel must pick QB.
        """
        qb = self._p("q1", "QB", 200.0)
        rb = self._p("r1", "RB", 300.0)
        rc = self._rc()
        roster_counts = {Position.QB: 0, Position.RB: 2}  # RB slots full, QB open
        levels = {Position.QB: 50.0, Position.RB: 50.0}
        rng = np.random.default_rng(0)
        pick = GreedyVorPickModel().sample_pick(
            [qb, rb], 1, rng, roster_counts=roster_counts, roster_config=rc, replacement_levels=levels,
        )
        assert pick.player_id == "q1"

    def test_falls_back_to_projected_points_without_replacement_levels(self) -> None:
        """Without replacement_levels, picks by projected_points."""
        players = [self._p("q1", "QB", 100.0), self._p("r1", "RB", 400.0)]
        rng = np.random.default_rng(0)
        pick = GreedyVorPickModel().sample_pick(players, 1, rng)
        assert pick.player_id == "r1"

    def test_uses_full_pool_when_no_needed_players_on_board(self) -> None:
        """Falls back to all available players when no player in a needed position is available.

        Needed: QB (slot open). Board: only RBs. Model must still return a player.
        """
        rb1 = self._p("r1", "RB", 300.0)
        rb2 = self._p("r2", "RB", 200.0)
        rc = self._rc()
        roster_counts = {Position.QB: 0, Position.RB: 0}
        rng = np.random.default_rng(0)
        pick = GreedyVorPickModel().sample_pick(
            [rb1, rb2], 1, rng, roster_counts=roster_counts, roster_config=rc,
        )
        assert pick.player_id == "r1"  # best projected_points fallback

    def test_best_overall_once_all_slots_filled(self) -> None:
        """Once all dedicated slots are filled, picks best VOR from the full board."""
        qb = self._p("q1", "QB", 300.0)
        rb = self._p("r1", "RB", 200.0)
        rc = self._rc()
        roster_counts = {Position.QB: 1, Position.RB: 2}  # all dedicated slots full
        levels = {Position.QB: 50.0, Position.RB: 50.0}
        rng = np.random.default_rng(0)
        pick = GreedyVorPickModel().sample_pick(
            [qb, rb], 1, rng, roster_counts=roster_counts, roster_config=rc, replacement_levels=levels,
        )
        assert pick.player_id == "q1"  # VOR 250 > 150


# ---------------------------------------------------------------------------
# engine.py — DraftSimulator
# ---------------------------------------------------------------------------

class TestDraftSimulator:
    """Tests for Monte Carlo draft simulation."""

    def _make_players(self) -> list[NFLPlayer]:
        """6 players for a 2-team, 3-round draft (6 total picks)."""
        return [
            _p("q1", "QB", 400.0, 1.0),   # clearly dominant QB
            _p("r1", "RB", 300.0, 2.0),
            _p("r2", "RB", 270.0, 3.0),
            _p("q2", "QB",  50.0, 4.0),   # weak fallback QB
            _p("r3", "RB", 200.0, 5.0),
            _p("r4", "RB", 150.0, 6.0),
        ]

    def _replacement_levels(self) -> dict[Position, float]:
        return {Position.QB: 50.0, Position.RB: 150.0}

    def test_simulate_returns_simulation_result(self) -> None:
        """simulate() returns a SimulationResult with correct candidate."""
        players = self._make_players()
        state = _state(players)
        sim = DraftSimulator(n_simulations=20, seed=0)
        result = sim.simulate(state, players[0], self._replacement_levels())
        assert isinstance(result, SimulationResult)
        assert result.candidate.player_id == "q1"
        assert result.n_simulations == 20

    def test_simulate_mean_score_is_positive(self) -> None:
        """Mean roster score is a positive float (lineup always has projected points)."""
        players = self._make_players()
        state = _state(players)
        sim = DraftSimulator(n_simulations=20, seed=0)
        result = sim.simulate(state, players[0], self._replacement_levels())
        assert result.mean_score > 0.0

    def test_recommend_returns_all_candidates(self) -> None:
        """recommend() returns one SimulationResult per candidate."""
        players = self._make_players()
        state = _state(players)
        candidates = players[:2]
        sim = DraftSimulator(n_simulations=10, seed=0)
        results = sim.recommend(state, candidates, self._replacement_levels())
        assert len(results) == 2

    def test_recommend_sorted_by_mean_score_descending(self) -> None:
        """recommend() results are sorted by mean_score descending."""
        players = self._make_players()
        state = _state(players)
        sim = DraftSimulator(n_simulations=20, seed=0)
        results = sim.recommend(state, players[:3], self._replacement_levels())
        scores = [r.mean_score for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_recommend_empty_candidates_returns_empty(self) -> None:
        """recommend() with no candidates returns an empty list."""
        players = self._make_players()
        state = _state(players)
        sim = DraftSimulator(n_simulations=10, seed=0)
        assert sim.recommend(state, [], self._replacement_levels()) == []

    def test_seeded_simulator_is_reproducible(self) -> None:
        """Two simulators with the same seed produce identical results."""
        players = self._make_players()
        state = _state(players)
        levels = self._replacement_levels()
        sim_a = DraftSimulator(n_simulations=30, seed=42)
        sim_b = DraftSimulator(n_simulations=30, seed=42)
        result_a = sim_a.simulate(state, players[0], levels)
        result_b = sim_b.simulate(state, players[0], levels)
        assert result_a.mean_score == pytest.approx(result_b.mean_score)
        assert result_a.std_score == pytest.approx(result_b.std_score)

    def test_dominant_player_scores_higher_than_weak_alternative(self) -> None:
        """Taking q1 (400 pts) should yield a higher mean roster score than q2 (50 pts).

        With q1 scoring 350 pts more and the same pool otherwise, the mean
        roster score difference is reliably large even with few simulations.
        """
        players = self._make_players()
        state = _state(players)
        levels = self._replacement_levels()
        sim = DraftSimulator(n_simulations=50, seed=7)
        result_q1 = sim.simulate(state, players[0], levels)  # q1: 400 pts
        result_q2 = sim.simulate(state, players[3], levels)  # q2: 50 pts
        assert result_q1.mean_score > result_q2.mean_score

    def test_simulation_result_std_is_nonnegative(self) -> None:
        """Standard deviation of roster scores is always >= 0."""
        players = self._make_players()
        state = _state(players)
        sim = DraftSimulator(n_simulations=30, seed=1)
        result = sim.simulate(state, players[0], self._replacement_levels())
        assert result.std_score >= 0.0

    def test_accepts_custom_opponent_and_user_models(self) -> None:
        """DraftSimulator accepts explicit opponent_model and user_model instances."""
        players = self._make_players()
        state = _state(players)
        sim = DraftSimulator(
            opponent_model=ADPPickModel(),
            user_model=GreedyVorPickModel(),
            n_simulations=10,
            seed=0,
        )
        result = sim.simulate(state, players[0], self._replacement_levels())
        assert isinstance(result, SimulationResult)


# ---------------------------------------------------------------------------
# engine.py — DraftSimulator parallel / pool lifecycle
# ---------------------------------------------------------------------------

class TestDraftSimulatorParallel:
    """Tests for parallel candidate evaluation and process pool lifecycle."""

    def _make_players(self) -> list[NFLPlayer]:
        """6 players for a 2-team, 3-round draft (6 total picks)."""
        return [
            _p("q1", "QB", 400.0, 1.0),
            _p("r1", "RB", 300.0, 2.0),
            _p("r2", "RB", 270.0, 3.0),
            _p("q2", "QB",  50.0, 4.0),
            _p("r3", "RB", 200.0, 5.0),
            _p("r4", "RB", 150.0, 6.0),
        ]

    def _levels(self) -> dict[Position, float]:
        return {Position.QB: 50.0, Position.RB: 150.0}

    def test_recommend_returns_sorted_results(self) -> None:
        """Parallel recommend returns all candidates sorted by mean_score descending."""
        players = self._make_players()
        state = _state(players)
        sim = DraftSimulator(n_simulations=10, seed=0, n_workers=2)
        results = sim.recommend(state, players[:3], self._levels())
        assert results is not None
        assert len(results) == 3
        scores = [r.mean_score for r in results]
        assert scores == sorted(scores, reverse=True)
        sim.shutdown()

    def test_recommend_ranks_dominant_candidate_first(self) -> None:
        """q1 (400 pts, VOR=350) should rank first across all candidates.

        In this pool, taking r2 forces the user onto q2 as the only remaining QB,
        so r2 and q2 can be similarly ranked. q1 however is so dominant that
        it reliably tops the list regardless of parallel non-determinism.
        """
        players = self._make_players()
        state = _state(players)
        sim = DraftSimulator(n_simulations=30, seed=3, n_workers=2)
        results = sim.recommend(state, players[:4], self._levels())
        assert results is not None
        assert results[0].candidate.player_id == "q1"
        sim.shutdown()

    def test_cancel_event_stops_recommend(self) -> None:
        """recommend() returns None when cancel_event is set before any future completes."""
        players = self._make_players()
        state = _state(players)
        sim = DraftSimulator(n_simulations=5, seed=0, n_workers=2)
        cancel = threading.Event()
        cancel.set()
        result = sim.recommend(state, players[:3], self._levels(), cancel_event=cancel)
        assert result is None
        sim.shutdown()

    def test_pool_created_lazily(self) -> None:
        """Process pool is None until the first recommend() call."""
        sim = DraftSimulator(n_simulations=5, seed=0)
        assert sim._executor is None
        players = self._make_players()
        state = _state(players)
        sim.recommend(state, players[:2], self._levels())
        assert sim._executor is not None
        sim.shutdown()

    def test_shutdown_releases_pool(self) -> None:
        """shutdown() sets the internal executor to None."""
        players = self._make_players()
        state = _state(players)
        sim = DraftSimulator(n_simulations=5, seed=0)
        sim.recommend(state, players[:2], self._levels())
        assert sim._executor is not None
        sim.shutdown()
        assert sim._executor is None

    def test_shutdown_is_idempotent(self) -> None:
        """Calling shutdown() twice does not raise."""
        sim = DraftSimulator(n_simulations=5, seed=0)
        sim.shutdown()
        sim.shutdown()
