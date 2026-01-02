"""CLI wrapper for GM data combining.

This script is a thin wrapper around the combine_gm_data function.
For programmatic use, import and call the function directly:

    from gridiron_yampylytics.processors.gm_data import combine_gm_data
    result = combine_gm_data()

Usage:
    uv run python -m scripts.combine_gm_data
"""
import sys
from gridiron_yampylytics.processors.gm_data import combine_gm_data


def main() -> None:
    """CLI entry point for combining GM data."""
    sys.stdout.reconfigure(encoding='utf-8')
    combine_gm_data()


if __name__ == "__main__":
    main()
