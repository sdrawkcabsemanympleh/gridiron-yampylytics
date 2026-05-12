"""Tests for ffb/data/sleeper.py."""
from unittest.mock import MagicMock, patch
import pytest
from gridiron_yampylytics.ffb.data.sleeper import (
    SleeperClient,
    SleeperDraft,
    SleeperPick,
    _parse_raw_pick,
    build_player_index,
    resolve_pick,
)
from gridiron_yampylytics.ffb.models.player import NFLPlayer, Position

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _p(pid: str, pos: str, sleeper_id: str | None = None) -> NFLPlayer:
    return NFLPlayer(
        player_id=pid,
        name=pid,
        position=Position(pos),
        team="KC",
        projected_points=100.0,
        adp=1.0,
        sleeper_id=sleeper_id,
    )


def _raw_pick(
    pick_no: int = 1,
    round_: int = 1,
    draft_slot: int = 1,
    picked_by: str = "user1",
    player_id: str = "4034",
    position: str = "QB",
    team: str = "KC",
) -> dict:
    return {
        "pick_no": pick_no,
        "round": round_,
        "draft_slot": draft_slot,
        "picked_by": picked_by,
        "player_id": player_id,
        "metadata": {"position": position, "team": team},
    }


# ---------------------------------------------------------------------------
# _parse_raw_pick
# ---------------------------------------------------------------------------

class TestParseRawPick:
    """Unit tests for _parse_raw_pick."""

    def test_parses_skill_player(self) -> None:
        raw = _raw_pick(pick_no=3, round_=1, draft_slot=3, position="RB", team="SF")
        pick = _parse_raw_pick(raw)
        assert pick.pick_no == 3
        assert pick.round == 1
        assert pick.draft_slot == 3
        assert pick.position == "RB"
        assert pick.team == "SF"
        assert pick.player_id == "4034"
        assert pick.is_dst is False

    def test_parses_dst_pick(self) -> None:
        raw = _raw_pick(position="DEF", team="SF", player_id="DST_SF")
        pick = _parse_raw_pick(raw)
        assert pick.is_dst is True
        assert pick.team == "SF"

    def test_is_dst_case_insensitive(self) -> None:
        raw = _raw_pick(position="def", team="KC")
        pick = _parse_raw_pick(raw)
        assert pick.is_dst is True

    def test_missing_team_produces_none(self) -> None:
        raw = _raw_pick()
        raw["metadata"].pop("team")
        pick = _parse_raw_pick(raw)
        assert pick.team is None

    def test_missing_metadata_produces_empty_position(self) -> None:
        raw = _raw_pick()
        del raw["metadata"]
        pick = _parse_raw_pick(raw)
        assert pick.position == ""
        assert pick.is_dst is False


# ---------------------------------------------------------------------------
# build_player_index
# ---------------------------------------------------------------------------

class TestBuildPlayerIndex:
    """Tests for build_player_index."""

    def test_skill_player_indexed_by_sleeper_id(self) -> None:
        p = _p("yid1", "QB", sleeper_id="4034")
        index = build_player_index([p])
        assert index["4034"] is p

    def test_player_without_sleeper_id_excluded(self) -> None:
        p = _p("yid1", "QB", sleeper_id=None)
        index = build_player_index([p])
        assert "yid1" not in index
        assert len(index) == 0

    def test_dst_indexed_by_synthetic_player_id(self) -> None:
        p = _p("DST_KC", "DEF", sleeper_id=None)
        index = build_player_index([p])
        assert index["DST_KC"] is p

    def test_dst_with_sleeper_id_indexed_under_both_keys(self) -> None:
        p = _p("DST_KC", "DEF", sleeper_id="sleeper_dst_kc")
        index = build_player_index([p])
        assert index["sleeper_dst_kc"] is p
        assert index["DST_KC"] is p

    def test_multiple_players_all_indexed(self) -> None:
        players = [
            _p("yid1", "QB", sleeper_id="101"),
            _p("yid2", "RB", sleeper_id="202"),
            _p("DST_KC", "DEF"),
        ]
        index = build_player_index(players)
        assert len(index) == 3

    def test_empty_pool_returns_empty_index(self) -> None:
        assert build_player_index([]) == {}


# ---------------------------------------------------------------------------
# resolve_pick
# ---------------------------------------------------------------------------

class TestResolvePick:
    """Tests for resolve_pick."""

    def _make_index(self) -> tuple[dict, NFLPlayer, NFLPlayer]:
        qb = _p("yid_q", "QB", sleeper_id="1001")
        dst = _p("DST_KC", "DEF")
        return build_player_index([qb, dst]), qb, dst

    def test_resolves_skill_player_by_sleeper_id(self) -> None:
        index, qb, _ = self._make_index()
        pick = _parse_raw_pick(_raw_pick(player_id="1001", position="QB", team="KC"))
        assert resolve_pick(pick, index) is qb

    def test_resolves_dst_by_team_abbreviation(self) -> None:
        index, _, dst = self._make_index()
        pick = _parse_raw_pick(_raw_pick(player_id="dst_x", position="DEF", team="KC"))
        assert resolve_pick(pick, index) is dst

    def test_unknown_player_returns_none(self) -> None:
        index, _, _ = self._make_index()
        pick = _parse_raw_pick(_raw_pick(player_id="9999", position="WR", team="NYG"))
        assert resolve_pick(pick, index) is None

    def test_dst_missing_team_returns_none(self) -> None:
        index, _, _ = self._make_index()
        raw = _raw_pick(position="DEF")
        raw["metadata"].pop("team")
        pick = _parse_raw_pick(raw)
        assert resolve_pick(pick, index) is None


