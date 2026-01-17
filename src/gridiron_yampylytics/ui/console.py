"""Fancy console UI using rich library.

This module provides a polished console interface for displaying data download
and processing progress. It supports two modes:
- Fancy: Live-updating tables with progress bars and status indicators
- Verbose: Traditional logging output (fallback for non-TTY or debugging)
"""

import sys
import time
from enum import Enum
from typing import Any, Optional

from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.table import Table


class DisplayMode(Enum):
    """Display mode for console output.

    - FANCY: Rich-based live-updating tables and progress bars
    - VERBOSE: Traditional logging output for debugging and non-TTY environments
    """

    FANCY = "fancy"
    VERBOSE = "verbose"


class TaskStatus(Enum):
    """Status indicators for tasks/datasets.

    Each status has: (emoji, label, color)
    """

    PENDING = ("⏳", "Pending", "dim")
    RUNNING = ("⚙️ ", "Downloading", "yellow")
    COMPLETE = ("✅", "Complete", "green")
    FAILED = ("❌", "Failed", "red")
    PARTIAL = ("⚠️ ", "Partial", "orange3")


class ConsoleUI:
    """Manages rich-based console display for data downloads and processing.

    This class provides a context manager for displaying live-updating progress
    information during parallel data downloads and processing tasks. It automatically
    falls back to verbose mode when not in a TTY environment.

    :ivar mode: Current display mode (FANCY or VERBOSE)
    :ivar config: Configuration dict for header display (datasets, seasons, workers, etc.)
    :ivar console: Rich Console instance for styled output
    :ivar is_tty: Whether stdout is a TTY (interactive terminal)
    :ivar datasets: Dictionary tracking dataset download states
    :ivar processing_tasks: Dictionary tracking processing task states
    :ivar start_time: Timestamp when UI was initialized
    :ivar live: Rich Live instance for live-updating displays (None until __enter__)

    Example usage:
        config = {"datasets": ["combine", "rosters"], "workers": 4}
        with ConsoleUI(mode=DisplayMode.FANCY, config=config) as ui:
            ui.update_dataset("combine", TaskStatus.RUNNING)
            # ... download logic ...
            ui.update_dataset("combine", TaskStatus.COMPLETE, rows=8649)
    """

    def __init__(self, mode: DisplayMode = DisplayMode.FANCY, config: Optional[dict[str, Any]] = None) -> None:
        """Initialize the ConsoleUI.

        :param mode: Display mode (DisplayMode.FANCY or DisplayMode.VERBOSE)
        :param config: Configuration dict for header display (datasets, seasons, workers, etc.)
        """
        self.mode = mode
        self.config = config or {}
        self.console = Console()
        self.is_tty = sys.stdout.isatty()

        # Force verbose mode if not a TTY (piped output, file redirect, etc.)
        if not self.is_tty and self.mode == DisplayMode.FANCY:
            self.mode = DisplayMode.VERBOSE

        # Track dataset states: {dataset_name: {status, rows, progress, start_time}}
        self.datasets: dict[str, dict[str, Any]] = {}

        # Track processing task states: {task_name: {status, progress, start_time}}
        self.processing_tasks: dict[str, dict[str, Any]] = {}

        # Track overall timing
        self.start_time = time.time()

        # Rich Live instance (created in __enter__ for fancy mode)
        self.live: Optional[Live] = None

    def __enter__(self) -> "ConsoleUI":
        """Enter context manager - start live display if in fancy mode.

        :return: self for context manager usage
        """
        if self.mode == DisplayMode.FANCY:
            # Create Live instance with initial display
            initial_table = self._generate_table()

            self.live = Live(
                initial_table,
                console=self.console,
                refresh_per_second=4,  # 4 FPS refresh rate
                transient=False,  # Keep display after exit
            )
            self.live.start()

        return self

    def __exit__(self, *args: Any) -> None:
        """Exit context manager - clean up live display if active.

        :param args: Exception info (exc_type, exc_value, traceback)
        """
        if self.mode == DisplayMode.FANCY and self.live is not None:
            # Update one final time then stop
            self.live.update(self._generate_table())
            self.live.stop()

    def update_dataset(
        self,
        name: str,
        status: TaskStatus,
        rows: Optional[int] = None,
        progress: Optional[float] = None,
    ) -> None:
        """Update the status of a dataset download.

        Thread-safe method for worker threads to report progress.

        :param name: Dataset name (e.g., "combine", "rosters", "gm_data")
        :param status: Current status (PENDING, RUNNING, COMPLETE, FAILED, PARTIAL)
        :param rows: Number of rows downloaded (optional)
        :param progress: Progress fraction 0.0-1.0 (optional, for incremental downloads)
        """
        # Update internal state
        if name not in self.datasets:
            self.datasets[name] = {
                "status": status,
                "rows": rows,
                "progress": progress or 0.0,
                "start_time": time.time(),
                "completion_time": None,
            }
        else:
            update_dict = {
                "status": status,
                "rows": rows if rows is not None else self.datasets[name].get("rows"),
                "progress": progress if progress is not None else self.datasets[name].get("progress", 0.0),
            }
            # Set completion time when task finishes
            if status in (TaskStatus.COMPLETE, TaskStatus.FAILED, TaskStatus.PARTIAL):
                update_dict["completion_time"] = time.time()
            self.datasets[name].update(update_dict)

        # Refresh live display if in fancy mode
        if self.mode == DisplayMode.FANCY and self.live is not None:
            self.live.update(self._generate_table())

    def update_processing(
        self,
        task_name: str,
        status: TaskStatus,
        progress: Optional[float] = None,
        detail: Optional[str] = None,
    ) -> None:
        """Update the status of a processing task.

        :param task_name: Processing task name (e.g., "clean_depth_charts", "generate_yamplayer_id")
        :param status: Current status (PENDING, RUNNING, COMPLETE, FAILED)
        :param progress: Progress fraction 0.0-1.0 (optional)
        :param detail: Additional detail string (e.g., "25,431/43,110 players matched")
        """
        # Phase 1: Just track state, no display yet
        if task_name not in self.processing_tasks:
            self.processing_tasks[task_name] = {
                "status": status,
                "progress": progress or 0.0,
                "detail": detail,
                "start_time": time.time(),
            }
        else:
            self.processing_tasks[task_name].update(
                {
                    "status": status,
                    "progress": progress if progress is not None else self.processing_tasks[task_name].get("progress", 0.0),
                    "detail": detail,
                }
            )

    def _create_config_header(self) -> Panel:
        """Create configuration header panel.

        :return: Rich Panel with configuration information
        """
        # Build config lines
        lines = []

        # Datasets
        if "datasets" in self.config:
            datasets = self.config["datasets"]
            if isinstance(datasets, (list, set)):
                datasets_str = ", ".join(sorted(datasets)[:5])  # Show first 5
                if len(datasets) > 5:
                    datasets_str += f" + {len(datasets) - 5} more"
            else:
                datasets_str = str(datasets)
            lines.append(f"  • Datasets: {datasets_str}")

        # Seasons
        if "seasons" in self.config:
            seasons = self.config["seasons"]
            if seasons is True:
                lines.append("  • Seasons: all available")
            elif seasons:
                lines.append(f"  • Seasons: {seasons}")
            else:
                lines.append("  • Seasons: current season")

        # GM data
        if "gm" in self.config:
            lines.append(f"  • GM data: {'included' if self.config['gm'] else 'excluded'}")

        # Workers
        if "workers" in self.config and self.config["workers"]:
            lines.append(f"  • Workers: {self.config['workers']} parallel threads")

        config_text = "\n".join(lines) if lines else "  • No configuration provided"

        return Panel(
            config_text,
            title="🏈 NFL DATA DOWNLOAD - PARALLEL MODE",
            border_style="blue",
            expand=False,
        )

    def _create_download_table(self) -> Table:
        """Create the download status table.

        :return: Rich Table with dataset download status
        """
        table = Table(
            show_header=True,
            header_style="bold cyan",
            border_style="blue",
            expand=False,
        )

        # Add columns
        table.add_column("Dataset", style="cyan", width=17)
        table.add_column("Status", width=18)  # Increased for emoji + "Downloading"
        table.add_column("Rows", justify="right", width=10)
        table.add_column("Progress", width=23)
        table.add_column("Time", justify="right", width=8)

        # Add rows for each dataset
        for name, state in self.datasets.items():
            status: TaskStatus = state["status"]
            rows = state.get("rows")
            progress = state.get("progress", 0.0)
            # Calculate elapsed time: use completion_time if task is done, otherwise current time
            start_time = state.get("start_time", time.time())
            end_time = state.get("completion_time") or time.time()
            elapsed = end_time - start_time

            # Format status with emoji and color
            emoji, label, color = status.value
            status_str = f"{emoji} {label}"

            # Format rows
            rows_str = f"{rows:,}" if rows is not None else "-"

            # Format progress bar (20 characters wide)
            bar_width = 20
            filled = int(progress * bar_width)
            bar = "█" * filled + "░" * (bar_width - filled)

            # Format time
            time_str = f"{elapsed:.1f}s"

            table.add_row(
                name,
                f"[{color}]{status_str}[/{color}]",
                rows_str,
                bar,
                time_str,
            )

        return table

    def _create_footer(self) -> str:
        """Create summary footer with stats.

        :return: Footer string with summary information
        """
        total_datasets = len(self.datasets)
        completed = sum(1 for d in self.datasets.values() if d["status"] == TaskStatus.COMPLETE)
        failed = sum(1 for d in self.datasets.values() if d["status"] == TaskStatus.FAILED)
        elapsed = time.time() - self.start_time

        # Count NFLverse vs GM datasets
        nflverse_datasets = [n for n in self.datasets.keys() if n != "gm_data"]
        nflverse_complete = sum(
            1 for n, d in self.datasets.items()
            if n != "gm_data" and d["status"] == TaskStatus.COMPLETE
        )

        parts = []
        if nflverse_datasets:
            parts.append(f"NFLverse: {nflverse_complete}/{len(nflverse_datasets)} complete")

        # GM progress (if present)
        if "gm_data" in self.datasets:
            gm_state = self.datasets["gm_data"]
            if gm_state.get("rows") and "/" in str(gm_state["rows"]):
                parts.append(f"GM: {gm_state['rows']}")

        parts.append(f"Elapsed: {elapsed:.1f}s")

        return " │ ".join(parts)

    def _generate_table(self) -> Panel:
        """Generate the complete display with header, table, and footer.

        :return: Rich Panel containing the entire display
        """

        # Build the display components
        config_header = self._create_config_header()
        download_table = self._create_download_table()
        footer = self._create_footer()

        # Combine into a group
        display_group = Group(
            config_header,
            "",  # Blank line
            download_table,
            "",  # Blank line
            footer,
        )

        return Panel(display_group, border_style="dim", expand=False)
