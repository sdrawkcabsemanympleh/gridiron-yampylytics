"""Add yamplayer_id (unified player ID) to all datasets with player data.

REFACTORED VERSION - Two-phase approach:
1. PHASE 1: Collect ALL unique player identities from ALL datasets
2. PHASE 2: Generate yamplayer_id for each unique identity and apply to all datasets

This ensures the same player gets the same ID across all datasets.

Usage:
    uv run python -m scripts.add_yamplayer_id
    uv run python -m scripts.add_yamplayer_id --dry-run  # Preview only
    uv run python -m scripts.add_yamplayer_id --validate  # Run validation checks
"""
import sys
import hashlib
from pathlib import Path
from typing import Any
from dataclasses import dataclass, field
import argparse
import pandas as pd


@dataclass
class PlayerIdentity:
    """Represents a unique player identity across all datasets.

    Used for entity resolution to ensure same player = same yamplayer_id.
    """
    # Official IDs (priority order)
    gsis_id: str = ''
    pfr_id: str = ''
    mfl_id: str = ''
    espn_id: str = ''
    stats_global_id: str = ''

    # Identifying metadata
    name: str = ''
    normalized_name: str = ''
    birthdate: str = ''

    # Temporal/contextual info for disambiguation
    seasons: set[int] = field(default_factory=set)
    teams: set[str] = field(default_factory=set)
    positions: set[str] = field(default_factory=set)

    # Source tracking
    source_datasets: set[str] = field(default_factory=set)

    def __hash__(self) -> int:
        """Hash based on primary identifiers."""
        # Use IDs if available, otherwise name+birthdate
        if self.gsis_id:
            return hash(('gsis', self.gsis_id))
        if self.pfr_id:
            return hash(('pfr', self.pfr_id))
        if self.mfl_id:
            return hash(('mfl', self.mfl_id))
        if self.birthdate:
            return hash(('name_birth', self.normalized_name, self.birthdate))
        # Last resort: name + earliest season
        earliest_season = min(self.seasons) if self.seasons else 0
        return hash(('name_season', self.normalized_name, earliest_season))

    def __eq__(self, other: object) -> bool:
        """Two identities are equal if they share any authoritative ID."""
        if not isinstance(other, PlayerIdentity):
            return False

        # If any official ID matches, they're the same player
        if self.gsis_id and self.gsis_id == other.gsis_id:
            return True
        if self.pfr_id and self.pfr_id == other.pfr_id:
            return True
        if self.mfl_id and self.mfl_id == other.mfl_id:
            return True
        if self.espn_id and self.espn_id == other.espn_id:
            return True
        if self.stats_global_id and self.stats_global_id == other.stats_global_id:
            return True

        # If they have birthdate and name matches, probably same player
        if (self.birthdate and other.birthdate and
            self.birthdate == other.birthdate and
            self.normalized_name == other.normalized_name):
            return True

        # If same normalized name and overlapping seasons/teams, might be same player
        # (but this is risky - handle in merge_identities)

        return False

    def merge_with(self, other: 'PlayerIdentity') -> None:
        """Merge another identity into this one, keeping all data."""
        # Take any IDs we don't have
        if not self.gsis_id and other.gsis_id:
            self.gsis_id = other.gsis_id
        if not self.pfr_id and other.pfr_id:
            self.pfr_id = other.pfr_id
        if not self.mfl_id and other.mfl_id:
            self.mfl_id = other.mfl_id
        if not self.espn_id and other.espn_id:
            self.espn_id = other.espn_id
        if not self.stats_global_id and other.stats_global_id:
            self.stats_global_id = other.stats_global_id

        # Take name/birthdate if we don't have them
        if not self.name and other.name:
            self.name = other.name
            self.normalized_name = other.normalized_name
        if not self.birthdate and other.birthdate:
            self.birthdate = other.birthdate

        # Merge sets
        self.seasons.update(other.seasons)
        self.teams.update(other.teams)
        self.positions.update(other.positions)
        self.source_datasets.update(other.source_datasets)


def normalize_name(name: str) -> str:
    """Normalize player name for matching.

    Based on nflverse merge_name field conventions.

    :param name: Raw player name
    :return: Normalized name (lowercase, no suffixes, no punctuation)
    """
    if pd.isna(name) or name == '':
        return ''

    name = str(name).lower().strip()

    # Remove suffixes
    suffixes = ['jr', 'jr.', 'sr', 'sr.', 'ii', 'iii', 'iv', 'v']
    for suffix in suffixes:
        name = name.replace(f' {suffix}', '').replace(f'.{suffix}', '')

    # Remove punctuation
    name = name.replace('.', '').replace(',', '').replace('-', ' ')
    name = name.replace("'", '')

    # Normalize whitespace
    name = ' '.join(name.split())

    return name


