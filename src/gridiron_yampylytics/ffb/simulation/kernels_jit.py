"""Numba JIT-compiled hot-path kernels for YampGM Monte Carlo simulation.

All functions in this module are decorated ``@numba.njit(cache=True)``.  They
operate exclusively on numpy primitive arrays — no Python objects, no dict
lookups.  The public entry point is :func:`_simulate_batch_jit`, called from
:func:`~gridiron_yampylytics.ffb.simulation.kernels.simulate_batch`.

Random state is seeded externally via ``np.random.seed`` before calling
:func:`_simulate_batch_jit`.  Internally the functions use ``np.random.uniform``
and ``np.random.randint`` — the legacy numpy random API that Numba supports in
nopython mode — instead of the modern ``Generator`` API.

Numba-compatibility notes
-------------------------
* ``np.isin`` is unsupported → replaced with a boolean lookup array of size P.
* ``np.argpartition`` is unsupported → replaced with ``np.argsort`` (O(N log N)
  vs O(N), negligible for N ≤ 500 players).
* ``rng.choice(p=weights)`` is unsupported → manual ``np.cumsum`` +
  ``np.searchsorted`` + ``np.random.uniform()``.
* Nested functions / closures are unsupported → ``_norm_jit`` is a separate
  ``@numba.njit`` function called by :func:`_compute_weighted_scores_jit`.
* ``np.partition`` with negative index is replaced with ``np.sort`` to avoid
  any negative-index edge cases in nopython mode.
"""
import numba  # type: ignore[import-untyped]
import numpy as np

#: Strategy code for NeedWeightedADPModel.
STRATEGY_NEED_WEIGHTED_ADP: int = 0
#: Strategy code for GreedyVorPickModel.
STRATEGY_GREEDY_VOR: int = 1
#: Strategy code for ADPPickModel.
STRATEGY_ADP: int = 2
#: Strategy code for WeightedScorerPickModel.
STRATEGY_WEIGHTED_SCORER: int = 3


@numba.njit(cache=True)  # type: ignore[misc]
def _norm_jit(arr: np.ndarray, available: np.ndarray) -> np.ndarray:
    """Normalise ``arr`` to [0, 1] over available-player positions.

    :param arr: Raw score array.  shape (N,) float64.
    :param available: Availability mask.  shape (N,) bool.
    :return: Normalised array; unavailable positions are 0.0.  shape (N,) float64.
    """
    n = len(arr)
    out = np.zeros(n, np.float64)
    avail_vals = arr[available]
    if len(avail_vals) == 0:
        return out
    vmin = avail_vals.min()
    vmax = avail_vals.max()
    denom = vmax - vmin if vmax != vmin else 1.0
    for i in range(n):
        if available[i]:
            out[i] = (arr[i] - vmin) / denom
    return out


