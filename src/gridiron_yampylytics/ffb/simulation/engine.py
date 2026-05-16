"""Monte Carlo draft simulation engine for YampGM.

Evaluates candidate draft picks by simulating N complete drafts from the
current state.  Candidates are evaluated concurrently via a persistent
:class:`concurrent.futures.ProcessPoolExecutor`; within each worker the draft
state is first flattened into a :class:`~gridiron_yampylytics.ffb.simulation.snapshot.SimSnapshot`
and then simulated entirely in numpy via
:func:`~gridiron_yampylytics.ffb.simulation.kernels.simulate_batch` — no
Python dict lookups or list rebuilds occur inside the hot loop.

The recommended pick is the candidate with the highest mean final roster
quality (total projected points of the optimal starting lineup) across all
simulations.  Standard deviation is also returned as a risk/variance signal.
"""
import threading
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
import numpy as np
from gridiron_yampylytics.ffb.models.draft import DraftState
from gridiron_yampylytics.ffb.models.player import NFLPlayer, Position
from gridiron_yampylytics.ffb.simulation.kernels import simulate_batch
from gridiron_yampylytics.ffb.simulation.pick_model import GreedyVorPickModel, NeedWeightedADPModel, PickModel, WeightedScorerPickModel
from gridiron_yampylytics.ffb.simulation.snapshot import SimSnapshot


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


def _simulate_candidate(
    draft_state: DraftState,
    candidate: NFLPlayer,
    replacement_levels: dict[Position, float],
    n_simulations: int,
    seed: int | None,
    opponent_strategy: int,
    opponent_params: np.ndarray,
    user_strategy: int,
    user_params: np.ndarray,
) -> SimulationResult:
    """Run all simulations for one candidate and return the aggregated result.

    Module-level so it can be pickled for :class:`ProcessPoolExecutor` workers.
    Builds a :class:`~gridiron_yampylytics.ffb.simulation.snapshot.SimSnapshot`
    from the draft state, then delegates to
    :func:`~gridiron_yampylytics.ffb.simulation.kernels.simulate_batch` which
    runs entirely on numpy arrays.

    :param draft_state: Current draft state snapshot.
    :param candidate: Player the user takes at their next pick.
    :param replacement_levels: Pre-computed VOR replacement levels.
    :param n_simulations: Number of simulations to run.
    :param seed: RNG seed for reproducibility; ``None`` = non-deterministic.
    :param opponent_strategy: Strategy code for opponent picks (see
        :mod:`~gridiron_yampylytics.ffb.simulation.kernels`).
    :param opponent_params: Parameter array for the opponent strategy.
    :param user_strategy: Strategy code for the user's within-simulation picks.
    :param user_params: Parameter array for the user strategy.
    :return: :class:`SimulationResult` with mean/std roster scores.
    """
    rng = np.random.default_rng(seed)
    snapshot = SimSnapshot.from_draft_state(draft_state, candidate, replacement_levels)
    mean_score, std_score = simulate_batch(
        snapshot,
        opponent_strategy, opponent_params,
        user_strategy, user_params,
        n_simulations, rng,
    )
    return SimulationResult(
        candidate=candidate,
        mean_score=mean_score,
        std_score=std_score,
        n_simulations=n_simulations,
    )