def generate_yamplayer_id(identity: PlayerIdentity, existing_ids: set[str]) -> str:
    """Generate yamplayer_id from player identity with collision detection.

    :param identity: PlayerIdentity object
    :param existing_ids: Set of already-generated IDs (for collision detection)
    :return: yamplayer_id in format YAMP_<hash>
    """
    # Combine all identifying information (full MD5 hash)
    id_components = [
        identity.gsis_id,
        identity.pfr_id,
        identity.mfl_id,
        identity.espn_id,
        identity.stats_global_id,
        identity.name,
        identity.birthdate
    ]

    # Filter out empty values
    id_string = '|'.join([c for c in id_components if c])

    # Generate full MD5 hash (32 chars for lower collision probability)
    hash_obj = hashlib.md5(id_string.encode('utf-8'))
    hash_str = hash_obj.hexdigest()

    # Use first 12 chars (still 281 trillion possibilities)
    candidate = f'YAMP_{hash_str[:12]}'

    # Collision detection (should be extremely rare)
    counter = 1
    while candidate in existing_ids:
        print(f"  WARNING: Hash collision detected! {candidate}")
        candidate = f'YAMP_{hash_str[:12]}_{counter}'
        counter += 1

    return candidate


def extract_player_identity(row: pd.Series, dataset_name: str) -> PlayerIdentity | None:
    """Extract player identity from a dataset row.

    :param row: DataFrame row
    :param dataset_name: Name of source dataset
    :return: PlayerIdentity or None if no player data
    """
    identity = PlayerIdentity()

    # Extract IDs
    identity.gsis_id = str(row.get('gsis_id', '')) if pd.notna(row.get('gsis_id')) else ''
    identity.pfr_id = str(row.get('pfr_id', '')) if pd.notna(row.get('pfr_id')) else ''
    identity.mfl_id = str(row.get('mfl_id', '')) if pd.notna(row.get('mfl_id')) else ''
    identity.espn_id = str(row.get('espn_id', '')) if pd.notna(row.get('espn_id')) else ''
    identity.stats_global_id = str(row.get('stats_global_id', '')) if pd.notna(row.get('stats_global_id')) else ''

    # Handle play-by-play role IDs (they're all gsis_id aliases)
    for role_col in ['passer_id', 'rusher_id', 'receiver_id', 'kicker_id', 'punter_id',
                     'tackler_1_id', 'tackler_2_id', 'player_id']:
        if role_col in row.index and pd.notna(row.get(role_col)):
            identity.gsis_id = str(row[role_col])
            break

    # Extract name (try different column names)
    name = ''
    for name_col in ['player_name', 'name', 'full_name']:
        if name_col in row.index and pd.notna(row.get(name_col)):
            name = str(row[name_col])
            break

    identity.name = name
    identity.normalized_name = normalize_name(name)

    # Extract birthdate
    identity.birthdate = str(row.get('birthdate', '')) if pd.notna(row.get('birthdate')) else ''

    # Extract contextual info
    for season_col in ['season', 'year', 'game_year', 'draft_year']:
        if season_col in row.index and pd.notna(row.get(season_col)):
            try:
                identity.seasons.add(int(row[season_col]))
            except (ValueError, TypeError):
                pass

    for team_col in ['team', 'team_abbr', 'posteam', 'defteam']:
        if team_col in row.index and pd.notna(row.get(team_col)):
            identity.teams.add(str(row[team_col]))

    for pos_col in ['position', 'pos', 'calculated_position']:
        if pos_col in row.index and pd.notna(row.get(pos_col)):
            identity.positions.add(str(row[pos_col]))

    identity.source_datasets.add(dataset_name)

    # If we have no identifying info at all, return None
    if not any([identity.gsis_id, identity.pfr_id, identity.mfl_id, identity.espn_id,
                identity.stats_global_id, identity.name]):
        return None

    return identity


