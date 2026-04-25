"""Sleeper fantasy football API client for YampGM live draft integration.

Provides both REST and WebSocket access to Sleeper draft data:

- :class:`SleeperClient` handles draft metadata and existing picks via
  synchronous REST calls (using ``requests``), and streams live picks as an
  async generator via WebSocket (using ``websockets``).
- :func:`build_player_index` builds a ``sleeper_id`` → :class:`NFLPlayer`
  lookup that :func:`resolve_pick` uses to map incoming Sleeper picks to
  our player pool without linear scans.

Expected WebSocket message format (Sleeper API, 2025)::

    {"type": "picked", "payload": {"picks": [<pick_object>, ...]}}

Each pick object contains at minimum::

    {
        "pick_no": 1,
        "round": 1,
        "draft_slot": 1,
        "picked_by": "<user_id>",
        "player_id": "<sleeper_player_id>",
        "metadata": {"position": "QB", "team": "KC", ...}
    }

DST picks carry ``metadata.position == "DEF"``. They are resolved by
:func:`resolve_pick` via the synthetic ``"DST_{team}"`` player_id key,
since team defenses have no entry in ``ff_playerids``.
"""
import json
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from typing import Any
import requests
import websockets
from gridiron_yampylytics.ffb.models.player import NFLPlayer, Position


_BASE_REST_URL: str = "https://api.sleeper.app/v1"
_WS_URL_TEMPLATE: str = "wss://draft.sleeper.app/ws/drafts/{draft_id}"
_PICK_MESSAGE_TYPE: str = "picked"


@dataclass
class SleeperDraft:
    """Metadata for a Sleeper draft.

    :param draft_id: Sleeper draft identifier.
    :param league_id: Associated Sleeper league identifier.
    :param draft_type: Pick order format: ``"snake"``, ``"auction"``, or ``"linear"``.
    :param status: Draft lifecycle state: ``"pre_draft"``, ``"drafting"``, or
        ``"complete"``.
    :param season: NFL season year (e.g. ``2025``).
    :param draft_order: Mapping of Sleeper ``user_id`` → draft slot (1-indexed).
        Empty dict if the league has not yet set the draft order.
    :param settings: Raw Sleeper draft settings dict (team count, rounds, pick
        timer, scoring type, etc.).
    """
    draft_id: str
    league_id: str
    draft_type: str
    status: str
    season: int
    draft_order: dict[str, int]
    settings: dict[str, Any] = field(default_factory=dict)


@dataclass
class SleeperPick:
    """A single pick event from a Sleeper draft.

    :param pick_no: 1-indexed overall pick number across the whole draft.
    :param round: Round number (1-indexed).
    :param draft_slot: Draft slot of the picking team (1-indexed).
    :param picked_by: Sleeper ``user_id`` of the manager who made the pick.
    :param player_id: Sleeper player ID for the picked player. For DST picks
        this is a Sleeper-internal DST ID that does not appear in our
        ``ff_playerids`` table; use :attr:`is_dst` and :attr:`team` instead.
    :param position: Position string from Sleeper metadata (e.g. ``"QB"``,
        ``"DEF"``). Use this rather than inferring from ``player_id``.
    :param team: NFL team abbreviation from Sleeper metadata (e.g. ``"KC"``).
        Always present for DST picks; also present for most skill players.
    :param is_dst: ``True`` when ``position == "DEF"``.
    """
    pick_no: int
    round: int
    draft_slot: int
    picked_by: str
    player_id: str
    position: str
    team: str | None
    is_dst: bool


def _parse_raw_pick(raw: dict[str, Any]) -> SleeperPick:
    """Parse a single raw Sleeper pick dict into a :class:`SleeperPick`.

    Handles both REST (``/draft/{id}/picks``) and WebSocket payload objects,
    which share the same schema.

    :param raw: Raw pick dict from the Sleeper API.
    :return: Parsed :class:`SleeperPick`.
    """
    metadata: dict[str, Any] = raw.get("metadata") or {}
    position: str = str(metadata.get("position") or "")
    team: str | None = str(metadata["team"]) if metadata.get("team") else None
    return SleeperPick(
        pick_no=int(raw["pick_no"]),
        round=int(raw["round"]),
        draft_slot=int(raw["draft_slot"]),
        picked_by=str(raw.get("picked_by") or ""),
        player_id=str(raw.get("player_id") or ""),
        position=position,
        team=team,
        is_dst=position.upper() == "DEF",
    )


