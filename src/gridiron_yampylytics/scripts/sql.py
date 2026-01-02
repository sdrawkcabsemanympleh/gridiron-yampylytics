"""Launch Harlequin SQL explorer for interactive data analysis.

Opens an interactive SQL terminal (like DBeaver/DataGrip but in your terminal)
for exploring the gridiron_yampylytics.db database.

Automatically detects Windows and adds --no-download-tzdata flag for compatibility.
"""
import os
import sys
import subprocess


def main() -> None:
    """Launch Harlequin SQL explorer for interactive data analysis.

    Opens an interactive SQL terminal (like DBeaver/DataGrip but in your terminal)
    for exploring the gridiron_yampylytics.db database.

    Automatically detects Windows and adds --no-download-tzdata flag for compatibility.

    Usage:
        uv run sql
    """
    # Check for --help before running
    if '--help' in sys.argv or '-h' in sys.argv:
        print(main.__doc__)
        return

    # Build command
    cmd = ['harlequin', 'gridiron_yampylytics.db']

    # Add Windows-specific flag
    if os.name == 'nt':
        cmd.append('--no-download-tzdata')

    # Run Harlequin
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error running Harlequin: {e}", file=sys.stderr)
        sys.exit(1)
    except FileNotFoundError:
        print("Error: Harlequin not found. Make sure it's installed.", file=sys.stderr)
        print("Install with: uv add harlequin", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