def collect_all_player_identities(data_dirs: list[Path]) -> dict[str, PlayerIdentity]:
    """PHASE 1: Collect all unique player identities from all datasets.

    :param data_dirs: List of directories to scan
    :return: Dict mapping identity key to PlayerIdentity
    """
    print("=" * 80)
    print("PHASE 1: COLLECTING PLAYER IDENTITIES FROM ALL DATASETS")
    print("=" * 80)
    print()

    # Collect all CSV files
    files_to_scan = []
    for data_dir in data_dirs:
        if data_dir.exists():
            files_to_scan.extend(data_dir.glob("*.csv"))

    print(f"Found {len(files_to_scan)} CSV files to scan")
    print()

    # Dictionary to store unique identities (keyed by hash)
    identities: dict[int, PlayerIdentity] = {}
    total_rows = 0

    # Scan each file
    for file_path in files_to_scan:
        print(f"Scanning {file_path.name}...", end=' ', flush=True)

        try:
            df = pd.read_csv(file_path)
            rows_in_file = 0

            # Check if file has player data
            has_player_data = any(col in df.columns for col in [
                'gsis_id', 'pfr_id', 'mfl_id', 'player_id', 'player_name', 'name',
                'passer_id', 'rusher_id', 'receiver_id'
            ])

            if not has_player_data:
                print("SKIP (no player data)")
                continue

            # Extract identity from each row
            for idx in range(len(df)):
                row = df.iloc[idx]
                identity = extract_player_identity(row, file_path.name)

                if identity:
                    rows_in_file += 1
                    identity_hash = hash(identity)

                    # Check if we've seen this player before
                    if identity_hash in identities:
                        # Merge with existing identity
                        identities[identity_hash].merge_with(identity)
                    else:
                        # New player
                        identities[identity_hash] = identity

            total_rows += rows_in_file
            print(f"OK ({rows_in_file:,} player rows, {len(identities):,} unique so far)")

        except Exception as e:
            print(f"ERROR: {e}")

    print()
    print(f"PHASE 1 COMPLETE:")
    print(f"  Total rows scanned: {total_rows:,}")
    print(f"  Unique players found: {len(identities):,}")
    print()

    # Convert hash keys to string keys for easier lookup
    identity_map = {str(k): v for k, v in identities.items()}

    return identity_map


def build_master_yamplayer_mapping(
    identities: dict[str, PlayerIdentity]
) -> tuple[pd.DataFrame, dict[str, pd.DataFrame]]:
    """PHASE 2: Generate yamplayer_id for all identities and create lookup tables.

    :param identities: Dict of PlayerIdentity objects from Phase 1
    :return: Tuple of (master_mapping_df, lookup_tables_by_id_type)
    """
    print("=" * 80)
    print("PHASE 2: GENERATING YAMPLAYER_IDs AND BUILDING LOOKUP TABLES")
    print("=" * 80)
    print()

    existing_ids: set[str] = set()
    mapping_rows = []

    # Generate yamplayer_id for each unique identity
    for identity_key, identity in identities.items():
        yamplayer_id = generate_yamplayer_id(identity, existing_ids)
        existing_ids.add(yamplayer_id)

        # Store in master mapping
        mapping_rows.append({
            'yamplayer_id': yamplayer_id,
            'gsis_id': identity.gsis_id or None,
            'pfr_id': identity.pfr_id or None,
            'mfl_id': identity.mfl_id or None,
            'espn_id': identity.espn_id or None,
            'stats_global_id': identity.stats_global_id or None,
            'name': identity.name or None,
            'normalized_name': identity.normalized_name or None,
            'birthdate': identity.birthdate or None,
            'seasons': '|'.join(str(s) for s in sorted(identity.seasons)) if identity.seasons else None,
            'teams': '|'.join(sorted(identity.teams)) if identity.teams else None,
            'positions': '|'.join(sorted(identity.positions)) if identity.positions else None,
            'source_datasets': '|'.join(sorted(identity.source_datasets)) if identity.source_datasets else None,
        })

    master_df = pd.DataFrame(mapping_rows)
    print(f"  Generated {len(master_df):,} yamplayer_ids")
    print()

    # Create lookup tables for each ID type
    print("Building lookup tables for each ID type...")
    lookups = {}

    id_columns = ['gsis_id', 'pfr_id', 'mfl_id', 'espn_id', 'stats_global_id']

    for id_col in id_columns:
        # Filter to non-null IDs and deduplicate
        lookup = master_df[master_df[id_col].notna()][[id_col, 'yamplayer_id']].copy()
        lookup = lookup.drop_duplicates(subset=[id_col])
        lookups[id_col] = lookup
        print(f"  {id_col}: {len(lookup):,} mappings")

    # Add aliases for gsis_id (play-by-play role IDs)
    if 'gsis_id' in lookups:
        gsis_lookup = lookups['gsis_id']
        lookups['player_id'] = gsis_lookup.rename(columns={'gsis_id': 'player_id'})

        for role_id in ['passer_id', 'rusher_id', 'receiver_id', 'kicker_id',
                        'punter_id', 'tackler_1_id', 'tackler_2_id']:
            lookups[role_id] = gsis_lookup.rename(columns={'gsis_id': role_id})

        print(f"  Created aliases for gsis_id (player_id, passer_id, rusher_id, etc.)")

    print()
    return master_df, lookups


