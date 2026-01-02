"""Process all downloaded data: clean, combine, enrich, and calculate metrics.

This orchestrates the full data processing pipeline:
1. Clean depth charts (split legacy vs modern schema)
2. Combine GM data (merge executive CSVs)
3. Generate yamplayer_id (universal player IDs)
4. Calculate YAS (Yampylytics Athletic Score)
"""
import argparse
from gridiron_yampylytics.scripts import (
    clean_depth_charts,
    combine_gm_data,
    generate_yamplayer_id,
    calculate_yas,
)


def main() -> None:
    """Run the complete data processing pipeline."""
    parser = argparse.ArgumentParser(
        description="Process all downloaded data through the complete pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument(
        '--include-large',
        action='store_true',
        help='Include large datasets like pbp in yamplayer_id processing'
    )
    args = parser.parse_args()

    print("=" * 80)
    print("DATA PROCESSING PIPELINE")
    print("=" * 80)
    print()

    # Step 1: Clean depth charts
    print("[1/4] Cleaning depth charts...")
    clean_depth_charts.main()
    print()

    # Step 2: Combine GM data
    print("[2/4] Combining GM data...")
    combine_gm_data.main()
    print()

    # Step 3: Generate yamplayer_id
    print("[3/4] Generating yamplayer_id...")
    # Pass args to the function if needed
    import sys
    original_argv = sys.argv.copy()
    try:
        sys.argv = ['generate_yamplayer_id']
        if args.include_large:
            sys.argv.append('--all_datasets')
        generate_yamplayer_id.main()
    finally:
        sys.argv = original_argv
    print()

    # Step 4: Calculate YAS
    print("[4/4] Calculating YAS...")
    calculate_yas.main()
    print()

    print("=" * 80)
    print("✅ PIPELINE COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    main()
