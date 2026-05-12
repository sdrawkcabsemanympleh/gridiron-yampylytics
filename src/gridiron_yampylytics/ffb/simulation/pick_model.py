"""Opponent and user pick models for YampGM Monte Carlo draft simulation.

A pick model decides which player a manager selects at a given point in the
draft. All implementations satisfy the :class:`PickModel` protocol and are
interchangeable at the :class:`~gridiron_yampylytics.ffb.simulation.engine.DraftSimulator`
call site.

Available models:

- :class:`ADPPickModel` — ADP-weighted probabilistic sampling, no roster context.
  Baseline for any manager whose tendencies are unknown.
- :class:`NeedWeightedADPModel` — extends ADPPickModel with positional need
  modulation. Models realistic drafter behavior: managers avoid overstocking
  positions and prioritise unfilled slots. Need influence fades in late rounds
  to capture autopick / best-available behaviour.
- :class:`GreedyVorPickModel` — deterministic VOR-based model for the user's
  future picks within simulation. Fills dedicated slots first, then best VOR.
- :class:`ScoredPickModel` — stub for a future full composite model (metric
  components with configurable weights, matching the WeightedLinearScorer pattern).
"""
import numpy as np
from typing import Protocol, runtime_checkable
from gridiron_yampylytics.ffb.models.league import RosterConfig
from gridiron_yampylytics.ffb.models.player import NFLPlayer, Position
from gridiron_yampylytics.ffb.scoring.vor import compute_vor
from gridiron_yampylytics.ffb.simulation.kernels import (
    STRATEGY_ADP,
    STRATEGY_GREEDY_VOR,
    STRATEGY_NEED_WEIGHTED_ADP,
)


@runtime_checkable
class PickModel(Protocol):
    """Protocol for pick models in Monte Carlo simulation.

    All keyword arguments beyond the three positional ones are optional context
    that richer models may use. Implementations must accept them as keyword-only
    args even if they ignore them, so callers can always pass the full context
    without checking which model is in use.
    """

    def sample_pick(
        self,
        available_players: list[NFLPlayer],
        pick_number: int,
        rng: np.random.Generator,
        *,
        roster_counts: dict[Position, int] | None = None,
        roster_config: RosterConfig | None = None,
        total_picks: int | None = None,
        replacement_levels: dict[Position, float] | None = None,
    ) -> NFLPlayer:
        """Sample one pick for a manager at a given overall pick number.

        :param available_players: Players still on the board.
        :param pick_number: 1-indexed overall pick number in the draft.
        :param rng: NumPy random Generator for reproducible sampling.
        :param roster_counts: Mapping of position → count already drafted by
            this manager. ``None`` if roster context is unavailable.
        :param roster_config: League roster configuration. Used with
            ``roster_counts`` to determine positional need.
        :param total_picks: Total picks in the full draft. Used for
            late-round fade calculations.
        :param replacement_levels: VOR replacement levels. Used by
            value-based models (e.g. :class:`GreedyVorPickModel`).
        :return: The sampled :class:`~gridiron_yampylytics.ffb.models.player.NFLPlayer`.
        """
        ...

    def to_sim_params(self) -> tuple[int, np.ndarray]:
        """Return the strategy code and parameter array for the vectorized kernel.

        Used by :class:`~gridiron_yampylytics.ffb.simulation.engine.DraftSimulator`
        to pass this model's behaviour into the numpy hot loop without pickling
        the full model object.  Strategy codes are defined in
        :mod:`~gridiron_yampylytics.ffb.simulation.kernels`.

        :return: ``(strategy_code, params)`` where ``params`` is a float64
            array of model-specific scalar parameters.
        """
        ...


class ADPPickModel:
    """Models picks using ADP-based Normal distributions.

    At overall pick k, player i is selected with probability proportional to
    the PDF of N(ADP_i, adp_std_i) evaluated at k::

        weight_i ∝ exp(−0.5 × ((k − ADP_i) / adp_std_i)²)

    Players at their expected ADP receive the highest weight. Consensus picks
    (low adp_std) have tight, peaked distributions. Sleepers (high adp_std)
    are spread across a wider range. Roster context is accepted but ignored —
    use :class:`NeedWeightedADPModel` for roster-aware behaviour.
    """

    def sample_pick(
        self,
        available_players: list[NFLPlayer],
        pick_number: int,
        rng: np.random.Generator,
        *,
        roster_counts: dict[Position, int] | None = None,
        roster_config: RosterConfig | None = None,
        total_picks: int | None = None,
        replacement_levels: dict[Position, float] | None = None,
    ) -> NFLPlayer:
        """Sample one pick using ADP-based Normal distribution weights.

        :param available_players: Players still on the board.
        :param pick_number: 1-indexed overall pick number.
        :param rng: NumPy random Generator.
        :param roster_counts: Ignored.
        :param roster_config: Ignored.
        :param total_picks: Ignored.
        :param replacement_levels: Ignored.
        :return: Sampled player.
        :raises ValueError: If ``available_players`` is empty.
        """
        if not available_players:
            raise ValueError("Cannot sample from an empty player pool.")
        adps = np.array([p.adp for p in available_players])
        stds = np.clip(np.array([p.adp_std for p in available_players]), 1.0, None)
        z = (pick_number - adps) / stds
        weights = np.exp(-0.5 * z * z)
        total = weights.sum()
        weights = weights / total if total > 0 else np.ones(len(available_players)) / len(available_players)
        idx = int(rng.choice(len(available_players), p=weights))
        return available_players[idx]

    def to_sim_params(self) -> tuple[int, np.ndarray]:
        """Return ADP strategy code with empty parameter array.

        :return: ``(STRATEGY_ADP, empty float64 array)``.
        """
        return (STRATEGY_ADP, np.empty(0, dtype=np.float64))


