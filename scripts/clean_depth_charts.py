"""Clean and split depth charts data into legacy and modern formats.

This script addresses data quality issues in the depth_charts_all.csv file:
1. Quoted newlines in depth_position field (causes CSV parsing errors)
2. Dual schema format (old vs new structure in same file)

The script splits the data into two clean files:
- depth_charts_legacy.csv (2001-2023): Traditional depth chart format
- depth_charts_modern.csv (2024-2025): New position group format

Usage:
    uv run python -m scripts.clean_depth_charts

Output:
    data/processed/depth_charts_legacy.csv
    data/processed/depth_charts_modern.csv
"""
import sys
import csv
from pathlib import Path


def clean_depth_charts() -> tuple[int, int]:
    """Clean depth charts data and split into legacy/modern formats.

    :return: Tuple of (legacy_rows, modern_rows) written
    """
    # File paths
    input_file = Path(__file__).parent.parent / "data" / "nflverse" / "depth_charts.csv"
    output_dir = Path(__file__).parent.parent / "data" / "nflverse"
    output_dir.mkdir(parents=True, exist_ok=True)

    legacy_file = output_dir / "depth_charts_legacy.csv"
    modern_file = output_dir / "depth_charts_modern.csv"

    legacy_count = 0
    modern_count = 0

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

    return legacy_count, modern_count


def main() -> None:
    """Main entry point for cleaning depth charts."""
    sys.stdout.reconfigure(encoding='utf-8')

    print("=" * 80)
    print("CLEANING DEPTH CHARTS DATA")
    print("=" * 80)
    print()
    print("This script fixes:")
    print("  1. Quoted newlines in depth_position field")
    print("  2. Dual schema format (splits into separate files)")
    print()

    try:
        legacy_count, modern_count = clean_depth_charts()

        print("=" * 80)
        print("✅ CLEANUP COMPLETE")
        print("=" * 80)
        print()
        print("Output files:")
        print(f"  Legacy (2001-2023): data/nflverse/depth_charts_legacy.csv")
        print(f"    Rows: {legacy_count:,}")
        print(f"    Columns: 15 (season, team, week, player, position, etc.)")
        print()
        print(f"  Modern (2024-2025): data/nflverse/depth_charts_modern.csv")
        print(f"    Rows: {modern_count:,}")
        print(f"    Columns: 12 (gsis_id, timestamp, team, position groups, rank)")
        print()
        print(f"Total rows processed: {legacy_count + modern_count:,}")
        print()
        print("Data is now ready for DuckDB/Harlequin!")
        print()
        print("Example DuckDB queries:")
        print()
        print("  -- Load legacy data")
        print("  CREATE TABLE depth_legacy AS")
        print("  SELECT * FROM 'data/nflverse/depth_charts_legacy.csv';")
        print()
        print("  -- Load modern data")
        print("  CREATE TABLE depth_modern AS")
        print("  SELECT * FROM 'data/nflverse/depth_charts_modern.csv';")
        print()
        print("  -- Query all depth charts (UNION)")
        print("  SELECT season, club_code as team, position, gsis_id")
        print("  FROM depth_legacy")
        print("  UNION ALL")
        print("  SELECT YEAR(dt::TIMESTAMP) as season, team, pos_name as position, gsis_id")
        print("  FROM depth_modern;")

    except Exception as e:
        print()
        print("=" * 80)
        print("❌ ERROR")
        print("=" * 80)
        print(f"Failed to clean depth charts: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
