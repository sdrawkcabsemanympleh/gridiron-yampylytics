"""Display all available gridiron-yampylytics commands.

Shows a categorized list of all uv script entry points with brief descriptions.
"""
import sys


def main() -> None:
    """Display all available commands."""
    # Configure UTF-8 output for emojis and unicode
    sys.stdout.reconfigure(encoding='utf-8')

    if '--help' in sys.argv or '-h' in sys.argv:
        print(main.__doc__)
        return

    print()
    print("=" * 80)
    print("GRIDIRON-YAMPYLYTICS AVAILABLE COMMANDS")
    print("=" * 80)
    print()

    print("📦 DATA DOWNLOAD & STATUS")
    print("-" * 80)
    print("  uv run load-data        Download NFL data (supports --essential, --analysis, --yampy)")
    print("  uv run show-status      Show status of downloaded data and database")
    print()

    print("🚀 SETUP WORKFLOWS (download → process → create database)")
    print("-" * 80)
    print("  uv run setup-quick      Fast setup with essentials (no GM data)")
    print("  uv run setup-analysis   Analysis-ready (all data except pbp)")
    print("  uv run setup-full       Complete data with views")
    print("  uv run setup-yampy      Complete data with indexed tables (max performance)")
    print()

    print("⚙️  DATA PROCESSING")
    print("-" * 80)
    print("  uv run clean-depth-charts      Split depth charts by schema (legacy vs modern)")
    print("  uv run combine-gm-data         Merge GM executive CSVs into unified file")
    print("  uv run generate-yamplayer-id   Generate universal player IDs")
    print("  uv run calculate-yas           Calculate Yampylytics Athletic Score (YAS)")
    print("  uv run process-data            Run complete processing pipeline")
    print()

    print("🗄️  DATABASE CREATION")
    print("-" * 80)
    print("  uv run create-duckdb-views     Create lightweight DuckDB views")
    print("  uv run create-duckdb-tables    Create indexed DuckDB tables (faster queries)")
    print()

    print("🔍 DATABASE EXPLORATION")
    print("-" * 80)
    print("  uv run sql              Launch Harlequin SQL explorer")
    print()

    print("💡 TIPS")
    print("-" * 80)
    print("  • Add --help to any command for detailed usage info")
    print("  • Example: uv run load-data --help")
    print("  • Most commands support --gm or --no-gm flags for GM data")
    print()

    print("📚 For more information, see:")
    print("  • README.md - Project overview and getting started")
    print("  • CLAUDE.md - Development commands and architecture notes")
    print()


if __name__ == "__main__":
    main()
