"""League context — snapshot of a single Sleeper league's current state.

:class:`LeagueContext` fetches and holds everything needed to evaluate a
specific league: scoring config, all rosters, the user's roster, user
identities, and the current NFL week.  It is the input to the per-roster
recommendation engine in :mod:`~gridiron_yampylytics.ffb.inseason.roster_fit`.

Typical usage::

    client = SleeperClient()
    user = client.get_user("CarlCCryMoar")
    ctx = LeagueContext.load(client, league_id="123456789", user_id=user.user_id)
    available_ids = ctx.available_player_ids
"""
from dataclasses import dataclass, field
from gridiron_yampylytics.ffb.data.sleeper import (
    SleeperClient,
    SleeperLeagueInfo,
    SleeperLeagueUser,
    SleeperNFLState,
    SleeperRoster,
)


@dataclass
class LeagueContext:
    """All Sleeper state for a single league at a point in time.

    Built via :meth:`load` rather than direct construction.

    :param league: League configuration including scoring type and roster
        slot layout.
    :param nfl_state: Current NFL week and season pulled at load time.
    :param user_roster: The tool owner's roster in this league.
    :param all_rosters: Every roster in the league, including the user's.
        Used to determine which players are available (not rostered anywhere).
    :param users_by_id: Mapping of Sleeper ``user_id`` → :class:`SleeperLeagueUser`
        for all managers in the league.
    """
    league: SleeperLeagueInfo
    nfl_state: SleeperNFLState
    user_roster: SleeperRoster
    all_rosters: list[SleeperRoster]
    users_by_id: dict[str, SleeperLeagueUser] = field(default_factory=dict)

    @classmethod
    def load(cls, client: SleeperClient, league_id: str, user_id: str) -> "LeagueContext":
        """Fetch all league state from the Sleeper API and construct a context.

        Makes four parallel-ish REST calls: league info, rosters, users, and
        NFL state.  All are synchronous.

        :param client: Authenticated :class:`SleeperClient` instance.
        :param league_id: Sleeper league identifier.
        :param user_id: Sleeper user ID for the tool owner (from
            :meth:`~SleeperClient.get_user`). Used to identify which roster
            belongs to the user.
        :return: Fully populated :class:`LeagueContext`.
        :raises ValueError: If no roster is found for the given ``user_id``
            in this league (wrong league or wrong user_id).
        :raises requests.HTTPError: On non-2xx Sleeper API responses.
        """
        league = client.get_league_info(league_id)
        rosters = client.get_league_rosters(league_id)
        users = client.get_league_users(league_id)
        nfl_state = client.get_nfl_state()
        user_roster = next((r for r in rosters if r.owner_id == user_id), None)
        if user_roster is None:
            raise ValueError(
                f"No roster found for user_id={user_id!r} in league {league_id!r}. "
                "Verify the user belongs to this league."
            )
        users_by_id = {u.user_id: u for u in users}
        return cls(
            league=league,
            nfl_state=nfl_state,
            user_roster=user_roster,
            all_rosters=rosters,
            users_by_id=users_by_id,
        )

    @property
    def rostered_player_ids(self) -> set[str]:
        """All Sleeper player IDs currently on any roster in the league.

        Includes starters, bench, and IR/reserve slots.  Players in this set
        are unavailable as free agents.

        :return: Set of Sleeper player ID strings.
        """
        rostered: set[str] = set()
        for roster in self.all_rosters:
            rostered.update(roster.players)
        return rostered

    @property
    def user_player_ids(self) -> set[str]:
        """Sleeper player IDs on the user's roster (all slots).

        :return: Set of Sleeper player ID strings.
        """
        return set(self.user_roster.players)

    def available_player_ids(self, all_known_ids: set[str]) -> set[str]:
        """Player IDs that are free agents in this league.

        :param all_known_ids: Universe of Sleeper player IDs to check against
            (e.g. all players in our DB who have a ``sleeper_id``). Players not
            in this set are outside our scoring scope regardless of availability.
        :return: IDs present in ``all_known_ids`` but not on any roster.
        """
        return all_known_ids - self.rostered_player_ids

    @property
    def current_week(self) -> int:
        """Convenience accessor for the current NFL week.

        :return: Current NFL regular-season week number.
        """
        return self.nfl_state.week

    @property
    def current_season(self) -> int:
        """Convenience accessor for the current NFL season year.

        :return: Current NFL season year (e.g. ``2025``).
        """
        return self.nfl_state.season
