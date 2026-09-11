"""Vectorized numpy simulation kernels for YampGM Monte Carlo draft evaluation.

This module is the public interface for the simulation hot path.  The actual
computation is performed by Numba JIT-compiled functions in
:mod:`~gridiron_yampylytics.ffb.simulation.kernels_jit`; the Python-level
functions here serve as reference implementations and are **not** called in the
hot path.

:func:`simulate_batch` unpacks a :class:`~gridiron_yampylytics.ffb.simulation.snapshot.SimSnapshot`
and delegates to :func:`~gridiron_yampylytics.ffb.simulation.kernels_jit._simulate_batch_jit`.
Call :func:`warmup_jit` once at server startup to trigger Numba compilation and
persist the result to ``__pycache__`` so worker processes load the cached binary.

Pick model strategies are identified by integer codes re-exported from
:mod:`~gridiron_yampylytics.ffb.simulation.kernels_jit`:

- :data:`STRATEGY_NEED_WEIGHTED_ADP` (``0``) — roster-aware ADP sampling.
- :data:`STRATEGY_GREEDY_VOR` (``1``) — deterministic VOR-based selection.
- :data:`STRATEGY_ADP` (``2``) — pure ADP sampling without roster context.
- :data:`STRATEGY_WEIGHTED_SCORER` (``3``) — stochastic composite scorer
  (VOR + VONA + gradient scarcity + need).
"""
import logging
import numpy as np
from gridiron_yampylytics.ffb.simulation.kernels_jit import (
    STRATEGY_ADP,
    STRATEGY_GREEDY_VOR,
    STRATEGY_NEED_WEIGHTED_ADP,
    STRATEGY_WEIGHTED_SCORER,
    _simulate_batch_jit,
)
from gridiron_yampylytics.ffb.simulation.snapshot import N_POSITIONS, SimSnapshot

__all__ = [
    "STRATEGY_NEED_WEIGHTED_ADP",
    "STRATEGY_GREEDY_VOR",
    "STRATEGY_ADP",
    "STRATEGY_WEIGHTED_SCORER",
    "simulate_batch",
    "warmup_jit",
]

logger = logging.getLogger(__name__)