@numba.njit(cache=True)  # type: ignore[misc]
def _compute_weighted_scores_jit(
    player_adps: np.ndarray,
    player_points: np.ndarray,
    player_positions: np.ndarray,
    mgr_roster_counts: np.ndarray,
    roster_slots: np.ndarray,
    replacement_levels: np.ndarray,
    flex_positions: np.ndarray,
    available: np.ndarray,
    picks_until_next_user: int,
    vor_weight: float,
    vona_weight: float,
    scarcity_weight: float,
    need_weight: float,
) -> np.ndarray:
    """Vectorized composite scorer: VOR + VONA + gradient scarcity + roster need.

    :param player_adps: ADP per player.  shape (N,) float64.
    :param player_points: Projected points per player.  shape (N,) float64.
    :param player_positions: Position index per player.  shape (N,) int32.
    :param mgr_roster_counts: Position counts for the picking manager.  shape (P,) int32.
    :param roster_slots: Dedicated slots per position.  shape (P,) int32.
    :param replacement_levels: VOR replacement thresholds per position.  shape (P,) float64.
    :param flex_positions: Position indices eligible for FLEX.  shape (F,) int32.
    :param available: Availability mask.  shape (N,) bool.
    :param picks_until_next_user: Picks until user's next turn, used for VONA estimation.
    :param vor_weight: Weight for VOR component.
    :param vona_weight: Weight for VONA component.
    :param scarcity_weight: Weight for gradient scarcity component.
    :param need_weight: Weight for roster need component.
    :return: Composite score per player.  shape (N,) float64.  Unavailable players are 0.0.
    """
    n = len(player_points)
    p_count = len(roster_slots)
    vor_raw = player_points - replacement_levels[player_positions]
    slot_counts = roster_slots.astype(np.float64)
    mgr_counts = mgr_roster_counts.astype(np.float64)
    need_ratios = np.maximum(0.0, (slot_counts - mgr_counts) / np.maximum(slot_counts, 1.0))
    need_per_player = need_ratios[player_positions]
    avail_idxs = np.where(available)[0]
    likely_taken_mask = np.zeros(n, np.bool_)
    if picks_until_next_user > 0 and len(avail_idxs) > 0:
        adp_order = np.argsort(player_adps[avail_idxs])
        n_taken = min(picks_until_next_user, len(avail_idxs) - 1)
        taken_idxs = avail_idxs[adp_order[:n_taken]]
        likely_taken_mask[taken_idxs] = True
    is_flex_pos = np.zeros(p_count, np.bool_)
    for fp_i in range(len(flex_positions)):
        is_flex_pos[flex_positions[fp_i]] = True
    dedicated_full = mgr_roster_counts >= roster_slots
    use_flex_comparison = dedicated_full & is_flex_pos
    best1_pos = np.zeros(p_count, np.float64)
    best2_pos = np.zeros(p_count, np.float64)
    for p in range(p_count):
        survivor_mask = available & ~likely_taken_mask & (player_positions == p)
        survivor_pts = player_points[survivor_mask]
        if len(survivor_pts) >= 2:
            sorted_pts = np.sort(survivor_pts)
            best1_pos[p] = sorted_pts[-1]
            best2_pos[p] = sorted_pts[-2]
        elif len(survivor_pts) == 1:
            best1_pos[p] = survivor_pts[0]
    flex_survivor_mask = available & ~likely_taken_mask & is_flex_pos[player_positions]
    flex_survivor_pts = player_points[flex_survivor_mask]
    best1_flex = 0.0
    best2_flex = 0.0
    if len(flex_survivor_pts) >= 2:
        sorted_flex = np.sort(flex_survivor_pts)
        best1_flex = sorted_flex[-1]
        best2_flex = sorted_flex[-2]
    elif len(flex_survivor_pts) == 1:
        best1_flex = flex_survivor_pts[0]
    is_top_same = player_points == best1_pos[player_positions]
    comparison_same = np.where(is_top_same, best2_pos[player_positions], best1_pos[player_positions])
    is_top_flex = player_points == best1_flex
    comparison_flex = np.where(is_top_flex, best2_flex, best1_flex)
    use_flex_per_player = use_flex_comparison[player_positions]
    comparison = np.where(use_flex_per_player, comparison_flex, comparison_same)
    vona_raw = np.where(available, player_points - np.maximum(comparison, 0.0), 0.0)
    scarcity_raw = np.zeros(n, np.float64)
    for p in range(p_count):
        pos_idxs = np.where(available & (player_positions == p))[0]
        if len(pos_idxs) < 2:
            continue
        sort_order = np.argsort(player_points[pos_idxs])[::-1]
        sorted_idxs = pos_idxs[sort_order]
        pts = player_points[sorted_idxs]
        cnt = len(pts)
        slopes = np.empty(cnt, np.float64)
        slopes[0] = pts[0] - pts[1]
        slopes[cnt - 1] = pts[cnt - 2] - pts[cnt - 1]
        if cnt > 2:
            slopes[1:cnt - 1] = (pts[0:cnt - 2] - pts[2:cnt]) / 2.0
        curvatures = np.zeros(cnt, np.float64)
        if cnt > 2:
            curvatures[1:cnt - 1] = pts[0:cnt - 2] - 2.0 * pts[1:cnt - 1] + pts[2:cnt]
        raw = slopes + np.abs(curvatures)
        raw_min = raw.min()
        raw_max = raw.max()
        denom = raw_max - raw_min if raw_max != raw_min else 1.0
        for local_i in range(cnt):
            scarcity_raw[sorted_idxs[local_i]] = (raw[local_i] - raw_min) / denom
    vor_norm = _norm_jit(vor_raw, available)
    vona_norm = _norm_jit(vona_raw, available)
    scarcity_norm = _norm_jit(scarcity_raw, available)
    need_norm = _norm_jit(need_per_player, available)
    composite = vor_weight * vor_norm + vona_weight * vona_norm + scarcity_weight * scarcity_norm + need_weight * need_norm
    composite[~available] = 0.0
    return composite


