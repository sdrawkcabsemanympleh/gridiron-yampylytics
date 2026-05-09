"""Server management scripts for gridiron-yampylytics FFB API and frontend.

Provides start, stop, and restart commands for the FastAPI backend and Vite
frontend dev server.  Auto-kills any existing process occupying the target
port before starting a fresh one, so you never have to manually hunt PIDs.

Usage::

    uv run serve-api     # start (or restart) the FastAPI backend
    uv run stop-api      # kill the FastAPI backend
    uv run serve-ui      # start (or restart) the Vite frontend
    uv run stop-ui       # kill the Vite frontend
    uv run serve         # start both
    uv run stop          # kill both
"""
import subprocess
import sys
import time
from pathlib import Path

_API_HOST: str = "127.0.0.1"
_API_PORT: int = 8767
_UI_PORT: int = 5173
_FRONTEND_DIR: Path = Path(__file__).parents[3] / "frontend"


def _find_pid_on_port(port: int) -> int | None:
    """Return the PID listening on ``port``, or ``None`` if the port is free.

    :param port: TCP port to check.
    :return: PID of the listening process, or ``None``.
    """
    if sys.platform == "win32":
        result = subprocess.run(["netstat", "-ano"], capture_output=True, text=True)
        for line in result.stdout.splitlines():
            if f":{port}" in line and "LISTENING" in line:
                parts = line.split()
                if parts:
                    try:
                        return int(parts[-1])
                    except ValueError:
                        pass
    else:
        result = subprocess.run(["lsof", "-ti", f":{port}"], capture_output=True, text=True)
        if result.stdout.strip():
            try:
                return int(result.stdout.strip().splitlines()[0])
            except ValueError:
                pass
    return None


def _kill_port(port: int, label: str) -> bool:
    """Kill the process listening on ``port`` if one exists.

    :param port: TCP port to free.
    :param label: Human-readable name for the service (used in output).
    :return: ``True`` if a process was killed, ``False`` if port was already free.
    """
    pid = _find_pid_on_port(port)
    if pid is None:
        print(f"  {label} not running on :{port}")
        return False
    print(f"  Stopping {label} (PID {pid})...", end=" ", flush=True)
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/PID", str(pid), "/F", "/T"], capture_output=True)
    else:
        import os
        import signal
        os.kill(pid, signal.SIGTERM)
    time.sleep(0.5)
    if _find_pid_on_port(port) is None:
        print("stopped")
        return True
    print("killed (SIGKILL)")
    if sys.platform != "win32":
        import os
        import signal
        os.kill(pid, signal.SIGKILL)
    return True


def _start_api() -> None:
    """Launch uvicorn for the FFB FastAPI backend, blocking until Ctrl+C.

    :raises SystemExit: When the server exits.
    """
    print(f"  Starting API on http://{_API_HOST}:{_API_PORT} (--reload enabled)")
    print("  Press Ctrl+C to stop.\n")
    subprocess.run([
        sys.executable, "-m", "uvicorn",
        "gridiron_yampylytics.ffb.api.main:app",
        "--host", _API_HOST,
        "--port", str(_API_PORT),
        "--reload",
    ])


def _start_ui() -> None:
    """Launch the Vite dev server for the React frontend, blocking until Ctrl+C.

    :raises SystemExit: When the dev server exits.
    :raises FileNotFoundError: If the frontend directory or npm is missing.
    """
    if not _FRONTEND_DIR.exists():
        print(f"  ERROR: frontend directory not found at {_FRONTEND_DIR}")
        sys.exit(1)
    print(f"  Starting Vite dev server in {_FRONTEND_DIR}")
    print("  Press Ctrl+C to stop.\n")
    npm = "npm.cmd" if sys.platform == "win32" else "npm"
    subprocess.run([npm, "run", "dev"], cwd=str(_FRONTEND_DIR))


def serve_api() -> None:
    """Kill any existing process on :8767 and start the FastAPI backend.

    :raises SystemExit: On server exit or Ctrl+C.
    """
    print("=" * 60)
    print("FFB API SERVER")
    print("=" * 60)
    _kill_port(_API_PORT, "API server")
    print()
    _start_api()


def stop_api() -> None:
    """Kill the FastAPI backend process if running.

    :raises SystemExit: After stopping (or reporting not running).
    """
    print("=" * 60)
    print("STOPPING FFB API SERVER")
    print("=" * 60)
    _kill_port(_API_PORT, "API server")


def serve_ui() -> None:
    """Kill any existing process on :5173 and start the Vite dev server.

    :raises SystemExit: On server exit or Ctrl+C.
    """
    print("=" * 60)
    print("FRONTEND DEV SERVER")
    print("=" * 60)
    _kill_port(_UI_PORT, "Vite dev server")
    print()
    _start_ui()


def stop_ui() -> None:
    """Kill the Vite frontend dev server process if running.

    :raises SystemExit: After stopping (or reporting not running).
    """
    print("=" * 60)
    print("STOPPING FRONTEND DEV SERVER")
    print("=" * 60)
    _kill_port(_UI_PORT, "Vite dev server")


def serve() -> None:
    """Kill any existing processes and start both API and frontend.

    The API is launched as a background subprocess; the Vite dev server runs
    in the foreground and blocks until Ctrl+C.  Stopping the frontend (Ctrl+C)
    does not automatically stop the API — use ``uv run stop-api`` for that.

    :raises SystemExit: When the frontend exits or Ctrl+C is pressed.
    """
    print("=" * 60)
    print("STARTING FFB STACK (API + FRONTEND)")
    print("=" * 60)
    _kill_port(_API_PORT, "API server")
    _kill_port(_UI_PORT, "Vite dev server")
    print()
    print("  Launching API in background...")
    subprocess.Popen([
        sys.executable, "-m", "uvicorn",
        "gridiron_yampylytics.ffb.api.main:app",
        "--host", _API_HOST,
        "--port", str(_API_PORT),
    ])
    time.sleep(1.5)
    print(f"  API running on http://{_API_HOST}:{_API_PORT}")
    print()
    _start_ui()


def stop() -> None:
    """Kill both the API and frontend dev server processes.

    :raises SystemExit: After stopping (or reporting not running).
    """
    print("=" * 60)
    print("STOPPING FFB STACK")
    print("=" * 60)
    _kill_port(_API_PORT, "API server")
    _kill_port(_UI_PORT, "Vite dev server")
    print("\nDone.")
