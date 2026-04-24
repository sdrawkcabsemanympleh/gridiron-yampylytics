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
from gridiron_yampylytics.ffb.models.player import NFLPlayer


@runtime_checkable
class VonaCalculator(Protocol):
    """Protocol for VONA calculators."""

    def compute_vona(
        self,
        player: NFLPlayer,
        available_players: list[NFLPlayer],
        picks_until_user: int,
    ) -> float:
        """Compute VONA for a player given current draft context.

        :param player: The player to evaluate.
        :param available_players: Players still on the board (includes ``player``).
        :param picks_until_user: Picks before the user's next turn (0 = user's turn now).
        :return: ``player.projected_points`` minus the best available at the same
            position after ``picks_until_user`` opponents pick. Returns
            ``player.projected_points`` when no competition remains at this position.
        """
        ...


class AdpVonaApproximation:
    """ADP-based VONA approximation.

    Estimates availability at the user's next pick by assuming the
    ``picks_until_user`` players with the lowest ADP values (i.e. most likely
    to be taken next) will be drafted before the user picks again. The best
    available at the same position among the survivors is then the baseline.

    This is a deliberate approximation — the Monte Carlo VONA will replace this
    once the simulation module is implemented.
    """

    def compute_vona(
        self,
        player: NFLPlayer,
        available_players: list[NFLPlayer],
        picks_until_user: int,
    ) -> float:
        """Compute VONA using ADP to estimate which players survive to the user's next pick.

        Players are sorted by ADP; the lowest-ADP ``picks_until_user`` are assumed
        taken. The best remaining player at the same position (excluding ``player``
        itself) is the VONA baseline.

        :param player: The player to evaluate.
        :param available_players: Players still on the board (includes ``player``).
        :param picks_until_user: Picks before the user's next turn.
        :return: ``player.projected_points`` minus the best available at the same
            position after opponent picks. Returns ``player.projected_points`` if
            no competition survives (position is fully cleared).
        """
        sorted_by_adp = sorted(available_players, key=lambda p: p.adp)
        likely_taken = {id(p) for p in sorted_by_adp[:picks_until_user]}
        survivors = [
            p for p in available_players
            if id(p) not in likely_taken
            and p.player_id != player.player_id
            and p.position == player.position
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
    ) -> float:
        """Raise :exc:`NotImplementedError` — simulation module not yet built.

        :param player: Unused.
        :param available_players: Unused.
        :param picks_until_user: Unused.
        :raises NotImplementedError: Always. Use :class:`AdpVonaApproximation`.
        """
        raise NotImplementedError(
            "MonteCarloVona requires ffb/simulation/ (not yet built). "
            "Use AdpVonaApproximation."
        )