class NeedWeightedADPModel:
    """Roster-aware pick model — ADP distributions modulated by positional need.

    Extends :class:`ADPPickModel` by multiplying ADP weights with a positional
    need factor derived from the manager's current roster. Positions with open
    dedicated slots get full weight; overstocked positions are suppressed toward
    ``min_need_factor``. Need influence fades in late rounds to capture the
    common behaviour of managers going best-available or autopicking.

    Without roster context (``roster_counts`` or ``roster_config`` absent) the
    model degrades gracefully to pure ADP sampling, identical to
    :class:`ADPPickModel`.

    :param need_weight: Fraction of each player's weight that comes from need
        modulation. ``0.0`` = pure ADP; ``1.0`` = fully need-weighted.
        Defaults to ``0.3``.
    :param min_need_factor: Floor multiplier applied to overstocked positions
        (prevents absolute zero probability). Defaults to ``0.15``.
    :param late_round_fade: Controls how much the need influence fades by the
        end of the draft. ``0.0`` = no fade; ``1.0`` = need drops to zero at
        the final pick. Defaults to ``0.7``.
    """

    def __init__(
        self,
        need_weight: float = 0.3,
        min_need_factor: float = 0.15,
        late_round_fade: float = 0.7,
    ) -> None:
        """Initialise the model.

        :param need_weight: Fraction of weight from need modulation.
        :param min_need_factor: Floor for overstocked-position multiplier.
        :param late_round_fade: Need fade rate across the draft.
        """
        self.need_weight = need_weight
        self.min_need_factor = min_need_factor
        self.late_round_fade = late_round_fade

    def _need_factor(
        self,
        position: Position,
        roster_counts: dict[Position, int],
        dedicated: dict[Position, int],
    ) -> float:
        """Compute a [min_need_factor, 1.0] multiplier for a position.

        Returns 1.0 when the position is completely unfilled, decreasing as
        dedicated slots are consumed, bottoming at ``min_need_factor`` when
        overstocked.

        :param position: The position to evaluate.
        :param roster_counts: Current position counts for this manager.
        :param dedicated: Dedicated slot counts from the roster config.
        :return: Need factor in [``min_need_factor``, 1.0].
        """
        slots = dedicated.get(position, 0)
        if slots == 0:
            return self.min_need_factor
        count = roster_counts.get(position, 0)
        ratio = max(0.0, (slots - count) / slots)
        return max(self.min_need_factor, ratio)

    def sample_pick(
        self,
        available_players: list[NFLPlayer],
        pick_number: int,
        rng: np.random.Generator,
        *,
        roster_counts: dict[Position, int] | None = None,
        roster_config: RosterConfig | None = None,
        total_picks: int | None = None,
        replacement_levels: dict[Position, float] | None = None,
    ) -> NFLPlayer:
        """Sample one pick using need-modulated ADP weights.

        Computes ADP weights per :class:`ADPPickModel`, then scales each
        player's weight by a positional need multiplier for the picking
        manager. The effective need influence fades linearly toward zero over
        the course of the draft according to ``late_round_fade``.

        Falls back to pure ADP if ``roster_counts`` or ``roster_config`` are
        absent.

        :param available_players: Players still on the board.
        :param pick_number: 1-indexed overall pick number.
        :param rng: NumPy random Generator.
        :param roster_counts: Current position counts for the picking manager.
        :param roster_config: League roster configuration.
        :param total_picks: Total picks in the draft (for late-round fade).
        :param replacement_levels: Ignored.
        :return: Sampled player.
        :raises ValueError: If ``available_players`` is empty.
        """
        if not available_players:
            raise ValueError("Cannot sample from an empty player pool.")
        adps = np.array([p.adp for p in available_players])
        stds = np.clip(np.array([p.adp_std for p in available_players]), 1.0, None)
        z = (pick_number - adps) / stds
        adp_weights = np.exp(-0.5 * z * z)
        if roster_counts is None or roster_config is None:
            weights = adp_weights
        else:
            dedicated: dict[Position, int] = {
                Position.QB: roster_config.qb,
                Position.RB: roster_config.rb,
                Position.WR: roster_config.wr,
                Position.TE: roster_config.te,
                Position.K: roster_config.k,
                Position.DEF: roster_config.def_,
            }
            need_factors = np.array([
                self._need_factor(p.position, roster_counts, dedicated)
                for p in available_players
            ])
            fade = 1.0
            if total_picks is not None and total_picks > 0:
                fade = max(0.0, 1.0 - self.late_round_fade * pick_number / total_picks)
            effective_need_weight = self.need_weight * fade
            weights = adp_weights * (1.0 - effective_need_weight + effective_need_weight * need_factors)
        total = weights.sum()
        weights = weights / total if total > 0 else np.ones(len(available_players)) / len(available_players)
        idx = int(rng.choice(len(available_players), p=weights))
        return available_players[idx]

    def to_sim_params(self) -> tuple[int, np.ndarray]:
        """Return NeedWeightedADP strategy code and scalar parameters.

        :return: ``(STRATEGY_NEED_WEIGHTED_ADP, [need_weight, min_need_factor, late_round_fade])``.
        """
        return (
            STRATEGY_NEED_WEIGHTED_ADP,
            np.array([self.need_weight, self.min_need_factor, self.late_round_fade], dtype=np.float64),
        )


