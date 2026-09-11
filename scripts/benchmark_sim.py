"""Benchmark: numpy/snapshot simulation vs baseline wall time.

Runs the current SimSnapshot + kernels path at increasing n_simulations and
reports candidates-per-second so we have a stable throughput number for
regression tracking.

Usage:
    uv run python scripts/benchmark_sim.py
"""
import time
import numpy as np
from gridiron_yampylytics.ffb.models.draft import DraftState
from gridiron_yampylytics.ffb.models.league import League, RosterConfig
from gridiron_yampylytics.ffb.models.manager import Manager
from gridiron_yampylytics.ffb.models.player import NFLPlayer, Position
from gridiron_yampylytics.ffb.simulation.engine import DraftSimulator
from gridiron_yampylytics.ffb.simulation.snapshot import SimSnapshot
from gridiron_yampylytics.ffb.simulation.kernels import simulate_batch


def _player(pid: str, pos: str, pts: float, adp: float) -> NFLPlayer:
    return NFLPlayer(
        player_id=pid, name=pid, position=Position(pos), team="KC",
        projected_points=pts, adp=adp, adp_std=3.0,
    )


def _build_state(n_players: int = 120, n_teams: int = 10, n_rounds: int = 12) -> DraftState:
    rc = RosterConfig(qb=1, rb=2, wr=2, te=1, flex=1, k=1, def_=1, bench=3)
    league = League(team_count=n_teams, roster=rc)
    managers = [
        Manager(manager_id=f"m{i}", name=f"Mgr{i}", draft_slot=i + 1, is_user=(i == 0))
        for i in range(n_teams)
    ]
    positions = ["QB"] * 20 + ["RB"] * 35 + ["WR"] * 35 + ["TE"] * 15 + ["K"] * 8 + ["DEF"] * 7
    players = [
        _player(f"p{i}", positions[i % len(positions)], 300.0 - i * 2.0, float(i + 1))
        for i in range(n_players)
    ]
    return DraftState.new(league=league, managers=managers, available_players=players)


def _replacement_levels() -> dict[Position, float]:
    return {
        Position.QB: 180.0, Position.RB: 100.0, Position.WR: 90.0,
        Position.TE: 70.0, Position.K: 50.0, Position.DEF: 40.0,
    }


def benchmark_single_candidate(n_simulations: int, n_runs: int = 5) -> float:
    """Return median wall-time (seconds) for one candidate over n_runs trials."""
    state = _build_state()
    candidate = list(state.available_players)[0]
    repl = _replacement_levels()
    snapshot = SimSnapshot.from_draft_state(state, candidate, repl)
    rng = np.random.default_rng(42)
    times = []
    for _ in range(n_runs):
        t0 = time.perf_counter()
        simulate_batch(snapshot, 0, np.array([0.3, 0.15, 0.7]), 1, np.empty(0), n_simulations, rng)
        times.append(time.perf_counter() - t0)
    return float(np.median(times))


def benchmark_recommend(n_candidates: int = 20, n_simulations: int = 100) -> float:
    """Return wall-time (seconds) for DraftSimulator.recommend() with n_candidates."""
    state = _build_state()
    available = list(state.available_players)[:n_candidates]
    repl = _replacement_levels()
    sim = DraftSimulator(n_simulations=n_simulations, n_workers=1)
    t0 = time.perf_counter()
    sim.recommend(state, available, repl)
    elapsed = time.perf_counter() - t0
    sim.shutdown()
    return elapsed


def main() -> None:
    print("=" * 60)
    print("simulate_batch (single candidate, median over 5 runs)")
    print("=" * 60)
    for n in [50, 100, 200, 500]:
        t = benchmark_single_candidate(n)
        rate = n / t
        print(f"  n_simulations={n:4d}  {t * 1000:.1f} ms  ({rate:.0f} sims/s)")

    print()
    print("=" * 60)
    print("DraftSimulator.recommend() — 1 worker (sequential baseline)")
    print("=" * 60)
    for n_cand, n_sim in [(5, 50), (10, 100), (20, 100)]:
        t = benchmark_recommend(n_candidates=n_cand, n_simulations=n_sim)
        cps = n_cand / t
        print(f"  candidates={n_cand:2d}  sims={n_sim:3d}  {t:.2f}s  ({cps:.1f} cands/s)")


if __name__ == "__main__":
    main()
