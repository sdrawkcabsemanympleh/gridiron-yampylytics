"""Unit tests for YampGM data models.

Covers NFLPlayer, Manager, ScoringConfig, RosterConfig, League,
Roster, DraftPick, and DraftState.
"""
import pytest
from pydantic import ValidationError
from gridiron_yampylytics.ffb.models.draft import DraftPick, DraftState, Roster
from gridiron_yampylytics.ffb.models.league import League, RosterConfig, ScoringConfig, ScoringType
from gridiron_yampylytics.ffb.models.manager import Manager
from gridiron_yampylytics.ffb.models.player import NFLPlayer, Position


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def standard_league() -> League:
    """A default 12-team PPR league with standard roster configuration.

    :return: League with default settings.
    """
    return League(team_count=12)


@pytest.fixture()
def two_team_league() -> League:
    """A minimal 2-team league for testing draft order math.

    :return: League with team_count=2 and 2-round roster (1 starter, 1 bench).
    """
    return League(
        team_count=2,
        roster=RosterConfig(qb=0, rb=0, wr=0, te=0, flex=0, k=0, def_=0, bench=1),
    )


@pytest.fixture()
def user_manager() -> Manager:
    """A manager representing the tool's user at draft slot 1.

    :return: Manager with is_user=True.
    """
    return Manager(manager_id="user_1", name="Yamp", draft_slot=1, is_user=True)


@pytest.fixture()
def opponent_manager() -> Manager:
    """A manager representing an opponent at draft slot 2.

    :return: Manager with is_user=False.
    """
    return Manager(manager_id="opp_1", name="Opponent", draft_slot=2, is_user=False)


@pytest.fixture()
def rb_player() -> NFLPlayer:
    """A standard RB player (single position).

    :return: NFLPlayer at RB with no multi-eligibility.
    """
    return NFLPlayer(
        player_id="p_rb",
        name="Standard RB",
        position=Position.RB,
        team="KC",
        projected_points=200.0,
        adp=5.0,
    )


@pytest.fixture()
def multi_position_player() -> NFLPlayer:
    """An RB/WR eligible player (CMC-type).

    :return: NFLPlayer with primary RB and WR in eligible_positions.
    """
    return NFLPlayer(
        player_id="p_flex",
        name="CMC Type",
        position=Position.RB,
        eligible_positions={Position.RB, Position.WR},
        team="SF",
        projected_points=280.0,
        adp=1.2,
    )


@pytest.fixture()
def wr_player() -> NFLPlayer:
    """A standard WR player (single position).

    :return: NFLPlayer at WR.
    """
    return NFLPlayer(
        player_id="p_wr",
        name="Standard WR",
        position=Position.WR,
        team="MIN",
        projected_points=220.0,
        adp=3.5,
    )


# ---------------------------------------------------------------------------
# NFLPlayer
# ---------------------------------------------------------------------------

class TestNFLPlayer:
    """Tests for NFLPlayer model."""

    def test_basic_creation(self, rb_player: NFLPlayer) -> None:
        """NFLPlayer creates successfully with required fields.

        :param rb_player: Standard RB fixture.
        """
        assert rb_player.name == "Standard RB"
        assert rb_player.position == Position.RB
        assert rb_player.team == "KC"

    def test_primary_position_auto_added_to_eligible(self, rb_player: NFLPlayer) -> None:
        """Primary position is always included in eligible_positions.

        :param rb_player: RB player with no explicit eligible_positions.
        """
        assert Position.RB in rb_player.eligible_positions

    def test_eligible_positions_default_is_primary_only(self, rb_player: NFLPlayer) -> None:
        """eligible_positions defaults to just the primary position.

        :param rb_player: RB player with no explicit eligible_positions.
        """
        assert rb_player.eligible_positions == {Position.RB}

    def test_multi_position_player_retains_both(self, multi_position_player: NFLPlayer) -> None:
        """Multi-eligible player has both positions in eligible_positions.

        :param multi_position_player: RB/WR eligible fixture.
        """
        assert Position.RB in multi_position_player.eligible_positions
        assert Position.WR in multi_position_player.eligible_positions

    def test_primary_position_added_even_if_omitted_from_eligible(self) -> None:
        """Primary position added to eligible_positions even if not explicitly set.

        Validator ensures eligible_positions always includes position.
        """
        player = NFLPlayer(
            player_id="p1", name="Test", position=Position.TE,
            eligible_positions={Position.WR},  # TE omitted but should be auto-added
            team="KC", projected_points=150.0, adp=20.0,
        )
        assert Position.TE in player.eligible_positions
        assert Position.WR in player.eligible_positions

    def test_adp_std_defaults_to_five(self, rb_player: NFLPlayer) -> None:
        """adp_std defaults to 5.0 when not provided.

        :param rb_player: RB player with no explicit adp_std.
        """
        assert rb_player.adp_std == 5.0

    def test_optional_fields_default_to_none(self, rb_player: NFLPlayer) -> None:
        """bye_week, ecr_rank, and injury_status default to None.

        :param rb_player: RB player without optional fields.
        """
        assert rb_player.bye_week is None
        assert rb_player.ecr_rank is None
        assert rb_player.injury_status is None

    def test_adp_std_cannot_be_negative(self) -> None:
        """adp_std must be >= 0.

        Negative ADP standard deviation is nonsensical.
        """
        with pytest.raises(ValidationError):
            NFLPlayer(
                player_id="p1", name="Test", position=Position.QB,
                team="BUF", projected_points=300.0, adp=10.0, adp_std=-1.0,
            )


