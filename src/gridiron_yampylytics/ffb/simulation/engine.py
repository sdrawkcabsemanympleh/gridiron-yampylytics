"""Monte Carlo draft simulation engine for YampGM.

Evaluates candidate draft picks by simulating N complete drafts from the current
state. Opponent picks are sampled from a
:class:`~gridiron_yampylytics.ffb.simulation.pick_model.PickModel`; the user's
subsequent picks within each simulation use a greedy VOR strategy to approximate
rational self-interested behavior without requiring a recursive scorer call.

The recommended pick is the candidate with the highest mean final roster quality
(total projected points of the optimal starting lineup) across all simulations.
Standard deviation is also returned as a risk/variance signal.
"""
from dataclasses import dataclass
import numpy as np
from gridiron_yampylytics.ffb.evaluation.roster_evaluator import score_roster
from gridiron_yampylytics.ffb.models.draft import DraftState
from gridiron_yampylytics.ffb.models.league import RosterConfig
from gridiron_yampylytics.ffb.models.manager import Manager
from gridiron_yampylytics.ffb.models.player import NFLPlayer, Position
from gridiron_yampylytics.ffb.scoring.vor import compute_vor
from gridiron_yampylytics.ffb.simulation.pick_model import ADPPickModel, PickModel


@dataclass
class SimulationResult:
    """Monte Carlo simulation result for a single candidate pick.

    :param candidate: The player evaluated as the user's next pick.
    :param mean_score: Mean final roster projected points across all simulations.
    :param std_score: Standard deviation of roster scores — a measure of outcome
        variance (risk). A risk-averse drafter may prefer lower std_score.
    :param n_simulations: Number of simulations run.
    """
    candidate: NFLPlayer
    mean_score: float
    std_score: float
    n_simulations: int


def _manager_at_pick(draft_state: DraftState, pick_number: int) -> Manager:
    """Return the Manager whose turn it is at a given overall pick number.

    Replicates the snake draft ordering logic from
    :attr:`~gridiron_yampylytics.ffb.models.draft.DraftState.current_manager`
    for an arbitrary pick number without requiring a full DraftState.

    :param draft_state: Current draft state (used for team_count and managers list).
    :param pick_number: 1-indexed overall pick number.
    :return: The Manager picking at ``pick_number``.
    """
    team_count = draft_state.league.team_count
    pick_in_round = (pick_number - 1) % team_count + 1
    round_number = (pick_number - 1) // team_count + 1
    target_slot = team_count - pick_in_round + 1 if round_number % 2 == 0 else pick_in_round
    return next(m for m in draft_state.managers if m.draft_slot == target_slot)


def _greedy_vor_pick(
    available: list[NFLPlayer],
    user_players: list[NFLPlayer],
    roster_config: RosterConfig,
    replacement_levels: dict[Position, float],
) -> NFLPlayer:
    """Select the best available player by VOR for the user's subsequent simulation picks.

    Prioritizes filling open dedicated position slots; falls back to best overall
    VOR when all dedicated slots are filled (bench picks).

    :param available: Players still on the board.
    :param user_players: Players already on the user's simulated roster.
    :param roster_config: League roster configuration.
    :param replacement_levels: Pre-computed VOR replacement levels.
    :return: Highest-VOR available player matching the user's positional needs.
    """
    dedicated: dict[Position, int] = {
        Position.QB: roster_config.qb,
        Position.RB: roster_config.rb,
        Position.WR: roster_config.wr,
        Position.TE: roster_config.te,
        Position.K: roster_config.k,
        Position.DEF: roster_config.def_,
    }
    current_counts: dict[Position, int] = {}
    for p in user_players:
        current_counts[p.position] = current_counts.get(p.position, 0) + 1
    needed = {pos for pos, slots in dedicated.items() if current_counts.get(pos, 0) < slots}
    pool = [p for p in available if p.position in needed] if needed else available
    if not pool:
        pool = available
    return max(pool, key=lambda p: compute_vor(p, replacement_levels))