def _compute_weighted_scores(
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
    """Compute composite weighted scores for all players — the vectorized
    analogue of :class:`~gridiron_yampylytics.ffb.scoring.scorer.WeightedLinearScorer`.

    All four components (VOR, VONA, gradient scarcity, roster need) are computed
    from the current array state and normalized to [0.0, 1.0] before weighting.
    Unavailable players receive a score of 0.0.

    VONA is flex-aware: when the user's dedicated slots at a position are full
    and the position is flex-eligible, comparison shifts to the best surviving
    flex-eligible player rather than the best same-position player.

    :param player_adps: ADP per player.  shape (N,) float64.
    :param player_points: Projected points per player.  shape (N,) float64.
    :param player_positions: Position index per player.  shape (N,) int32.
    :param mgr_roster_counts: Current position counts for the picking manager.
        shape (P,) int32.
    :param roster_slots: Dedicated slots per position.  shape (P,) int32.
    :param replacement_levels: VOR replacement thresholds per position.
        shape (P,) float64.
    :param flex_positions: Position indices eligible for FLEX.  shape (F,) int32.
    :param available: Boolean availability mask.  shape (N,) bool.
    :param picks_until_next_user: Picks between this pick and the next user pick.
        Used by VONA to estimate which players survive to the user's next turn.
    :param vor_weight: Weight for VOR component.
    :param vona_weight: Weight for VONA component.
    :param scarcity_weight: Weight for gradient scarcity component.
    :param need_weight: Weight for roster need component.
    :return: Composite score per player.  shape (N,) float64.  Unavailable
        players are 0.0.
    """
    N = len(player_points)
    P = len(roster_slots)
    # --- VOR ---
    vor_raw = player_points - replacement_levels[player_positions]
    # --- Roster Need ---
    slot_counts = roster_slots.astype(np.float64)
    need_ratios = np.maximum(
        0.0,
        (slot_counts - mgr_roster_counts.astype(np.float64)) / np.maximum(slot_counts, 1.0),
    )
    need_per_player = need_ratios[player_positions]
    # --- VONA (flex-aware) ---
    # Identify likely-taken set: lowest-ADP available players taken before user picks again.
    avail_idxs = np.where(available)[0]
    likely_taken_mask = np.zeros(N, dtype=bool)
    if picks_until_next_user > 0 and len(avail_idxs) > 0:
        adp_order = np.argsort(player_adps[avail_idxs])
        n_taken = min(picks_until_next_user, len(avail_idxs) - 1)
        likely_taken_mask[avail_idxs[adp_order[:n_taken]]] = True
    is_flex_pos = np.zeros(P, dtype=bool)
    if len(flex_positions) > 0:
        is_flex_pos[flex_positions] = True
    dedicated_full = mgr_roster_counts >= roster_slots  # bool[P]
    use_flex_comparison = dedicated_full & is_flex_pos   # bool[P]
    # Top-2 survivors per position (top-2 handles self-exclusion: if player is
    # the best at their position, compare against the second-best instead).
    best1_pos = np.zeros(P, dtype=np.float64)
    best2_pos = np.zeros(P, dtype=np.float64)
    for p in range(P):
        survivor_pts = player_points[available & ~likely_taken_mask & (player_positions == p)]
        if len(survivor_pts) >= 2:
            top2 = np.partition(survivor_pts, -2)[-2:]
            best1_pos[p] = top2[1]
            best2_pos[p] = top2[0]
        elif len(survivor_pts) == 1:
            best1_pos[p] = survivor_pts[0]
    # Top-2 flex-eligible survivors.
    flex_survivor_pts = player_points[
        available & ~likely_taken_mask & is_flex_pos[player_positions]
    ]
    best1_flex = 0.0
    best2_flex = 0.0
    if len(flex_survivor_pts) >= 2:
        top2 = np.partition(flex_survivor_pts, -2)[-2:]
        best1_flex = top2[1]
        best2_flex = top2[0]
    elif len(flex_survivor_pts) == 1:
        best1_flex = flex_survivor_pts[0]
    # Vectorized per-player comparison: use second-best when player is the top survivor.
    is_top_same = player_points == best1_pos[player_positions]
    comparison_same = np.where(is_top_same, best2_pos[player_positions], best1_pos[player_positions])
    is_top_flex = player_points == best1_flex
    comparison_flex = np.where(is_top_flex, best2_flex, best1_flex)
    use_flex_per_player = use_flex_comparison[player_positions]
    comparison = np.where(use_flex_per_player, comparison_flex, comparison_same)
    vona_raw = np.where(available, player_points - np.maximum(comparison, 0.0), 0.0)
    # --- Gradient Scarcity ---
    scarcity_raw = np.zeros(N, dtype=np.float64)
    for p in range(P):
        pos_idxs = np.where(available & (player_positions == p))[0]
        if len(pos_idxs) < 2:
            continue
        sort_order = np.argsort(player_points[pos_idxs])[::-1]
        sorted_idxs = pos_idxs[sort_order]
        pts = player_points[sorted_idxs]
        n = len(pts)
        slopes = np.empty(n, dtype=np.float64)
        slopes[0] = pts[0] - pts[1]
        slopes[-1] = pts[-2] - pts[-1]
        if n > 2:
            slopes[1:-1] = (pts[:-2] - pts[2:]) / 2.0
        curvatures = np.zeros(n, dtype=np.float64)
        if n > 2:
            curvatures[1:-1] = pts[:-2] - 2.0 * pts[1:-1] + pts[2:]
        raw = slopes + np.abs(curvatures)
        raw_min, raw_max = raw.min(), raw.max()
        denom = raw_max - raw_min if raw_max != raw_min else 1.0
        scarcity_raw[sorted_idxs] = (raw - raw_min) / denom
    # --- Normalize each component to [0,1] across available players ---
    def _norm(arr: np.ndarray) -> np.ndarray:
        vals = arr[available]
        vmin, vmax = vals.min(), vals.max()
        denom = vmax - vmin if vmax != vmin else 1.0
        out = np.zeros(N, dtype=np.float64)
        out[available] = (arr[available] - vmin) / denom
        return out
    vor_norm = _norm(vor_raw)
    vona_norm = _norm(vona_raw)
    scarcity_norm = _norm(scarcity_raw)
    need_norm = _norm(need_per_player)
    composite = (
        vor_weight * vor_norm
        + vona_weight * vona_norm
        + scarcity_weight * scarcity_norm
        + need_weight * need_norm
    )
    composite[~available] = 0.0
    return composite


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
    flex_positions: np.ndarray,
    picks_until_next_user: int,
    rng: np.random.Generator,
) -> int:
    """Sample one pick using the specified strategy, operating entirely on arrays.

    All inputs are numpy primitives — no :class:`~gridiron_yampylytics.ffb.models.player.NFLPlayer`
    objects are accessed inside this function.  Returns the index of the chosen
    player in the player arrays.

    :param strategy: One of :data:`STRATEGY_NEED_WEIGHTED_ADP`,
        :data:`STRATEGY_GREEDY_VOR`, :data:`STRATEGY_ADP`, or
        :data:`STRATEGY_WEIGHTED_SCORER`.
    :param params: Strategy-specific float parameters.
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
    :param flex_positions: Position indices eligible for FLEX.  shape (F,) int32.
        Used by :data:`STRATEGY_WEIGHTED_SCORER` for flex-aware VONA.
    :param picks_until_next_user: Picks between this pick and the next user pick.
        Used by :data:`STRATEGY_WEIGHTED_SCORER` for VONA estimation.
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
            need_ratios = np.maximum(
                0.0,
                (slot_counts - mgr_roster_counts.astype(np.float64)) / np.maximum(slot_counts, 1.0),
            )
            position_need_factors = np.maximum(min_need_factor, need_ratios)
            position_need_factors = np.where(roster_slots > 0, position_need_factors, min_need_factor)
            need_factors = position_need_factors[player_positions]
            weights *= 1.0 - effective_weight + effective_weight * need_factors
            weights[~available] = 0.0
        total_weight = weights.sum()
        if total_weight == 0.0:
            return int(rng.choice(np.where(available)[0]))
        return int(rng.choice(len(player_adps), p=weights / total_weight))
    if strategy == STRATEGY_WEIGHTED_SCORER:
        scores = _compute_weighted_scores(
            player_adps, player_points, player_positions,
            mgr_roster_counts, roster_slots, replacement_levels,
            flex_positions, available,
            picks_until_next_user,
            vor_weight=params[0],
            vona_weight=params[1],
            scarcity_weight=params[2],
            need_weight=params[3],
        )
        temperature: float = params[4]
        avail_idxs = np.where(available)[0]
        avail_scores = scores[avail_idxs]
        shifted = (avail_scores - avail_scores.max()) / temperature
        sampling_weights = np.exp(shifted)
        total_weight = sampling_weights.sum()
        if total_weight == 0.0:
            return int(rng.choice(avail_idxs))
        return int(rng.choice(avail_idxs, p=sampling_weights / total_weight))
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
) -> tuple[float, float]:
    """Run all simulations for one candidate and return mean and std roster scores.

    Unpacks ``snapshot`` into raw numpy arrays and delegates to the Numba
    JIT-compiled :func:`~gridiron_yampylytics.ffb.simulation.kernels_jit._simulate_batch_jit`.
    Random state must be seeded externally via ``np.random.seed`` before this
    call (done by :func:`~gridiron_yampylytics.ffb.simulation.engine._simulate_candidate`).

    :param snapshot: Pre-built :class:`~gridiron_yampylytics.ffb.simulation.snapshot.SimSnapshot`
        for the candidate being evaluated.
    :param opponent_strategy: Strategy code for opponent picks.
    :param opponent_params: Parameter array for the opponent strategy.
    :param user_strategy: Strategy code for the user's within-simulation picks.
    :param user_params: Parameter array for the user strategy.
    :param n_simulations: Number of complete draft simulations to run.
    :return: ``(mean_score, std_score)`` of final roster projected points across
        all simulations.
    """
    mean_score, std_score = _simulate_batch_jit(
        snapshot.player_adps, snapshot.player_adp_stds,
        snapshot.player_points, snapshot.player_positions,
        snapshot.available_mask, snapshot.user_initial_mask,
        snapshot.pick_manager_idxs, snapshot.pick_is_user,
        snapshot.picks_until_next_user,
        snapshot.roster_counts_init,
        snapshot.user_manager_idx, snapshot.candidate_idx,
        snapshot.roster_slots, snapshot.flex_positions, snapshot.flex_slots,
        snapshot.replacement_levels,
        opponent_strategy, opponent_params,
        user_strategy, user_params,
        n_simulations,
        snapshot.current_pick, snapshot.total_picks,
    )
    return float(mean_score), float(std_score)


def warmup_jit() -> None:
    """Trigger Numba JIT compilation for the simulation hot path.

    Call once at server startup.  With ``cache=True`` on all JIT functions the
    compiled machine code is persisted to ``__pycache__``; worker processes
    spawned by :class:`~concurrent.futures.ProcessPoolExecutor` then load the
    cached binary without recompiling.

    Uses ``STRATEGY_WEIGHTED_SCORER`` for the user model so that
    :func:`~gridiron_yampylytics.ffb.simulation.kernels_jit._compute_weighted_scores_jit`
    is compiled along with all other hot-path functions in a single warmup call.
    """
    logger.info("Numba JIT warmup starting...")
    n, p, m, r = 10, 6, 2, 5
    positions = np.zeros(n, dtype=np.int32)
    positions[2] = 1  # a couple of RBs
    positions[4] = 2  # a couple of WRs
    _simulate_batch_jit(
        np.ones(n, dtype=np.float64),
        np.ones(n, dtype=np.float64),
        np.full(n, 100.0, dtype=np.float64),
        positions,
        np.ones(n, dtype=bool),
        np.zeros(n, dtype=bool),
        np.zeros(r, dtype=np.int32),
        np.zeros(r, dtype=bool),
        np.zeros(r, dtype=np.int32),
        np.zeros((m, p), dtype=np.int32),
        0, 0,
        np.ones(p, dtype=np.int32),
        np.array([1, 2], dtype=np.int32),
        1,
        np.zeros(p, dtype=np.float64),
        STRATEGY_NEED_WEIGHTED_ADP,
        np.array([0.3, 0.15, 0.7], dtype=np.float64),
        STRATEGY_WEIGHTED_SCORER,
        np.array([0.40, 0.30, 0.20, 0.10, 1.0], dtype=np.float64),
        1,
        1,
        r + 2,
    )
    logger.info("Numba JIT warmup complete.")
