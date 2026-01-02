"""Data status utility module.

This module provides status checking for downloaded data files and databases,
giving a quick overview of what's available locally.

For programmatic use:
    from gridiron_yampylytics.utils.status import show_status
    result = show_status()

Provides:
- NFLverse dataset inventory with sizes
- GM/executive data status
- DuckDB database status
- Quick start recommendations
"""
from pathlib import Path
from typing import Any
from gridiron_yampylytics.manifest import read_manifest


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


def check_nflverse_data(data_dir: Path | None = None) -> dict[str, dict]:
    """Check what nflverse data files exist.

    :param data_dir: Data directory to check (default: ./data/nflverse)
    :return: Dictionary mapping dataset names to file info (path, size, format)
    """
    if data_dir is None:
        data_dir = Path.cwd() / "data" / "nflverse"

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


def check_gm_data(gm_dir: Path | None = None) -> dict[str, int | None]:
    """Check GM executives data status.

    :param gm_dir: GM data directory to check (default: ./data/raw/executives)
    :return: Dictionary with count and total size info
    """
    if gm_dir is None:
        gm_dir = Path.cwd() / "data" / "raw" / "executives"

    if not gm_dir.exists():
        return {'count': 0, 'size': None}

    csv_files = list(gm_dir.glob("*.csv"))
    total_size = sum(f.stat().st_size for f in csv_files)

    return {
        'count': len(csv_files),
        'size': total_size
    }


def check_database(db_path: Path | None = None) -> dict[str, bool | int | None]:
    """Check DuckDB database status.

    :param db_path: Database path to check (default: ./gridiron_yampylytics.db)
    :return: Dictionary with existence and size info
    """
    if db_path is None:
        db_path = Path.cwd() / "gridiron_yampylytics.db"

    if not db_path.exists():
        return {'exists': False, 'size': None}

    return {
        'exists': True,
        'size': db_path.stat().st_size
    }


def show_status(
    data_dir: Path | None = None,
    gm_dir: Path | None = None,
    db_path: Path | None = None
) -> dict[str, Any]:
    """Display status of all data sources.

    Shows comprehensive status of all gridiron-yampylytics data components:
    - NFLverse datasets (with sizes and formats)
    - GM/executive data files
    - DuckDB database
    - Quick start recommendations

    :param data_dir: NFLverse data directory (default: ./data/nflverse)
    :param gm_dir: GM data directory (default: ./data/raw/executives)
    :param db_path: Database path (default: ./gridiron_yampylytics.db)
    :return: Summary dict with status information
    """
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
    nflverse_datasets = check_nflverse_data(data_dir)
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
    gm_info = check_gm_data(gm_dir)
    print("👔 GM/EXECUTIVE DATA")
    print("-" * 80)

    if gm_info['count'] == 0:
        print("  ❌ No GM data found")
        print("  Run: inv download-gm")
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
    db_info = check_database(db_path)
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

    # Return structured data for programmatic use
    return {
        'nflverse': {
            'datasets': nflverse_datasets,
            'count': len(nflverse_datasets),
            'total_size': sum(d['size'] for d in nflverse_datasets.values()) if nflverse_datasets else 0,
        },
        'gm_data': gm_info,
        'database': db_info,
        'missing_components': missing_components,
        'ready': len(missing_components) == 0,
    }
