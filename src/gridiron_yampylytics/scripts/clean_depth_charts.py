"""CLI wrapper for depth charts cleaning.

This script is a thin wrapper around the clean_depth_charts function.
For programmatic use, import and call the function directly:

    from gridiron_yampylytics.processors.depth_charts import clean_depth_charts
    result = clean_depth_charts()

Usage:
    uv run python -m scripts.clean_depth_charts
"""
import sys
from gridiron_yampylytics.processors.depth_charts import clean_depth_charts


def main() -> None:
    """CLI entry point for cleaning depth charts."""
    sys.stdout.reconfigure(encoding='utf-8')
    clean_depth_charts()


if __name__ == "__main__":
    main()