@numba.njit(cache=True)  # type: ignore[misc]
def _sample_pick_jit(
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
    flex_positions: np.ndarray,
    picks_until_next_user: int,
) -> int:
    """Sample one pick using the specified strategy, operating entirely on arrays.

    Uses ``np.random.uniform`` / ``np.random.randint`` seeded externally via
    ``np.random.seed`` before the enclosing :func:`_simulate_batch_jit` call.

    :param strategy: One of the ``STRATEGY_*`` constants in this module.
    :param params: Strategy-specific float64 parameter array.
    :param player_adps: ADP per player.  shape (N,) float64.
    :param player_adp_stds: ADP std per player.  shape (N,) float64.
    :param player_points: Projected points per player.  shape (N,) float64.
    :param player_positions: Position index per player.  shape (N,) int32.
    :param mgr_roster_counts: Position counts for the picking manager.  shape (P,) int32.
    :param roster_slots: Dedicated slots per position.  shape (P,) int32.
    :param replacement_levels: VOR thresholds per position.  shape (P,) float64.
    :param available: Availability mask.  shape (N,) bool.
    :param pick_number: 1-indexed overall pick number.
    :param total_picks: Total picks in the draft.
    :param flex_positions: Position indices eligible for FLEX.  shape (F,) int32.
    :param picks_until_next_user: Picks until the user's next turn.
    :return: Index of the chosen player in the player arrays.
    """
    if strategy == STRATEGY_NEED_WEIGHTED_ADP or strategy == STRATEGY_ADP:
        adp_stds = np.maximum(player_adp_stds, 1.0)
        z = (pick_number - player_adps) / adp_stds
        weights = np.exp(-0.5 * z * z)
        weights[~available] = 0.0
        if strategy == STRATEGY_NEED_WEIGHTED_ADP:
            need_weight = params[0]
            min_need_factor = params[1]
            late_round_fade = params[2]
            fade = 1.0 - late_round_fade * pick_number / total_picks
            if fade < 0.0:
                fade = 0.0
            effective_weight = need_weight * fade
            slot_counts = roster_slots.astype(np.float64)
            mgr_counts = mgr_roster_counts.astype(np.float64)
            need_ratios = np.maximum(0.0, (slot_counts - mgr_counts) / np.maximum(slot_counts, 1.0))
            position_need_factors = np.maximum(min_need_factor, need_ratios)
            for p in range(len(roster_slots)):
                if roster_slots[p] == 0:
                    position_need_factors[p] = min_need_factor
            need_factors = position_need_factors[player_positions]
            weights = weights * (1.0 - effective_weight + effective_weight * need_factors)
            weights[~available] = 0.0
        total_weight = weights.sum()
        if total_weight == 0.0:
            avail_idxs = np.where(available)[0]
            return avail_idxs[np.random.randint(0, len(avail_idxs))]
        cumsum = np.cumsum(weights / total_weight)
        r = np.random.uniform(0.0, 1.0)
        pick = np.searchsorted(cumsum, r)
        if pick >= len(player_adps):
            pick = len(player_adps) - 1
        return pick
    if strategy == STRATEGY_WEIGHTED_SCORER:
        scores = _compute_weighted_scores_jit(
            player_adps, player_points, player_positions,
            mgr_roster_counts, roster_slots, replacement_levels,
            flex_positions, available, picks_until_next_user,
            params[0], params[1], params[2], params[3],
        )
        temperature = params[4]
        avail_idxs = np.where(available)[0]
        avail_scores = scores[avail_idxs]
        shifted = (avail_scores - avail_scores.max()) / temperature
        sampling_weights = np.exp(shifted)
        total_weight = sampling_weights.sum()
        if total_weight == 0.0:
            return avail_idxs[np.random.randint(0, len(avail_idxs))]
        cumsum = np.cumsum(sampling_weights / total_weight)
        r = np.random.uniform(0.0, 1.0)
        chosen_local = np.searchsorted(cumsum, r)
        if chosen_local >= len(avail_idxs):
            chosen_local = len(avail_idxs) - 1
        return avail_idxs[chosen_local]
    # STRATEGY_GREEDY_VOR (and any unrecognised code)
    vor = player_points - replacement_levels[player_positions]
    needs_more = mgr_roster_counts < roster_slots
    needed_player_mask = needs_more[player_positions] & available
    if needed_player_mask.any():
        vor[~needed_player_mask] = -np.inf
    else:
        vor[~available] = -np.inf
    return np.argmax(vor)


