"""Load all NFL data sources for gridiron-yampylytics.

This unified script calls all data acquisition scripts to build
a complete dataset from scratch.

Usage:
    uv run python -m scripts.load_all_data

This script runs:
    1. cache_nflreadpy_data.py - Download all 10 nflreadpy datasets
    2. download_gm_data.py - Scrape GM executives from Pro Football Reference

Total runtime: ~10-15 minutes (depends on network speed and PFR response times)
"""
import sys
import subprocess
from pathlib import Path


def main() -> None:
    """Load all data sources sequentially."""
    sys.stdout.reconfigure(encoding='utf-8')

    print("=" * 80)
    print("LOADING ALL NFL DATA SOURCES")
    print("=" * 80)
    print()
    print("This will download:")
    print("  - 10 nflreadpy datasets (3.1M+ rows)")
    print("  - GM executives for 32 teams (1960-2025)")
    print()
    print("Estimated time: 10-15 minutes")
    print("=" * 80)
    print()

    # 1. Load nflreadpy datasets (10 datasets)
    print("[1/2] Loading nflreadpy data...")
    print("-" * 80)
    result = subprocess.run(
        ["uv", "run", "python", "-m", "scripts.cache_nflreadpy_data", "--all"],
        cwd=Path(__file__).parent.parent
    )
    if result.returncode != 0:
        print("\n❌ nflreadpy cache failed")
        sys.exit(1)

    print()

    # 2. Scrape GM executives
    print("[2/2] Scraping GM executives...")
    print("-" * 80)
    result = subprocess.run(
        ["uv", "run", "python", "-m", "scripts.download_gm_data"],
        cwd=Path(__file__).parent.parent
    )
    if result.returncode != 0:
        print("\n❌ GM scraper failed")
        sys.exit(1)

    print()
    print("=" * 80)
    print("✅ ALL DATA LOADED SUCCESSFULLY")
    print("=" * 80)
    print()
    print("Data locations:")
    print("  - nflreadpy: data/cached/nflreadpy/")
    print("  - GM executives: data/raw/executives/")
    print()
    print("Next steps:")
    print("  - Verify data loaded correctly")
    print("  - Begin data transformation phase")
    print("  - Start GM performance analysis")


if __name__ == "__main__":
    main()
