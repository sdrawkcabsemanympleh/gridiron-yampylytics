"""Live draft session orchestrator for YampGM.

:class:`DraftSession` is the central coordinator for a live Sleeper draft.
It holds the mutable :class:`~gridiron_yampylytics.ffb.models.draft.DraftState`,
applies incoming :class:`~gridiron_yampylytics.ffb.data.sleeper.SleeperPick`
events, and generates ranked recommendations via Monte Carlo simulation when
requested.

The session itself is interface-agnostic — a FastAPI WebSocket handler, a CLI
loop, or a test harness all interact with it through the same two entry points:

- :meth:`DraftSession.process_pick` — advance state by one pick.
- :meth:`DraftSession.get_recommendations` — score and rank available players.
"""
import logging
import threading
from dataclasses import dataclass
from gridiron_yampylytics.ffb.data.sleeper import SleeperPick, resolve_pick
from gridiron_yampylytics.ffb.models.draft import DraftState
from gridiron_yampylytics.ffb.models.player import NFLPlayer, Position
from gridiron_yampylytics.ffb.scoring.scorer import WeightedLinearScorer
from gridiron_yampylytics.ffb.simulation.engine import DraftSimulator

logger = logging.getLogger(__name__)


@dataclass
class EnrichedResult:
    """Simulation result enriched with pre-scorer component values.

    Combines :class:`~gridiron_yampylytics.ffb.simulation.engine.SimulationResult`
    output with the raw scorer signals that drove candidate selection, so the
    full recommendation context is available to API and UI layers.

    :param candidate: The player evaluated.
    :param mean_score: Mean final roster projected points across all simulations.
    :param std_score: Standard deviation of roster scores (outcome variance).
    :param n_simulations: Number of simulations run.
    :param vor: Raw VOR in fantasy points above replacement.
    :param vona: Raw VONA in fantasy points (value over next available).
    :param scarcity_score: Normalized positional scarcity in [0.0, 1.0].
    :param roster_need_score: Normalized roster need in [0.0, 1.0].
    """
    candidate: NFLPlayer
    mean_score: float
    std_score: float
    n_simulations: int
    vor: float
    vona: float
    scarcity_score: float
    roster_need_score: float


