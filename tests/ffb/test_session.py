"""Tests for ffb/session.py — DraftSession orchestrator."""
from unittest.mock import MagicMock
import pytest
from gridiron_yampylytics.ffb.data.sleeper import SleeperPick, build_player_index
from gridiron_yampylytics.ffb.models.draft import DraftState
from gridiron_yampylytics.ffb.models.league import League, RosterConfig
from gridiron_yampylytics.ffb.models.manager import Manager
from gridiron_yampylytics.ffb.models.player import NFLPlayer, Position
from gridiron_yampylytics.ffb.scoring.vor import compute_replacement_levels
from gridiron_yampylytics.ffb.session import DraftSession
from gridiron_yampylytics.ffb.simulation.engine import DraftSimulator, SimulationResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _p(pid: str, pos: str, pts: float, adp: float, sleeper_id: str | None = None) -> NFLPlayer:
    return NFLPlayer(
        player_id=pid, name=pid, position=Position(pos), team="KC",
        projected_points=pts, adp=adp, sleeper_id=sleeper_id,
    )


def _sleeper_pick(
    player_id: str = "s1",
    position: str = "QB",
    team: str = "KC",
    pick_no: int = 1,
    draft_slot: int = 1,
) -> SleeperPick:
    return SleeperPick(
        pick_no=pick_no, round=1, draft_slot=draft_slot,
        picked_by="user", player_id=player_id, position=position, team=team,
        is_dst=(position == "DEF"),
    )


def _make_session(players: list[NFLPlayer], user_slot: int = 1) -> DraftSession:
    """Build a minimal 2-team, 3-round DraftSession with the given player pool."""
    rc = RosterConfig(qb=1, rb=1, wr=0, te=0, flex=0, k=0, def_=0, bench=1)
    league = League(team_count=2, roster=rc)
    managers = [
        Manager(manager_id="user", name="User", draft_slot=user_slot, is_user=True),
        Manager(manager_id="opp", name="Opp", draft_slot=2 if user_slot == 1 else 1, is_user=False),
    ]
    state = DraftState.new(league=league, managers=managers, available_players=players)
    player_index = build_player_index(players)
    replacement_levels = compute_replacement_levels(players, rc, league.team_count)
    return DraftSession(
        initial_state=state,
        player_index=player_index,
        replacement_levels=replacement_levels,
        simulator=DraftSimulator(n_simulations=5, seed=0),
    )


# ---------------------------------------------------------------------------
# process_pick — state advancement
# ---------------------------------------------------------------------------

class TestDraftSessionProcessPick:
    """Tests for DraftSession.process_pick."""

    def test_returns_resolved_player(self) -> None:
        """process_pick returns the NFLPlayer from the pool when known."""
        qb = _p("yid_q", "QB", 300.0, 1.0, sleeper_id="s_qb")
        rb = _p("yid_r", "RB", 200.0, 2.0, sleeper_id="s_rb")
        session = _make_session([qb, rb])
        result = session.process_pick(_sleeper_pick(player_id="s_qb", position="QB"))
        assert result.player_id == "yid_q"

    def test_state_advances_after_pick(self) -> None:
        """process_pick advances current_pick by 1."""
        qb = _p("yid_q", "QB", 300.0, 1.0, sleeper_id="s_qb")
        rb = _p("yid_r", "RB", 200.0, 2.0, sleeper_id="s_rb")
        session = _make_session([qb, rb])
        assert session.state.current_pick == 1
        session.process_pick(_sleeper_pick(player_id="s_qb", position="QB"))
        assert session.state.current_pick == 2

    def test_player_removed_from_available(self) -> None:
        """process_pick removes the drafted player from available_players."""
        qb = _p("yid_q", "QB", 300.0, 1.0, sleeper_id="s_qb")
        rb = _p("yid_r", "RB", 200.0, 2.0, sleeper_id="s_rb")
        session = _make_session([qb, rb])
        session.process_pick(_sleeper_pick(player_id="s_qb", position="QB"))
        available_ids = {p.player_id for p in session.state.available_players}
        assert "yid_q" not in available_ids
        assert "yid_r" in available_ids

    def test_unknown_player_creates_placeholder(self) -> None:
        """process_pick with a player not in the index returns a placeholder."""
        qb = _p("yid_q", "QB", 300.0, 1.0, sleeper_id="s_qb")
        session = _make_session([qb])
        result = session.process_pick(_sleeper_pick(player_id="unknown_id", position="RB"))
        assert result.player_id.startswith("unknown_")
        assert result.projected_points == 0.0

    def test_placeholder_still_advances_pick(self) -> None:
        """Placeholder picks still advance current_pick."""
        qb = _p("yid_q", "QB", 300.0, 1.0, sleeper_id="s_qb")
        session = _make_session([qb])
        session.process_pick(_sleeper_pick(player_id="mystery", position="WR"))
        assert session.state.current_pick == 2

    def test_placeholder_invalid_position_defaults_to_qb(self) -> None:
        """Placeholder with unrecognised position string defaults to QB."""
        session = _make_session([_p("yid_q", "QB", 300.0, 1.0)])
        result = session.process_pick(_sleeper_pick(player_id="x", position="PUNTER"))
        assert result.position == Position.QB

    def test_dst_pick_resolved_by_team(self) -> None:
        """DST picks are resolved via the DST_{team} synthetic key."""
        dst = _p("DST_KC", "DEF", 100.0, 15.0, sleeper_id=None)
        session = _make_session([dst, _p("q1", "QB", 300.0, 1.0, sleeper_id="s_q")])
        result = session.process_pick(_sleeper_pick(player_id="irrelevant", position="DEF", team="KC"))
        assert result.player_id == "DST_KC"


