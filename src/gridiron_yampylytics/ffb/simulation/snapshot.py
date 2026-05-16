"""SimSnapshot: flat numpy representation of draft state for vectorized simulation.

:class:`SimSnapshot` is the transformation boundary between the rich OO domain
models (:class:`~gridiron_yampylytics.ffb.models.draft.DraftState`,
:class:`~gridiron_yampylytics.ffb.models.player.NFLPlayer`, etc.) and the
numpy hot loop in :mod:`~gridiron_yampylytics.ffb.simulation.kernels`.

The factory :meth:`SimSnapshot.from_draft_state` flattens a draft state into
contiguous numpy arrays once per recommendation call.  From that point on the
simulation runs entirely on primitive arrays — no Python dict lookups, no
list rebuilds, no per-pick object attribute access.

Player array layout::

    indices 0..A-1    — available players  (available_mask[i] = True)
    indices A..A+E-1  — user's existing roster  (user_initial_mask[i] = True)

Where ``A = len(available_players)`` and ``E = len(user_roster.players)``.
Existing user picks are included so the final lineup scorer can evaluate the
complete final roster without special-casing them.
"""
import numpy as np
from dataclasses import dataclass
from gridiron_yampylytics.ffb.models.draft import DraftState
from gridiron_yampylytics.ffb.models.player import NFLPlayer, Position

#: Stable Position → integer index mapping.  Order follows enum declaration:
#: QB=0, RB=1, WR=2, TE=3, K=4, DEF=5.
POSITION_INDEX: dict[Position, int] = {pos: i for i, pos in enumerate(Position)}

#: Number of distinct fantasy positions.
N_POSITIONS: int = len(Position)

#: Attribute name on RosterConfig for each Position's dedicated slot count.
_ROSTER_SLOT_ATTR: dict[Position, str] = {
    Position.QB: "qb",
    Position.RB: "rb",
    Position.WR: "wr",
    Position.TE: "te",
    Position.K: "k",
    Position.DEF: "def_",
}


def _snake_manager_idx(
    pick_number: int,
    team_count: int,
    slot_to_idx: list[int],
) -> int:
    """Return the manager array row index whose turn it is at ``pick_number``.

    Replicates snake draft ordering without requiring a full DraftState
    object — uses a precomputed slot→row-index list for O(1) lookup.

    :param pick_number: 1-indexed overall pick number.
    :param team_count: Number of teams in the draft.
    :param slot_to_idx: List indexed by draft slot (1-indexed; slot ``k`` is
        at position ``k``) mapping to the manager's row index in
        ``roster_counts``.  Index 0 is unused.
    :return: Row index into the manager dimension of ``roster_counts``.
    """
    pick_in_round = (pick_number - 1) % team_count + 1
    round_number = (pick_number - 1) // team_count + 1
    target_slot = team_count - pick_in_round + 1 if round_number % 2 == 0 else pick_in_round
    return slot_to_idx[target_slot]