# ---------------------------------------------------------------------------
# Manager
# ---------------------------------------------------------------------------

class TestManager:
    """Tests for Manager model."""

    def test_basic_creation(self, user_manager: Manager) -> None:
        """Manager creates with expected fields.

        :param user_manager: User manager fixture.
        """
        assert user_manager.name == "Yamp"
        assert user_manager.draft_slot == 1
        assert user_manager.is_user is True

    def test_is_user_defaults_to_false(self, opponent_manager: Manager) -> None:
        """is_user defaults to False.

        :param opponent_manager: Opponent manager fixture.
        """
        assert opponent_manager.is_user is False

    def test_draft_slot_must_be_at_least_one(self) -> None:
        """draft_slot must be >= 1 (1-indexed).

        Slot 0 is not a valid position in a draft.
        """
        with pytest.raises(ValidationError):
            Manager(manager_id="m1", name="Bad", draft_slot=0)


# ---------------------------------------------------------------------------
# ScoringConfig
# ---------------------------------------------------------------------------

class TestScoringConfig:
    """Tests for ScoringConfig model and classmethods."""

    def test_default_is_ppr(self) -> None:
        """Default ScoringConfig is full PPR."""
        config = ScoringConfig()
        assert config.scoring_type == ScoringType.PPR
        assert config.reception == 1.0

    def test_ppr_classmethod(self) -> None:
        """ScoringConfig.ppr() produces 1.0 reception value."""
        config = ScoringConfig.ppr()
        assert config.reception == 1.0
        assert config.scoring_type == ScoringType.PPR

    def test_half_ppr_classmethod(self) -> None:
        """ScoringConfig.half_ppr() produces 0.5 reception value."""
        config = ScoringConfig.half_ppr()
        assert config.reception == 0.5
        assert config.scoring_type == ScoringType.HALF_PPR

    def test_standard_classmethod(self) -> None:
        """ScoringConfig.standard() produces 0.0 reception value."""
        config = ScoringConfig.standard()
        assert config.reception == 0.0
        assert config.scoring_type == ScoringType.STANDARD

    def test_passing_yards_per_point_cannot_be_zero(self) -> None:
        """passing_yards_per_point must be > 0.

        Zero would cause division-by-zero in scoring calculations.
        """
        with pytest.raises(ValidationError):
            ScoringConfig(passing_yards_per_point=0.0)


# ---------------------------------------------------------------------------
# RosterConfig
# ---------------------------------------------------------------------------

