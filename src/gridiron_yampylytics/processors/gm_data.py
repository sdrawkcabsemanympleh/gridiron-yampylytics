"""Combine GM executive data from individual team files into single CSV.

This module processes GM/executive data scraped from Pro Football Reference,
combining 32 individual team CSV files into a single unified dataset with
standardized team codes and cleaned data fields.
"""
from pathlib import Path
from datetime import datetime
from typing import Any
import pandas as pd
from src.gridiron_yampylytics.manifest import update_transformation_script


def load_team_code_mapping() -> pd.DataFrame:
    """Load team code mapping (PFR to nflverse codes).

    :return: DataFrame with pfr_code, nflverse_code, team_name columns
    """
    # Team code mapping (PFR 3-letter codes from filenames to standard codes)
    # Based on the executive file naming (e.g., atl_executives.csv)
    mapping_data = {
        'pfr_code': [
            'atl', 'buf', 'car', 'chi', 'cin', 'cle', 'dal', 'den', 'det', 'gnb',
            'htx', 'clt', 'jax', 'kan', 'sdg', 'rai', 'mia', 'min', 'nwe', 'nor',
            'nyg', 'nyj', 'phi', 'pit', 'sfo', 'sea', 'ram', 'tam', 'oti', 'was',
            'crd', 'rav'
        ],
        'nflverse_code': [
            'ATL', 'BUF', 'CAR', 'CHI', 'CIN', 'CLE', 'DAL', 'DEN', 'DET', 'GB',
            'HOU', 'IND', 'JAX', 'KC', 'LAC', 'LV', 'MIA', 'MIN', 'NE', 'NO',
            'NYG', 'NYJ', 'PHI', 'PIT', 'SF', 'SEA', 'LA', 'TB', 'TEN', 'WAS',
            'ARI', 'BAL'
        ],
        'team_name': [
            'Atlanta Falcons', 'Buffalo Bills', 'Carolina Panthers', 'Chicago Bears',
            'Cincinnati Bengals', 'Cleveland Browns', 'Dallas Cowboys', 'Denver Broncos',
            'Detroit Lions', 'Green Bay Packers', 'Houston Texans', 'Indianapolis Colts',
            'Jacksonville Jaguars', 'Kansas City Chiefs', 'Los Angeles Chargers',
            'Las Vegas Raiders', 'Miami Dolphins', 'Minnesota Vikings',
            'New England Patriots', 'New Orleans Saints', 'New York Giants',
            'New York Jets', 'Philadelphia Eagles', 'Pittsburgh Steelers',
            'San Francisco 49ers', 'Seattle Seahawks', 'Los Angeles Rams',
            'Tampa Bay Buccaneers', 'Tennessee Titans', 'Washington Commanders',
            'Arizona Cardinals', 'Baltimore Ravens'
        ]
    }

    return pd.DataFrame(mapping_data)


def extract_team_code(filename: str) -> str:
    """Extract team code from filename (e.g., 'atl_executives.csv' -> 'atl').

    :param filename: Name of the executive CSV file
    :return: Team code (PFR format)
    """
    return filename.replace('_executives.csv', '')


def combine_gm_files(executives_dir: Path) -> pd.DataFrame:
    """Combine all GM executive CSV files into single DataFrame.

    :param executives_dir: Directory containing *_executives.csv files
    :return: Combined DataFrame with all GM/executive records
    """
    all_data = []
    files_processed = 0

    # Read all executive CSV files
    for csv_file in sorted(executives_dir.glob("*_executives.csv")):
        team_code = extract_team_code(csv_file.name)

        try:
            df = pd.read_csv(csv_file)
            df['pfr_team_code'] = team_code
            all_data.append(df)
            files_processed += 1
            print(f"  ✓ Loaded {csv_file.name} ({len(df)} records)")

        except Exception as e:
            print(f"  ⚠️  Failed to load {csv_file.name}: {e}")

    if not all_data:
        raise Exception("No executive files found!")

    # Combine all team data
    combined = pd.concat(all_data, ignore_index=True)
    print(f"\n  Combined {files_processed} files → {len(combined)} total records")

    return combined


def add_team_mapping(df: pd.DataFrame, mapping: pd.DataFrame) -> pd.DataFrame:
    """Add nflverse team codes to GM data.

    :param df: Combined GM DataFrame with pfr_team_code
    :param mapping: Team code mapping DataFrame
    :return: DataFrame with added nflverse_code and team_name columns
    """
    return df.merge(
        mapping[['pfr_code', 'nflverse_code', 'team_name']],
        left_on='pfr_team_code',
        right_on='pfr_code',
        how='left'
    ).drop(columns=['pfr_code'])


