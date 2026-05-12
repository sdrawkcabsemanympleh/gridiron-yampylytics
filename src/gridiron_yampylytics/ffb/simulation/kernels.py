"""Vectorized numpy simulation kernels for YampGM Monte Carlo draft evaluation.

This module contains the hot path functions that operate exclusively on
:class:`~gridiron_yampylytics.ffb.simulation.snapshot.SimSnapshot` arrays —
no Python domain objects, dict lookups, or list rebuilds inside the loops.

:func:`simulate_batch` runs all simulations for one candidate and returns
``(mean_score, std_score)``.  It is called from
:func:`~gridiron_yampylytics.ffb.simulation.engine._simulate_candidate` in
each ``ProcessPoolExecutor`` worker.

Pick model strategies are identified by integer codes defined here and
referenced by pick model classes via ``to_sim_params()``:

- :data:`STRATEGY_NEED_WEIGHTED_ADP` (``0``) — roster-aware ADP sampling.
- :data:`STRATEGY_GREEDY_VOR` (``1``) — deterministic VOR-based selection.
- :data:`STRATEGY_ADP` (``2``) — pure ADP sampling without roster context.
"""
import numpy as np
from gridiron_yampylytics.ffb.simulation.snapshot import SimSnapshot

#: Strategy code for :class:`~gridiron_yampylytics.ffb.simulation.pick_model.NeedWeightedADPModel`.
STRATEGY_NEED_WEIGHTED_ADP: int = 0
#: Strategy code for :class:`~gridiron_yampylytics.ffb.simulation.pick_model.GreedyVorPickModel`.
STRATEGY_GREEDY_VOR: int = 1
#: Strategy code for :class:`~gridiron_yampylytics.ffb.simulation.pick_model.ADPPickModel`.
STRATEGY_ADP: int = 2


def _sample_pick(
    strategy: int,
    params: np.ndarray,
    player_adps: np.ndarray,
    player_adp_stds: np.ndarray,
    player_points: np.ndarray,
    player_positions: np.ndarray,
    mgr_roster_counts: np.ndarray,
    roster_slots: np.ndarray,
    replacement_levels: np.ndarray,
    available: np.ndarray,
    pick_number: int,
    total_picks: int,
    rng: np.random.Generator,
) -> int:
    """Sample one pick using the specified strategy, operating entirely on arrays.

    All inputs are numpy primitives — no :class:`~gridiron_yampylytics.ffb.models.player.NFLPlayer`
    objects are accessed inside this function.  Returns the index of the chosen
    player in the player arrays.

    :param strategy: One of :data:`STRATEGY_NEED_WEIGHTED_ADP`,
        :data:`STRATEGY_GREEDY_VOR`, or :data:`STRATEGY_ADP`.
    :param params: Strategy-specific float parameters (e.g. need_weight for
        NeedWeightedADP; empty array for GreedyVor).
    :param player_adps: ADP per player.  shape (N,) float64.
    :param player_adp_stds: ADP std per player.  shape (N,) float64.
    :param player_points: Projected points per player.  shape (N,) float64.
    :param player_positions: Position index per player.  shape (N,) int32.
    :param mgr_roster_counts: Current position counts for the picking manager.
        shape (P,) int32.
    :param roster_slots: Dedicated slots per position.  shape (P,) int32.
    :param replacement_levels: VOR replacement thresholds per position.
        shape (P,) float64.
    :param available: Boolean availability mask.  shape (N,) bool.
    :param pick_number: 1-indexed overall pick number (for ADP z-score and fade).
    :param total_picks: Total picks in the full draft (for late-round fade).
    :param rng: NumPy random generator.
    :return: Index of the chosen player in the player arrays.
    """
    if strategy == STRATEGY_NEED_WEIGHTED_ADP or strategy == STRATEGY_ADP:
        adp_stds = np.clip(player_adp_stds, 1.0, None)
        z = (pick_number - player_adps) / adp_stds
        weights = np.exp(-0.5 * z * z)
        weights[~available] = 0.0
        if strategy == STRATEGY_NEED_WEIGHTED_ADP:
            need_weight: float = params[0]
            min_need_factor: float = params[1]
            late_round_fade: float = params[2]
            fade = max(0.0, 1.0 - late_round_fade * pick_number / total_picks)
            effective_weight = need_weight * fade
            slot_counts = roster_slots.astype(np.float64)
            # Gradual need ratio per position: max(0, (slots - count) / slots)
            need_ratios = np.maximum(
                0.0,
                (slot_counts - mgr_roster_counts.astype(np.float64)) / np.maximum(slot_counts, 1.0),
            )
            position_need_factors = np.maximum(min_need_factor, need_ratios)
            position_need_factors = np.where(roster_slots > 0, position_need_factors, min_need_factor)
            need_factors = position_need_factors[player_positions]  # broadcast to player level
            weights *= 1.0 - effective_weight + effective_weight * need_factors
            weights[~available] = 0.0
        total_weight = weights.sum()
        if total_weight == 0.0:
            return int(rng.choice(np.where(available)[0]))
        return int(rng.choice(len(player_adps), p=weights / total_weight))
    # STRATEGY_GREEDY_VOR
    vor = player_points - replacement_levels[player_positions]
    needs_more = mgr_roster_counts < roster_slots  # bool[P]
    needed_player_mask = needs_more[player_positions] & available
    pool = needed_player_mask if needed_player_mask.any() else available
    vor[~pool] = -np.inf
    return int(np.argmax(vor))


