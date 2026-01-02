"""Parallel task execution utilities.

Provides utilities for running tasks in parallel using threading.
Designed for I/O-bound operations like network requests.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, NamedTuple


class Task(NamedTuple):
    """A task to be executed in parallel.

    :param name: Identifier for the task (used in results/error reporting)
    :param func: Callable to execute
    :param args: Positional arguments for func (default: empty tuple)
    :param kwargs: Keyword arguments for func (default: empty dict)
    """
    name: str
    func: Callable
    args: tuple = ()
    kwargs: dict[str, Any] = {}


def run_tasks_parallel(
    tasks: list[Task],
    max_workers: int | None = None
) -> dict[str, Any]:
    """Run tasks in parallel using ThreadPoolExecutor.

    Designed for I/O-bound operations (network requests, file I/O).
    Uses threading (not multiprocessing) since GIL doesn't affect I/O operations.

    :param tasks: List of Task objects to execute
    :param max_workers: Max concurrent workers (None = one worker per task)
    :return: Dict with 'successful', 'failed', and 'results' keys

    Example:
        from gridiron_yampylytics.utils.parallel import Task, run_tasks_parallel

        tasks = [
            Task('task1', my_func, (arg1, arg2), {'kwarg': value}),
            Task('task2', other_func),  # No args needed
        ]
        results = run_tasks_parallel(tasks, max_workers=4)
        print(f"Success: {results['successful']}")
        print(f"Failed: {results['failed']}")
    """
    if max_workers is None:
        max_workers = len(tasks)  # One worker per task (unlimited parallelism)

    successful = []
    failed = []
    results = {}

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        futures = {}
        for task in tasks:
            future = executor.submit(task.func, *task.args, **task.kwargs)
            futures[future] = task.name

        # Collect results as they complete
        for future in as_completed(futures):
            name = futures[future]
            try:
                result = future.result()  # Will raise if task failed
                successful.append(name)
                results[name] = result
            except Exception as e:
                failed.append((name, str(e)))
                results[name] = None

    return {
        'successful': successful,
        'failed': failed,
        'results': results,
    }
