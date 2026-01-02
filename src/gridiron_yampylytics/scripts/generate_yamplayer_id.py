"""CLI wrapper for yamplayer_id generation.

This script is a thin wrapper around the generate_yamplayer_id function.
For programmatic use, import and call the function directly:

    from gridiron_yampylytics.processors.yamplayer_id import generate_yamplayer_id
    result = generate_yamplayer_id()

Usage:
    uv run python -m scripts.generate_yamplayer_id
    uv run python -m scripts.generate_yamplayer_id --dry-run
"""
import sys
import argparse
from pathlib import Path
from gridiron_yampylytics.processors.yamplayer_id import generate_yamplayer_id


def main() -> None:
    """CLI entry point for yamplayer_id generation."""
    sys.stdout.reconfigure(encoding='utf-8')

    parser = argparse.ArgumentParser(description='Generate yamplayer_id for all datasets')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be done without modifying files')
    args = parser.parse_args()

    base_dir = Path(__file__).parent.parent
    generate_yamplayer_id(base_dir=base_dir, dry_run=args.dry_run)


if __name__ == '__main__':
    main()