class TestRosterConfig:
    """Tests for RosterConfig model and computed properties."""

    def test_default_total_starters(self) -> None:
        """Default RosterConfig has 10 starters (1 QB, 2 RB, 3 WR, 1 TE, 1 FLEX, 1 K, 1 DEF)."""
        config = RosterConfig()
        assert config.total_starters == 10

    def test_default_total_spots(self) -> None:
        """Default total_spots = 10 starters + 6 bench = 16."""
        config = RosterConfig()
        assert config.total_spots == 16

    def test_total_spots_excludes_ir(self) -> None:
        """IR slots do not count toward total_spots (which determines draft rounds).

        A league with IR slots drafts the same number of rounds as one without.
        """
        config_no_ir = RosterConfig(ir_slots=0)
        config_with_ir = RosterConfig(ir_slots=2)
        assert config_no_ir.total_spots == config_with_ir.total_spots

    def test_total_capacity_includes_ir(self) -> None:
        """total_capacity = total_spots + ir_slots.

        Reflects maximum players a manager can hold including IR.
        """
        config = RosterConfig(ir_slots=2)
        assert config.total_capacity == config.total_spots + 2

    def test_total_rounds_equals_total_spots(self) -> None:
        """total_rounds matches total_spots since IR is excluded from drafting."""
        config = RosterConfig(ir_slots=3)
        assert config.total_rounds == config.total_spots

    def test_flex_eligible_defaults(self) -> None:
        """Default flex_eligible is RB, WR, TE."""
        config = RosterConfig()
        assert Position.RB in config.flex_eligible
        assert Position.WR in config.flex_eligible
        assert Position.TE in config.flex_eligible
        assert Position.QB not in config.flex_eligible

    def test_ir_slots_cannot_be_negative(self) -> None:
        """ir_slots must be >= 0."""
        with pytest.raises(ValidationError):
            RosterConfig(ir_slots=-1)


# ---------------------------------------------------------------------------
# League
# ---------------------------------------------------------------------------

class TestLeague:
    """Tests for League model."""

    def test_default_creation(self, standard_league: League) -> None:
        """League creates with expected defaults.

        :param standard_league: 12-team PPR league fixture.
        """
        assert standard_league.team_count == 12
        assert standard_league.draft_type == "snake"

    def test_team_count_minimum_is_two(self) -> None:
        """team_count must be >= 2 (a draft needs at least 2 teams)."""
        with pytest.raises(ValidationError):
            League(team_count=1)

    def test_zero_roster_spots_raises(self) -> None:
        """A league with zero total roster spots is invalid."""
        with pytest.raises(ValidationError):
            League(roster=RosterConfig(qb=0, rb=0, wr=0, te=0, flex=0, k=0, def_=0, bench=0))


# ---------------------------------------------------------------------------
# Roster
# ---------------------------------------------------------------------------

class TestRoster:
    """Tests for Roster model."""

    def test_players_at_position(
        self, user_manager: Manager, rb_player: NFLPlayer, wr_player: NFLPlayer
    ) -> None:
        """players_at_position returns only players matching that position.

        :param user_manager: Manager fixture.
        :param rb_player: RB player fixture.
        :param wr_player: WR player fixture.
        """
        roster = Roster(manager=user_manager, players=[rb_player, wr_player])
        assert roster.players_at_position(Position.RB) == [rb_player]
        assert roster.players_at_position(Position.WR) == [wr_player]
        assert roster.players_at_position(Position.TE) == []

    def test_count_at_position(
        self, user_manager: Manager, rb_player: NFLPlayer, multi_position_player: NFLPlayer
    ) -> None:
        """count_at_position counts by primary position only.

        :param user_manager: Manager fixture.
        :param rb_player: RB fixture.
        :param multi_position_player: RB/WR eligible fixture (primary=RB).
        """
        roster = Roster(manager=user_manager, players=[rb_player, multi_position_player])
        assert roster.count_at_position(Position.RB) == 2  # both are primary RB
        assert roster.count_at_position(Position.WR) == 0

    def test_is_full_when_at_capacity(self, user_manager: Manager, rb_player: NFLPlayer) -> None:
        """is_full returns True when players count reaches total_spots.

        :param user_manager: Manager fixture.
        :param rb_player: Player to fill the roster.
        """
        tiny_config = RosterConfig(qb=0, rb=1, wr=0, te=0, flex=0, k=0, def_=0, bench=0)
        roster = Roster(manager=user_manager, players=[rb_player])
        assert roster.is_full(tiny_config) is True

    def test_is_full_false_when_space_remains(
        self, user_manager: Manager, rb_player: NFLPlayer
    ) -> None:
        """is_full returns False when spots remain.

        :param user_manager: Manager fixture.
        :param rb_player: One player on a 2-spot roster.
        """
        config = RosterConfig(qb=0, rb=2, wr=0, te=0, flex=0, k=0, def_=0, bench=0)
        roster = Roster(manager=user_manager, players=[rb_player])
        assert roster.is_full(config) is False

    def test_is_full_ignores_ir_slots(
        self, user_manager: Manager, rb_player: NFLPlayer
    ) -> None:
        """is_full uses total_spots (excludes IR), not total_capacity.

        A roster at total_spots is full for drafting purposes even if IR
        slots are still available.

        :param user_manager: Manager fixture.
        :param rb_player: Player on a 1-spot roster with 2 IR slots.
        """
        config = RosterConfig(qb=0, rb=1, wr=0, te=0, flex=0, k=0, def_=0, bench=0, ir_slots=2)
        roster = Roster(manager=user_manager, players=[rb_player])
        assert roster.is_full(config) is True


