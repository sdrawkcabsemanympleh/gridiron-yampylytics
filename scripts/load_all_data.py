"""CLI wrapper for unified data loading.

This script is a thin wrapper around the load_all_data function.
For programmatic use, import and call the function directly:

    from src.gridiron_yampylytics.loaders.all_data import load_all_data
    result = load_all_data()

Usage:
    uv run python -m scripts.load_all_data

This runs:
    1. nflverse data caching - Download all 10 nflreadpy datasets
    2. GM data scraping - Scrape GM executives from Pro Football Reference

Total runtime: ~10-15 minutes (depends on network speed and PFR response times)
"""
import sys
from src.gridiron_yampylytics.loaders.all_data import load_all_data


def main() -> None:
    """CLI entry point for loading all data sources."""
    sys.stdout.reconfigure(encoding='utf-8')

    result = load_all_data()

    if not result['success']:
        sys.exit(1)


if __name__ == "__main__":
    main()
