"""Draft state models for fantasy football.

``DraftState`` is the central snapshot passed to simulation and scoring
components. It is purely descriptive — all mutation and computation
live in the simulation and orchestration layers.
"""
from pydantic import BaseModel, Field, model_validator
from .league import League, RosterConfig
from .manager import Manager
from .player import NFLPlayer, Position


class Roster(BaseModel):
    """A manager's current player holdings during or after a draft.

    :param manager: The manager who owns this roster.
    :param players: Players currently on the roster, in draft order.
    """
    manager: Manager
    players: list[NFLPlayer] = Field(default_factory=list)

    def players_at_position(self, position: Position) -> list[NFLPlayer]:
        """Return all rostered players at a given position.

        :param position: The position to filter by.
        :return: List of players whose position matches.
        """
        return [p for p in self.players if p.position == position]

    def count_at_position(self, position: Position) -> int:
        """Return the number of rostered players at a given position.

        :param position: The position to count.
        :return: Count of players at that position.
        """
        return len(self.players_at_position(position))

    def is_full(self, roster_config: RosterConfig) -> bool:
        """Return whether this roster has reached its maximum spots.

        :param roster_config: The league's roster configuration.
        :return: ``True`` if no more spots remain.
        """
        return len(self.players) >= roster_config.total_spots


class DraftPick(BaseModel):
    """A single completed pick in a fantasy draft.

    :param overall_pick: 1-indexed overall pick number across all rounds.
    :param round_number: 1-indexed round in which this pick occurred.
    :param pick_in_round: 1-indexed position within the round.
    :param manager: The manager who made this pick.
    :param player: The NFL player who was selected.
    """
    overall_pick: int = Field(ge=1)
    round_number: int = Field(ge=1)
    pick_in_round: int = Field(ge=1)
    manager: Manager
    player: NFLPlayer


class DraftState(BaseModel):
    """A complete snapshot of draft state at a single point in time.

    This model is immutable in intent — the simulation and session layers
    produce new ``DraftState`` instances rather than mutating this one.
    All computed properties are derived from ``current_pick`` and ``league``.

    :param league: League configuration (roster spots, scoring, team count).
    :param managers: All managers in the league, in no required order.
        Exactly one must have ``is_user=True``.
    :param rosters: Current roster for each manager, keyed by ``manager_id``.
    :param available_players: Players not yet drafted, in no required order.
    :param picks: Ordered history of all picks made so far.
    :param current_pick: 1-indexed overall pick number for the next selection.
    """
    league: League
    managers: list[Manager]
    rosters: dict[str, Roster]
    available_players: list[NFLPlayer]
    picks: list[DraftPick] = Field(default_factory=list)
    current_pick: int = Field(default=1, ge=1)

    @model_validator(mode="after")
    def validate_managers(self) -> "DraftState":
        """Validate manager list consistency.

        :return: The validated ``DraftState`` instance.
        :raises ValueError: If manager count doesn't match league team count,
            or if exactly one manager is not marked as the user.
        """
        if len(self.managers) != self.league.team_count:
            raise ValueError(
                f"Expected {self.league.team_count} managers, got {len(self.managers)}."
            )
        user_managers = [m for m in self.managers if m.is_user]
        if len(user_managers) != 1:
            raise ValueError(
                f"Exactly one manager must have is_user=True, found {len(user_managers)}."
            )
        return self

    @property
    def total_picks(self) -> int:
        """Total number of picks in the full draft.

        :return: ``team_count * total_rounds``.
        """
        return self.league.team_count * self.league.roster.total_rounds

    @property
    def is_complete(self) -> bool:
        """Whether the draft has concluded.

        :return: ``True`` if ``current_pick`` exceeds ``total_picks``.
        """
        return self.current_pick > self.total_picks

    @property
    def current_round(self) -> int:
        """1-indexed round number for the current pick.

        :return: Round number derived from ``current_pick`` and team count.
        """
        return (self.current_pick - 1) // self.league.team_count + 1

    @property
    def current_pick_in_round(self) -> int:
        """1-indexed pick position within the current round.

        :return: Position within the round for ``current_pick``.
        """
        return (self.current_pick - 1) % self.league.team_count + 1

    @property
    def current_manager(self) -> Manager:
        """The manager whose turn it is to pick.

        Uses snake draft ordering: odd rounds go ascending by draft position,
        even rounds go descending.

        :return: The ``Manager`` whose pick is next.
        """
        pick_in_round = self.current_pick_in_round  # 1-indexed
        is_even_round = self.current_round % 2 == 0
        if is_even_round:
            target_position = self.league.team_count - pick_in_round + 1
        else:
            target_position = pick_in_round
        return next(m for m in self.managers if m.draft_slot == target_position)

    @property
    def user_manager(self) -> Manager:
        """The manager representing the tool's user.

        :return: The single ``Manager`` with ``is_user=True``.
        """
        return next(m for m in self.managers if m.is_user)

    @property
    def user_roster(self) -> Roster:
        """The user's current roster.

        :return: The ``Roster`` belonging to the user manager.
        """
        return self.rosters[self.user_manager.manager_id]

    def picks_until_user(self) -> int:
        """Number of picks until the user's next turn.

        Walks forward from ``current_pick`` through snake draft order
        until the user's draft position is reached.

        :return: 0 if it is currently the user's pick, otherwise the count
            of intervening picks.
        """
        user_position = self.user_manager.draft_slot
        team_count = self.league.team_count
        count = 0
        for offset in range(team_count):  # at most one full round to find user
            pick_number = self.current_pick + offset
            pick_in_round = (pick_number - 1) % team_count + 1
            round_number = (pick_number - 1) // team_count + 1
            is_even_round = round_number % 2 == 0
            if is_even_round:
                position_picking = team_count - pick_in_round + 1
            else:
                position_picking = pick_in_round
            if position_picking == user_position:
                return count
            count += 1
        return count  # fallback; should not be reached in a valid draft state

    @classmethod
    def new(
        cls,
        league: League,
        managers: list[Manager],
        available_players: list[NFLPlayer],
    ) -> "DraftState":
        """Create a fresh ``DraftState`` at the start of a draft.

        :param league: The league configuration.
        :param managers: All managers, each with a unique ``draft_slot`` in [1, team_count].
        :param available_players: The full pool of draftable players.
        :return: A ``DraftState`` at pick 1 with empty rosters.
        """
        rosters = {m.manager_id: Roster(manager=m) for m in managers}
        return cls(
            league=league,
            managers=managers,
            rosters=rosters,
            available_players=available_players,
        )