# ---------------------------------------------------------------------------
# DraftState — construction and validation
# ---------------------------------------------------------------------------

class TestDraftStateConstruction:
    """Tests for DraftState construction, validation, and the new() factory."""

    def test_new_factory_creates_empty_rosters(
        self,
        two_team_league: League,
        user_manager: Manager,
        opponent_manager: Manager,
        rb_player: NFLPlayer,
    ) -> None:
        """DraftState.new() produces empty rosters for all managers.

        :param two_team_league: 2-team league fixture.
        :param user_manager: User at slot 1.
        :param opponent_manager: Opponent at slot 2.
        :param rb_player: Player in the available pool.
        """
        state = DraftState.new(
            league=two_team_league,
            managers=[user_manager, opponent_manager],
            available_players=[rb_player],
        )
        assert state.rosters[user_manager.manager_id].players == []
        assert state.rosters[opponent_manager.manager_id].players == []

    def test_new_factory_starts_at_pick_one(
        self,
        two_team_league: League,
        user_manager: Manager,
        opponent_manager: Manager,
    ) -> None:
        """DraftState.new() sets current_pick to 1.

        :param two_team_league: 2-team league fixture.
        :param user_manager: User manager fixture.
        :param opponent_manager: Opponent manager fixture.
        """
        state = DraftState.new(
            league=two_team_league,
            managers=[user_manager, opponent_manager],
            available_players=[],
        )
        assert state.current_pick == 1

    def test_wrong_manager_count_raises(
        self, two_team_league: League, user_manager: Manager
    ) -> None:
        """Validator raises if manager count doesn't match league team_count.

        :param two_team_league: 2-team league (expects exactly 2 managers).
        :param user_manager: Only one manager provided — should fail.
        """
        with pytest.raises(ValidationError, match="managers"):
            DraftState.new(
                league=two_team_league,
                managers=[user_manager],
                available_players=[],
            )

    def test_no_user_manager_raises(
        self, two_team_league: League, opponent_manager: Manager
    ) -> None:
        """Validator raises if no manager has is_user=True.

        :param two_team_league: 2-team league fixture.
        :param opponent_manager: Non-user manager.
        """
        second_opponent = Manager(manager_id="opp_2", name="Also Opponent", draft_slot=1)
        with pytest.raises(ValidationError, match="is_user"):
            DraftState.new(
                league=two_team_league,
                managers=[second_opponent, opponent_manager],
                available_players=[],
            )

    def test_two_user_managers_raises(
        self, two_team_league: League, user_manager: Manager
    ) -> None:
        """Validator raises if more than one manager has is_user=True.

        :param two_team_league: 2-team league fixture.
        :param user_manager: User manager at slot 1.
        """
        second_user = Manager(manager_id="u2", name="Also User", draft_slot=2, is_user=True)
        with pytest.raises(ValidationError, match="is_user"):
            DraftState.new(
                league=two_team_league,
                managers=[user_manager, second_user],
                available_players=[],
            )


# ---------------------------------------------------------------------------
# DraftState — computed properties and snake order
# ---------------------------------------------------------------------------