class DraftSimulator:
    """Monte Carlo draft simulation engine with parallel candidate evaluation.

    For each candidate player, simulates N complete drafts from the current
    state and computes the mean final roster quality.  Candidate simulations
    run concurrently in a persistent :class:`ProcessPoolExecutor`; each worker
    process receives a copy of the draft state and its own seeded RNG so
    results are independent and reproducible.

    The simulation hot path operates entirely on numpy arrays (via
    :func:`~gridiron_yampylytics.ffb.simulation.kernels.simulate_batch`) —
    no Python dict lookups or list rebuilds occur per pick.  Pick model
    behaviour is serialised to ``(strategy_code, params)`` pairs at
    construction time via :meth:`~gridiron_yampylytics.ffb.simulation.pick_model.PickModel.to_sim_params`.

    The pool is created lazily on first use and reused across all
    :meth:`recommend` calls for the lifetime of this instance.  Call
    :meth:`shutdown` explicitly when the session ends to release worker
    processes immediately; :meth:`__del__` provides a fallback for GC cleanup.

    :param opponent_model: Pick model for opposing managers. Defaults to
        :class:`~gridiron_yampylytics.ffb.simulation.pick_model.NeedWeightedADPModel`.
    :param user_model: Pick model for the user's within-simulation picks. Defaults
        to :class:`~gridiron_yampylytics.ffb.simulation.pick_model.GreedyVorPickModel`.
    :param n_simulations: Simulations per candidate. Defaults to 200.
    :param seed: Random seed for reproducibility. ``None`` = non-deterministic.
    :param n_workers: Worker processes for candidate parallelism. ``None`` uses
        :func:`os.cpu_count` (default :class:`ProcessPoolExecutor` behaviour).
        Cap this on machines where you need CPU headroom for other tasks.
    """

    def __init__(
        self,
        opponent_model: PickModel | None = None,
        user_model: PickModel | None = None,
        n_simulations: int = 200,
        seed: int | None = None,
        n_workers: int | None = None,
    ) -> None:
        """Initialise the simulator.

        :param opponent_model: Opponent pick model. ``None`` uses :class:`NeedWeightedADPModel`.
        :param user_model: User sim pick model. ``None`` uses :class:`GreedyVorPickModel`.
        :param n_simulations: Simulations per candidate.
        :param seed: Random seed. ``None`` = non-deterministic.
        :param n_workers: Worker process count. ``None`` = :func:`os.cpu_count`.
        """
        resolved_opponent = opponent_model or NeedWeightedADPModel()
        resolved_user = user_model or WeightedScorerPickModel()
        self._opponent_strategy, self._opponent_params = resolved_opponent.to_sim_params()
        self._user_strategy, self._user_params = resolved_user.to_sim_params()
        self.n_simulations = n_simulations
        self.rng = np.random.default_rng(seed)
        self._n_workers = n_workers
        self._executor: ProcessPoolExecutor | None = None

    @property
    def _pool(self) -> ProcessPoolExecutor:
        """Lazily-initialised process pool, reused across :meth:`recommend` calls.

        :return: The active :class:`ProcessPoolExecutor`.
        """
        if self._executor is None:
            self._executor = ProcessPoolExecutor(max_workers=self._n_workers)
        return self._executor

    def shutdown(self) -> None:
        """Shut down the process pool, releasing worker processes immediately.

        Safe to call multiple times. Called automatically by :meth:`__del__` if
        not called explicitly, but explicit shutdown is preferred when the owning
        session ends so workers are released before garbage collection.
        """
        if self._executor is not None:
            self._executor.shutdown(wait=False)
            self._executor = None

    def __del__(self) -> None:
        self.shutdown()

    def simulate(
        self,
        draft_state: DraftState,
        candidate: NFLPlayer,
        replacement_levels: dict[Position, float],
    ) -> SimulationResult:
        """Evaluate a single candidate via sequential Monte Carlo simulation.

        Runs all simulations in the calling thread — intended for single-candidate
        evaluation and testing.  For multi-candidate ranking use :meth:`recommend`,
        which parallelises across the candidate pool.

        :param draft_state: Current draft state snapshot.
        :param candidate: Player to evaluate as the user's next pick.
        :param replacement_levels: Pre-computed VOR replacement levels.
        :return: :class:`SimulationResult` with mean and std roster scores.
        """
        seed = int(self.rng.integers(2**63))
        return _simulate_candidate(
            draft_state, candidate, replacement_levels,
            self.n_simulations, seed,
            self._opponent_strategy, self._opponent_params,
            self._user_strategy, self._user_params,
        )

    def recommend(
        self,
        draft_state: DraftState,
        candidates: list[NFLPlayer],
        replacement_levels: dict[Position, float],
        cancel_event: threading.Event | None = None,
    ) -> list[SimulationResult] | None:
        """Rank candidates by expected final roster quality using parallel evaluation.

        Submits one task per candidate to the process pool and collects results
        via :func:`~concurrent.futures.as_completed`.  When ``cancel_event`` is
        set, any pending (not yet started) futures are cancelled and ``None`` is
        returned so the caller can discard the stale computation.

        :param draft_state: Current draft state snapshot.
        :param candidates: Players to evaluate.
        :param replacement_levels: Pre-computed VOR replacement levels.
        :param cancel_event: Optional :class:`threading.Event`. When set, cancels
            pending futures and returns ``None``. ``None`` disables cancellation.
        :return: :class:`SimulationResult` list sorted by ``mean_score`` descending,
            ``None`` if cancelled, or an empty list if ``candidates`` is empty.
        """
        if not candidates:
            return []
        seeds = [int(x) for x in self.rng.integers(2**63, size=len(candidates))]
        futures = []
        for c, s in zip(candidates, seeds):
            futures.append(self._pool.submit(
                _simulate_candidate,
                draft_state, c, replacement_levels,
                self.n_simulations, s,
                self._opponent_strategy, self._opponent_params,
                self._user_strategy, self._user_params,
            ))
        results = []
        for future in as_completed(futures):
            if cancel_event is not None and cancel_event.is_set():
                for f in futures:
                    f.cancel()
                return None
            results.append(future.result())
        results.sort(key=lambda r: r.mean_score, reverse=True)
        return results
