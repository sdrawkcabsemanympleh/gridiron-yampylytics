"""Sessions router for YampGM FastAPI backend.

Endpoints:
- ``POST /api/sessions`` — create and start a live draft session.
- ``GET /api/sessions/{draft_id}`` — fetch current state (page refresh).
- ``WS /api/sessions/{draft_id}/ws`` — frontend WebSocket push stream.
- ``DELETE /api/sessions/{draft_id}`` — tear down a session.
"""
import asyncio
import logging
import threading
from pathlib import Path

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

from gridiron_yampylytics.ffb.api.schemas import (
    DraftCompleteEvent,
    PickMadeEvent,
    PickRecord,
    PlayerInfo,
    RecommendationItem,
    RecommendationsEvent,
    SessionCreateRequest,
    SessionResponse,
)
from gridiron_yampylytics.ffb.api.session_store import (
    SessionContext,
    broadcast,
    get_context,
    register_context,
    remove_context,
)
from gridiron_yampylytics.ffb.data.player_loader import load_player_pool
from gridiron_yampylytics.ffb.data.sleeper import SleeperClient, build_player_index
from gridiron_yampylytics.ffb.models.draft import DraftState
from gridiron_yampylytics.ffb.models.league import League, RosterConfig
from gridiron_yampylytics.ffb.models.manager import Manager
from gridiron_yampylytics.ffb.models.player import NFLPlayer
from gridiron_yampylytics.ffb.scoring.vor import compute_replacement_levels
from gridiron_yampylytics.ffb.session import DraftSession, EnrichedResult
from gridiron_yampylytics.ffb.simulation.engine import DraftSimulator

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _player_info(p: NFLPlayer) -> PlayerInfo:
    return PlayerInfo(
        player_id=p.player_id,
        name=p.name,
        position=str(p.position),
        team=p.team,
        projected_points=p.projected_points,
        adp=p.adp,
    )


def _roster_config_from_sleeper(settings: dict) -> RosterConfig:
    """Derive a RosterConfig from Sleeper draft settings.

    When ``settings`` includes a ``rounds`` field (the authoritative draft
    length), bench spots are back-calculated as ``rounds - total_starters`` so
    that our round count always matches Sleeper's.  Falls back to ``slots_bn``
    or a default of 6 when ``rounds`` is absent.

    :param settings: The ``settings`` dict from a :class:`~gridiron_yampylytics.ffb.data.sleeper.SleeperDraft`.
    :return: Equivalent :class:`~gridiron_yampylytics.ffb.models.league.RosterConfig`.
    """
    qb = int(settings.get("slots_qb", 1))
    rb = int(settings.get("slots_rb", 2))
    wr = int(settings.get("slots_wr", 2))
    te = int(settings.get("slots_te", 1))
    flex = int(settings.get("slots_flex", 1))
    k = int(settings.get("slots_k", 1))
    def_ = int(settings.get("slots_def", 1))
    total_starters = qb + rb + wr + te + flex + k + def_
    if settings.get("rounds"):
        bench = max(0, int(settings["rounds"]) - total_starters)
    else:
        bench = int(settings.get("slots_bn", 6))
    return RosterConfig(qb=qb, rb=rb, wr=wr, te=te, flex=flex, k=k, def_=def_, bench=bench)


def _session_response(draft_id: str, ctx: SessionContext, picks_replayed: int = 0) -> SessionResponse:
    state = ctx.session.state
    user_manager = next((m for m in state.managers if m.is_user), None)
    picks = [
        PickRecord(
            overall_pick=pk.overall_pick,
            round=pk.round_number,
            pick_in_round=pk.pick_in_round,
            manager_id=pk.manager.manager_id,
            player_id=pk.player.player_id,
            player_name=pk.player.name,
            position=str(pk.player.position),
            team=pk.player.team,
        )
        for pk in state.picks
    ]
    return SessionResponse(
        draft_id=draft_id,
        current_pick=state.current_pick,
        total_picks=state.total_picks,
        team_count=state.league.team_count,
        user_draft_slot=user_manager.draft_slot if user_manager else 1,
        is_user_turn=ctx.session.is_user_turn,
        is_complete=ctx.session.is_complete,
        picks_replayed=picks_replayed,
        picks=picks,
        user_roster=[_player_info(p) for p in state.user_roster.players],
    )


