"""Tests for ffb/simulation/snapshot.py — SimSnapshot construction and layout."""
import numpy as np
import pytest
from gridiron_yampylytics.ffb.models.draft import DraftState
from gridiron_yampylytics.ffb.models.league import League, RosterConfig
from gridiron_yampylytics.ffb.models.manager import Manager
from gridiron_yampylytics.ffb.models.player import NFLPlayer, Position
from gridiron_yampylytics.ffb.simulation.snapshot import POSITION_INDEX, SimSnapshot


def _p(pid: str, pos: str, pts: float, adp: float, std: float = 2.0) -> NFLPlayer:
    return NFLPlayer(player_id=pid, name=pid, position=Position(pos), team="KC",
                     projected_points=pts, adp=adp, adp_std=std)


def _state_with_picks(
    available: list[NFLPlayer],
    user_picks: list[NFLPlayer] | None = None,
    opp_picks: list[NFLPlayer] | None = None,
) -> DraftState:
    """2 teams, 4 rounds (qb=1, rb=1, flex=1, bench=1); user at slot 1."""
    rc = RosterConfig(qb=1, rb=1, wr=0, te=0, flex=1, k=0, def_=0, bench=1)
    league = League(team_count=2, roster=rc)
    managers = [
        Manager(manager_id="user", name="User", draft_slot=1, is_user=True),
        Manager(manager_id="opp", name="Opp", draft_slot=2, is_user=False),
    ]
    state = DraftState.new(league=league, managers=managers, available_players=available)
    for p in (user_picks or []):
        state = state.apply_pick(p)  # pick 1 = user
    for p in (opp_picks or []):
        state = state.apply_pick(p)  # pick 2 = opp
    return state


def _repl() -> dict[Position, float]:
    return {Position.QB: 50.0, Position.RB: 100.0, Position.WR: 80.0,
            Position.TE: 60.0, Position.K: 30.0, Position.DEF: 20.0}


class TestSimSnapshotArrayShapes:
    def test_player_arrays_cover_available_plus_user_existing(self) -> None:
        q1 = _p("q1", "QB", 300, 1.0)
        r1 = _p("r1", "RB", 200, 2.0)
        r2 = _p("r2", "RB", 150, 3.0)
        available = [q1, r1, r2]
        state = _state_with_picks(available)
        snap = SimSnapshot.from_draft_state(state, q1, _repl())
        assert snap.player_adps.shape == (3,)
        assert snap.player_points.shape == (3,)
        assert snap.player_positions.shape == (3,)

    def test_existing_user_picks_extend_array(self) -> None:
        q1 = _p("q1", "QB", 300, 1.0)
        r1 = _p("r1", "RB", 200, 2.0)
        r2 = _p("r2", "RB", 150, 3.0)
        r3 = _p("r3", "RB", 100, 4.0)
        # User already picked q1 at pick 1 (slot 1).
        state = _state_with_picks([r1, r2, r3], user_picks=[q1])
        # Advance opp pick so it's user's turn again.
        # (After pick 1=user, pick 2=opp. Apply opp pick r1.)
        state = state.apply_pick(r1)
        # Now available = [r2, r3], user_existing = [q1]
        snap = SimSnapshot.from_draft_state(state, r2, _repl())
        # N = 2 available + 1 user existing = 3
        assert snap.player_adps.shape == (3,)

    def test_roster_counts_shape_matches_managers_times_positions(self) -> None:
        available = [_p("q1", "QB", 300, 1.0), _p("r1", "RB", 200, 2.0)]
        state = _state_with_picks(available)
        snap = SimSnapshot.from_draft_state(state, available[0], _repl())
        assert snap.roster_counts_init.shape == (2, len(Position))

    def test_pick_sequence_length_matches_remaining_picks(self) -> None:
        available = [_p(f"p{i}", "RB", 100 - i * 5, float(i + 1)) for i in range(8)]
        state = _state_with_picks(available)
        snap = SimSnapshot.from_draft_state(state, available[0], _repl())
        remaining = state.total_picks - state.current_pick
        assert snap.pick_manager_idxs.shape == (remaining,)
        assert snap.pick_is_user.shape == (remaining,)


class TestSimSnapshotMasks:
    def test_available_mask_true_for_available_players(self) -> None:
        q1 = _p("q1", "QB", 300, 1.0)
        r1 = _p("r1", "RB", 200, 2.0)
        available = [q1, r1]
        state = _state_with_picks(available)
        snap = SimSnapshot.from_draft_state(state, q1, _repl())
        assert snap.available_mask[:2].all()

    def test_available_mask_false_for_user_existing(self) -> None:
        q1 = _p("q1", "QB", 300, 1.0)
        r1 = _p("r1", "RB", 200, 2.0)
        r2 = _p("r2", "RB", 150, 3.0)
        r3 = _p("r3", "RB", 100, 4.0)
        state = _state_with_picks([r1, r2, r3], user_picks=[q1])
        state = state.apply_pick(r1)
        snap = SimSnapshot.from_draft_state(state, r2, _repl())
        assert not snap.available_mask[2:].any()

    def test_user_initial_mask_covers_existing_roster(self) -> None:
        q1 = _p("q1", "QB", 300, 1.0)
        r1 = _p("r1", "RB", 200, 2.0)
        r2 = _p("r2", "RB", 150, 3.0)
        r3 = _p("r3", "RB", 100, 4.0)
        state = _state_with_picks([r1, r2, r3], user_picks=[q1])
        state = state.apply_pick(r1)
        snap = SimSnapshot.from_draft_state(state, r2, _repl())
        # q1 is the only user existing pick; it's at index 2 (after [r2, r3])
        assert snap.user_initial_mask[2]
        assert not snap.user_initial_mask[:2].any()

    def test_candidate_idx_resolves_correctly(self) -> None:
        q1 = _p("q1", "QB", 300, 1.0)
        r1 = _p("r1", "RB", 200, 2.0)
        available = [q1, r1]
        state = _state_with_picks(available)
        snap = SimSnapshot.from_draft_state(state, r1, _repl())
        assert snap.player_adps[snap.candidate_idx] == r1.adp
        assert snap.player_positions[snap.candidate_idx] == POSITION_INDEX[Position.RB]


