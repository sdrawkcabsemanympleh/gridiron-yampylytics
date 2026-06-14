"""In-memory session registry and broadcast utilities for YampGM API.

Holds all active :class:`SessionContext` instances keyed by ``draft_id``.
The registry is process-local and resets on server restart — appropriate for
a single-user local tool, but would need a persistent backing store for a
shared deployment.
"""
import asyncio
from dataclasses import dataclass, field
from fastapi import WebSocket
from gridiron_yampylytics.ffb.data.sleeper import SleeperClient
from gridiron_yampylytics.ffb.session import DraftSession, EnrichedResult


@dataclass
class SessionContext:
    """All mutable runtime state for one active draft session.

    :param draft_id: Sleeper draft identifier.
    :param session: The core draft session state machine.
    :param sleeper_client: Sleeper API client for this session.
    :param clients: Currently connected frontend WebSocket connections.
        Stale connections are pruned on the next broadcast.
    :param reco_task: In-flight asyncio task running recommendation computation,
        or ``None`` when idle.  Stored so callers can check whether a computation
        is already running for the current pick.
    :param last_recommendations: Most recently completed recommendation result list,
        cached for push-on-connect to late-joining clients.
    :param last_recommendations_for_pick: The ``current_pick`` value that
        ``last_recommendations`` was computed for; used to detect stale cache.
    :param listener_task: Background asyncio task running the Sleeper WS
        listener.  Cancelled when the session is deleted.
    :param shutdown: Set to ``True`` before cancelling ``listener_task`` so
        the listener loop can distinguish intentional shutdown from transient
        connection errors.
    """
    draft_id: str
    session: DraftSession
    sleeper_client: SleeperClient
    clients: list[WebSocket] = field(default_factory=list)
    reco_task: asyncio.Task | None = None
    last_recommendations: list[EnrichedResult] | None = None
    last_recommendations_for_pick: int | None = None
    listener_task: asyncio.Task | None = None
    shutdown: bool = False


_sessions: dict[str, SessionContext] = {}


def get_context(draft_id: str) -> SessionContext | None:
    """Retrieve an active session context by draft ID.

    :param draft_id: Sleeper draft identifier.
    :return: :class:`SessionContext` or ``None`` if no session exists.
    """
    return _sessions.get(draft_id)


def register_context(ctx: SessionContext) -> None:
    """Store a new session context, replacing any existing one for the same draft.

    :param ctx: The session context to register.
    """
    _sessions[ctx.draft_id] = ctx


def remove_context(draft_id: str) -> SessionContext | None:
    """Remove and return a session context.

    :param draft_id: Sleeper draft identifier.
    :return: The removed :class:`SessionContext`, or ``None`` if not found.
    """
    return _sessions.pop(draft_id, None)


def all_draft_ids() -> list[str]:
    """Return all currently registered draft IDs.

    :return: List of draft ID strings.
    """
    return list(_sessions.keys())


async def broadcast(draft_id: str, payload: dict) -> None:
    """Send a JSON message to all frontend clients connected to a session.

    Clients that have disconnected are silently removed from the list.

    :param draft_id: Sleeper draft identifier.
    :param payload: JSON-serialisable dict to send.
    """
    ctx = _sessions.get(draft_id)
    if ctx is None:
        return
    dead: list[WebSocket] = []
    for ws in ctx.clients:
        try:
            await ws.send_json(payload)
        except Exception:
            dead.append(ws)
    for ws in dead:
        if ws in ctx.clients:
            ctx.clients.remove(ws)
