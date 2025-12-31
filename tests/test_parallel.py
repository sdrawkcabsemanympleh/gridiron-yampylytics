"""Tests for parallel task execution utilities."""
from src.gridiron_yampylytics.utils.parallel import Task, run_tasks_parallel


class DummyException(Exception):
    """Custom exception for testing failure handling."""


def success_no_args() -> str:
    """Dummy function that succeeds without arguments."""
    return "success_no_args"


def success_with_args(x: int, y: int, z: str | None = None) -> str:
    """Dummy function that succeeds with arguments."""
    return f"success: {x}, {y}, {z}"


def failing_func() -> None:
    """Dummy function that raises an exception."""
    raise DummyException("intentional test failure")


def test_run_tasks_parallel_unlimited_workers() -> None:
    """Test parallel execution with unlimited workers (one per task)."""
    tasks = [
        Task("no_args", success_no_args),
        Task("with_args", success_with_args, (1, 2), {"z": "test"}),
        Task("failing", failing_func),
    ]

    results = run_tasks_parallel(tasks, max_workers=None)

    # Check successful tasks (order not guaranteed, use set)
    assert set(results["successful"]) == {"no_args", "with_args"}

    # Check failed tasks
    assert len(results["failed"]) == 1
    assert results["failed"][0][0] == "failing"
    assert "intentional test failure" in results["failed"][0][1]

    # Check return values
    assert results["results"] == {
        "no_args": "success_no_args",
        "with_args": "success: 1, 2, test",
        "failing": None,
    }


def test_run_tasks_parallel_limited_workers() -> None:
    """Test parallel execution with limited workers."""
    tasks = [
        Task("no_args", success_no_args),
        Task("with_args", success_with_args, (10, 20), {"z": "limited"}),
        Task("failing", failing_func),
    ]

    results = run_tasks_parallel(tasks, max_workers=2)

    # Check successful tasks (order not guaranteed, use set)
    assert set(results["successful"]) == {"no_args", "with_args"}

    # Check failed tasks
    assert len(results["failed"]) == 1
    assert results["failed"][0][0] == "failing"
    assert "intentional test failure" in results["failed"][0][1]

    # Check return values
    assert results["results"] == {
        "no_args": "success_no_args",
        "with_args": "success: 10, 20, limited",
        "failing": None,
    }
