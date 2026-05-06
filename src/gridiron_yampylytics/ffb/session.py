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
from gridiron_yampylytics.ffb.data.sleeper import SleeperPick, resolve_pick
from gridiron_yampylytics.ffb.models.draft import DraftState
from gridiron_yampylytics.ffb.models.player import NFLPlayer, Position
from gridiron_yampylytics.ffb.scoring.scorer import WeightedLinearScorer
from gridiron_yampylytics.ffb.simulation.engine import DraftSimulator, SimulationResult


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
        Defaults to 10.
    """

    def __init__(
        self,
        initial_state: DraftState,
        player_index: dict[str, NFLPlayer],
        replacement_levels: dict[Position, float],
        simulator: DraftSimulator | None = None,
        scorer: WeightedLinearScorer | None = None,
        n_candidates: int = 10,
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

    def get_recommendations(self) -> list[SimulationResult]:
        """Compute ranked pick recommendations for the user's current turn.

        Runs :class:`~gridiron_yampylytics.ffb.scoring.scorer.WeightedLinearScorer`
        to select the top ``n_candidates`` available players, then evaluates
        each via :meth:`~gridiron_yampylytics.ffb.simulation.engine.DraftSimulator.recommend`.

        This method is CPU-bound (Monte Carlo simulation).  FastAPI callers
        should dispatch it with ``asyncio.get_event_loop().run_in_executor``
        rather than calling it directly from an async handler.

        :return: :class:`~gridiron_yampylytics.ffb.simulation.engine.SimulationResult`
            list sorted by ``mean_score`` descending.  Empty list if no players
            are available.
        """
        scored = self._scorer.score(self.state, self._replacement_levels)
        candidates = [s.player for s in scored[:self._n_candidates]]
        return self._simulator.recommend(self.state, candidates, self._replacement_levels)

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
