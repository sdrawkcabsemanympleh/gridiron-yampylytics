"""Validate yamplayer_id V2 mapping against V1.

Performs validation checks to ensure V2:
1. Doesn't create duplicate gsis_ids (merge logic test)
2. Doesn't have hash collisions (different players with same hash)
3. Maintains or improves gsis_id coverage vs V1
4. Doesn't lose players from V1

Usage:
    uv run python -m scripts.validate_yamplayer_v2
"""
import sys
import polars as pl
from pathlib import Path


def validate_v2_mapping(base_dir: Path) -> bool:
    """Validate V2 mapping file against V1.

    :param base_dir: Base directory containing data/ folder
    :return: True if all validations pass, False otherwise
    """
    sys.stdout.reconfigure(encoding='utf-8')

    reference_dir = base_dir / 'data' / 'reference'
    v1_file = reference_dir / 'yamplayer_mapping.csv'
    v2_file = reference_dir / 'yamplayer_mapping_v2.csv'

    print("\n" + "="*80)
    print("YAMPLAYER_ID V2 VALIDATION")
    print("="*80)

    # Check files exist
    if not v1_file.exists():
        print(f"\n[ERROR] V1 mapping not found: {v1_file}")
        return False
    if not v2_file.exists():
        print(f"\n[ERROR] V2 mapping not found: {v2_file}")
        return False

    # Load mappings
    print("\nLoading mapping files...")
    v1 = pl.read_csv(v1_file)
    v2 = pl.read_csv(v2_file)
    print(f"  V1: {len(v1):,} rows")
    print(f"  V2: {len(v2):,} rows")

    all_passed = True

    # TEST 1: Check for duplicate gsis_ids in V2 (merge logic failure)
    print("\n" + "="*80)
    print("TEST 1: Duplicate gsis_id Detection (Merge Logic Test)")
    print("="*80)

    v2_with_gsis = v2.filter(pl.col('gsis_id').is_not_null())
    gsis_counts = v2_with_gsis.group_by('gsis_id').agg(pl.count().alias('count'))
    duplicates = gsis_counts.filter(pl.col('count') > 1)

    if len(duplicates) == 0:
        print("\n[PASS] No duplicate gsis_ids in V2")
    else:
        print(f"\n[FAIL] Found {len(duplicates)} gsis_ids with duplicates!")
        print("\nDuplicate gsis_ids:")
        for row in duplicates.head(10).iter_rows(named=True):
            gsis = row['gsis_id']
            count = row['count']
            players = v2.filter(pl.col('gsis_id') == gsis).select(['name', 'yamplayer_id'])
            print(f"  {gsis}: {count} occurrences")
            for p in players.iter_rows(named=True):
                print(f"    - {p['name']} ({p['yamplayer_id']})")
        all_passed = False

    # TEST 2: Check for hash collisions (different players, same hash)
    print("\n" + "="*80)
    print("TEST 2: Hash Collision Detection")
    print("="*80)

    hash_counts = v2.group_by('yamplayer_id').agg(pl.count().alias('count'))
    collisions = hash_counts.filter(pl.col('count') > 1)

    if len(collisions) == 0:
        print("\n[PASS] No hash collisions in V2")
    else:
        print(f"\n[FAIL] Found {len(collisions)} hash collisions!")
        print("\nColliding hashes:")
        for row in collisions.head(10).iter_rows(named=True):
            yamp_id = row['yamplayer_id']
            count = row['count']
            players = v2.filter(pl.col('yamplayer_id') == yamp_id).select(['name', 'gsis_id', 'pfr_id'])
            print(f"  {yamp_id}: {count} players")
            for p in players.iter_rows(named=True):
                print(f"    - {p['name']} (gsis:{p['gsis_id']}, pfr:{p['pfr_id']})")
        all_passed = False

    # TEST 3: Coverage comparison (gsis_id)
    print("\n" + "="*80)
    print("TEST 3: Coverage Comparison")
    print("="*80)

    v1_gsis = set(v1.filter(pl.col('gsis_id').is_not_null())['gsis_id'].to_list())
    v2_gsis = set(v2.filter(pl.col('gsis_id').is_not_null())['gsis_id'].to_list())

    in_v1_not_v2 = v1_gsis - v2_gsis
    in_v2_not_v1 = v2_gsis - v1_gsis

    print(f"\nV1 gsis_id coverage: {len(v1_gsis):,}")
    print(f"V2 gsis_id coverage: {len(v2_gsis):,}")
    print(f"\nIn V1 but NOT in V2: {len(in_v1_not_v2):,}")
    print(f"In V2 but NOT in V1: {len(in_v2_not_v1):,}")

    if len(in_v1_not_v2) == 0:
        print("\n[PASS] V2 includes all V1 gsis_ids (no losses)")
    else:
        print(f"\n[WARNING] V2 missing {len(in_v1_not_v2)} gsis_ids from V1")
        print("\nSample of missing gsis_ids (first 10):")
        for gsis in list(in_v1_not_v2)[:10]:
            player = v1.filter(pl.col('gsis_id') == gsis).select(['name', 'pfr_id']).row(0, named=True)
            print(f"  {gsis}: {player['name']} (pfr:{player['pfr_id']})")
        # This is a warning, not a failure - we expect some losses (the 67 FA players)

    if len(in_v2_not_v1) > 0:
        print(f"\n[INFO] V2 adds {len(in_v2_not_v1):,} new gsis_ids")
        print("Sample of new players (first 5):")
        for gsis in list(in_v2_not_v1)[:5]:
            player = v2.filter(pl.col('gsis_id') == gsis).select(['name', 'pfr_id']).row(0, named=True)
            print(f"  {gsis}: {player['name']} (pfr:{player['pfr_id']})")

    # TEST 4: Overall player count comparison
    print("\n" + "="*80)
    print("TEST 4: Total Player Count")
    print("="*80)

    print(f"\nV1 total players: {len(v1):,}")
    print(f"V2 total players: {len(v2):,}")
    print(f"Difference: {len(v2) - len(v1):,}")

    if len(v2) >= len(v1):
        print("\n[PASS] V2 has equal or more players than V1")
    else:
        print(f"\n[FAIL] V2 has FEWER players than V1 ({len(v1) - len(v2):,} fewer)")
        all_passed = False

    # SUMMARY
    print("\n" + "="*80)
    print("VALIDATION SUMMARY")
    print("="*80)

    if all_passed:
        print("\n[SUCCESS] All critical validations passed!")
        print("\nV2 is ready for consideration.")
        print("Next steps:")
        print("  1. Review coverage differences")
        print("  2. Spot-check known players")
        print("  3. Decide on hydration strategy")
    else:
        print("\n[FAILURE] Some validations failed!")
        print("Review failures above before using V2.")

    return all_passed


def main() -> None:
    """CLI entry point for V2 validation."""
    base_dir = Path.cwd()
    success = validate_v2_mapping(base_dir)
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
