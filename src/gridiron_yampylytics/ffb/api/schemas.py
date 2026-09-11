"""Pydantic request and response schemas for the YampGM FastAPI layer.

These are distinct from the domain models in ``ffb/models/`` — they define
the wire format that the React frontend and API clients consume.
"""
from pydantic import BaseModel


class SessionCreateRequest(BaseModel):
    """Request body for POST /api/sessions.

    :param draft_id: Sleeper draft identifier (from the Sleeper draft URL).
    :param sleeper_user_id: Sleeper user ID of the person running YampGM.
        Used to identify which draft slot is ``is_user=True``.
    :param db_path: Path to the gridiron-yampylytics DuckDB file. Defaults to
        ``gridiron_yampylytics.db`` in the server's working directory.
    :param n_simulations: Monte Carlo simulations run per candidate. Higher
        values produce more stable rankings at the cost of compute time.
        Defaults to 500.
    :param n_candidates: Number of top pre-scored players forwarded to the
        simulator each turn. Defaults to 20.
    """
    draft_id: str
    sleeper_user_id: str
    db_path: str | None = None
    n_simulations: int = 500
    n_candidates: int = 20


class PlayerInfo(BaseModel):
    """Compact player representation for API responses.

    :param player_id: Internal yamplayer_id.
    :param name: Display name.
    :param position: Primary fantasy position string (e.g. ``"QB"``).
    :param team: NFL team abbreviation.
    :param projected_points: Full-season projected fantasy points.
    :param adp: Average draft position.
    """
    player_id: str
    name: str
    position: str
    team: str
    projected_points: float
    adp: float


class RecommendationItem(BaseModel):
    """Single ranked candidate from Monte Carlo simulation.

    :param player: The candidate player.
    :param mean_score: Mean final roster projected points across all simulations.
    :param std_score: Standard deviation of roster scores (risk signal).
    :param n_simulations: Number of simulations run.
    :param vor: Raw VOR in fantasy points above replacement.
    :param vona: Raw VONA in fantasy points (value over next available).
    :param scarcity_score: Normalized positional scarcity in [0.0, 1.0].
    :param roster_need_score: Normalized roster need in [0.0, 1.0].
    """
    player: PlayerInfo
    mean_score: float
    std_score: float
    n_simulations: int
    vor: float
    vona: float
    scarcity_score: float
    roster_need_score: float


class PickRecord(BaseModel):
    """Compact pick history entry for draft board rendering.

    :param overall_pick: 1-indexed pick number.
    :param round: Round number.
    :param pick_in_round: Position within the round.
    :param manager_id: Manager who made the pick.
    :param player_id: Internal player ID.
    :param player_name: Display name.
    :param position: Player's primary position string.
    :param team: Player's NFL team abbreviation.
    """
    overall_pick: int
    round: int
    pick_in_round: int
    manager_id: str
    player_id: str
    player_name: str
    position: str
    team: str


class SessionResponse(BaseModel):
    """Response body for POST /api/sessions and GET /api/sessions/{draft_id}.

    :param draft_id: Sleeper draft identifier.
    :param current_pick: Next pick number to be made.
    :param total_picks: Total picks in the full draft.
    :param team_count: Number of teams in the draft.
    :param user_draft_slot: The user's 1-indexed draft slot (snake position).
    :param is_user_turn: Whether it is currently the user's pick.
    :param is_complete: Whether the draft has concluded.
    :param picks_replayed: Number of existing picks replayed on session creation.
    :param picks: Full pick history so the frontend can render the draft board.
    :param user_roster: User's current roster for display.
    """
    draft_id: str
    current_pick: int
    total_picks: int
    team_count: int
    user_draft_slot: int
    is_user_turn: bool
    is_complete: bool
    picks_replayed: int = 0
    picks: list[PickRecord] = []
    user_roster: list[PlayerInfo] = []


# ---------------------------------------------------------------------------
# WebSocket push event schemas
# All WS messages have a "type" discriminator field.
# ---------------------------------------------------------------------------

class PickMadeEvent(BaseModel):
    """Pushed to all frontend clients when a pick is applied.

    :param type: Always ``"pick_made"``.
    :param overall_pick: Pick number that was just made.
    :param round: Round in which the pick occurred.
    :param pick_in_round: Position within the round.
    :param manager_id: Manager who picked.
    :param player_id: Internal player ID.
    :param player_name: Display name.
    :param position: Position string.
    :param team: NFL team abbreviation.
    :param is_user_pick: ``True`` if the user made this pick.
    :param current_pick: The NEW current pick (i.e. next pick number).
    :param is_user_turn: Whether the new current pick is the user's turn.
    :param candidates: Pre-scored top candidates for the new current pick,
        ordered by :class:`~gridiron_yampylytics.ffb.scoring.scorer.WeightedLinearScorer`
        rank.  Simulation scores are zero (``n_simulations=0``) — the frontend
        should show these immediately and replace them when a
        :class:`RecommendationsEvent` arrives.
    """
    type: str = "pick_made"
    overall_pick: int
    round: int
    pick_in_round: int
    manager_id: str
    player_id: str
    player_name: str
    position: str
    team: str
    is_user_pick: bool
    current_pick: int
    is_user_turn: bool
    candidates: list[RecommendationItem] = []


class RecommendationsEvent(BaseModel):
    """Pushed to all frontend clients after each pick with fresh recommendations.

    :param type: Always ``"recommendations"``.
    :param for_pick: The ``current_pick`` value these recommendations apply to.
        Lets the frontend discard stale events on rapid pick sequences.
    :param candidates: Ranked simulation results.
    """
    type: str = "recommendations"
    for_pick: int
    candidates: list[RecommendationItem]


class DraftCompleteEvent(BaseModel):
    """Pushed to all frontend clients when the draft finishes.

    :param type: Always ``"draft_complete"``.
    """
    type: str = "draft_complete"
