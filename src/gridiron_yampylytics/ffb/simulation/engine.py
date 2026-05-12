"""Monte Carlo draft simulation engine for YampGM.

Evaluates candidate draft picks by simulating N complete drafts from the current
state. Opponent picks are sampled from a configurable
:class:`~gridiron_yampylytics.ffb.simulation.pick_model.PickModel`; the user's
subsequent within-simulation picks use a separate, also-configurable model that
defaults to greedy VOR.  Both models receive per-manager roster counts so that
roster-aware implementations can modulate their decisions based on current holdings.

The recommended pick is the candidate with the highest mean final roster quality
(total projected points of the optimal starting lineup) across all simulations.
Standard deviation is also returned as a risk/variance signal.
"""
from dataclasses import dataclass
import numpy as np
from gridiron_yampylytics.ffb.evaluation.roster_evaluator import score_roster
from gridiron_yampylytics.ffb.models.draft import DraftState
from gridiron_yampylytics.ffb.models.manager import Manager
from gridiron_yampylytics.ffb.models.player import NFLPlayer, Position
from gridiron_yampylytics.ffb.simulation.pick_model import GreedyVorPickModel, NeedWeightedADPModel, PickModel


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


class DraftSimulator:
    """Monte Carlo draft simulation engine.

    For each candidate player, simulates N complete drafts from the current state
    and computes the mean final roster quality. Opponent picks are sampled from the
    ``opponent_model``; the user's subsequent within-simulation picks use the
    ``user_model``.  Both models receive per-manager roster counts at each pick
    so that roster-aware implementations (e.g.
    :class:`~gridiron_yampylytics.ffb.simulation.pick_model.NeedWeightedADPModel`)
    can factor in current holdings.

    Available players are tracked in a dict keyed by player_id for O(1) removal
    at each simulated pick, keeping per-simulation cost proportional to the number
    of remaining picks rather than the pool size.

    :param opponent_model: Pick model for opposing managers. Defaults to
        :class:`~gridiron_yampylytics.ffb.simulation.pick_model.NeedWeightedADPModel`.
    :param user_model: Pick model for the user's within-simulation picks. Defaults
        to :class:`~gridiron_yampylytics.ffb.simulation.pick_model.GreedyVorPickModel`.
    :param n_simulations: Simulations per candidate. Higher values reduce variance
        in the estimate at the cost of compute time. Defaults to 200.
    :param seed: Random seed for reproducibility. ``None`` gives non-deterministic
        results suitable for production use.
    """

    def __init__(
        self,
        opponent_model: PickModel | None = None,
        user_model: PickModel | None = None,
        n_simulations: int = 200,
        seed: int | None = None,
    ) -> None:
        """Initialise the simulator.

        :param opponent_model: Opponent pick model. ``None`` uses :class:`NeedWeightedADPModel`.
        :param user_model: User sim pick model. ``None`` uses :class:`GreedyVorPickModel`.
        :param n_simulations: Simulations per candidate.
        :param seed: Random seed. ``None`` = non-deterministic.
        """
        self._opponent_model: PickModel = opponent_model or NeedWeightedADPModel()
        self._user_model: PickModel = user_model or GreedyVorPickModel()
        self.n_simulations = n_simulations
        self.rng = np.random.default_rng(seed)

    def _simulate_one(
        self,
        draft_state: DraftState,
        candidate: NFLPlayer,
        replacement_levels: dict[Position, float],
    ) -> float:
        """Run one complete draft simulation with the user taking ``candidate`` next.

        Initialises per-manager roster counts from the current draft state and
        passes them to each model call so pick selection can be roster-aware.
        Both models receive the full context kwargs; models that ignore context
        (e.g. :class:`~gridiron_yampylytics.ffb.simulation.pick_model.ADPPickModel`)
        simply discard unused kwargs.

        :param draft_state: Current draft state snapshot.
        :param candidate: Player the user takes at their next turn.
        :param replacement_levels: Pre-computed VOR replacement levels.
        :return: Final roster quality score — total projected points of the
            optimal starting lineup.
        """
        available: dict[str, NFLPlayer] = {p.player_id: p for p in draft_state.available_players}
        del available[candidate.player_id]
        roster_config = draft_state.league.roster
        total_picks = draft_state.total_picks
        roster_counts: dict[str, dict[Position, int]] = {}
        for manager_id, roster in draft_state.rosters.items():
            counts: dict[Position, int] = {}
            for p in roster.players:
                counts[p.position] = counts.get(p.position, 0) + 1
            roster_counts[manager_id] = counts
        user_id = draft_state.user_manager.manager_id
        roster_counts[user_id][candidate.position] = roster_counts[user_id].get(candidate.position, 0) + 1
        user_players = list(draft_state.user_roster.players) + [candidate]
        current_pick = draft_state.current_pick + 1
        while current_pick <= total_picks:
            manager = _manager_at_pick(draft_state, current_pick)
            available_list = list(available.values())
            manager_counts = roster_counts[manager.manager_id]
            if manager.is_user:
                pick = self._user_model.sample_pick(
                    available_list, current_pick, self.rng,
                    roster_counts=manager_counts,
                    roster_config=roster_config,
                    total_picks=total_picks,
                    replacement_levels=replacement_levels,
                )
                user_players.append(pick)
            else:
                pick = self._opponent_model.sample_pick(
                    available_list, current_pick, self.rng,
                    roster_counts=manager_counts,
                    roster_config=roster_config,
                    total_picks=total_picks,
                    replacement_levels=replacement_levels,
                )
            manager_counts[pick.position] = manager_counts.get(pick.position, 0) + 1
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