@numba.njit(cache=True)  # type: ignore[misc]
def _score_lineup_jit(
    user_mask: np.ndarray,
    player_points: np.ndarray,
    player_positions: np.ndarray,
    roster_slots: np.ndarray,
    flex_positions: np.ndarray,
    flex_slots: int,
) -> float:
    """Score the user's final lineup using greedy optimal starter selection.

    Fills dedicated positional slots first (highest projected points), then fills
    FLEX slots from remaining flex-eligible players.

    :param user_mask: True for every player on the user's final roster.  shape (N,) bool.
    :param player_points: Projected points per player.  shape (N,) float64.
    :param player_positions: Position index per player.  shape (N,) int32.
    :param roster_slots: Dedicated starter slots per position.  shape (P,) int32.
    :param flex_positions: Position indices eligible for FLEX.  shape (F,) int32.
    :param flex_slots: Number of FLEX starter spots.
    :return: Total projected points of the optimal starting lineup.
    """
    n = len(user_mask)
    p_count = len(roster_slots)
    used = np.zeros(n, np.bool_)
    total = 0.0
    for pos_idx in range(p_count):
        slots = roster_slots[pos_idx]
        if slots == 0:
            continue
        pool = user_mask & ~used & (player_positions == pos_idx)
        n_available = int(pool.sum())
        if n_available == 0:
            continue
        n_to_take = int(slots) if int(slots) < n_available else n_available
        if n_to_take == n_available:
            top_idxs = np.where(pool)[0]
        else:
            pts = np.where(pool, player_points, -np.inf)
            sorted_order = np.argsort(pts)
            top_idxs = sorted_order[n - n_to_take:]
        total += float(player_points[top_idxs].sum())
        used[top_idxs] = True
    if flex_slots > 0 and len(flex_positions) > 0:
        flex_eligible_lookup = np.zeros(p_count, np.bool_)
        for fp_i in range(len(flex_positions)):
            flex_eligible_lookup[flex_positions[fp_i]] = True
        pool = user_mask & ~used & flex_eligible_lookup[player_positions]
        n_available = int(pool.sum())
        if n_available > 0:
            n_to_take = flex_slots if flex_slots < n_available else n_available
            if n_to_take == n_available:
                top_idxs = np.where(pool)[0]
            else:
                pts = np.where(pool, player_points, -np.inf)
                sorted_order = np.argsort(pts)
                top_idxs = sorted_order[n - n_to_take:]
            total += float(player_points[top_idxs].sum())
    return total