# ---------------------------------------------------------------------------
# is_user_turn and is_complete
# ---------------------------------------------------------------------------

class TestDraftSessionTurnProperties:
    """Tests for is_user_turn and is_complete."""

    def test_is_user_turn_true_at_user_slot(self) -> None:
        """is_user_turn is True when the current pick belongs to the user."""
        players = [_p(f"p{i}", "QB", 300.0 - i, float(i), sleeper_id=f"s{i}") for i in range(6)]
        session = _make_session(players, user_slot=1)
        assert session.is_user_turn is True  # pick 1, user is at slot 1

    def test_is_user_turn_false_at_opponent_slot(self) -> None:
        """is_user_turn is False when it's the opponent's pick."""
        players = [_p(f"p{i}", "QB", 300.0 - i, float(i), sleeper_id=f"s{i}") for i in range(6)]
        session = _make_session(players, user_slot=2)
        assert session.is_user_turn is False  # pick 1, user is at slot 2

    def test_is_user_turn_changes_after_user_picks(self) -> None:
        """is_user_turn becomes False after user makes their pick."""
        players = [_p(f"p{i}", "QB", 300.0 - i, float(i), sleeper_id=f"s{i}") for i in range(6)]
        session = _make_session(players, user_slot=1)
        assert session.is_user_turn is True
        session.process_pick(_sleeper_pick(player_id="s0", position="QB", pick_no=1, draft_slot=1))
        assert session.is_user_turn is False  # now opponent's turn (slot 2)

    def test_is_complete_false_during_draft(self) -> None:
        """is_complete is False while picks remain."""
        players = [_p(f"p{i}", "QB", 300.0 - i, float(i), sleeper_id=f"s{i}") for i in range(6)]
        session = _make_session(players)
        assert session.is_complete is False

    def test_is_complete_true_after_all_picks(self) -> None:
        """is_complete is True once all 6 picks in a 2-team, 3-round draft are applied."""
        players = [_p(f"p{i}", "QB", 300.0 - i, float(i), sleeper_id=f"s{i}") for i in range(6)]
        session = _make_session(players)
        for i, player in enumerate(players):
            pick_no = i + 1
            slot = (i % 2) + 1 if (i // 2) % 2 == 0 else (2 - i % 2)
            session.process_pick(_sleeper_pick(
                player_id=f"s{i}", position="QB", pick_no=pick_no, draft_slot=slot,
            ))
        assert session.is_complete is True


# ---------------------------------------------------------------------------
# get_recommendations
# ---------------------------------------------------------------------------

class TestDraftSessionGetRecommendations:
    """Tests for DraftSession.get_recommendations."""

    def _session_at_user_turn(self) -> DraftSession:
        players = [
            _p("q1", "QB", 400.0, 1.0, sleeper_id="s_q1"),
            _p("r1", "RB", 300.0, 2.0, sleeper_id="s_r1"),
            _p("r2", "RB", 270.0, 3.0, sleeper_id="s_r2"),
            _p("q2", "QB",  50.0, 4.0, sleeper_id="s_q2"),
            _p("r3", "RB", 200.0, 5.0, sleeper_id="s_r3"),
            _p("r4", "RB", 150.0, 6.0, sleeper_id="s_r4"),
        ]
        return _make_session(players, user_slot=1)

    def test_returns_simulation_results(self) -> None:
        """get_recommendations returns a non-empty list of SimulationResults."""
        session = self._session_at_user_turn()
        results = session.get_recommendations()
        assert len(results) > 0
        assert all(isinstance(r, SimulationResult) for r in results)

    def test_results_sorted_by_mean_score_descending(self) -> None:
        """get_recommendations results are sorted by mean_score descending."""
        session = self._session_at_user_turn()
        results = session.get_recommendations()
        scores = [r.mean_score for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_respects_n_candidates_limit(self) -> None:
        """At most n_candidates players are simulated (one simulate() call each)."""
        players = [_p(f"p{i}", "QB", 300.0 - i, float(i + 1), sleeper_id=f"s{i}") for i in range(6)]
        rc = RosterConfig(qb=1, rb=0, wr=0, te=0, flex=0, k=0, def_=0, bench=1)
        league = League(team_count=2, roster=rc)
        managers = [
            Manager(manager_id="user", name="User", draft_slot=1, is_user=True),
            Manager(manager_id="opp", name="Opp", draft_slot=2, is_user=False),
        ]
        state = DraftState.new(league=league, managers=managers, available_players=players)
        replacement_levels = compute_replacement_levels(players, rc, 2)
        mock_sim = MagicMock(spec=DraftSimulator)
        mock_sim.simulate.return_value = SimulationResult(
            candidate=players[0], mean_score=100.0, std_score=5.0, n_simulations=5,
        )
        session = DraftSession(
            initial_state=state,
            player_index=build_player_index(players),
            replacement_levels=replacement_levels,
            simulator=mock_sim,
            n_candidates=3,
        )
        session.get_recommendations()
        assert mock_sim.simulate.call_count <= 3

    def test_empty_available_returns_empty(self) -> None:
        """get_recommendations returns [] when no players remain."""
        rc = RosterConfig(qb=1, rb=0, wr=0, te=0, flex=0, k=0, def_=0, bench=0)
        league = League(team_count=2, roster=rc)
        managers = [
            Manager(manager_id="user", name="User", draft_slot=1, is_user=True),
            Manager(manager_id="opp", name="Opp", draft_slot=2, is_user=False),
        ]
        state = DraftState.new(league=league, managers=managers, available_players=[])
        session = DraftSession(
            initial_state=state,
            player_index={},
            replacement_levels={},
            simulator=DraftSimulator(n_simulations=5, seed=0),
        )
        assert session.get_recommendations() == []