def detect_player_id_columns(df: pd.DataFrame) -> list[str]:
    """Detect which player ID columns exist in dataset.

    :param df: DataFrame to check
    :return: List of detected ID column names in priority order
    """
    # Priority order (expert-recommended)
    priority_ids = [
        'gsis_id',      # Best for modern play-by-play
        'pfr_id',       # Best for draft/combine/historical
        'mfl_id',       # Fallback with widest coverage
        'espn_id',
        'stats_global_id',
        'player_id',    # Alias for gsis_id
    ]

    # Play-by-play role IDs
    pbp_ids = [
        'passer_id', 'rusher_id', 'receiver_id', 'kicker_id',
        'punter_id', 'tackler_1_id', 'tackler_2_id'
    ]

    detected = []
    for col in priority_ids + pbp_ids:
        if col in df.columns:
            detected.append(col)

    return detected


def apply_yamplayer_id_to_file(
    file_path: Path,
    lookups: dict[str, pd.DataFrame],
    dry_run: bool = False
) -> dict[str, Any]:
    """Apply yamplayer_id to a single file using lookup tables.

    :param file_path: Path to CSV file
    :param lookups: Lookup tables from build_master_yamplayer_mapping()
    :param dry_run: If True, don't save changes
    :return: Dict with stats about the operation
    """
    result = {
        'file': file_path.name,
        'processed': False,
        'rows_before': 0,
        'rows_after': 0,
        'id_column': None,
        'matched': 0,
        'unmatched': 0,
        'error': None
    }

    try:
        # Load file
        df = pd.read_csv(file_path)
        result['rows_before'] = len(df)

        # Detect player ID columns
        detected_ids = detect_player_id_columns(df)

        if not detected_ids:
            # No player IDs found - skip this file
            return result

        # Find first available ID column that we have a lookup for
        id_col = None
        for col in detected_ids:
            if col in lookups:
                id_col = col
                break

        if not id_col:
            result['error'] = f"Has player IDs {detected_ids} but no lookup available"
            return result

        result['id_column'] = id_col

        # Filter out empty strings before merge (data quality fix)
        df_filtered = df[df[id_col].notna() & (df[id_col] != '')].copy()
        df_empty = df[~(df[id_col].notna() & (df[id_col] != ''))].copy()

        # Join to add yamplayer_id
        lookup = lookups[id_col]
        df_filtered = df_filtered.merge(lookup, on=id_col, how='left')

        # Recombine
        if len(df_empty) > 0:
            df_empty['yamplayer_id'] = None
            df = pd.concat([df_filtered, df_empty], ignore_index=True)
        else:
            df = df_filtered

        result['rows_after'] = len(df)
        result['matched'] = df['yamplayer_id'].notna().sum()
        result['unmatched'] = df['yamplayer_id'].isna().sum()

        # Save if not dry run
        if not dry_run:
            df.to_csv(file_path, index=False)
            result['processed'] = True

    except Exception as e:
        result['error'] = str(e)

    return result


def validate_yamplayer_ids(master_df: pd.DataFrame, data_dirs: list[Path]) -> dict[str, Any]:
    """Run validation checks on yamplayer_id assignments.

    :param master_df: Master mapping DataFrame
    :param data_dirs: Directories containing datasets
    :return: Dict with validation results
    """
    print("=" * 80)
    print("VALIDATION: CHECKING YAMPLAYER_ID INTEGRITY")
    print("=" * 80)
    print()

    results = {
        'duplicate_ids': [],
        'split_players': [],
        'collision_count': 0,
        'total_players': len(master_df)
    }

    # Check 1: No duplicate IDs for different players
    print("Checking for duplicate yamplayer_ids...")
    duplicate_check = master_df.groupby('yamplayer_id').agg({
        'gsis_id': 'nunique',
        'pfr_id': 'nunique',
        'name': 'nunique'
    })

    duplicates = duplicate_check[
        (duplicate_check['gsis_id'] > 1) |
        (duplicate_check['pfr_id'] > 1)
    ]

    if len(duplicates) > 0:
        print(f"  WARNING: Found {len(duplicates)} yamplayer_ids mapping to multiple players!")
        results['duplicate_ids'] = duplicates.index.tolist()
    else:
        print("  OK: No duplicate IDs found")

    # Check 2: No split players (same gsis_id, different yamplayer_ids)
    print("Checking for split players...")
    gsis_check = master_df[master_df['gsis_id'].notna()].groupby('gsis_id').agg({
        'yamplayer_id': 'nunique',
        'name': 'first'
    })

    splits = gsis_check[gsis_check['yamplayer_id'] > 1]

    if len(splits) > 0:
        print(f"  WARNING: Found {len(splits)} players with multiple yamplayer_ids!")
        results['split_players'] = splits.index.tolist()
    else:
        print("  OK: No split players found")

    # Check 3: Coverage report
    print()
    print("Coverage by ID type:")
    for id_col in ['gsis_id', 'pfr_id', 'mfl_id', 'espn_id', 'stats_global_id']:
        if id_col in master_df.columns:
            count = master_df[id_col].notna().sum()
            pct = (count / len(master_df)) * 100
            print(f"  {id_col}: {count:,} ({pct:.1f}%)")

    print()
    return results


