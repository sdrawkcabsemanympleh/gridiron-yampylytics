"""Clean and split depth charts data into legacy and modern formats.

This module addresses data quality issues in the depth_charts.csv file:
1. Quoted newlines in depth_position field (causes CSV parsing errors)
2. Dual schema format (old vs new structure in same file)

The function splits the data into two clean files:
- depth_charts_legacy.csv (2001-2023): Traditional depth chart format
- depth_charts_modern.csv (2024-2025): New position group format
"""
import csv
from pathlib import Path
from datetime import datetime
from typing import Any
from src.gridiron_yampylytics.manifest import update_transformation_script


def clean_depth_charts(
    input_file: Path | None = None,
    output_dir: Path | None = None
) -> dict[str, Any]:
    """Clean depth charts data and split into legacy/modern formats.

    :param input_file: Path to depth_charts.csv (default: data/nflverse/depth_charts.csv)
    :param output_dir: Output directory (default: data/nflverse/)
    :return: Summary dict with counts and file paths
    """
    # Set default paths if not provided
    if input_file is None:
        input_file = Path.cwd() / "data" / "nflverse" / "depth_charts.csv"
    if output_dir is None:
        output_dir = Path.cwd() / "data" / "nflverse"

    output_dir.mkdir(parents=True, exist_ok=True)

    legacy_file = output_dir / "depth_charts_legacy.csv"
    modern_file = output_dir / "depth_charts_modern.csv"

    legacy_count = 0
    modern_count = 0

    print("=" * 80)
    print("CLEANING DEPTH CHARTS DATA")
    print("=" * 80)
    print()
    print("This script fixes:")
    print("  1. Quoted newlines in depth_position field")
    print("  2. Dual schema format (splits into separate files)")
    print()
    print("Reading depth charts data...")
    print(f"  Input: {input_file}")
    print()

    # Read with proper CSV handling (handles quoted newlines)
    with open(input_file, 'r', encoding='utf-8', newline='') as fin:
        reader = csv.reader(fin)
        header = next(reader)

        # Define column indices (0-based)
        # Old format uses columns 0-14
        # New format uses columns 9, 15-25 (gsis_id is shared)

        legacy_columns = [
            'season', 'club_code', 'week', 'game_type', 'depth_team',
            'last_name', 'first_name', 'football_name', 'formation',
            'gsis_id', 'jersey_number', 'position', 'elias_id',
            'depth_position', 'full_name'
        ]

        modern_columns = [
            'gsis_id', 'dt', 'team', 'player_name', 'espn_id',
            'pos_grp_id', 'pos_grp', 'pos_id', 'pos_name',
            'pos_abb', 'pos_slot', 'pos_rank'
        ]

        # Open output files
        with open(legacy_file, 'w', encoding='utf-8', newline='') as legacy_out, \
             open(modern_file, 'w', encoding='utf-8', newline='') as modern_out:

            legacy_writer = csv.writer(legacy_out, lineterminator='\n')
            modern_writer = csv.writer(modern_out, lineterminator='\n')

            # Write headers
            legacy_writer.writerow(legacy_columns)
            modern_writer.writerow(modern_columns)

            # Process data rows
            for row in reader:
                if len(row) < 26:
                    # Skip malformed rows (shouldn't happen with proper csv.reader)
                    continue

                # Determine format based on which columns are populated
                # Old format: season (index 0) is not empty
                # New format: dt (index 15) is not empty

                if row[0]:  # season is populated - OLD FORMAT
                    legacy_row = [
                        row[0],   # season
                        row[1],   # club_code
                        row[2],   # week
                        row[3],   # game_type
                        row[4],   # depth_team
                        row[5],   # last_name
                        row[6],   # first_name
                        row[7],   # football_name
                        row[8],   # formation
                        row[9],   # gsis_id
                        row[10],  # jersey_number
                        row[11],  # position
                        row[12],  # elias_id
                        row[13].replace('\n', ' ').replace('\r', ' ').strip() if row[13] else '',  # depth_position (CLEAN NEWLINES)
                        row[14]   # full_name
                    ]
                    legacy_writer.writerow(legacy_row)
                    legacy_count += 1

                elif row[15]:  # dt is populated - NEW FORMAT
                    modern_row = [
                        row[9],   # gsis_id (shared column)
                        row[15],  # dt
                        row[16],  # team
                        row[17],  # player_name
                        row[18],  # espn_id
                        row[19],  # pos_grp_id
                        row[20],  # pos_grp
                        row[21],  # pos_id
                        row[22],  # pos_name
                        row[23],  # pos_abb
                        row[24],  # pos_slot
                        row[25]   # pos_rank
                    ]
                    modern_writer.writerow(modern_row)
                    modern_count += 1

    print("=" * 80)
    print("✅ CLEANUP COMPLETE")
    print("=" * 80)
    print()
    print("Output files:")
    print(f"  Legacy (2001-2023): {legacy_file}")
    print(f"    Rows: {legacy_count:,}")
    print(f"    Columns: 15 (season, team, week, player, position, etc.)")
    print()
    print(f"  Modern (2024-2025): {modern_file}")
    print(f"    Rows: {modern_count:,}")
    print(f"    Columns: 12 (gsis_id, timestamp, team, position groups, rank)")
    print()
    print(f"Total rows processed: {legacy_count + modern_count:,}")
    print()

    # Get file sizes
    legacy_size = legacy_file.stat().st_size if legacy_file.exists() else 0
    modern_size = modern_file.stat().st_size if modern_file.exists() else 0
    total_size = legacy_size + modern_size

    # Update manifest with processing metadata
    print()
    print("=" * 80)
    print("UPDATING MANIFEST")
    print("=" * 80)
    try:
        update_transformation_script("clean_depth_charts", {
            "last_processed": datetime.now().strftime("%Y-%m-%d"),
            "legacy_rows": legacy_count,
            "modern_rows": modern_count,
            "total_rows": legacy_count + modern_count,
            "legacy_size_bytes": legacy_size,
            "modern_size_bytes": modern_size,
            "total_size_bytes": total_size
        })
        print(f"\n[OK] Manifest updated with processing metadata:")
        print(f"  • Last processed: {datetime.now().strftime('%Y-%m-%d')}")
        print(f"  • Legacy rows: {legacy_count:,}")
        print(f"  • Modern rows: {modern_count:,}")
        print(f"  • Total rows: {legacy_count + modern_count:,}")
    except Exception as e:
        # Don't fail the whole function if manifest update fails
        print(f"\n[WARNING] Could not update manifest: {e}")

    # Return structured data
    return {
        'legacy_rows': legacy_count,
        'modern_rows': modern_count,
        'total_rows': legacy_count + modern_count,
        'legacy_file': legacy_file,
        'modern_file': modern_file,
        'legacy_size_bytes': legacy_size,
        'modern_size_bytes': modern_size,
        'total_size_bytes': total_size,
    }