@numba.njit(cache=True)  # type: ignore[misc]
def _simulate_batch_jit(
    player_adps: np.ndarray,
    player_adp_stds: np.ndarray,
    player_points: np.ndarray,
    player_positions: np.ndarray,
    available_mask: np.ndarray,
    user_initial_mask: np.ndarray,
    pick_manager_idxs: np.ndarray,
    pick_is_user: np.ndarray,
    picks_until_next_user: np.ndarray,
    roster_counts_init: np.ndarray,
    user_manager_idx: int,
    candidate_idx: int,
    roster_slots: np.ndarray,
    flex_positions: np.ndarray,
    flex_slots: int,
    replacement_levels: np.ndarray,
    opponent_strategy: int,
    opponent_params: np.ndarray,
    user_strategy: int,
    user_params: np.ndarray,
    n_simulations: int,
    current_pick: int,
    total_picks: int,
) -> tuple:  # type: ignore[type-arg]
    """Run all simulations for one candidate; return ``(mean_score, std_score)``.

    Operates entirely on numpy arrays.  Random state must be seeded externally
    via ``np.random.seed`` before this call.

    :param player_adps: ADP per player.  shape (N,) float64.
    :param player_adp_stds: ADP std per player.  shape (N,) float64.
    :param player_points: Projected points per player.  shape (N,) float64.
    :param player_positions: Position index per player.  shape (N,) int32.
    :param available_mask: True for draftable players.  shape (N,) bool.
    :param user_initial_mask: True for user's already-drafted players.  shape (N,) bool.
    :param pick_manager_idxs: Manager row-index per remaining pick.  shape (R,) int32.
    :param pick_is_user: True when the pick belongs to the user.  shape (R,) bool.
    :param picks_until_next_user: Picks until next user turn, per pick.  shape (R,) int32.
    :param roster_counts_init: Per-manager position counts before candidate is taken.  shape (M, P) int32.
    :param user_manager_idx: Row index of the user in ``roster_counts_init``.
    :param candidate_idx: Player array index of the candidate.
    :param roster_slots: Dedicated roster slots per position.  shape (P,) int32.
    :param flex_positions: Position indices eligible for FLEX.  shape (F,) int32.
    :param flex_slots: Number of FLEX roster spots.
    :param replacement_levels: VOR replacement thresholds per position.  shape (P,) float64.
    :param opponent_strategy: Strategy code for opponent picks.
    :param opponent_params: Parameter array for the opponent strategy.
    :param user_strategy: Strategy code for the user's within-simulation picks.
    :param user_params: Parameter array for the user strategy.
    :param n_simulations: Number of simulations to run.
    :param current_pick: Current overall pick number (candidate is taken here).
    :param total_picks: Total picks in the full draft.
    :return: ``(mean_score, std_score)`` of final roster projected points.
    """
    scores = np.empty(n_simulations, np.float64)
    candidate_pos = player_positions[candidate_idx]
    n_picks = len(pick_manager_idxs)
    for sim_i in range(n_simulations):
        available = available_mask.copy()
        available[candidate_idx] = False
        roster_counts = roster_counts_init.copy()
        roster_counts[user_manager_idx, candidate_pos] += 1
        user_mask = user_initial_mask.copy()
        user_mask[candidate_idx] = True
        for pick_i in range(n_picks):
            mgr_idx = pick_manager_idxs[pick_i]
            is_user = pick_is_user[pick_i]
            pick_num = current_pick + pick_i + 1
            strategy = user_strategy if is_user else opponent_strategy
            params = user_params if is_user else opponent_params
            picks_left = int(picks_until_next_user[pick_i])
            pick_idx = _sample_pick_jit(
                strategy, params,
                player_adps, player_adp_stds, player_points, player_positions,
                roster_counts[mgr_idx], roster_slots, replacement_levels, available,
                pick_num, total_picks, flex_positions, picks_left,
            )
            roster_counts[mgr_idx, player_positions[pick_idx]] += 1
            available[pick_idx] = False
            if is_user:
                user_mask[pick_idx] = True
        scores[sim_i] = _score_lineup_jit(
            user_mask, player_points, player_positions,
            roster_slots, flex_positions, flex_slots,
        )
    return np.mean(scores), np.std(scores)
