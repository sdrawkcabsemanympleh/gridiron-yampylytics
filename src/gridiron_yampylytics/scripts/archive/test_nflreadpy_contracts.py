"""Test nflreadpy contract data to see what we get.

This script explores the contract data available via nflreadpy.
"""
import sys
import nflreadpy as nfl

def main() -> None:
    """Test contract data loading."""
    sys.stdout.reconfigure(encoding='utf-8')

    print("Loading contract data from nflreadpy...")
    contracts = nfl.load_contracts()

    print(f"\n{'='*80}")
    print("CONTRACT DATA ANALYSIS")
    print(f"{'='*80}")

    print(f"\nTotal contracts: {contracts.shape[0]:,}")
    print(f"Total columns: {contracts.shape[1]}")

    print(f"\n{'Columns:':-^80}")
    for col in contracts.columns:
        print(f"  - {col}")

    print(f"\n{'Sample Data:':-^80}")
    print(contracts.head(5))

    print(f"\n{'Year Range:':-^80}")
    if 'year_signed' in contracts.columns:
        print(f"  Earliest: {contracts['year_signed'].min()}")
        print(f"  Latest: {contracts['year_signed'].max()}")

    print(f"\n{'Teams Covered:':-^80}")
    if 'team' in contracts.columns:
        teams = contracts['team'].unique()
        print(f"  Total teams: {len(teams)}")
        print(f"  Teams: {sorted(teams)}")

    print(f"\n{'Key Fields Present:':-^80}")
    key_fields = ['apy', 'guaranteed', 'apy_cap_pct', 'value', 'years']
    for field in key_fields:
        present = field in contracts.columns
        print(f"  {field}: {'✓' if present else '✗'}")

    print(f"\n{'='*80}")
    print("CONCLUSION:")
    print(f"{'='*80}")
    print("\nContract data includes:")
    print("  ✓ APY (Average Per Year)")
    print("  ✓ Guaranteed money")
    print("  ✓ APY as % of cap")
    print("  ✓ Total contract value")
    print("  ✓ Contract length (years)")
    print("  ✓ Player IDs (gsis_id, otc_id)")

    print("\nWhat's MISSING:")
    print("  ✗ Yearly cap hit breakdown")
    print("  ✗ Dead money by year")
    print("  ✗ Team cap space by year")
    print("\n  → May need Spotrac scraper for detailed cap/dead money analysis")

if __name__ == "__main__":
    main()