async def _compute_and_broadcast_recommendations(
    draft_id: str, for_pick: int, cancel_event: threading.Event
) -> None:
    """Run MC simulation in a thread pool and push results to all frontend clients.

    ``cancel_event`` must be captured by the caller at task-creation time.  When a
    new pick arrives the listener sets that event and replaces ``ctx.cancel_event``
    with a fresh one, orphaning this computation before it finishes.

    :param draft_id: Session to compute for.
    :param for_pick: The ``current_pick`` snapshot these recommendations target;
        used to let the frontend discard stale events on rapid pick sequences.
    :param cancel_event: Threading event captured at task-creation time; set by
        the listener when a superseding pick arrives.
    """
    ctx = get_context(draft_id)
    if ctx is None:
        return
    loop = asyncio.get_event_loop()
    results: list[SimulationResult] | None = await loop.run_in_executor(
        None,
        lambda: ctx.session.get_recommendations(cancel_event),
    )
    if results is None:  # cancelled
        return
    top = results[0] if results else None
    logger.info(
        "Broadcasting %d candidates for pick %d; top=%s proj=%.0f VOR=%.1f VONA=%.1f scarcity=%.2f need=%.2f sim=%.1f",
        len(results),
        for_pick,
        f"{top.candidate.position} {top.candidate.name}" if top else "none",
        top.candidate.projected_points if top else 0,
        top.vor if top else 0,
        top.vona if top else 0,
        top.scarcity_score if top else 0,
        top.roster_need_score if top else 0,
        top.mean_score if top else 0,
    )
    event = RecommendationsEvent(
        for_pick=for_pick,
        candidates=[
            RecommendationItem(
                player=_player_info(r.candidate),
                mean_score=r.mean_score,
                std_score=r.std_score,
                n_simulations=r.n_simulations,
                vor=r.vor,
                vona=r.vona,
                scarcity_score=r.scarcity_score,
                roster_need_score=r.roster_need_score,
            )
            for r in results
        ],
    )
    await broadcast(draft_id, event.model_dump())