class TestDraftStateProperties:
    """Tests for DraftState computed properties."""

    @pytest.fixture()
    def twelve_team_state(self) -> DraftState:
        """A 12-team DraftState at pick 1 for testing snake order.

        :return: DraftState with 12 managers at slots 1–12, user at slot 3.
        """
        league = League(team_count=12)
        managers = [
            Manager(manager_id=f"m{i}", name=f"Manager {i}", draft_slot=i, is_user=(i == 3))
            for i in range(1, 13)
        ]
        return DraftState.new(league=league, managers=managers, available_players=[])

    def test_current_round_at_pick_one(self, twelve_team_state: DraftState) -> None:
        """current_round is 1 at pick 1.

        :param twelve_team_state: 12-team state fixture.
        """
        assert twelve_team_state.current_round == 1

    def test_current_round_advances_correctly(self, twelve_team_state: DraftState) -> None:
        """current_round increments after team_count picks.

        :param twelve_team_state: 12-team state fixture.
        """
        state = twelve_team_state.model_copy(update={"current_pick": 13})
        assert state.current_round == 2

    def test_snake_order_round_one_ascending(self, twelve_team_state: DraftState) -> None:
        """Round 1 picks go in ascending draft slot order (slot 1 picks first).

        :param twelve_team_state: 12-team state fixture.
        """
        state = twelve_team_state.model_copy(update={"current_pick": 1})
        assert state.current_manager.draft_slot == 1
        state = twelve_team_state.model_copy(update={"current_pick": 6})
        assert state.current_manager.draft_slot == 6
        state = twelve_team_state.model_copy(update={"current_pick": 12})
        assert state.current_manager.draft_slot == 12

    def test_snake_order_round_two_descending(self, twelve_team_state: DraftState) -> None:
        """Round 2 picks go in descending draft slot order (slot 12 picks first).

        :param twelve_team_state: 12-team state fixture.
        """
        state = twelve_team_state.model_copy(update={"current_pick": 13})
        assert state.current_manager.draft_slot == 12
        state = twelve_team_state.model_copy(update={"current_pick": 24})
        assert state.current_manager.draft_slot == 1

    def test_snake_order_round_three_ascending(self, twelve_team_state: DraftState) -> None:
        """Round 3 returns to ascending order.

        :param twelve_team_state: 12-team state fixture.
        """
        state = twelve_team_state.model_copy(update={"current_pick": 25})
        assert state.current_manager.draft_slot == 1

    def test_total_picks(self, twelve_team_state: DraftState) -> None:
        """total_picks = team_count * total_rounds.

        :param twelve_team_state: 12-team state with default 16-round roster (10 starters + 6 bench).
        """
        assert twelve_team_state.total_picks == 12 * 16

    def test_is_complete_false_at_start(self, twelve_team_state: DraftState) -> None:
        """is_complete is False at pick 1.

        :param twelve_team_state: 12-team state fixture.
        """
        assert twelve_team_state.is_complete is False

    def test_is_complete_true_after_last_pick(self, twelve_team_state: DraftState) -> None:
        """is_complete is True when current_pick exceeds total_picks.

        :param twelve_team_state: 12-team state fixture.
        """
        state = twelve_team_state.model_copy(update={"current_pick": twelve_team_state.total_picks + 1})
        assert state.is_complete is True

    def test_user_manager_returns_correct_manager(self, twelve_team_state: DraftState) -> None:
        """user_manager returns the manager with is_user=True.

        :param twelve_team_state: 12-team state with user at slot 3.
        """
        assert twelve_team_state.user_manager.draft_slot == 3
        assert twelve_team_state.user_manager.is_user is True

    def test_picks_until_user_when_it_is_users_turn(self, twelve_team_state: DraftState) -> None:
        """picks_until_user returns 0 when current pick belongs to the user.

        User is at slot 3, so pick 3 is their turn.

        :param twelve_team_state: 12-team state with user at slot 3.
        """
        state = twelve_team_state.model_copy(update={"current_pick": 3})
        assert state.picks_until_user() == 0

    def test_picks_until_user_counts_intervening_picks(self, twelve_team_state: DraftState) -> None:
        """picks_until_user counts correctly when user's turn is ahead.

        User is at slot 3; pick 1 means 2 picks before user's turn.

        :param twelve_team_state: 12-team state with user at slot 3.
        """
        state = twelve_team_state.model_copy(update={"current_pick": 1})
        assert state.picks_until_user() == 2

    def test_picks_until_user_in_even_round(self, twelve_team_state: DraftState) -> None:
        """picks_until_user works correctly in even (reversed) rounds.

        User at slot 3 picks at position 10 in round 2 (12 - 3 + 1 = 10).
        Starting at pick 13 (first pick of round 2), that's 9 picks away.

        :param twelve_team_state: 12-team state with user at slot 3.
        """
        state = twelve_team_state.model_copy(update={"current_pick": 13})
        assert state.picks_until_user() == 9


# ---------------------------------------------------------------------------
# DraftState — apply_pick
# ---------------------------------------------------------------------------