class SleeperClient:
    """REST and WebSocket client for Sleeper draft data.

    REST methods are synchronous and can be called from any context. The
    :meth:`stream_picks` async generator must be awaited inside an asyncio
    event loop (e.g. via ``asyncio.run`` or within an async task).

    :param timeout: HTTP request timeout in seconds for REST calls. Defaults to 10.
    """

    def __init__(self, timeout: int = 10) -> None:
        """Initialise the client.

        :param timeout: HTTP request timeout in seconds. Defaults to 10.
        """
        self._timeout = timeout

    def get_draft(self, draft_id: str) -> SleeperDraft:
        """Fetch draft metadata from the Sleeper REST API.

        :param draft_id: Sleeper draft identifier.
        :return: :class:`SleeperDraft` populated from the API response.
        :raises requests.HTTPError: On non-2xx HTTP responses.
        :raises requests.Timeout: If the request exceeds :attr:`_timeout` seconds.
        """
        url = f"{_BASE_REST_URL}/draft/{draft_id}"
        response = requests.get(url, timeout=self._timeout)
        response.raise_for_status()
        data: dict[str, Any] = response.json()
        return SleeperDraft(
            draft_id=str(data["draft_id"]),
            league_id=str(data.get("league_id") or ""),
            draft_type=str(data.get("type") or "snake"),
            status=str(data.get("status") or ""),
            season=int(data.get("season") or 0),
            draft_order={str(k): int(v) for k, v in (data.get("draft_order") or {}).items()},
            settings=dict(data.get("settings") or {}),
        )

    def get_existing_picks(self, draft_id: str) -> list[SleeperPick]:
        """Fetch all picks already made in a draft.

        Useful for initialising :class:`~gridiron_yampylytics.ffb.models.draft.DraftState`
        when connecting to an in-progress draft, so the simulation engine has
        an accurate view of who has been taken.

        :param draft_id: Sleeper draft identifier.
        :return: List of :class:`SleeperPick` ordered by ``pick_no`` ascending.
        :raises requests.HTTPError: On non-2xx HTTP responses.
        :raises requests.Timeout: If the request exceeds :attr:`_timeout` seconds.
        """
        url = f"{_BASE_REST_URL}/draft/{draft_id}/picks"
        response = requests.get(url, timeout=self._timeout)
        response.raise_for_status()
        picks_raw: list[dict[str, Any]] = response.json()
        return [_parse_raw_pick(p) for p in picks_raw]

    async def stream_picks(self, draft_id: str) -> AsyncGenerator[SleeperPick, None]:
        """Stream live pick events from the Sleeper draft WebSocket.

        Opens a persistent WebSocket connection to the Sleeper draft channel
        and yields :class:`SleeperPick` objects as picks are made. Non-pick
        messages (heartbeats, status updates, etc.) are silently discarded.
        The generator exits cleanly when the server closes the connection.

        Intended usage inside an async task::

            async for pick in client.stream_picks(draft_id):
                await handle_pick(pick)

        :param draft_id: Sleeper draft identifier.
        :yields: :class:`SleeperPick` for each pick event received over the
            WebSocket. May yield multiple picks per message if the server
            batches them (e.g. commissioner autopick).
        """
        url = _WS_URL_TEMPLATE.format(draft_id=draft_id)
        async with websockets.connect(url) as ws:
            async for message in ws:
                parsed: dict[str, Any] = json.loads(message)
                if parsed.get("type") != _PICK_MESSAGE_TYPE:
                    continue
                payload: dict[str, Any] = parsed.get("payload") or {}
                for raw_pick in payload.get("picks") or []:
                    yield _parse_raw_pick(raw_pick)


def build_player_index(players: list[NFLPlayer]) -> dict[str, NFLPlayer]:
    """Build a Sleeper-ID-keyed lookup index from a player pool.

    For skill players the key is :attr:`~NFLPlayer.sleeper_id` (when present).
    For DST players the synthetic :attr:`~NFLPlayer.player_id` (``"DST_{team}"``)
    is added as an additional key, enabling :func:`resolve_pick` to resolve
    DST picks by team abbreviation without an ``ff_playerids`` entry.

    Players with neither a ``sleeper_id`` nor a DST position are excluded; they
    cannot be matched from Sleeper pick events.

    :param players: Player pool from
        :func:`~gridiron_yampylytics.ffb.data.player_loader.load_player_pool`.
    :return: Dict mapping Sleeper-side identifier strings to
        :class:`NFLPlayer` instances. O(1) average lookup.
    """
    index: dict[str, NFLPlayer] = {}
    for p in players:
        if p.sleeper_id is not None:
            index[p.sleeper_id] = p
        if p.position == Position.DEF:
            index[p.player_id] = p  # "DST_{team}" synthetic key for DST resolution
    return index


def resolve_pick(
    pick: SleeperPick,
    player_index: dict[str, NFLPlayer],
) -> NFLPlayer | None:
    """Map a :class:`SleeperPick` to an :class:`NFLPlayer` from our player pool.

    DST resolution uses the ``"DST_{team}"`` synthetic key (e.g. ``"DST_KC"``)
    rather than :attr:`SleeperPick.player_id`, since DST entities have no entry
    in ``ff_playerids`` and therefore no ``sleeper_id`` in our pool.

    Skill players are looked up by :attr:`SleeperPick.player_id`, which must
    match a ``sleeper_id`` value indexed by :func:`build_player_index`.

    :param pick: Pick event from :meth:`SleeperClient.stream_picks` or
        :meth:`SleeperClient.get_existing_picks`.
    :param player_index: Lookup index built by :func:`build_player_index`.
    :return: Matching :class:`NFLPlayer` from our pool, or ``None`` if the
        picked player is not in our pool (e.g. unranked handcuff, IR stash).
    """
    if pick.is_dst:
        return player_index.get(f"DST_{pick.team}") if pick.team else None
    return player_index.get(pick.player_id)
