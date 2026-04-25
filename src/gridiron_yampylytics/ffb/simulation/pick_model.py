"""Opponent pick models for YampGM Monte Carlo draft simulation.

A pick model predicts which player an opponent manager will select at a given
overall pick number. All implementations satisfy the :class:`PickModel` protocol
and are interchangeable at the
:class:`~gridiron_yampylytics.ffb.simulation.engine.DraftSimulator` call site.

:class:`ADPPickModel` models each player's draft position as a Normal distribution
centered at their ADP. Players near their ADP are most likely chosen; adp_std
controls how concentrated (consensus pick) or diffuse (boom-bust/sleeper) each
distribution is. This is intentionally a plugin architecture — more sophisticated
models (opponent-tendency-based, scarcity-aware) can replace :class:`ADPPickModel`
without touching the simulation engine.
"""
import numpy as np
from typing import Protocol, runtime_checkable
from gridiron_yampylytics.ffb.models.player import NFLPlayer


@runtime_checkable
class PickModel(Protocol):
    """Protocol for opponent pick models in Monte Carlo simulation."""

    def sample_pick(
        self,
        available_players: list[NFLPlayer],
        pick_number: int,
        rng: np.random.Generator,
    ) -> NFLPlayer:
        """Sample one pick for a non-user manager at a given overall pick number.

        :param available_players: Players still on the board.
        :param pick_number: 1-indexed overall pick number in the draft.
        :param rng: NumPy random Generator for reproducible sampling.
        :return: The sampled :class:`~gridiron_yampylytics.ffb.models.player.NFLPlayer`.
        """
        ...


class ADPPickModel:
    """Models opponent picks using ADP-based Normal distributions.

    At overall pick k, player i is selected with probability proportional to
    the PDF of N(ADP_i, adp_std_i) evaluated at k::

        weight_i ∝ exp(−0.5 × ((k − ADP_i) / adp_std_i)²)

    Players at their expected ADP (z ≈ 0) receive the highest weight.
    Consensus picks (low adp_std) have tight, peaked distributions.
    Sleepers and boom-bust players (high adp_std) are spread across a wider range.
    All weights are normalized to a valid probability distribution before sampling.
    """

    def sample_pick(
        self,
        available_players: list[NFLPlayer],
        pick_number: int,
        rng: np.random.Generator,
    ) -> NFLPlayer:
        """Sample one pick using ADP-based Normal distribution weights.

        :param available_players: Players still on the board.
        :param pick_number: 1-indexed overall pick number.
        :param rng: NumPy random Generator.
        :return: Sampled player.
        :raises ValueError: If ``available_players`` is empty.
        """
        if not available_players:
            raise ValueError("Cannot sample from an empty player pool.")
        adps = np.array([p.adp for p in available_players])
        stds = np.array([p.adp_std for p in available_players])
        z = (pick_number - adps) / stds
        weights = np.exp(-0.5 * z * z)
        weights /= weights.sum()
        idx = int(rng.choice(len(available_players), p=weights))
        return available_players[idx]


class ScoredPickModel:
    """Stub: uses a scorer to model opponent picks by positional value.

    Future implementation will weight picks by a simplified scoring function,
    making opponents more contextually realistic (filling positional needs,
    responding to scarcity, etc.). Not yet implemented.
    """

    def sample_pick(
        self,
        available_players: list[NFLPlayer],
        pick_number: int,
        rng: np.random.Generator,
    ) -> NFLPlayer:
        """Raise :exc:`NotImplementedError` — not yet implemented.

        :param available_players: Unused.
        :param pick_number: Unused.
        :param rng: Unused.
        :raises NotImplementedError: Always. Use :class:`ADPPickModel`.
        """
        raise NotImplementedError(
            "ScoredPickModel is not yet implemented. Use ADPPickModel."
        )