class DraftSession:
    """Live draft session — state machine and recommendation engine.

    Accepts :class:`~gridiron_yampylytics.ffb.data.sleeper.SleeperPick`
    events one at a time, resolves each to an
    :class:`~gridiron_yampylytics.ffb.models.player.NFLPlayer` from our pool,
    and applies the pick to produce the next immutable
    :class:`~gridiron_yampylytics.ffb.models.draft.DraftState`.

    Players picked in Sleeper that are not in our pool (deep handcuffs, IR
    stashes) become zero-projected-points placeholders — they land on the
    correct roster and advance the pick counter, keeping state consistent
    without crashing.

    :param initial_state: Draft state at the point where this session begins
        (typically :meth:`~gridiron_yampylytics.ffb.models.draft.DraftState.new`,
        optionally advanced by replaying existing picks via
        :meth:`process_pick`).
    :param player_index: ``sleeper_id`` → :class:`NFLPlayer` lookup built by
        :func:`~gridiron_yampylytics.ffb.data.sleeper.build_player_index`.
    :param replacement_levels: Pre-computed VOR replacement levels from
        :func:`~gridiron_yampylytics.ffb.scoring.vor.compute_replacement_levels`.
        Should be computed from the full pre-draft pool and held constant.
    :param simulator: Monte Carlo simulation engine. Defaults to
        :class:`~gridiron_yampylytics.ffb.simulation.engine.DraftSimulator`.
    :param scorer: Candidate pre-scorer. Defaults to
        :class:`~gridiron_yampylytics.ffb.scoring.scorer.WeightedLinearScorer`.
    :param n_candidates: Number of top-scored players passed to the simulator.
        Higher values improve recommendation coverage at the cost of compute time.
        Defaults to 20.
    """

    def __init__(
        self,
        initial_state: DraftState,
        player_index: dict[str, NFLPlayer],
        replacement_levels: dict[Position, float],
        simulator: DraftSimulator | None = None,
        scorer: WeightedLinearScorer | None = None,
        n_candidates: int = 20,
    ) -> None:
        """Initialise the session.

        :param initial_state: Starting draft state.
        :param player_index: ``sleeper_id`` → :class:`NFLPlayer` index.
        :param replacement_levels: Pre-computed VOR replacement levels.
        :param simulator: Simulation engine. ``None`` uses defaults.
        :param scorer: Pre-scorer for candidate selection. ``None`` uses defaults.
        :param n_candidates: Candidates forwarded to the simulator per call.
        """
        self.state: DraftState = initial_state
        self._player_index = player_index
        self._replacement_levels = replacement_levels
        self._simulator = simulator or DraftSimulator()
        self._scorer = scorer or WeightedLinearScorer()
        self._n_candidates = n_candidates

    @property
    def is_user_turn(self) -> bool:
        """Whether it is currently the user's pick.

        :return: ``True`` if the draft is not complete and the current manager
            is the user.
        """
        return not self.state.is_complete and self.state.current_manager.is_user

    @property
    def is_complete(self) -> bool:
        """Whether the draft has concluded.

        :return: Delegates to :attr:`~gridiron_yampylytics.ffb.models.draft.DraftState.is_complete`.
        """
        return self.state.is_complete

    def process_pick(self, sleeper_pick: SleeperPick) -> NFLPlayer:
        """Apply one Sleeper pick event to the current draft state.

        Resolves ``sleeper_pick`` to an :class:`NFLPlayer` via the player
        index and calls :meth:`~gridiron_yampylytics.ffb.models.draft.DraftState.apply_pick`
        to produce the next state.  If the player is not in our pool, a minimal
        placeholder with ``projected_points=0.0`` is used so that state
        remains consistent without requiring every player in the league to be
        pre-loaded.

        :param sleeper_pick: Pick event from
            :meth:`~gridiron_yampylytics.ffb.data.sleeper.SleeperClient.stream_picks`
            or :meth:`~gridiron_yampylytics.ffb.data.sleeper.SleeperClient.get_existing_picks`.
        :return: The :class:`NFLPlayer` that was applied (may be a placeholder
            when the Sleeper player is not in our pool).
        """
        player = resolve_pick(sleeper_pick, self._player_index)
        if player is None:
            player = self._make_placeholder(sleeper_pick)
        self.state = self.state.apply_pick(player)
        return player

    def get_recommendations(
        self,
        cancel_event: threading.Event | None = None,
    ) -> list[EnrichedResult] | None:
        """Compute ranked pick recommendations for the current draft state.

        Runs :class:`~gridiron_yampylytics.ffb.scoring.scorer.WeightedLinearScorer`
        to select the top ``n_candidates`` available players, then evaluates
        each via Monte Carlo simulation.  Iterates candidates one at a time so
        that a ``cancel_event`` can interrupt computation between candidates
        (used by the FastAPI layer when a new pick arrives mid-computation).

        This method is CPU-bound.  FastAPI callers should dispatch it with
        ``asyncio.get_event_loop().run_in_executor`` rather than calling it
        directly from an async handler.

        :param cancel_event: Optional :class:`threading.Event`.  When set,
            computation stops after the current candidate finishes and ``None``
            is returned to signal cancellation.  ``None`` disables cancellation.
        :return: :class:`EnrichedResult` list sorted by ``mean_score`` descending,
            or ``None`` if cancelled.  Empty list if no players are available.
        """
        scored = self._scorer.score(self.state, self._replacement_levels)
        top_scored = scored[:self._n_candidates]
        logger.info(
            "Pick %d: scoring %d candidates from %d available",
            self.state.current_pick, len(top_scored), len(self.state.available_players),
        )
        results: list[EnrichedResult] = []
        for ps in top_scored:
            if cancel_event is not None and cancel_event.is_set():
                return None
            sim = self._simulator.simulate(self.state, ps.player, self._replacement_levels)
            results.append(EnrichedResult(
                candidate=ps.player,
                mean_score=sim.mean_score,
                std_score=sim.std_score,
                n_simulations=sim.n_simulations,
                vor=ps.vor,
                vona=ps.vona,
                scarcity_score=ps.scarcity_score,
                roster_need_score=ps.roster_need_score,
            ))
        results.sort(key=lambda r: r.mean_score, reverse=True)
        if results:
            top = results[0]
            logger.info(
                "Top pick: %s %s (proj=%.0f, VOR=%.1f, VONA=%.1f, sim=%.1f)",
                top.candidate.position, top.candidate.name,
                top.candidate.projected_points, top.vor, top.vona, top.mean_score,
            )
        return results

    def _make_placeholder(self, sleeper_pick: SleeperPick) -> NFLPlayer:
        """Create a zero-value placeholder for a Sleeper player not in our pool.

        :param sleeper_pick: The unresolved pick event.
        :return: Minimal :class:`NFLPlayer` that can be applied to rosters and
            excluded from lineup optimisation due to its zero projected points.
        """
        try:
            position = Position(sleeper_pick.position)
        except ValueError:
            position = Position.QB
        raw_id = sleeper_pick.player_id or f"{sleeper_pick.position}_{sleeper_pick.team or 'UNK'}"
        return NFLPlayer(
            player_id=f"unknown_{raw_id}",
            name=f"Unknown ({sleeper_pick.position or 'UNK'})",
            position=position,
            team=sleeper_pick.team or "FA",
            projected_points=0.0,
            adp=999.0,
        )
