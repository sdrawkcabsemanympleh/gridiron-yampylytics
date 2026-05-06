"""Smoke tests for the YampGM FastAPI layer.

Uses FastAPI's TestClient (synchronous) and mocks all external I/O
(Sleeper REST, Sleeper WebSocket, DuckDB) so tests run offline.
"""
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from fastapi.testclient import TestClient
from gridiron_yampylytics.ffb.api.main import app
from gridiron_yampylytics.ffb.api.session_store import _sessions
from gridiron_yampylytics.ffb.data.sleeper import SleeperDraft, SleeperPick
from gridiron_yampylytics.ffb.models.player import NFLPlayer, Position

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _p(pid: str, pos: str, pts: float, adp: float, sleeper_id: str | None = None) -> NFLPlayer:
    return NFLPlayer(
        player_id=pid, name=pid, position=Position(pos), team="KC",
        projected_points=pts, adp=adp, sleeper_id=sleeper_id,
    )


def _fake_draft(team_count: int = 2) -> SleeperDraft:
    return SleeperDraft(
        draft_id="draft1",
        league_id="league1",
        draft_type="snake",
        status="drafting",
        season=2024,
        draft_order={"user_abc": 1, "opp_xyz": 2},
        settings={
            "teams": team_count,
            "slots_qb": 1, "slots_rb": 1, "slots_wr": 0,
            "slots_te": 0, "slots_flex": 0, "slots_k": 0,
            "slots_def": 0, "slots_bn": 1,
        },
    )


def _fake_players() -> list[NFLPlayer]:
    return [
        _p("q1", "QB", 400.0, 1.0, sleeper_id="s_q1"),
        _p("r1", "RB", 300.0, 2.0, sleeper_id="s_r1"),
        _p("q2", "QB",  50.0, 3.0, sleeper_id="s_q2"),
        _p("r2", "RB", 150.0, 4.0, sleeper_id="s_r2"),
        _p("q3", "QB",  30.0, 5.0, sleeper_id="s_q3"),
        _p("r3", "RB", 100.0, 6.0, sleeper_id="s_r3"),
    ]


@pytest.fixture(autouse=True)
def _clear_sessions():
    """Ensure session store is empty before and after each test."""
    _sessions.clear()
    yield
    _sessions.clear()


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app, raise_server_exceptions=True)


def _patch_sleeper_and_db(draft: SleeperDraft, existing_picks: list[SleeperPick] | None = None):
    """Return a context manager that patches SleeperClient and load_player_pool."""
    mock_sleeper = MagicMock()
    mock_sleeper.get_draft.return_value = draft
    mock_sleeper.get_existing_picks.return_value = existing_picks or []
    return patch.multiple(
        "gridiron_yampylytics.ffb.api.routers.sessions",
        SleeperClient=MagicMock(return_value=mock_sleeper),
        load_player_pool=MagicMock(return_value=_fake_players()),
        _run_sleeper_listener=AsyncMock(return_value=None),
        _compute_and_broadcast_recommendations=AsyncMock(return_value=None),
    )


# ---------------------------------------------------------------------------
# POST /api/sessions
# ---------------------------------------------------------------------------

class TestCreateSession:
    """Tests for POST /api/sessions."""

    def test_creates_session_successfully(self, client: TestClient) -> None:
        """POST /api/sessions returns 200 and a SessionResponse."""
        with _patch_sleeper_and_db(_fake_draft()):
            resp = client.post("/api/sessions", json={
                "draft_id": "draft1",
                "sleeper_user_id": "user_abc",
            })
        assert resp.status_code == 200
        data = resp.json()
        assert data["draft_id"] == "draft1"
        assert data["current_pick"] == 1
        assert data["is_user_turn"] is True  # user at slot 1, pick 1

    def test_replays_existing_picks(self, client: TestClient) -> None:
        """Existing picks are replayed; current_pick advances past them."""
        existing = [SleeperPick(
            pick_no=1, round=1, draft_slot=1, picked_by="user_abc",
            player_id="s_q1", position="QB", team="KC", is_dst=False,
        )]
        with _patch_sleeper_and_db(_fake_draft(), existing_picks=existing):
            resp = client.post("/api/sessions", json={
                "draft_id": "draft1",
                "sleeper_user_id": "user_abc",
            })
        assert resp.status_code == 200
        data = resp.json()
        assert data["picks_replayed"] == 1
        assert data["current_pick"] == 2

    def test_returns_409_if_session_already_exists(self, client: TestClient) -> None:
        """Creating a session for an already-active draft ID returns 409."""
        with _patch_sleeper_and_db(_fake_draft()):
            client.post("/api/sessions", json={"draft_id": "draft1", "sleeper_user_id": "user_abc"})
            resp = client.post("/api/sessions", json={"draft_id": "draft1", "sleeper_user_id": "user_abc"})
        assert resp.status_code == 409

    def test_returns_400_for_non_snake_draft(self, client: TestClient) -> None:
        """Auction drafts return 400."""
        auction_draft = _fake_draft()
        auction_draft.draft_type = "auction"
        with _patch_sleeper_and_db(auction_draft):
            resp = client.post("/api/sessions", json={"draft_id": "draft1", "sleeper_user_id": "user_abc"})
        assert resp.status_code == 400

    def test_returns_400_if_user_not_in_draft_order(self, client: TestClient) -> None:
        """Returns 400 if the provided sleeper_user_id is not in the draft order."""
        with _patch_sleeper_and_db(_fake_draft()):
            resp = client.post("/api/sessions", json={
                "draft_id": "draft1",
                "sleeper_user_id": "not_in_draft",
            })
        assert resp.status_code == 400

    def test_returns_400_if_draft_order_empty(self, client: TestClient) -> None:
        """Returns 400 when draft order has not been set."""
        draft = _fake_draft()
        draft.draft_order = {}
        with _patch_sleeper_and_db(draft):
            resp = client.post("/api/sessions", json={"draft_id": "draft1", "sleeper_user_id": "user_abc"})
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# GET /api/sessions/{draft_id}
# ---------------------------------------------------------------------------

class TestGetSession:
    """Tests for GET /api/sessions/{draft_id}."""

    def test_returns_current_state(self, client: TestClient) -> None:
        """GET returns session state after creation."""
        with _patch_sleeper_and_db(_fake_draft()):
            client.post("/api/sessions", json={"draft_id": "draft1", "sleeper_user_id": "user_abc"})
            resp = client.get("/api/sessions/draft1")
        assert resp.status_code == 200
        assert resp.json()["draft_id"] == "draft1"

    def test_returns_404_for_unknown_session(self, client: TestClient) -> None:
        """GET on an unknown draft ID returns 404."""
        resp = client.get("/api/sessions/nonexistent")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /api/sessions/{draft_id}
# ---------------------------------------------------------------------------

class TestDeleteSession:
    """Tests for DELETE /api/sessions/{draft_id}."""

    def test_deletes_existing_session(self, client: TestClient) -> None:
        """DELETE returns 204 and session is gone."""
        with _patch_sleeper_and_db(_fake_draft()):
            client.post("/api/sessions", json={"draft_id": "draft1", "sleeper_user_id": "user_abc"})
            resp = client.delete("/api/sessions/draft1")
        assert resp.status_code == 204
        assert client.get("/api/sessions/draft1").status_code == 404

    def test_returns_404_for_unknown_session(self, client: TestClient) -> None:
        """DELETE on unknown draft ID returns 404."""
        resp = client.delete("/api/sessions/nonexistent")
        assert resp.status_code == 404
