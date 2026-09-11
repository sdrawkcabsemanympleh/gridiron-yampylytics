"""CLI wrapper for FantasyPros pre-draft season projections download.

Downloads projected season point totals from FantasyPros for all standard
fantasy positions in PPR, half-PPR, and standard scoring formats.
Saves to ``data/nflverse/ff_projections.csv``.

Usage::

    uv run download-fp-projections

After downloading, rebuild the DuckDB database to include the new table::

    echo y | uv run create-duckdb-tables
"""
import sys
from gridiron_yampylytics.loaders.fp_projections import download_fp_projections


def main() -> None:
    """CLI entry point for FantasyPros projections download."""
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")
    print("=" * 60)
    print("FANTASYPROS PRE-DRAFT PROJECTIONS (PPR / HALF / STD)")
    print("=" * 60)
    print()
    try:
        df = download_fp_projections()
        print()
        print("=" * 60)
        print(f"✅ COMPLETE — {len(df)} total projections downloaded")
        print("=" * 60)
        print()
        print("Next step: rebuild DuckDB to include ff_projections table:")
        print("  echo y | uv run create-duckdb-tables")
    except Exception as exc:
        print(f"\n✗ FAILED: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
