"""Tests for YampGM data access layer.

Unit tests cover path resolution and error handling in db.py.
Integration tests (marked ``integration``) hit the real DuckDB and are
skipped automatically when the database file is not present — they pass
in CI without the data artifact and run locally where the DB exists.
"""
from pathlib import Path
import pytest
from gridiron_yampylytics.ffb.data.db import connect, get_db_path
from gridiron_yampylytics.ffb.models.player import Position

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _db_available() -> bool:
    """Return True if gridiron_yampylytics.db exists in the cwd.

    :return: Whether the database file is present.
    """
    return (Path.cwd() / "gridiron_yampylytics.db").exists()


requires_db = pytest.mark.skipif(
    not _db_available(),
    reason="gridiron_yampylytics.db not present — skipping integration tests",
)

# ---------------------------------------------------------------------------
# db.py — unit tests (no DB required)
# ---------------------------------------------------------------------------

class TestGetDbPath:
    """Tests for get_db_path() path resolution."""

    def test_raises_when_path_does_not_exist(self, tmp_path: Path) -> None:
        """get_db_path raises FileNotFoundError for a non-existent path.

        :param tmp_path: pytest tmp_path fixture — a real temp directory.
        """
        missing = tmp_path / "does_not_exist.db"
        with pytest.raises(FileNotFoundError, match="Database not found"):
            get_db_path(missing)

    def test_returns_path_when_file_exists(self, tmp_path: Path) -> None:
        """get_db_path returns a Path when the file exists.

        :param tmp_path: pytest tmp_path fixture.
        """
        db_file = tmp_path / "test.db"
        db_file.touch()
        result = get_db_path(db_file)
        assert result == db_file
        assert isinstance(result, Path)

    def test_accepts_string_path(self, tmp_path: Path) -> None:
        """get_db_path accepts a string path and returns a Path.

        :param tmp_path: pytest tmp_path fixture.
        """
        db_file = tmp_path / "test.db"
        db_file.touch()
        result = get_db_path(str(db_file))
        assert isinstance(result, Path)
        assert result == db_file


# ---------------------------------------------------------------------------
# player_loader.py — integration tests (require real DB)
# ---------------------------------------------------------------------------

class TestLoadPlayerPool:
    """Integration tests for load_player_pool() against the real DuckDB."""

    @requires_db
    def test_returns_nonempty_list(self) -> None:
        """load_player_pool returns a non-empty list of players."""
        from gridiron_yampylytics.ffb.data.player_loader import load_player_pool
        players = load_player_pool()
        assert len(players) > 0

    @requires_db
    def test_all_skill_positions_represented(self) -> None:
        """Player pool contains at least one player at each skill position."""
        from gridiron_yampylytics.ffb.data.player_loader import load_player_pool
        players = load_player_pool()
        positions = {p.position for p in players}
        for pos in (Position.QB, Position.RB, Position.WR, Position.TE, Position.K):
            assert pos in positions, f"No {pos.value} players in pool"

    @requires_db
    def test_dst_included_by_default(self) -> None:
        """DEF players are included by default."""
        from gridiron_yampylytics.ffb.data.player_loader import load_player_pool
        players = load_player_pool()
        dst = [p for p in players if p.position == Position.DEF]
        assert len(dst) > 0

    @requires_db
    def test_dst_excluded_when_flag_false(self) -> None:
        """No DEF players when include_dst=False."""
        from gridiron_yampylytics.ffb.data.player_loader import load_player_pool
        players = load_player_pool(include_dst=False)
        dst = [p for p in players if p.position == Position.DEF]
        assert dst == []

    @requires_db
    def test_dst_player_ids_use_synthetic_prefix(self) -> None:
        """All DEF players have player_id starting with 'DST_'."""
        from gridiron_yampylytics.ffb.data.player_loader import load_player_pool
        players = load_player_pool()
        dst = [p for p in players if p.position == Position.DEF]
        for p in dst:
            assert p.player_id.startswith("DST_"), f"{p.name} has unexpected id: {p.player_id}"

    @requires_db
    def test_skill_players_have_yamplayer_ids(self) -> None:
        """Skill players (non-DEF) all have non-synthetic player_ids."""
        from gridiron_yampylytics.ffb.data.player_loader import load_player_pool
        players = load_player_pool()
        skill = [p for p in players if p.position != Position.DEF]
        for p in skill:
            assert not p.player_id.startswith("DST_"), (
                f"{p.name} ({p.position.value}) unexpectedly has a DST_ id"
            )

    @requires_db
    def test_players_sorted_by_adp_ascending(self) -> None:
        """Player pool is sorted by ADP ascending (best player first)."""
        from gridiron_yampylytics.ffb.data.player_loader import load_player_pool
        players = load_player_pool()
        adps = [p.adp for p in players]
        assert adps == sorted(adps), "Players are not sorted by ADP ascending"

    @requires_db
    def test_all_players_have_required_fields(self) -> None:
        """Every player has non-empty player_id, name, team, and valid adp."""
        from gridiron_yampylytics.ffb.data.player_loader import load_player_pool
        players = load_player_pool()
        for p in players:
            assert p.player_id, f"Empty player_id for {p.name}"
            assert p.name, f"Empty name for player_id={p.player_id}"
            assert p.team, f"Empty team for {p.name}"
            assert p.adp > 0, f"Non-positive ADP for {p.name}: {p.adp}"

    @requires_db
    def test_connect_context_manager_closes_connection(self, tmp_path: Path) -> None:
        """connect() context manager closes the connection on exit.

        :param tmp_path: pytest tmp_path fixture (unused here, just verifying
            the real DB path convention works with the context manager).
        """
        with connect() as con:
            result = con.execute("SELECT 1 AS x").fetchone()
            assert result == (1,)
        # After exiting, the connection should be closed; further queries raise
        with pytest.raises(Exception):
            con.execute("SELECT 1")