class TestSimSnapshotPickSequence:
    def test_first_pick_belongs_to_user_slot_1(self) -> None:
        """In a 2-team draft at pick 1, the first *remaining* pick after the
        candidate is taken should be pick 2 = opponent (slot 2)."""
        available = [_p(f"p{i}", "RB", 100.0, float(i + 1)) for i in range(8)]
        state = _state_with_picks(available)
        # current_pick=1; after candidate, next remaining picks are 2..8
        snap = SimSnapshot.from_draft_state(state, available[0], _repl())
        # pick 2 in a 2-team snake = slot 2 = opponent
        assert not snap.pick_is_user[0]

    def test_snake_reversal_at_round_boundary(self) -> None:
        """Round 1 picks: user(1), opp(2). Round 2 snake: opp(3), user(4)."""
        available = [_p(f"p{i}", "RB", 100.0, float(i + 1)) for i in range(8)]
        state = _state_with_picks(available)
        snap = SimSnapshot.from_draft_state(state, available[0], _repl())
        # pick_manager_idxs[0] = pick 2 (opp), [1] = pick 3 (opp, snake round 2 first)
        # [2] = pick 4 (user, snake round 2 second)
        assert not snap.pick_is_user[0]   # pick 2: opp
        assert not snap.pick_is_user[1]   # pick 3: opp (round 2, slot 2 picks first)
        assert snap.pick_is_user[2]        # pick 4: user (round 2, slot 1 picks second)

    def test_picks_until_next_user_correct_in_snake(self) -> None:
        """2-team, 4-round snake from pick 1.  Remaining pick_is_user: [F,F,T,T,F,F,T].
        picks_until_next_user[i] = argmax(pick_is_user[i+1:]) = gap to next user pick."""
        available = [_p(f"p{i}", "RB", 100.0, float(i + 1)) for i in range(8)]
        state = _state_with_picks(available)
        snap = SimSnapshot.from_draft_state(state, available[0], _repl())
        # index 0 (opp): future=[F,T,T,F,F,T] → argmax=1 → 1 pick before next user
        assert snap.picks_until_next_user[0] == 1
        # index 2 (user): future=[T,F,F,T] → argmax=0 → next pick is also user
        assert snap.picks_until_next_user[2] == 0
        # index 3 (user): future=[F,F,T] → argmax=2 → 2 opp picks before next user
        assert snap.picks_until_next_user[3] == 2

    def test_roster_counts_init_reflects_existing_picks(self) -> None:
        q1 = _p("q1", "QB", 300, 1.0)
        r1 = _p("r1", "RB", 200, 2.0)
        r2 = _p("r2", "RB", 150, 3.0)
        r3 = _p("r3", "RB", 100, 4.0)
        state = _state_with_picks([r1, r2, r3], user_picks=[q1])
        state = state.apply_pick(r1)
        snap = SimSnapshot.from_draft_state(state, r2, _repl())
        qb_idx = POSITION_INDEX[Position.QB]
        rb_idx = POSITION_INDEX[Position.RB]
        # user (manager idx determined by sorted draft slot)
        user_idx = snap.user_manager_idx
        assert snap.roster_counts_init[user_idx, qb_idx] == 1  # user has q1
        opp_idx = 1 - user_idx
        assert snap.roster_counts_init[opp_idx, rb_idx] == 1  # opp has r1


class TestSimSnapshotConfig:
    def test_roster_slots_match_config(self) -> None:
        available = [_p("q1", "QB", 300, 1.0)]
        state = _state_with_picks(available)
        snap = SimSnapshot.from_draft_state(state, available[0], _repl())
        qb_idx = POSITION_INDEX[Position.QB]
        rb_idx = POSITION_INDEX[Position.RB]
        assert snap.roster_slots[qb_idx] == 1
        assert snap.roster_slots[rb_idx] == 1

    def test_replacement_levels_ordered_by_position_index(self) -> None:
        available = [_p("q1", "QB", 300, 1.0)]
        state = _state_with_picks(available)
        repl = _repl()
        snap = SimSnapshot.from_draft_state(state, available[0], repl)
        for pos, idx in POSITION_INDEX.items():
            assert snap.replacement_levels[idx] == pytest.approx(repl.get(pos, 0.0))
