"""DuckDB connection utilities for YampGM.

Follows the same path convention as the rest of gridiron-yampylytics:
the database defaults to ``gridiron_yampylytics.db`` in the current
working directory, with an optional override.
"""
from contextlib import contextmanager
from pathlib import Path
from typing import Generator
import duckdb


def get_db_path(db_path: Path | str | None = None) -> Path:
    """Resolve the DuckDB database path.

    :param db_path: Explicit path to override the default. If ``None``,
        resolves to ``gridiron_yampylytics.db`` in the current working directory.
    :return: Resolved ``Path`` to the database file.
    :raises FileNotFoundError: If the resolved path does not exist.
    """
    resolved = Path(db_path) if db_path is not None else Path.cwd() / "gridiron_yampylytics.db"
    if not resolved.exists():
        raise FileNotFoundError(
            f"Database not found at {resolved}. "
            "Run 'create-duckdb-tables' from the gridiron-yampylytics root to build it."
        )
    return resolved


@contextmanager
def connect(db_path: Path | str | None = None) -> Generator[duckdb.DuckDBPyConnection, None, None]:
    """Open a read-only DuckDB connection as a context manager.

    Read-only mode prevents accidental writes and allows concurrent access
    from multiple processes (e.g., running the draft tool alongside Harlequin).

    :param db_path: Path to the database file. Defaults to
        ``gridiron_yampylytics.db`` in the current working directory.
    :return: Yields an open ``DuckDBPyConnection``.
    :raises FileNotFoundError: If the database file does not exist.

    Usage::

        with connect() as con:
            df = con.execute("SELECT * FROM nflverse.players LIMIT 5").df()
    """
    path = get_db_path(db_path)
    con = duckdb.connect(str(path), read_only=True)
    try:
        yield con
    finally:
        con.close()