def main() -> None:
    """Main entry point for adding yamplayer_id to all datasets."""
    sys.stdout.reconfigure(encoding='utf-8')

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run', action='store_true', help='Preview changes without saving')
    parser.add_argument('--validate', action='store_true', help='Run validation checks')
    args = parser.parse_args()

    print("=" * 80)
    print("YAMPLAYER_ID GENERATOR - TWO-PHASE APPROACH")
    print("=" * 80)
    print()
    if args.dry_run:
        print("DRY RUN MODE - No files will be modified")
        print()

    base_dir = Path(__file__).parent.parent
    data_dirs = [
        base_dir / "data" / "nflverse",
        base_dir / "data" / "yas",
        base_dir / "data" / "reference"
    ]

    # PHASE 1: Collect all player identities
    identities = collect_all_player_identities(data_dirs)

    # PHASE 2: Generate IDs and build lookups
    master_df, lookups = build_master_yamplayer_mapping(identities)

    # Save master mapping (audit trail)
    mapping_file = base_dir / "data" / "yamplayer_mapping.csv"
    if not args.dry_run:
        master_df.to_csv(mapping_file, index=False)
        print(f"Saved master mapping to: {mapping_file}")
        print()

    # PHASE 3: Apply to all datasets
    print("=" * 80)
    print("PHASE 3: APPLYING YAMPLAYER_IDs TO ALL DATASETS")
    print("=" * 80)
    print()

    files_to_process = []
    for data_dir in data_dirs:
        if data_dir.exists():
            files_to_process.extend(data_dir.glob("*.csv"))

    results = []
    for file_path in files_to_process:
        # Skip the mapping file we just created
        if file_path.name == 'yamplayer_mapping.csv':
            continue

        print(f"Processing {file_path.name}...", end=' ', flush=True)
        result = apply_yamplayer_id_to_file(file_path, lookups, dry_run=args.dry_run)
        results.append(result)

        if result['processed'] or args.dry_run:
            print(f"OK Added via {result['id_column']} ({result['matched']:,} matched, {result['unmatched']:,} unmatched)")
        elif result['error']:
            print(f"ERROR: {result['error']}")
        else:
            print("SKIP (no player IDs)")

    # Summary
    print()
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)

    processed = [r for r in results if r['processed'] or args.dry_run]
    skipped = [r for r in results if not r['processed'] and not r['error'] and not args.dry_run]
    errors = [r for r in results if r['error']]

    print(f"\nProcessed: {len(processed)} files")
    for r in processed:
        if r['id_column']:
            print(f"   • {r['file']}: {r['matched']:,} matched, {r['unmatched']:,} unmatched")

    if skipped:
        print(f"\nSkipped: {len(skipped)} files (no player data)")

    if errors:
        print(f"\nErrors: {len(errors)} files")
        for r in errors:
            print(f"   • {r['file']}: {r['error']}")

    total_unmatched = sum(r.get('unmatched', 0) for r in processed)
    if total_unmatched > 0:
        print(f"\nWARNING: Total unmatched rows across all files: {total_unmatched:,}")
        print("   (These should be significantly reduced compared to old approach)")

    # Run validation if requested
    if args.validate:
        print()
        validation_results = validate_yamplayer_ids(master_df, data_dirs)

        if validation_results['duplicate_ids'] or validation_results['split_players']:
            print("\nVALIDATION FAILED - Issues detected!")
            sys.exit(1)
        else:
            print("\nVALIDATION PASSED - All checks OK!")

    if args.dry_run:
        print("\nDRY RUN - No files were modified. Run without --dry-run to apply changes.")
    else:
        print(f"\nAll changes saved!")


if __name__ == "__main__":
    main()
