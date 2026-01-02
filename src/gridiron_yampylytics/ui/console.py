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

from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.table import Table


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

    Example usage:
        config = {"datasets": ["combine", "rosters"], "workers": 4}
        with ConsoleUI(mode="fancy", config=config) as ui:
            ui.update_dataset("combine", TaskStatus.RUNNING)
            # ... download logic ...
            ui.update_dataset("combine", TaskStatus.COMPLETE, rows=8649)
    """

    def __init__(self, mode: str = "fancy", config: Optional[dict[str, Any]] = None) -> None:
        """Initialize the ConsoleUI.

        :param mode: Display mode - "fancy" for rich UI, "verbose" for traditional logging
        :param config: Configuration dict for header display (datasets, seasons, workers, etc.)
        """
        self.mode = mode
        self.config = config or {}
        self.console = Console()
        self.is_tty = sys.stdout.isatty()

        # Force verbose mode if not a TTY (piped output, file redirect, etc.)
        if not self.is_tty and self.mode == "fancy":
            self.mode = "verbose"

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
        if self.mode == "fancy":
            # Phase 1: Just create the Live instance, we'll implement display later
            # For now, this is a no-op placeholder
            pass

        return self

    def __exit__(self, *args: Any) -> None:
        """Exit context manager - clean up live display if active.

        :param args: Exception info (exc_type, exc_value, traceback)
        """
        if self.mode == "fancy" and self.live is not None:
            # Phase 1: Cleanup placeholder
            # Later phases will stop the live display here
            pass

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
        # Phase 1: Just track state, no display yet
        if name not in self.datasets:
            self.datasets[name] = {
                "status": status,
                "rows": rows,
                "progress": progress or 0.0,
                "start_time": time.time(),
            }
        else:
            self.datasets[name].update(
                {
                    "status": status,
                    "rows": rows if rows is not None else self.datasets[name].get("rows"),
                    "progress": progress if progress is not None else self.datasets[name].get("progress", 0.0),
                }
            )

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
