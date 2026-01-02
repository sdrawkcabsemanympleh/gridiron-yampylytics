"""CLI wrapper for YAS (Yampylytics Athletic Score) calculation.

This script is a thin wrapper around the calculate_yas function.
For programmatic use, import and call the function directly:

    from src.gridiron_yampylytics.processors.yas import calculate_yas
    result = calculate_yas()

Usage:
    uv run python -m scripts.calculate_yas
"""
import sys
from src.gridiron_yampylytics.processors.yas import calculate_yas


def main() -> None:
    """CLI entry point for YAS calculation."""
    sys.stdout.reconfigure(encoding='utf-8')
    calculate_yas()


if __name__ == "__main__":
    main()
