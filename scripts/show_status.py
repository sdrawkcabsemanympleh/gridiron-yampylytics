"""Show status of downloaded data files and database.

This script provides a quick overview of what data is available locally,
including file sizes, coverage information from manifest, and database status.
"""
import sys
from pathlib import Path
from src.gridiron_yampylytics.manifest import read_manifest


def format_size(size_bytes: int) -> str:
    """Format byte size as human-readable string.

    :param size_bytes: Size in bytes
    :return: Formatted string (e.g., "1.2 GB", "45 MB")
    """
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} PB"


def check_nflverse_data() -> dict[str, dict]:
    """Check what nflverse data files exist.

    :return: Dictionary mapping dataset names to file info (path, size)
    """
    data_dir = Path(__file__).parent.parent / "data" / "nflverse"
    if not data_dir.exists():
        return {}

    datasets = {}
    for file_path in data_dir.iterdir():
        if file_path.is_file() and file_path.suffix in ['.csv', '.parquet']:
            datasets[file_path.stem] = {
                'path': file_path,
                'size': file_path.stat().st_size,
                'format': file_path.suffix[1:]  # Remove leading dot
            }
    return datasets


def check_gm_data() -> dict[str, int | None]:
    """Check GM executives data status.

    :return: Dictionary with count and total size info
    """
    gm_dir = Path(__file__).parent.parent / "data" / "raw" / "executives"
    if not gm_dir.exists():
        return {'count': 0, 'size': None}

    csv_files = list(gm_dir.glob("*.csv"))
    total_size = sum(f.stat().st_size for f in csv_files)

    return {
        'count': len(csv_files),
        'size': total_size
    }


def check_database() -> dict[str, bool | int | None]:
    """Check DuckDB database status.

    :return: Dictionary with existence, size, and type info
    """
    db_path = Path(__file__).parent.parent / "gridiron_yampylytics.db"
    if not db_path.exists():
        return {'exists': False, 'size': None}

    return {
        'exists': True,
        'size': db_path.stat().st_size
    }


def main() -> None:
    """Display status of all data sources."""
    sys.stdout.reconfigure(encoding='utf-8')

    print("=" * 80)
    print("GRIDIRON-YAMPYLYTICS DATA STATUS")
    print("=" * 80)
    print()

    # Try to read manifest for enhanced info
    try:
        manifest = read_manifest()
        has_manifest = True
    except FileNotFoundError:
        manifest = None
        has_manifest = False
        print("⚠️  Warning: manifest.json not found (enhanced info unavailable)")
        print()

    # Check nflverse data
    nflverse_datasets = check_nflverse_data()
    print("📊 NFLVERSE DATA")
    print("-" * 80)

    if not nflverse_datasets:
        print("  ❌ No nflverse data found")
        print("  Run: inv load-data")
    else:
        total_size = sum(d['size'] for d in nflverse_datasets.values())
        print(f"  ✓ {len(nflverse_datasets)} dataset(s) downloaded")
        print(f"  Total size: {format_size(total_size)}")
        print()
        print("  Datasets:")

        # Sort by size (largest first)
        sorted_datasets = sorted(
            nflverse_datasets.items(),
            key=lambda x: x[1]['size'],
            reverse=True
        )

        for name, info in sorted_datasets:
            size_str = format_size(info['size'])
            format_str = info['format'].upper()
            print(f"    • {name:<25} {size_str:>10}  ({format_str})")

    print()

    # Check GM data
    gm_info = check_gm_data()
    print("👔 GM/EXECUTIVE DATA")
    print("-" * 80)

    if gm_info['count'] == 0:
        print("  ❌ No GM data found")
        print("  Run: inv download-gm-data (coming in Phase 3)")
    else:
        size_str = format_size(gm_info['size']) if gm_info['size'] else 'N/A'
        print(f"  ✓ {gm_info['count']} team file(s) downloaded")
        print(f"  Total size: {size_str}")

        if has_manifest and 'gm_executives' in manifest['datasets']:
            gm_data = manifest['datasets']['gm_executives']
            if 'coverage' in gm_data:
                years = gm_data['coverage'].get('years', 'Unknown')
                teams = gm_data['coverage'].get('teams', 'Unknown')
                print(f"  Coverage: {years} ({teams} teams)")

    print()

    # Check database
    db_info = check_database()
    print("🗄️  DUCKDB DATABASE")
    print("-" * 80)

    if not db_info['exists']:
        print("  ❌ Database not found")
        print("  Run: inv create-duckdb")
    else:
        size_str = format_size(db_info['size'])
        print(f"  ✓ Database exists")
        print(f"  Size: {size_str}")
        print(f"  Location: gridiron_yampylytics.db")
        print()
        print("  Open with: inv sql")

    print()

    # Summary recommendations
    print("💡 QUICK START")
    print("-" * 80)

    missing_components = []
    if not nflverse_datasets:
        missing_components.append("nflverse data")
    if gm_info['count'] == 0:
        missing_components.append("GM data")
    if not db_info['exists']:
        missing_components.append("database")

    if missing_components:
        print("  Missing: " + ", ".join(missing_components))
        print()
        print("  Run complete setup:")
        print("    inv setup              # Downloads data + creates database")
        print()
        print("  Or run individual steps:")
        print("    inv load-data          # Download nflverse + GM data")
        print("    inv process-data       # Process and enrich data")
        print("    inv create-duckdb      # Create database")
    else:
        print("  ✓ All components present!")
        print()
        print("  Ready to analyze:")
        print("    inv sql                # Open interactive SQL explorer")
        print()
        print("  Update data:")
        print("    inv load-data          # Refresh nflverse data")

    print()
    print("=" * 80)


if __name__ == "__main__":
    main()
