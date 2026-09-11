"""VONA (Value Over Next Available) calculators for YampGM.

VONA measures how much a player is worth relative to the best player at the same
position still available at the user's next draft turn. A high VONA signals urgency
— if you pass on this player now, the position drops off significantly before you
pick again.

Two implementations are provided:

- :class:`AdpVonaApproximation` — ADP-based estimate; available now.
- :class:`MonteCarloVona` — simulation-based stub; requires ``ffb/simulation/``.

Both satisfy the :class:`VonaCalculator` protocol and are interchangeable at the
:class:`~gridiron_yampylytics.ffb.scoring.scorer.WeightedLinearScorer` call site.
"""
from typing import Protocol, runtime_checkable
from gridiron_yampylytics.ffb.models.draft import Roster
from gridiron_yampylytics.ffb.models.league import RosterConfig
from gridiron_yampylytics.ffb.models.player import NFLPlayer, Position


@runtime_checkable
class VonaCalculator(Protocol):
    """Protocol for VONA calculators."""

    def compute_vona(
        self,
        player: NFLPlayer,
        available_players: list[NFLPlayer],
        picks_until_user: int,
        *,
        user_roster: Roster | None = None,
        roster_config: RosterConfig | None = None,
    ) -> float:
        """Compute VONA for a player given current draft context.

        :param player: The player to evaluate.
        :param available_players: Players still on the board (includes ``player``).
        :param picks_until_user: Picks before the user's next turn (0 = user's turn now).
        :param user_roster: The user's current roster. When provided alongside
            ``roster_config``, enables flex-aware comparison: once dedicated
            position slots are filled, compares against the flex-eligible pool
            instead of the same position only.
        :param roster_config: League roster configuration. Used with ``user_roster``
            to determine dedicated slot counts and flex eligibility.
        :return: ``player.projected_points`` minus the best available at the
            comparison position(s) after ``picks_until_user`` opponents pick. Returns
            ``player.projected_points`` when no competition remains.
        """
        ...


class AdpVonaApproximation:
    """ADP-based VONA approximation.

    Estimates availability at the user's next pick by assuming the
    ``picks_until_user`` players with the lowest ADP values (i.e. most likely
    to be taken next) will be drafted before the user picks again. The best
    available among the survivors is the baseline.

    When ``user_roster`` and ``roster_config`` are provided, the comparison is
    flex-aware: if the user's dedicated slots at ``player.position`` are already
    filled and the position is flex-eligible, the baseline is the best remaining
    flex-eligible player (RB/WR/TE or league-configured equivalents) rather than
    the best same-position player. This prevents over-valuing a third RB compared
    to a superior WR competing for the same flex slot.

    This is a deliberate approximation — the Monte Carlo VONA will replace this
    once the simulation module is implemented.
    """

    def compute_vona(
        self,
        player: NFLPlayer,
        available_players: list[NFLPlayer],
        picks_until_user: int,
        *,
        user_roster: Roster | None = None,
        roster_config: RosterConfig | None = None,
    ) -> float:
        """Compute VONA using ADP to estimate which players survive to the user's next pick.

        Players are sorted by ADP; the lowest-ADP ``picks_until_user`` are assumed
        taken. The comparison pool is position-specific by default; flex-aware when
        ``user_roster`` and ``roster_config`` are provided and dedicated slots are full.

        :param player: The player to evaluate.
        :param available_players: Players still on the board (includes ``player``).
        :param picks_until_user: Picks before the user's next turn.
        :param user_roster: The user's current roster for flex-aware comparison.
        :param roster_config: League roster configuration for flex-aware comparison.
        :return: ``player.projected_points`` minus the best available at the
            comparison position(s) after opponent picks. Returns
            ``player.projected_points`` if no competition survives.
        """
        sorted_by_adp = sorted(available_players, key=lambda p: p.adp)
        likely_taken = {id(p) for p in sorted_by_adp[:picks_until_user]}
        comparison_positions: frozenset[Position] = frozenset({player.position})
        if (
            user_roster is not None
            and roster_config is not None
            and roster_config.flex > 0
            and player.position in roster_config.flex_eligible
        ):
            dedicated_slots: dict[Position, int] = {
                Position.QB: roster_config.qb,
                Position.RB: roster_config.rb,
                Position.WR: roster_config.wr,
                Position.TE: roster_config.te,
                Position.K: roster_config.k,
                Position.DEF: roster_config.def_,
            }
            if user_roster.count_at_position(player.position) >= dedicated_slots.get(player.position, 0):
                comparison_positions = frozenset(roster_config.flex_eligible)
        survivors = [
            p for p in available_players
            if id(p) not in likely_taken
            and p.player_id != player.player_id
            and p.position in comparison_positions
        ]
        if not survivors:
            return player.projected_points
        best_next = max(survivors, key=lambda p: p.projected_points)
        return player.projected_points - best_next.projected_points


class MonteCarloVona:
    """Monte Carlo simulation-based VONA calculator.

    Uses draft simulations to compute true expected value over next available,
    accounting for opponent pick tendencies and positional scarcity dynamics.

    Not yet implemented — requires ``ffb/simulation/``. Use
    :class:`AdpVonaApproximation` until the simulation module is available.
    """

    def compute_vona(
        self,
        player: NFLPlayer,
        available_players: list[NFLPlayer],
        picks_until_user: int,
        *,
        user_roster: Roster | None = None,
        roster_config: RosterConfig | None = None,
    ) -> float:
        """Raise :exc:`NotImplementedError` — simulation module not yet built.

        :param player: Unused.
        :param available_players: Unused.
        :param picks_until_user: Unused.
        :param user_roster: Unused.
        :param roster_config: Unused.
        :raises NotImplementedError: Always. Use :class:`AdpVonaApproximation`.
        """
        raise NotImplementedError(
            "MonteCarloVona requires ffb/simulation/ (not yet built). "
            "Use AdpVonaApproximation."
        )
