"""FantasyPros pre-draft PPR season projections scraper.

Scrapes projected season point totals from FantasyPros for all standard
fantasy positions (QB, RB, WR, TE, K, DST).  Uses the ``?week=draft``
parameter which returns season-long pre-draft projections rather than
weekly numbers.

For programmatic use::

    from gridiron_yampylytics.loaders.fp_projections import download_fp_projections
    df = download_fp_projections()

Output CSV columns: ``player_name``, ``team``, ``position``, ``fpts_ppr``.
"""
import time
import random
from pathlib import Path
from typing import Any
import pandas as pd
import requests
from io import StringIO


_BASE_URL: str = "https://www.fantasypros.com/nfl/projections/{pos}.php?week=draft&scoring=PPR"
_HEADERS: dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}
_POSITIONS: list[tuple[str, str]] = [
    ("qb", "QB"),
    ("rb", "RB"),
    ("wr", "WR"),
    ("te", "TE"),
    ("k", "K"),
    ("dst", "DEF"),
]
_REQUEST_DELAY: tuple[float, float] = (1.5, 3.0)


def _build_dst_team_map(data_dir: Path) -> dict[str, str]:
    """Build full team name → nflverse abbreviation mapping for DST parsing.

    Loads from ``data/reference/team_code_mapping.csv`` when available,
    otherwise falls back to a hardcoded map covering all 32 current franchises.

    :param data_dir: Project data directory.
    :return: Dict mapping full team name to nflverse team code (e.g. ``"Philadelphia Eagles"`` → ``"PHI"``).
    """
    team_csv = data_dir / "reference" / "team_code_mapping.csv"
    if team_csv.exists():
        df = pd.read_csv(team_csv)
        return dict(zip(df["team_name"], df["nflverse_code"]))
    return {
        "Arizona Cardinals": "ARI", "Atlanta Falcons": "ATL",
        "Baltimore Ravens": "BAL", "Buffalo Bills": "BUF",
        "Carolina Panthers": "CAR", "Chicago Bears": "CHI",
        "Cincinnati Bengals": "CIN", "Cleveland Browns": "CLE",
        "Dallas Cowboys": "DAL", "Denver Broncos": "DEN",
        "Detroit Lions": "DET", "Green Bay Packers": "GB",
        "Houston Texans": "HOU", "Indianapolis Colts": "IND",
        "Jacksonville Jaguars": "JAX", "Kansas City Chiefs": "KC",
        "Las Vegas Raiders": "LV", "Los Angeles Chargers": "LAC",
        "Los Angeles Rams": "LA", "Miami Dolphins": "MIA",
        "Minnesota Vikings": "MIN", "New England Patriots": "NE",
        "New Orleans Saints": "NO", "New York Giants": "NYG",
        "New York Jets": "NYJ", "Philadelphia Eagles": "PHI",
        "Pittsburgh Steelers": "PIT", "San Francisco 49ers": "SF",
        "Seattle Seahawks": "SEA", "Tampa Bay Buccaneers": "TB",
        "Tennessee Titans": "TEN", "Washington Commanders": "WAS",
    }


def _find_col(df: pd.DataFrame, target: str) -> Any:
    """Find a column by name in either single-level or multi-level headers.

    :param df: DataFrame to search.
    :param target: Column label to find (e.g. ``"Player"``, ``"FPTS"``).
    :return: Column key (string or tuple) suitable for ``df[key]``.
    :raises KeyError: If no column matching ``target`` is found.
    """
    for col in df.columns:
        if isinstance(col, tuple):
            if target in col:
                return col
        elif col == target:
            return col
    raise KeyError(f"Column {target!r} not found in {list(df.columns)}")


def _parse_skill_row(player_raw: str) -> tuple[str, str]:
    """Parse a skill-player ``Player`` cell into ``(name, team)``.

    FantasyPros skill-player cells are formatted as ``"Josh Allen BUF"``.
    The last token is always the 2-3 character team abbreviation.

    :param player_raw: Raw ``Player`` cell value.
    :return: ``(player_name, team)`` tuple.
    """
    parts = player_raw.strip().split()
    if len(parts) >= 2:
        return " ".join(parts[:-1]), parts[-1]
    return player_raw.strip(), "FA"