class DraftSimulator:
    """Monte Carlo draft simulation engine.

    For each candidate player, simulates N complete drafts from the current state
    and computes the mean final roster quality. Opponent picks are sampled from the
    provided :class:`~gridiron_yampylytics.ffb.simulation.pick_model.PickModel`;
    the user's subsequent picks use a greedy VOR strategy.

    Available players are tracked in a dict keyed by player_id for O(1) removal
    at each simulated pick, keeping per-simulation cost proportional to the number
    of remaining picks rather than the pool size.

    :param pick_model: Opponent pick model. Defaults to :class:`ADPPickModel`.
    :param n_simulations: Simulations per candidate. Higher values reduce variance
        in the estimate at the cost of compute time. Defaults to 200.
    :param seed: Random seed for reproducibility. ``None`` gives non-deterministic
        results suitable for production use.
    """

    def __init__(
        self,
        pick_model: PickModel | None = None,
        n_simulations: int = 200,
        seed: int | None = None,
    ) -> None:
        """Initialise the simulator.

        :param pick_model: Opponent pick model. ``None`` uses :class:`ADPPickModel`.
        :param n_simulations: Simulations per candidate.
        :param seed: Random seed. ``None`` = non-deterministic.
        """
        self.pick_model: PickModel = pick_model or ADPPickModel()
        self.n_simulations = n_simulations
        self.rng = np.random.default_rng(seed)

    def _simulate_one(
        self,
        draft_state: DraftState,
        candidate: NFLPlayer,
        replacement_levels: dict[Position, float],
    ) -> float:
        """Run one complete draft simulation with the user taking ``candidate`` next.

        Uses a dict for O(1) player removal at each pick. Opponent picks are
        sampled stochastically; the user's subsequent picks are greedy by VOR.

        :param draft_state: Current draft state snapshot.
        :param candidate: Player the user takes at their next turn.
        :param replacement_levels: Pre-computed VOR replacement levels.
        :return: Final roster quality score — total projected points of the
            optimal starting lineup.
        """
        available: dict[str, NFLPlayer] = {p.player_id: p for p in draft_state.available_players}
        del available[candidate.player_id]
        user_players = list(draft_state.user_roster.players) + [candidate]
        roster_config = draft_state.league.roster
        current_pick = draft_state.current_pick + 1
        while current_pick <= draft_state.total_picks:
            manager = _manager_at_pick(draft_state, current_pick)
            available_list = list(available.values())
            if manager.is_user:
                pick = _greedy_vor_pick(available_list, user_players, roster_config, replacement_levels)
                user_players.append(pick)
            else:
                pick = self.pick_model.sample_pick(available_list, current_pick, self.rng)
            del available[pick.player_id]
            current_pick += 1
        return score_roster(user_players, roster_config)

    def simulate(
        self,
        draft_state: DraftState,
        candidate: NFLPlayer,
        replacement_levels: dict[Position, float],
    ) -> SimulationResult:
        """Evaluate a single candidate via Monte Carlo simulation.

        :param draft_state: Current draft state snapshot.
        :param candidate: Player to evaluate as the user's next pick.
        :param replacement_levels: Pre-computed VOR replacement levels.
        :return: :class:`SimulationResult` with mean and std roster scores.
        """
        scores = [
            self._simulate_one(draft_state, candidate, replacement_levels)
            for _ in range(self.n_simulations)
        ]
        return SimulationResult(
            candidate=candidate,
            mean_score=float(np.mean(scores)),
            std_score=float(np.std(scores)),
            n_simulations=self.n_simulations,
        )

    def recommend(
        self,
        draft_state: DraftState,
        candidates: list[NFLPlayer],
        replacement_levels: dict[Position, float],
    ) -> list[SimulationResult]:
        """Rank candidates by expected final roster quality.

        :param draft_state: Current draft state snapshot.
        :param candidates: Players to evaluate. Typically the top-N available
            by VOR or ADP — there is no need to evaluate every player on the board.
        :param replacement_levels: Pre-computed VOR replacement levels.
        :return: :class:`SimulationResult` list sorted by ``mean_score`` descending.
            Empty list if ``candidates`` is empty.
        """
        results = [self.simulate(draft_state, c, replacement_levels) for c in candidates]
        results.sort(key=lambda r: r.mean_score, reverse=True)
        return results
