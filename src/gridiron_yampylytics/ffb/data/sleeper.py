"""Sleeper fantasy football API client for YampGM draft and in-season integration.

Provides REST access to Sleeper draft data, polls for live picks, and fetches
all in-season league/roster/matchup data:

- :class:`SleeperClient` handles draft metadata and existing picks via
  synchronous REST calls (using ``requests``), and streams live picks as an
  async generator via REST polling (every :attr:`_POLL_INTERVAL_SECONDS` seconds).
- In-season methods cover users, leagues, rosters, matchups, transactions,
  trending players, and NFL state — all synchronous REST calls.
- :func:`build_player_index` builds a ``sleeper_id`` → :class:`NFLPlayer`
  lookup that :func:`resolve_pick` uses to map incoming Sleeper picks to
  our player pool without linear scans.

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
import asyncio
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from typing import Any
import requests
from gridiron_yampylytics.ffb.models.player import NFLPlayer, Position


_BASE_REST_URL: str = "https://api.sleeper.app/v1"
_POLL_INTERVAL_SECONDS: float = 0.5


# ---------------------------------------------------------------------------
# Draft dataclasses
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# In-season dataclasses
# ---------------------------------------------------------------------------

@dataclass
class SleeperUser:
    """A Sleeper platform user.

    :param user_id: Sleeper internal user identifier.
    :param username: Public username (login handle).
    :param display_name: Display name shown in the UI.
    """
    user_id: str
    username: str
    display_name: str


@dataclass
class SleeperLeagueInfo:
    """Metadata and configuration for a Sleeper fantasy league.

    :param league_id: Sleeper league identifier.
    :param name: Human-readable league name.
    :param season: NFL season year (e.g. ``2025``).
    :param status: League lifecycle state: ``"pre_draft"``, ``"drafting"``,
        ``"in_season"``, or ``"complete"``.
    :param scoring_type: Derived from ``scoring_settings.rec``:
        ``"ppr"``, ``"half_ppr"``, or ``"standard"``.
    :param total_rosters: Number of teams in the league.
    :param roster_positions: Ordered list of roster slot labels as returned
        by Sleeper (e.g. ``["QB", "RB", "RB", "WR", "FLEX", "K", "DEF",
        "BN", "BN", ...]``). Includes bench (``"BN"``), IR (``"IR"``), and
        FLEX slots.
    """
    league_id: str
    name: str
    season: int
    status: str
    scoring_type: str
    total_rosters: int
    roster_positions: list[str]


@dataclass
class SleeperRoster:
    """A single team's roster within a Sleeper league.

    :param roster_id: Sleeper-assigned roster identifier (1-indexed per league).
    :param owner_id: ``user_id`` of the manager who owns this roster.
        ``None`` for orphaned / co-managed teams with no primary owner.
    :param league_id: Parent league identifier.
    :param players: All Sleeper player IDs currently on this roster
        (starters + bench + reserve combined).
    :param starters: Player IDs locked into starting slots for the current
        or most recent week. Order matches :attr:`SleeperLeagueInfo.roster_positions`
        (excluding bench/IR slots).
    :param reserve: Player IDs placed in IR / reserve slots.
    """
    roster_id: int
    owner_id: str | None
    league_id: str
    players: list[str]
    starters: list[str]
    reserve: list[str]


@dataclass
class SleeperLeagueUser:
    """A user's identity within a specific Sleeper league.

    :param user_id: Sleeper user identifier.
    :param display_name: Sleeper account display name.
    :param team_name: Custom team name set by the manager. ``None`` if
        the manager has not set a team name.
    """
    user_id: str
    display_name: str
    team_name: str | None


@dataclass
class SleeperMatchup:
    """One side of a weekly fantasy matchup.

    Two :class:`SleeperMatchup` records share the same :attr:`matchup_id`
    within a week — they are the two opposing rosters.

    :param matchup_id: Shared identifier linking the two sides of a matchup.
    :param roster_id: Roster identifier for this side.
    :param starters: Player IDs in starting lineup slots.
    :param players: All player IDs on the active roster for this week.
    :param points: Total fantasy points scored by this roster this week.
    :param players_points: Per-player fantasy point totals keyed by Sleeper
        player ID. May be empty mid-week before games complete.
    """
    matchup_id: int
    roster_id: int
    starters: list[str]
    players: list[str]
    points: float
    players_points: dict[str, float]


@dataclass
class SleeperTransaction:
    """A single waiver claim, free agent pickup, or trade transaction.

    :param transaction_id: Sleeper transaction identifier.
    :param type: Transaction type: ``"free_agent"``, ``"waiver"``, or
        ``"trade"``.
    :param status: Processing status: ``"complete"``, ``"failed"``, or
        ``"waived"`` (outbid on waivers).
    :param adds: Mapping of Sleeper player ID → roster ID for players
        added. Empty dict if no adds (e.g. a pure drop).
    :param drops: Mapping of Sleeper player ID → roster ID for players
        dropped. Empty dict if no drops (e.g. a pure add from IR).
    :param created: Unix timestamp (milliseconds) when the transaction
        was created.
    :param week: NFL week this transaction occurred in.
    """
    transaction_id: str
    type: str
    status: str
    adds: dict[str, int]
    drops: dict[str, int]
    created: int
    week: int


@dataclass
class SleeperTrendingPlayer:
    """A player trending on the Sleeper waiver wire.

    :param player_id: Sleeper player identifier.
    :param count: Number of adds or drops in the lookback window, depending
        on which trending endpoint was called.
    """
    player_id: str
    count: int


@dataclass
class SleeperNFLState:
    """Current NFL season and week state from Sleeper.

    :param week: Current NFL week number (1-18 for regular season).
    :param season: Current NFL season year (e.g. ``2025``).
    :param season_type: Broad phase: ``"pre"``, ``"regular"``, or ``"post"``.
    :param display_week: Week number intended for display (may differ from
        :attr:`week` during bye weeks or playoffs).
    """
    week: int
    season: int
    season_type: str
    display_week: int


# ---------------------------------------------------------------------------
# Parse helpers
# ---------------------------------------------------------------------------

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


def _parse_scoring_type(scoring_settings: dict[str, Any]) -> str:
    """Derive a scoring type label from Sleeper ``scoring_settings``.

    :param scoring_settings: Raw ``scoring_settings`` dict from a Sleeper
        league or draft response.
    :return: ``"ppr"`` (rec≥1.0), ``"half_ppr"`` (rec≥0.5), or ``"standard"``.
    """
    rec = float(scoring_settings.get("rec", 1.0))
    if rec >= 1.0:
        return "ppr"
    if rec >= 0.5:
        return "half_ppr"
    return "standard"


def _parse_league_info(data: dict[str, Any]) -> SleeperLeagueInfo:
    """Parse a raw Sleeper league dict into a :class:`SleeperLeagueInfo`.

    :param data: Raw league dict from ``/league/{id}`` or
        ``/user/{id}/leagues/nfl/{season}``.
    :return: Parsed :class:`SleeperLeagueInfo`.
    """
    scoring: dict[str, Any] = dict(data.get("scoring_settings") or {})
    return SleeperLeagueInfo(
        league_id=str(data["league_id"]),
        name=str(data.get("name") or ""),
        season=int(data.get("season") or 0),
        status=str(data.get("status") or ""),
        scoring_type=_parse_scoring_type(scoring),
        total_rosters=int(data.get("total_rosters") or 0),
        roster_positions=list(data.get("roster_positions") or []),
    )


def _parse_roster(data: dict[str, Any], league_id: str) -> SleeperRoster:
    """Parse a raw Sleeper roster dict into a :class:`SleeperRoster`.

    :param data: Raw roster dict from ``/league/{id}/rosters``.
    :param league_id: Parent league identifier (not present in the roster
        payload itself).
    :return: Parsed :class:`SleeperRoster`.
    """
    return SleeperRoster(
        roster_id=int(data["roster_id"]),
        owner_id=str(data["owner_id"]) if data.get("owner_id") else None,
        league_id=league_id,
        players=list(data.get("players") or []),
        starters=list(data.get("starters") or []),
        reserve=list(data.get("reserve") or []),
    )


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

class SleeperClient:
    """REST and polling client for all Sleeper API interactions.

    Covers both draft-time (live pick streaming) and in-season (leagues,
    rosters, matchups, transactions, trending) endpoints. REST methods are
    synchronous; :meth:`stream_picks` is an async generator.

    :param timeout: HTTP request timeout in seconds for REST calls. Defaults to 10.
    """

    def __init__(self, timeout: int = 10) -> None:
        """Initialise the client.

        :param timeout: HTTP request timeout in seconds. Defaults to 10.
        """
        self._timeout = timeout

    # ------------------------------------------------------------------
    # Draft methods
    # ------------------------------------------------------------------

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

    def get_league_scoring_type(self, league_id: str) -> str:
        """Return the scoring type for a Sleeper league.

        Convenience wrapper around :meth:`get_league_info` for callers that
        only need the scoring type string.

        :param league_id: Sleeper league identifier.
        :return: One of ``"ppr"``, ``"half_ppr"``, or ``"standard"``.
        :raises requests.HTTPError: On non-2xx HTTP responses.
        :raises requests.Timeout: If the request exceeds :attr:`_timeout` seconds.
        """
        return self.get_league_info(league_id).scoring_type

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

    async def stream_picks(self, draft_id: str, seen_count: int = 0) -> AsyncGenerator[SleeperPick, None]:
        """Stream live pick events by polling the Sleeper REST API.

        Polls ``/draft/{draft_id}/picks`` every :attr:`_POLL_INTERVAL_SECONDS`
        seconds and yields new picks as they appear.  Exits when the draft
        status transitions to ``"complete"`` and no further picks arrive.

        Intended usage inside an async task::

            async for pick in client.stream_picks(draft_id):
                await handle_pick(pick)

        :param draft_id: Sleeper draft identifier.
        :param seen_count: Number of picks already processed by the caller
            (e.g. replayed at session creation). Only picks beyond this index
            are yielded.
        :yields: :class:`SleeperPick` for each new pick observed during polling.
        """
        url = f"{_BASE_REST_URL}/draft/{draft_id}/picks"
        draft_url = f"{_BASE_REST_URL}/draft/{draft_id}"
        loop = asyncio.get_event_loop()
        while True:
            picks_raw: list[dict[str, Any]] = await loop.run_in_executor(
                None,
                lambda: requests.get(url, timeout=self._timeout).json(),
            )
            for raw in picks_raw[seen_count:]:
                seen_count += 1
                yield _parse_raw_pick(raw)
            if len(picks_raw) > 0 or seen_count > 0:
                draft_data: dict[str, Any] = await loop.run_in_executor(
                    None,
                    lambda: requests.get(draft_url, timeout=self._timeout).json(),
                )
                if str(draft_data.get("status") or "") == "complete" and len(picks_raw) == seen_count:
                    return
            await asyncio.sleep(_POLL_INTERVAL_SECONDS)

    # ------------------------------------------------------------------
    # In-season methods
    # ------------------------------------------------------------------

    def get_user(self, username: str) -> SleeperUser:
        """Fetch a Sleeper user by username.

        :param username: Sleeper username (login handle, case-insensitive).
        :return: :class:`SleeperUser` with ``user_id``, ``username``, and
            ``display_name``.
        :raises requests.HTTPError: On non-2xx HTTP responses.
        :raises requests.Timeout: If the request exceeds :attr:`_timeout` seconds.
        """
        url = f"{_BASE_REST_URL}/user/{username}"
        response = requests.get(url, timeout=self._timeout)
        response.raise_for_status()
        data: dict[str, Any] = response.json()
        return SleeperUser(
            user_id=str(data["user_id"]),
            username=str(data.get("username") or username),
            display_name=str(data.get("display_name") or username),
        )

    def get_user_leagues(self, user_id: str, season: int) -> list[SleeperLeagueInfo]:
        """Fetch all fantasy football leagues for a user in a given season.

        :param user_id: Sleeper user identifier.
        :param season: NFL season year (e.g. ``2025``).
        :return: List of :class:`SleeperLeagueInfo` for every league the user
            belongs to this season, ordered as returned by Sleeper.
        :raises requests.HTTPError: On non-2xx HTTP responses.
        :raises requests.Timeout: If the request exceeds :attr:`_timeout` seconds.
        """
        url = f"{_BASE_REST_URL}/user/{user_id}/leagues/nfl/{season}"
        response = requests.get(url, timeout=self._timeout)
        response.raise_for_status()
        leagues_raw: list[dict[str, Any]] = response.json() or []
        return [_parse_league_info(raw) for raw in leagues_raw]

    def get_league_info(self, league_id: str) -> SleeperLeagueInfo:
        """Fetch metadata and configuration for a single league.

        :param league_id: Sleeper league identifier.
        :return: :class:`SleeperLeagueInfo` with scoring type, roster positions,
            and lifecycle status.
        :raises requests.HTTPError: On non-2xx HTTP responses.
        :raises requests.Timeout: If the request exceeds :attr:`_timeout` seconds.
        """
        url = f"{_BASE_REST_URL}/league/{league_id}"
        response = requests.get(url, timeout=self._timeout)
        response.raise_for_status()
        return _parse_league_info(response.json())

    def get_league_rosters(self, league_id: str) -> list[SleeperRoster]:
        """Fetch all rosters in a league.

        :param league_id: Sleeper league identifier.
        :return: One :class:`SleeperRoster` per team, in roster_id order.
        :raises requests.HTTPError: On non-2xx HTTP responses.
        :raises requests.Timeout: If the request exceeds :attr:`_timeout` seconds.
        """
        url = f"{_BASE_REST_URL}/league/{league_id}/rosters"
        response = requests.get(url, timeout=self._timeout)
        response.raise_for_status()
        rosters_raw: list[dict[str, Any]] = response.json() or []
        return [_parse_roster(raw, league_id) for raw in rosters_raw]

    def get_league_users(self, league_id: str) -> list[SleeperLeagueUser]:
        """Fetch all users (managers) in a league.

        :param league_id: Sleeper league identifier.
        :return: List of :class:`SleeperLeagueUser` with display names and
            custom team names.
        :raises requests.HTTPError: On non-2xx HTTP responses.
        :raises requests.Timeout: If the request exceeds :attr:`_timeout` seconds.
        """
        url = f"{_BASE_REST_URL}/league/{league_id}/users"
        response = requests.get(url, timeout=self._timeout)
        response.raise_for_status()
        users_raw: list[dict[str, Any]] = response.json() or []
        return [
            SleeperLeagueUser(
                user_id=str(u["user_id"]),
                display_name=str(u.get("display_name") or u["user_id"]),
                team_name=str(u["metadata"]["team_name"])
                if u.get("metadata") and u["metadata"].get("team_name")
                else None,
            )
            for u in users_raw
        ]

    def get_matchups(self, league_id: str, week: int) -> list[SleeperMatchup]:
        """Fetch matchup data for all teams in a given week.

        Two records share the same ``matchup_id`` — they are the two sides of
        one head-to-head matchup.

        :param league_id: Sleeper league identifier.
        :param week: NFL week number (1-18).
        :return: List of :class:`SleeperMatchup`, two per matchup pair.
        :raises requests.HTTPError: On non-2xx HTTP responses.
        :raises requests.Timeout: If the request exceeds :attr:`_timeout` seconds.
        """
        url = f"{_BASE_REST_URL}/league/{league_id}/matchups/{week}"
        response = requests.get(url, timeout=self._timeout)
        response.raise_for_status()
        raw_list: list[dict[str, Any]] = response.json() or []
        return [
            SleeperMatchup(
                matchup_id=int(m["matchup_id"]),
                roster_id=int(m["roster_id"]),
                starters=list(m.get("starters") or []),
                players=list(m.get("players") or []),
                points=float(m.get("points") or 0.0),
                players_points={str(k): float(v) for k, v in (m.get("players_points") or {}).items()},
            )
            for m in raw_list
        ]

    def get_transactions(self, league_id: str, week: int) -> list[SleeperTransaction]:
        """Fetch all transactions (waivers, FA pickups, trades) for a given week.

        :param league_id: Sleeper league identifier.
        :param week: NFL week number. Sleeper uses this as a round identifier
            for waiver/FA transactions.
        :return: List of :class:`SleeperTransaction` ordered as returned by
            Sleeper (newest first).
        :raises requests.HTTPError: On non-2xx HTTP responses.
        :raises requests.Timeout: If the request exceeds :attr:`_timeout` seconds.
        """
        url = f"{_BASE_REST_URL}/league/{league_id}/transactions/{week}"
        response = requests.get(url, timeout=self._timeout)
        response.raise_for_status()
        raw_list: list[dict[str, Any]] = response.json() or []
        return [
            SleeperTransaction(
                transaction_id=str(t["transaction_id"]),
                type=str(t.get("type") or ""),
                status=str(t.get("status") or ""),
                adds={str(k): int(v) for k, v in (t.get("adds") or {}).items()},
                drops={str(k): int(v) for k, v in (t.get("drops") or {}).items()},
                created=int(t.get("created") or 0),
                week=int(t.get("leg") or week),
            )
            for t in raw_list
        ]

    def get_trending_players(
        self,
        trend_type: str,
        lookback_hours: int = 24,
        limit: int = 25,
    ) -> list[SleeperTrendingPlayer]:
        """Fetch trending adds or drops from the Sleeper platform.

        :param trend_type: ``"add"`` or ``"drop"``.
        :param lookback_hours: Hours of history to consider. Defaults to 24.
        :param limit: Maximum number of results to return. Defaults to 25.
        :return: List of :class:`SleeperTrendingPlayer` sorted by count
            descending.
        :raises requests.HTTPError: On non-2xx HTTP responses.
        :raises requests.Timeout: If the request exceeds :attr:`_timeout` seconds.
        """
        url = f"{_BASE_REST_URL}/players/nfl/trending/{trend_type}"
        response = requests.get(
            url,
            params={"lookback_hours": lookback_hours, "limit": limit},
            timeout=self._timeout,
        )
        response.raise_for_status()
        raw_list: list[dict[str, Any]] = response.json() or []
        return [
            SleeperTrendingPlayer(
                player_id=str(p["player_id"]),
                count=int(p.get("count") or 0),
            )
            for p in raw_list
        ]

    def get_nfl_state(self) -> SleeperNFLState:
        """Fetch the current NFL season and week state from Sleeper.

        :return: :class:`SleeperNFLState` with current week, season, and
            season type.
        :raises requests.HTTPError: On non-2xx HTTP responses.
        :raises requests.Timeout: If the request exceeds :attr:`_timeout` seconds.
        """
        url = f"{_BASE_REST_URL}/state/nfl"
        response = requests.get(url, timeout=self._timeout)
        response.raise_for_status()
        data: dict[str, Any] = response.json()
        return SleeperNFLState(
            week=int(data.get("week") or 1),
            season=int(data.get("season") or 0),
            season_type=str(data.get("season_type") or "regular"),
            display_week=int(data.get("display_week") or data.get("week") or 1),
        )


# ---------------------------------------------------------------------------
# Draft utility functions
# ---------------------------------------------------------------------------

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