async def _run_sleeper_listener(draft_id: str, picks_already_seen: int) -> None:
    """Background task: poll Sleeper for new picks, update session state, push events.

    Polls the Sleeper REST API every few seconds for new picks.  Exits cleanly
    when ``ctx.shutdown`` is set or the draft completes.

    :param draft_id: The draft to listen to.
    :param picks_already_seen: Number of picks replayed at session creation;
        polling starts from this offset to avoid re-processing them.
    """
    ctx = get_context(draft_id)
    if ctx is None:
        return
    try:
        async for sleeper_pick in ctx.sleeper_client.stream_picks(draft_id, seen_count=picks_already_seen):
            if ctx.shutdown:
                return
            # Cancel any in-progress recommendation computation
            ctx.cancel_event.set()
            ctx.cancel_event = threading.Event()
            new_cancel = ctx.cancel_event  # capture NOW before next pick replaces it
            # Apply pick to session state
            player = ctx.session.process_pick(sleeper_pick)
            state = ctx.session.state
            last_pick = state.picks[-1]
            pick_event = PickMadeEvent(
                overall_pick=last_pick.overall_pick,
                round=last_pick.round_number,
                pick_in_round=last_pick.pick_in_round,
                manager_id=last_pick.manager.manager_id,
                player_id=player.player_id,
                player_name=player.name,
                position=str(player.position),
                team=player.team,
                is_user_pick=last_pick.manager.is_user,
                current_pick=state.current_pick,
                is_user_turn=ctx.session.is_user_turn,
            )
            await broadcast(draft_id, pick_event.model_dump())
            if ctx.session.is_complete:
                await broadcast(draft_id, DraftCompleteEvent().model_dump())
                return
            if ctx.session.is_user_turn:
                asyncio.create_task(
                    _compute_and_broadcast_recommendations(draft_id, state.current_pick, new_cancel)
                )
    except Exception:
        pass  # draft complete or session torn down


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/", response_model=SessionResponse)
async def create_session(body: SessionCreateRequest) -> SessionResponse:
    """Create and start a YampGM draft session.

    Fetches draft metadata from Sleeper, loads the player pool from DuckDB,
    replays any picks already made, and starts a background WebSocket listener
    that will stream live picks to all connected frontend clients.

    :param body: Session creation parameters.
    :return: Initial session state.
    :raises HTTPException 400: If the Sleeper draft type is not ``"snake"``.
    :raises HTTPException 400: If the draft order has not been set yet.
    :raises HTTPException 409: If a session for this draft ID already exists.
    :raises HTTPException 500: On Sleeper API or DuckDB errors.
    """
    if get_context(body.draft_id) is not None:
        raise HTTPException(status_code=409, detail=f"Session for draft {body.draft_id!r} already exists.")
    try:
        client = SleeperClient()
        draft = client.get_draft(body.draft_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Sleeper API error: {exc}") from exc
    if draft.draft_type != "snake":
        raise HTTPException(status_code=400, detail=f"Only snake drafts are supported; got {draft.draft_type!r}.")
    prefetched_picks: list | None = None
    if not draft.draft_order and draft.status == "complete":
        # Sleeper omits draft_order for auto-randomised completed drafts; reconstruct from picks.
        try:
            prefetched_picks = client.get_existing_picks(body.draft_id)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Sleeper API error fetching picks: {exc}") from exc
        draft.draft_order = {p.picked_by: p.draft_slot for p in prefetched_picks if p.round == 1}
    if not draft.draft_order:
        raise HTTPException(status_code=400, detail="Draft order has not been set yet.")
    if body.sleeper_user_id not in draft.draft_order:
        raise HTTPException(
            status_code=400,
            detail=f"User {body.sleeper_user_id!r} not found in draft order.",
        )
    roster_config = _roster_config_from_sleeper(draft.settings)
    team_count = int(draft.settings.get("teams", len(draft.draft_order)))
    league = League(team_count=team_count, roster=roster_config)
    managers = [
        Manager(
            manager_id=uid,
            name=uid,
            draft_slot=slot,
            is_user=(uid == body.sleeper_user_id),
        )
        for uid, slot in draft.draft_order.items()
    ]
    # Pad missing slots with CPU placeholders (mock drafts / partial draft_order)
    filled_slots = {m.draft_slot for m in managers}
    for slot in range(1, team_count + 1):
        if slot not in filled_slots:
            managers.append(Manager(manager_id=f"cpu_{slot}", name=f"CPU {slot}", draft_slot=slot, is_user=False))
    managers.sort(key=lambda m: m.draft_slot)
    try:
        players = load_player_pool(
            db_path=Path(body.db_path) if body.db_path else None,
            season=draft.season or 2025,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Player pool load error: {exc}") from exc
    player_index = build_player_index(players)
    replacement_levels = compute_replacement_levels(players, roster_config, team_count)
    logger.info(
        "Session %s: %d players loaded, replacement levels: %s",
        body.draft_id, len(players),
        {str(k): round(v, 1) for k, v in replacement_levels.items()},
    )
    initial_state = DraftState.new(league=league, managers=managers, available_players=players)
    session = DraftSession(
        initial_state=initial_state,
        player_index=player_index,
        replacement_levels=replacement_levels,
        simulator=DraftSimulator(n_simulations=20, seed=None),
    )
    try:
        existing_picks = prefetched_picks if prefetched_picks is not None else client.get_existing_picks(body.draft_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to fetch existing picks: {exc}") from exc
    for pick in existing_picks:
        session.process_pick(pick)
    picks_replayed = len(existing_picks)
    ctx = SessionContext(
        draft_id=body.draft_id,
        session=session,
        sleeper_client=client,
    )
    register_context(ctx)
    ctx.listener_task = asyncio.create_task(_run_sleeper_listener(body.draft_id, picks_replayed))
    # Push initial recommendations if it's already the user's turn
    if session.is_user_turn:
        asyncio.create_task(
            _compute_and_broadcast_recommendations(body.draft_id, session.state.current_pick, ctx.cancel_event)
        )
    return _session_response(body.draft_id, ctx, picks_replayed=picks_replayed)


@router.get("/{draft_id}", response_model=SessionResponse)
async def get_session(draft_id: str) -> SessionResponse:
    """Fetch current session state for a page refresh or initial load.

    :param draft_id: Sleeper draft identifier.
    :return: Current session state with full pick history and user roster.
    :raises HTTPException 404: If no active session exists for this draft ID.
    """
    ctx = get_context(draft_id)
    if ctx is None:
        raise HTTPException(status_code=404, detail=f"No active session for draft {draft_id!r}.")
    return _session_response(draft_id, ctx)


@router.websocket("/{draft_id}/ws")
async def session_websocket(websocket: WebSocket, draft_id: str) -> None:
    """WebSocket endpoint for real-time draft event streaming.

    The server pushes :class:`~gridiron_yampylytics.ffb.api.schemas.PickMadeEvent`,
    :class:`~gridiron_yampylytics.ffb.api.schemas.RecommendationsEvent`, and
    :class:`~gridiron_yampylytics.ffb.api.schemas.DraftCompleteEvent` messages.
    The client only needs to keep the connection open; no messages need to be sent.

    :param websocket: The incoming WebSocket connection.
    :param draft_id: Sleeper draft identifier to subscribe to.
    """
    ctx = get_context(draft_id)
    if ctx is None:
        await websocket.close(code=4404, reason=f"No active session for draft {draft_id!r}.")
        return
    await websocket.accept()
    ctx.clients.append(websocket)
    # If it's already the user's turn when they connect, kick off fresh recommendations
    # so they don't miss events that were broadcast before the WS was established.
    if ctx.session.is_user_turn and not ctx.session.is_complete:
        asyncio.create_task(
            _compute_and_broadcast_recommendations(
                draft_id, ctx.session.state.current_pick, ctx.cancel_event
            )
        )
    try:
        while True:
            await websocket.receive_text()  # blocks; raises WebSocketDisconnect on close
    except WebSocketDisconnect:
        pass
    finally:
        if websocket in ctx.clients:
            ctx.clients.remove(websocket)


@router.delete("/{draft_id}", status_code=204)
async def delete_session(draft_id: str) -> None:
    """Tear down an active draft session.

    Cancels the Sleeper WebSocket listener and removes the session from the
    registry.  All connected frontend clients will receive no further events.

    :param draft_id: Sleeper draft identifier.
    :raises HTTPException 404: If no active session exists.
    """
    ctx = remove_context(draft_id)
    if ctx is None:
        raise HTTPException(status_code=404, detail=f"No active session for draft {draft_id!r}.")
    ctx.shutdown = True
    if ctx.listener_task is not None:
        ctx.listener_task.cancel()