def _scrape_position(fp_pos: str, position: str, dst_map: dict[str, str]) -> pd.DataFrame:
    """Scrape one FantasyPros projections page and return a tidy DataFrame.

    :param fp_pos: FantasyPros URL position slug (e.g. ``"qb"``, ``"dst"``).
    :param position: Canonical position label to store (e.g. ``"QB"``, ``"DEF"``).
    :param dst_map: Full team name → abbreviation mapping (used for DST only).
    :return: DataFrame with columns ``player_name``, ``team``, ``position``, ``fpts_ppr``.
    :raises requests.HTTPError: On non-2xx HTTP response.
    :raises ValueError: If the projections table cannot be parsed from the page.
    """
    url = _BASE_URL.format(pos=fp_pos)
    response = requests.get(url, headers=_HEADERS, timeout=15)
    response.raise_for_status()
    tables = pd.read_html(StringIO(response.text))
    if not tables:
        raise ValueError(f"No tables found on FantasyPros projections page for {fp_pos!r}")
    df = tables[0]
    player_col = _find_col(df, "Player")
    fpts_col = _find_col(df, "FPTS")
    rows: list[dict[str, Any]] = []
    for _, row in df.iterrows():
        player_raw = str(row[player_col]).strip()
        fpts_raw = row[fpts_col]
        try:
            fpts = float(fpts_raw)
        except (ValueError, TypeError):
            continue
        if position == "DEF":
            team = dst_map.get(player_raw, "")
            if not team:
                # Fallback: check if it looks like "Eagles" or similar nickname
                for full_name, abbr in dst_map.items():
                    if player_raw in full_name:
                        team = abbr
                        break
            player_name = player_raw
        else:
            player_name, team = _parse_skill_row(player_raw)
        rows.append({"player_name": player_name, "team": team, "position": position, "fpts_ppr": fpts})
    return pd.DataFrame(rows)


def download_fp_projections(
    data_dir: Path | None = None,
    output_filename: str = "ff_projections.csv",
) -> pd.DataFrame:
    """Scrape FantasyPros pre-draft PPR season projections for all positions.

    Fetches the ``?week=draft`` projection page for QB, RB, WR, TE, K, and
    DST, combines them into a single DataFrame, and saves to
    ``data/nflverse/ff_projections.csv``.

    :param data_dir: Project data directory.  Defaults to ``./data`` relative
        to the current working directory.
    :param output_filename: Output CSV filename within ``data/nflverse/``.
    :return: Combined DataFrame with columns ``player_name``, ``team``,
        ``position``, ``fpts_ppr``.
    :raises requests.HTTPError: If any individual position page request fails.
    """
    if data_dir is None:
        data_dir = Path.cwd() / "data"
    else:
        data_dir = Path(data_dir)
    output_path = data_dir / "nflverse" / output_filename
    dst_map = _build_dst_team_map(data_dir)
    all_frames: list[pd.DataFrame] = []
    total = len(_POSITIONS)
    for i, (fp_pos, position) in enumerate(_POSITIONS, 1):
        print(f"  [{i}/{total}] Scraping {position} projections...", end=" ", flush=True)
        try:
            df = _scrape_position(fp_pos, position, dst_map)
            all_frames.append(df)
            print(f"✓ ({len(df)} players)")
        except Exception as exc:
            print(f"✗ ERROR: {exc}")
        if i < total:
            delay = random.uniform(*_REQUEST_DELAY)
            time.sleep(delay)
    if not all_frames:
        raise RuntimeError("All FantasyPros projection pages failed to scrape.")
    combined = pd.concat(all_frames, ignore_index=True)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    combined.to_csv(output_path, index=False)
    print(f"\n  ✓ Saved {len(combined)} projections → {output_path}")
    return combined