# ---------------------------------------------------------------------------
# SleeperClient — REST methods (mocked)
# ---------------------------------------------------------------------------

class TestSleeperClientGetDraft:
    """Tests for SleeperClient.get_draft using mocked HTTP."""

    def _draft_response(self) -> dict:
        return {
            "draft_id": "d1",
            "league_id": "l1",
            "type": "snake",
            "status": "drafting",
            "season": "2025",
            "draft_order": {"user1": 1, "user2": 2},
            "settings": {"teams": 10, "rounds": 15},
        }

    def test_returns_sleeper_draft(self) -> None:
        mock_resp = MagicMock()
        mock_resp.json.return_value = self._draft_response()
        with patch("requests.get", return_value=mock_resp):
            draft = SleeperClient().get_draft("d1")
        assert isinstance(draft, SleeperDraft)
        assert draft.draft_id == "d1"
        assert draft.league_id == "l1"
        assert draft.draft_type == "snake"
        assert draft.status == "drafting"
        assert draft.season == 2025
        assert draft.draft_order == {"user1": 1, "user2": 2}

    def test_raises_on_http_error(self) -> None:
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = Exception("404")
        with patch("requests.get", return_value=mock_resp):
            with pytest.raises(Exception, match="404"):
                SleeperClient().get_draft("bad")


class TestSleeperClientGetExistingPicks:
    """Tests for SleeperClient.get_existing_picks using mocked HTTP."""

    def test_returns_list_of_picks(self) -> None:
        raw_picks = [_raw_pick(pick_no=1), _raw_pick(pick_no=2, draft_slot=2)]
        mock_resp = MagicMock()
        mock_resp.json.return_value = raw_picks
        with patch("requests.get", return_value=mock_resp):
            picks = SleeperClient().get_existing_picks("d1")
        assert len(picks) == 2
        assert all(isinstance(p, SleeperPick) for p in picks)
        assert picks[0].pick_no == 1
        assert picks[1].pick_no == 2

    def test_empty_draft_returns_empty_list(self) -> None:
        mock_resp = MagicMock()
        mock_resp.json.return_value = []
        with patch("requests.get", return_value=mock_resp):
            assert SleeperClient().get_existing_picks("d1") == []


# ---------------------------------------------------------------------------
# SleeperClient — stream_picks (mocked REST polling)
# ---------------------------------------------------------------------------

class TestSleeperClientStreamPicks:
    """Tests for SleeperClient.stream_picks using mocked REST polling."""

    def _picks_resp(self, pick_nos: list[int]) -> MagicMock:
        mock = MagicMock()
        mock.json.return_value = [_raw_pick(pick_no=n) for n in pick_nos]
        return mock

    def _draft_resp(self, status: str = "complete") -> MagicMock:
        mock = MagicMock()
        mock.json.return_value = {"status": status}
        return mock

    async def test_yields_picks_on_first_poll(self) -> None:
        """All picks returned by the first poll are yielded."""
        with patch("requests.get", side_effect=[self._picks_resp([1, 2]), self._draft_resp()]), \
             patch("asyncio.sleep"):
            picks = [p async for p in SleeperClient().stream_picks("d1")]
        assert [p.pick_no for p in picks] == [1, 2]

    async def test_skips_already_seen_picks(self) -> None:
        """seen_count causes picks already replayed at session start to be skipped."""
        with patch("requests.get", side_effect=[self._picks_resp([1, 2, 3]), self._draft_resp()]), \
             patch("asyncio.sleep"):
            picks = [p async for p in SleeperClient().stream_picks("d1", seen_count=2)]
        assert len(picks) == 1
        assert picks[0].pick_no == 3

    async def test_yields_new_picks_across_multiple_polls(self) -> None:
        """New picks arriving on a later poll are yielded after earlier picks."""
        with patch("requests.get", side_effect=[
            self._picks_resp([1]),           # first picks poll
            self._draft_resp("drafting"),    # not complete yet
            self._picks_resp([1, 2]),        # second poll — pick 2 is new
            self._draft_resp("complete"),
        ]), patch("asyncio.sleep"):
            picks = [p async for p in SleeperClient().stream_picks("d1")]
        assert [p.pick_no for p in picks] == [1, 2]

    async def test_exits_when_all_picks_already_seen(self) -> None:
        """Exits without yielding when seen_count equals total picks and draft is complete."""
        with patch("requests.get", side_effect=[self._picks_resp([1, 2]), self._draft_resp()]), \
             patch("asyncio.sleep"):
            picks = [p async for p in SleeperClient().stream_picks("d1", seen_count=2)]
        assert picks == []
