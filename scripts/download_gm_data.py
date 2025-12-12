"""CLI wrapper for GM/Executive data scraper.

This script is a thin wrapper around the download_gm_data function.
For programmatic use, import and call the function directly:

    from src.gridiron_yampylytics.loaders.gm_data import download_gm_data
    result = download_gm_data()

Usage:
    uv run python -m scripts.download_gm_data
"""
import sys
from src.gridiron_yampylytics.loaders.gm_data import download_gm_data


def main() -> None:
    """CLI entry point for GM data download."""
    sys.stdout.reconfigure(encoding='utf-8')
    download_gm_data()


if __name__ == "__main__":
    main()