class TestDraftStateApplyPick:
    """Tests for DraftState.apply_pick()."""

    @pytest.fixture()
    def two_team_state(
        self,
        two_team_league: League,
        user_manager: Manager,
        opponent_manager: Manager,
        rb_player: NFLPlayer,
        wr_player: NFLPlayer,
    ) -> DraftState:
        """2-team, 2-round draft state with 2 available players.

        :return: DraftState at pick 1 (user's turn, slot 1).
        """
        return DraftState.new(
            league=two_team_league,
            managers=[user_manager, opponent_manager],
            available_players=[rb_player, wr_player],
        )

    def test_current_pick_advances(
        self, two_team_state: DraftState, rb_player: NFLPlayer
    ) -> None:
        """current_pick increments by 1 after apply_pick.

        :param two_team_state: 2-team state at pick 1.
        :param rb_player: Player to draft.
        """
        next_state = two_team_state.apply_pick(rb_player)
        assert next_state.current_pick == 2

    def test_player_removed_from_available(
        self, two_team_state: DraftState, rb_player: NFLPlayer, wr_player: NFLPlayer
    ) -> None:
        """Drafted player is removed from available_players.

        :param two_team_state: State with rb_player and wr_player available.
        :param rb_player: Player being drafted.
        :param wr_player: Should remain available.
        """
        next_state = two_team_state.apply_pick(rb_player)
        available_ids = {p.player_id for p in next_state.available_players}
        assert rb_player.player_id not in available_ids
        assert wr_player.player_id in available_ids

    def test_player_added_to_current_managers_roster(
        self, two_team_state: DraftState, user_manager: Manager, rb_player: NFLPlayer
    ) -> None:
        """Picked player appears on the picking manager's roster.

        User is at slot 1 and picks first.

        :param two_team_state: State at pick 1 (user's turn).
        :param user_manager: The user manager fixture.
        :param rb_player: Player being drafted.
        """
        next_state = two_team_state.apply_pick(rb_player)
        user_roster = next_state.rosters[user_manager.manager_id]
        assert rb_player in user_roster.players

    def test_draft_pick_appended_to_history(
        self, two_team_state: DraftState, rb_player: NFLPlayer
    ) -> None:
        """A DraftPick is appended to picks with correct metadata.

        :param two_team_state: State at pick 1, round 1.
        :param rb_player: Player being drafted.
        """
        next_state = two_team_state.apply_pick(rb_player)
        assert len(next_state.picks) == 1
        recorded = next_state.picks[0]
        assert recorded.player is rb_player
        assert recorded.overall_pick == 1
        assert recorded.round_number == 1
        assert recorded.pick_in_round == 1

    def test_original_state_is_unchanged(
        self, two_team_state: DraftState, rb_player: NFLPlayer
    ) -> None:
        """apply_pick returns a new state; original is not mutated.

        :param two_team_state: Original state.
        :param rb_player: Player drafted in the copy.
        """
        original_pick = two_team_state.current_pick
        two_team_state.apply_pick(rb_player)
        assert two_team_state.current_pick == original_pick

    def test_unknown_player_still_advances_state(
        self, two_team_state: DraftState
    ) -> None:
        """Applying a player not in available_players still advances current_pick.

        This handles placeholder picks for players not in our pool.

        :param two_team_state: State with its own available pool.
        """
        stranger = NFLPlayer(
            player_id="unknown_xyz", name="Unknown", position=Position.QB,
            team="FA", projected_points=0.0, adp=999.0,
        )
        next_state = two_team_state.apply_pick(stranger)
        assert next_state.current_pick == 2
        assert stranger in next_state.rosters[next_state.picks[0].manager.manager_id].players

    def test_two_picks_simulate_snake_turn(
        self,
        two_team_state: DraftState,
        user_manager: Manager,
        opponent_manager: Manager,
        rb_player: NFLPlayer,
        wr_player: NFLPlayer,
    ) -> None:
        """Two sequential apply_pick calls advance through snake order correctly.

        Pick 1: user (slot 1). Pick 2: opponent (slot 2).

        :param two_team_state: 2-team state at pick 1.
        :param user_manager: User at draft slot 1.
        :param opponent_manager: Opponent at draft slot 2.
        :param rb_player: Drafted at pick 1.
        :param wr_player: Drafted at pick 2.
        """
        state_after_1 = two_team_state.apply_pick(rb_player)
        state_after_2 = state_after_1.apply_pick(wr_player)
        assert rb_player in state_after_2.rosters[user_manager.manager_id].players
        assert wr_player in state_after_2.rosters[opponent_manager.manager_id].players