def clean_gm_data(df: pd.DataFrame) -> pd.DataFrame:
    """Clean and standardize GM data.

    :param df: Raw combined DataFrame
    :return: Cleaned DataFrame
    """
    # Convert years to integers (handle empty strings for current positions)
    df['From'] = pd.to_numeric(df['From'], errors='coerce').astype('Int64')

    # Handle 'To' column (empty string means current/ongoing)
    df['To'] = df['To'].replace('', pd.NA)
    df['To'] = pd.to_numeric(df['To'], errors='coerce').astype('Int64')

    # Calculate tenure length (ongoing positions get NA)
    df['tenure_years'] = df['To'] - df['From'] + 1

    # Add flag for ongoing positions
    df['is_current'] = df['To'].isna()

    # Reorder columns for clarity
    column_order = [
        'Person', 'pfr_team_code', 'nflverse_code', 'team_name',
        'From', 'To', 'tenure_years', 'is_current',
        'Titles', 'Teams', 'Notes'
    ]

    return df[column_order]


def combine_gm_data(
    input_dir: Path | None = None,
    output_dir: Path | None = None
) -> dict[str, Any]:
    """Combine GM executive data from individual team files into single CSV.

    :param input_dir: Directory with *_executives.csv files (default: data/raw/executives)
    :param output_dir: Output directory (default: data/reference)
    :return: Summary dict with counts and file paths
    """
    # Set default paths if not provided
    if input_dir is None:
        input_dir = Path.cwd() / "data" / "raw" / "executives"
    if output_dir is None:
        output_dir = Path.cwd() / "data" / "reference"

    output_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 80)
    print("COMBINING GM/EXECUTIVE DATA")
    print("=" * 80)
    print()

    # Load team code mapping
    print("Loading team code mapping...")
    team_mapping = load_team_code_mapping()
    print(f"  ✓ Loaded {len(team_mapping)} team mappings")
    print()

    # Combine all GM files
    print("Loading GM executive files...")
    combined_df = combine_gm_files(input_dir)
    print()

    # Add team mapping
    print("Adding nflverse team codes...")
    combined_df = add_team_mapping(combined_df, team_mapping)
    print(f"  ✓ Mapped {combined_df['nflverse_code'].notna().sum()} records to nflverse codes")
    print()

    # Clean data
    print("Cleaning and standardizing data...")
    cleaned_df = clean_gm_data(combined_df)
    print(f"  ✓ Cleaned {len(cleaned_df)} records")
    print(f"  ✓ Date range: {cleaned_df['From'].min()}-{cleaned_df['To'].max()} (ongoing positions: {cleaned_df['is_current'].sum()})")
    print()

    # Save combined file
    output_file = output_dir / "gm_tenures.csv"
    cleaned_df.to_csv(output_file, index=False)

    print("=" * 80)
    print("✅ COMBINE COMPLETE")
    print("=" * 80)
    print()
    print(f"Output: {output_file}")
    print(f"Records: {len(cleaned_df)}")
    print(f"Teams: {cleaned_df['nflverse_code'].nunique()}")
    print(f"Date range: {cleaned_df['From'].min()}-{cleaned_df['To'].max()}")
    print()
    print("Summary by team:")
    print(cleaned_df.groupby('team_name').size().sort_values(ascending=False).to_string())

    # Update manifest with processing metadata
    print()
    print("=" * 80)
    print("UPDATING MANIFEST")
    print("=" * 80)
    try:
        # Get file size
        file_size = output_file.stat().st_size if output_file.exists() else 0

        # Calculate stats
        num_teams = cleaned_df['nflverse_code'].nunique()
        total_records = len(cleaned_df)
        date_from = int(cleaned_df['From'].min())
        date_to = int(cleaned_df['To'].max()) if pd.notna(cleaned_df['To'].max()) else datetime.now().year
        current_positions = int(cleaned_df['is_current'].sum())

        # Update manifest
        update_transformation_script("combine_gm_data", {
            "last_processed": datetime.now().strftime("%Y-%m-%d"),
            "file_size_bytes": file_size,
            "total_records": total_records,
            "teams": num_teams,
            "date_range": f"{date_from}-{date_to}",
            "current_positions": current_positions
        })
        print(f"\n[OK] Manifest updated with processing metadata:")
        print(f"  • Last processed: {datetime.now().strftime('%Y-%m-%d')}")
        print(f"  • Total records: {total_records:,}")
        print(f"  • Teams: {num_teams}")
        print(f"  • Date range: {date_from}-{date_to}")
        print(f"  • Current positions: {current_positions}")
    except Exception as e:
        # Don't fail the whole function if manifest update fails
        print(f"\n[WARNING] Could not update manifest: {e}")

    # Return structured data
    return {
        'total_records': len(cleaned_df),
        'teams': cleaned_df['nflverse_code'].nunique(),
        'date_from': int(cleaned_df['From'].min()),
        'date_to': int(cleaned_df['To'].max()) if pd.notna(cleaned_df['To'].max()) else datetime.now().year,
        'current_positions': int(cleaned_df['is_current'].sum()),
        'output_file': output_file,
        'file_size_bytes': output_file.stat().st_size if output_file.exists() else 0,
    }