@dataclass
class SimSnapshot:
    """Flat, numpy-ready representation of draft state for one candidate evaluation.

    All per-player arrays are indexed over the combined pool (available players
    0..A-1 followed by the user's existing picks A..A+E-1).  The simulation
    hot loop in :mod:`~gridiron_yampylytics.ffb.simulation.kernels` operates
    exclusively on these arrays — no Python objects or dict lookups inside the
    per-simulation loop.

    Build via :meth:`from_draft_state`; do not construct directly.

    :param player_adps: ADP per player.  shape (N,) float64.
    :param player_adp_stds: ADP standard deviation per player.  shape (N,) float64.
    :param player_points: Season projected PPR points per player.  shape (N,) float64.
    :param player_positions: :data:`POSITION_INDEX` integer per player.
        shape (N,) int32.
    :param available_mask: True for players still available to draft.
        shape (N,) bool.
    :param user_initial_mask: True for the user's already-drafted players
        (not including the candidate; that is applied at simulation start).
        shape (N,) bool.
    :param pick_manager_idxs: Manager row-index for each remaining pick,
        precomputed from snake draft order.  shape (remaining_picks,) int32.
    :param pick_is_user: True when the corresponding pick belongs to the user.
        shape (remaining_picks,) bool.
    :param roster_counts_init: Per-manager position counts before the candidate
        is applied.  shape (M, P) int32.
    :param user_manager_idx: Row in ``roster_counts_init`` for the user.
    :param candidate_idx: Index in the player arrays for the candidate player.
    :param roster_slots: Dedicated roster slots per position.  shape (P,) int32.
        Ordered by :data:`POSITION_INDEX` (QB=0 … DEF=5).
    :param flex_positions: Position indices eligible for the FLEX slot(s).
        shape (flex_count,) int32.
    :param flex_slots: Number of FLEX roster spots.
    :param replacement_levels: VOR replacement projected-points threshold per
        position.  Ordered by :data:`POSITION_INDEX`.  shape (P,) float64.
    :param picks_until_next_user: For each remaining pick, the number of picks
        between that pick and the next user pick.  Used by
        :data:`~gridiron_yampylytics.ffb.simulation.kernels.STRATEGY_WEIGHTED_SCORER`
        to estimate VONA at user pick turns.  shape (remaining_picks,) int32.
    :param total_picks: Total picks in the full draft.
    :param current_pick: The pick number at which the candidate is taken.
    """
    player_adps: np.ndarray
    player_adp_stds: np.ndarray
    player_points: np.ndarray
    player_positions: np.ndarray
    available_mask: np.ndarray
    user_initial_mask: np.ndarray
    pick_manager_idxs: np.ndarray
    pick_is_user: np.ndarray
    picks_until_next_user: np.ndarray
    roster_counts_init: np.ndarray
    user_manager_idx: int
    candidate_idx: int
    roster_slots: np.ndarray
    flex_positions: np.ndarray
    flex_slots: int
    replacement_levels: np.ndarray
    total_picks: int
    current_pick: int

    @classmethod
    def from_draft_state(
        cls,
        draft_state: DraftState,
        candidate: NFLPlayer,
        replacement_levels: dict[Position, float],
    ) -> "SimSnapshot":
        """Build a :class:`SimSnapshot` from a live draft state for one candidate.

        Combines available players and the user's existing picks into a single
        contiguous player array, precomputes the full snake pick sequence, and
        initialises per-manager roster counts from current rosters.

        :param draft_state: Current draft state snapshot.
        :param candidate: The player the user is evaluating as their next pick.
        :param replacement_levels: Pre-computed VOR replacement thresholds keyed
            by :class:`~gridiron_yampylytics.ffb.models.player.Position`.
        :return: :class:`SimSnapshot` ready for
            :func:`~gridiron_yampylytics.ffb.simulation.kernels.simulate_batch`.
        """
        available: list[NFLPlayer] = list(draft_state.available_players)
        user_existing: list[NFLPlayer] = list(draft_state.user_roster.players)
        all_players: list[NFLPlayer] = available + user_existing
        n_players = len(all_players)
        n_available = len(available)
        player_adps = np.array([p.adp for p in all_players], dtype=np.float64)
        player_adp_stds = np.array([p.adp_std for p in all_players], dtype=np.float64)
        player_points = np.array([p.projected_points for p in all_players], dtype=np.float64)
        player_positions = np.array(
            [POSITION_INDEX[p.position] for p in all_players], dtype=np.int32
        )
        available_mask = np.zeros(n_players, dtype=bool)
        available_mask[:n_available] = True
        user_initial_mask = np.zeros(n_players, dtype=bool)
        user_initial_mask[n_available:] = True
        candidate_idx = next(
            i for i, p in enumerate(all_players) if p.player_id == candidate.player_id
        )
        managers = draft_state.managers  # sorted by draft_slot
        manager_id_to_idx: dict[str, int] = {m.manager_id: i for i, m in enumerate(managers)}
        team_count = draft_state.league.team_count
        slot_to_idx: list[int] = [0] * (team_count + 1)  # index 0 unused
        for m in managers:
            slot_to_idx[m.draft_slot] = manager_id_to_idx[m.manager_id]
        user_manager_idx = manager_id_to_idx[draft_state.user_manager.manager_id]
        n_remaining = draft_state.total_picks - draft_state.current_pick
        pick_manager_idxs = np.empty(n_remaining, dtype=np.int32)
        pick_is_user = np.empty(n_remaining, dtype=bool)
        for i, pick_num in enumerate(
            range(draft_state.current_pick + 1, draft_state.total_picks + 1)
        ):
            mgr_idx = _snake_manager_idx(pick_num, team_count, slot_to_idx)
            pick_manager_idxs[i] = mgr_idx
            pick_is_user[i] = managers[mgr_idx].is_user
        picks_until_next_user = np.zeros(n_remaining, dtype=np.int32)
        for i in range(n_remaining):
            future = pick_is_user[i + 1:]
            if future.size > 0 and future.any():
                picks_until_next_user[i] = int(np.argmax(future))
            else:
                picks_until_next_user[i] = n_remaining - i - 1
        roster_config = draft_state.league.roster
        n_managers = len(managers)
        roster_counts_init = np.zeros((n_managers, N_POSITIONS), dtype=np.int32)
        for manager_id, roster in draft_state.rosters.items():
            mgr_idx = manager_id_to_idx[manager_id]
            for player in roster.players:
                roster_counts_init[mgr_idx, POSITION_INDEX[player.position]] += 1
        roster_slots = np.array(
            [getattr(roster_config, _ROSTER_SLOT_ATTR[pos]) for pos in Position],
            dtype=np.int32,
        )
        flex_positions = np.array(
            [POSITION_INDEX[p] for p in roster_config.flex_eligible],
            dtype=np.int32,
        )
        repl_arr = np.array(
            [replacement_levels.get(pos, 0.0) for pos in Position],
            dtype=np.float64,
        )
        return cls(
            player_adps=player_adps,
            player_adp_stds=player_adp_stds,
            player_points=player_points,
            player_positions=player_positions,
            available_mask=available_mask,
            user_initial_mask=user_initial_mask,
            pick_manager_idxs=pick_manager_idxs,
            pick_is_user=pick_is_user,
            picks_until_next_user=picks_until_next_user,
            roster_counts_init=roster_counts_init,
            user_manager_idx=user_manager_idx,
            candidate_idx=candidate_idx,
            roster_slots=roster_slots,
            flex_positions=flex_positions,
            flex_slots=roster_config.flex,
            replacement_levels=repl_arr,
            total_picks=draft_state.total_picks,
            current_pick=draft_state.current_pick,
        )