def _score_lineup(
    user_mask: np.ndarray,
    player_points: np.ndarray,
    player_positions: np.ndarray,
    roster_slots: np.ndarray,
    flex_positions: np.ndarray,
    flex_slots: int,
) -> float:
    """Score the user's final lineup using greedy optimal starter selection.

    Fills dedicated positional slots first (highest projected points), then
    fills FLEX slots from remaining flex-eligible players.  Matches the logic
    of :func:`~gridiron_yampylytics.ffb.evaluation.roster_evaluator.optimize_lineup`
    but operates entirely on numpy arrays.

    :param user_mask: True for every player on the user's final roster.
        shape (N,) bool.
    :param player_points: Projected points per player.  shape (N,) float64.
    :param player_positions: Position index per player.  shape (N,) int32.
    :param roster_slots: Dedicated starter slots per position.  shape (P,) int32.
    :param flex_positions: Position indices eligible for FLEX.  shape (F,) int32.
    :param flex_slots: Number of FLEX starter spots.
    :return: Total projected points of the optimal starting lineup.
    """
    used = np.zeros(len(user_mask), dtype=bool)
    total = 0.0
    for pos_idx, slots in enumerate(roster_slots):
        if slots == 0:
            continue
        pool = user_mask & ~used & (player_positions == pos_idx)
        n_available = int(pool.sum())
        if n_available == 0:
            continue
        n_to_take = min(int(slots), n_available)
        if n_to_take >= n_available:
            top_idxs = np.where(pool)[0]
        else:
            pts = np.where(pool, player_points, -np.inf)
            top_idxs = np.argpartition(pts, -n_to_take)[-n_to_take:]
        total += float(player_points[top_idxs].sum())
        used[top_idxs] = True
    if flex_slots > 0 and len(flex_positions) > 0:
        flex_eligible = np.isin(player_positions, flex_positions)
        pool = user_mask & ~used & flex_eligible
        n_available = int(pool.sum())
        if n_available > 0:
            n_to_take = min(flex_slots, n_available)
            if n_to_take >= n_available:
                top_idxs = np.where(pool)[0]
            else:
                pts = np.where(pool, player_points, -np.inf)
                top_idxs = np.argpartition(pts, -n_to_take)[-n_to_take:]
            total += float(player_points[top_idxs].sum())
    return total


def simulate_batch(
    snapshot: SimSnapshot,
    opponent_strategy: int,
    opponent_params: np.ndarray,
    user_strategy: int,
    user_params: np.ndarray,
    n_simulations: int,
    rng: np.random.Generator,
) -> tuple[float, float]:
    """Run all simulations for one candidate and return mean and std roster scores.

    Operates entirely on the pre-flattened arrays in ``snapshot``.  The outer
    loop runs ``n_simulations`` times; the inner pick loop runs
    ``len(snapshot.pick_manager_idxs)`` times.  No Python domain objects or
    dict lookups occur inside either loop.

    :param snapshot: Pre-built :class:`~gridiron_yampylytics.ffb.simulation.snapshot.SimSnapshot`
        for the candidate being evaluated.
    :param opponent_strategy: Strategy code for opponent picks.
    :param opponent_params: Parameter array for the opponent strategy.
    :param user_strategy: Strategy code for the user's within-simulation picks.
    :param user_params: Parameter array for the user strategy.
    :param n_simulations: Number of complete draft simulations to run.
    :param rng: NumPy random generator (seeded per candidate for reproducibility).
    :return: ``(mean_score, std_score)`` of final roster projected points across
        all simulations.
    """
    scores = np.empty(n_simulations, dtype=np.float64)
    candidate_pos = snapshot.player_positions[snapshot.candidate_idx]
    for sim_i in range(n_simulations):
        available = snapshot.available_mask.copy()
        available[snapshot.candidate_idx] = False
        roster_counts = snapshot.roster_counts_init.copy()
        roster_counts[snapshot.user_manager_idx, candidate_pos] += 1
        user_mask = snapshot.user_initial_mask.copy()
        user_mask[snapshot.candidate_idx] = True
        for pick_i in range(len(snapshot.pick_manager_idxs)):
            mgr_idx = snapshot.pick_manager_idxs[pick_i]
            is_user = snapshot.pick_is_user[pick_i]
            strategy = user_strategy if is_user else opponent_strategy
            params = user_params if is_user else opponent_params
            pick_num = snapshot.current_pick + pick_i + 1
            pick_idx = _sample_pick(
                strategy, params,
                snapshot.player_adps, snapshot.player_adp_stds,
                snapshot.player_points, snapshot.player_positions,
                roster_counts[mgr_idx], snapshot.roster_slots,
                snapshot.replacement_levels, available,
                pick_num, snapshot.total_picks, rng,
            )
            roster_counts[mgr_idx, snapshot.player_positions[pick_idx]] += 1
            available[pick_idx] = False
            if is_user:
                user_mask[pick_idx] = True
        scores[sim_i] = _score_lineup(
            user_mask, snapshot.player_points, snapshot.player_positions,
            snapshot.roster_slots, snapshot.flex_positions, snapshot.flex_slots,
        )
    return float(np.mean(scores)), float(np.std(scores))
