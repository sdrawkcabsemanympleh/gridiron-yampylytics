"""Unified data loader for all NFL data sources.

This module orchestrates loading of all data sources for gridiron-yampylytics.
Calls both nflverse and GM data loaders to build a complete dataset.

For programmatic use:
    from src.gridiron_yampylytics.loaders.all_data import load_all_data
    result = load_all_data()

Downloads:
    - 10 nflreadpy datasets (3.1M+ rows)
    - GM executives for 32 teams (1960-2025)

Estimated time: 10-15 minutes
"""
from typing import Any
from .nflverse import cache_nflverse_data
from .gm_data import download_gm_data


def load_all_data() -> dict[str, Any]:
    """Load all NFL data sources sequentially.

    Runs both data acquisition modules:
    1. nflverse data caching (all datasets)
    2. GM executive data scraping (all 32 teams)

    :return: Summary dict with results from both loaders
    """
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

    # Track overall success
    all_succeeded = True
    results = {}

    # 1. Load nflreadpy datasets (10 datasets)
    print("[1/2] Loading nflreadpy data...")
    print("-" * 80)
    try:
        nflverse_result = cache_nflverse_data(dataset="all", seasons=True)
        results['nflverse'] = nflverse_result

        if nflverse_result['failed']:
            print(f"\n⚠️  Some nflverse datasets failed")
            if not nflverse_result['successful']:
                all_succeeded = False
    except Exception as e:
        print(f"\n❌ nflreadpy cache failed: {e}")
        results['nflverse'] = {'error': str(e)}
        all_succeeded = False

    print()

    # 2. Scrape GM executives
    print("[2/2] Scraping GM executives...")
    print("-" * 80)
    try:
        gm_result = download_gm_data()
        results['gm_data'] = gm_result

        if gm_result['failed'] > 0:
            print(f"\n⚠️  Some GM data downloads failed")
            if gm_result['successful'] == 0:
                all_succeeded = False
    except Exception as e:
        print(f"\n❌ GM scraper failed: {e}")
        results['gm_data'] = {'error': str(e)}
        all_succeeded = False

    print()
    print("=" * 80)
    if all_succeeded:
        print("✅ ALL DATA LOADED SUCCESSFULLY")
    else:
        print("⚠️  DATA LOADING COMPLETED WITH SOME ERRORS")
    print("=" * 80)
    print()
    print("Data locations:")
    print("  - nflreadpy: data/nflverse/")
    print("  - GM executives: data/raw/executives/")
    print()
    print("Next steps:")
    print("  - Verify data loaded correctly")
    print("  - Begin data transformation phase")
    print("  - Start GM performance analysis")

    return {
        'success': all_succeeded,
        'nflverse': results.get('nflverse', {}),
        'gm_data': results.get('gm_data', {}),
    }