class GreedyVorPickModel:
    """Models the user's future picks within simulation using greedy VOR strategy.

    Fills open dedicated position slots first (by VOR), then selects best
    available VOR overall once all dedicated slots are filled. Deterministic
    — does not use the ``rng`` parameter.

    This is the direct replacement for the ``_greedy_vor_pick`` function that
    previously lived in the engine, promoted to a proper :class:`PickModel`
    implementation so both user and opponent strategies share the same protocol.

    Without ``replacement_levels`` the model falls back to picking by
    ``projected_points`` directly.
    """

    def sample_pick(
        self,
        available_players: list[NFLPlayer],
        pick_number: int,
        rng: np.random.Generator,
        *,
        roster_counts: dict[Position, int] | None = None,
        roster_config: RosterConfig | None = None,
        total_picks: int | None = None,
        replacement_levels: dict[Position, float] | None = None,
    ) -> NFLPlayer:
        """Select the highest-VOR available player, prioritising unfilled slots.

        :param available_players: Players still on the board.
        :param pick_number: Ignored (deterministic strategy).
        :param rng: Ignored (deterministic strategy).
        :param roster_counts: Current position counts for this manager.
        :param roster_config: League roster configuration.
        :param total_picks: Ignored.
        :param replacement_levels: VOR replacement levels. Falls back to
            projected points if absent.
        :return: Selected player.
        :raises ValueError: If ``available_players`` is empty.
        """
        if not available_players:
            raise ValueError("Cannot pick from an empty player pool.")
        key = (lambda p: compute_vor(p, replacement_levels)) if replacement_levels is not None else (lambda p: p.projected_points)
        if roster_counts is None or roster_config is None:
            return max(available_players, key=key)
        dedicated: dict[Position, int] = {
            Position.QB: roster_config.qb,
            Position.RB: roster_config.rb,
            Position.WR: roster_config.wr,
            Position.TE: roster_config.te,
            Position.K: roster_config.k,
            Position.DEF: roster_config.def_,
        }
        needed = {pos for pos, slots in dedicated.items() if roster_counts.get(pos, 0) < slots}
        pool = [p for p in available_players if p.position in needed] if needed else available_players
        return max(pool or available_players, key=key)

    def to_sim_params(self) -> tuple[int, np.ndarray]:
        """Return GreedyVOR strategy code with empty parameter array.

        :return: ``(STRATEGY_GREEDY_VOR, empty float64 array)``.
        """
        return (STRATEGY_GREEDY_VOR, np.empty(0, dtype=np.float64))


class ScoredPickModel:
    """Stub: future composite pick model with pluggable metric components.

    Intended architecture: metric components (VOR, need, scarcity, etc.) each
    produce per-player scores that are weighted and blended into a sampling
    distribution — the same compositional pattern as
    :class:`~gridiron_yampylytics.ffb.scoring.scorer.WeightedLinearScorer`.
    This would unify the scoring vocabulary used for the user's current-pick
    recommendations and the simulation's opponent modelling.

    Not yet implemented. Use :class:`NeedWeightedADPModel` for roster-aware
    opponent behaviour.
    """

    def sample_pick(
        self,
        available_players: list[NFLPlayer],
        pick_number: int,
        rng: np.random.Generator,
        *,
        roster_counts: dict[Position, int] | None = None,
        roster_config: RosterConfig | None = None,
        total_picks: int | None = None,
        replacement_levels: dict[Position, float] | None = None,
    ) -> NFLPlayer:
        """Raise :exc:`NotImplementedError` — not yet implemented.

        :raises NotImplementedError: Always. Use :class:`NeedWeightedADPModel`.
        """
        raise NotImplementedError(
            "ScoredPickModel is not yet implemented. Use NeedWeightedADPModel."
        )

    def to_sim_params(self) -> tuple[int, np.ndarray]:
        """Raise :exc:`NotImplementedError` — not yet vectorizable.

        :raises NotImplementedError: Always.
        """
        raise NotImplementedError("ScoredPickModel is not yet vectorizable.")
