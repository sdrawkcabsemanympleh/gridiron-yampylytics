"""Lineup optimization and roster quality scoring for YampGM.

Given a player pool and a RosterConfig, determines the optimal starting lineup
to maximize total projected points and returns a quality score.

The optimizer uses a greedy two-pass strategy:
1. Assign the top-N players by projected_points to each dedicated position slot.
2. Assign the best remaining flex-eligible players to FLEX slots.

This is provably optimal for maximizing total projected points because dedicated
slots have no cross-position competition and FLEX is resolved greedily from the
full surplus pool.
"""
from dataclasses import dataclass, field
from gridiron_yampylytics.ffb.models.league import RosterConfig
from gridiron_yampylytics.ffb.models.player import NFLPlayer, Position


@dataclass
class LineupResult:
    """Result of lineup optimization.

    :param starters: Players assigned to starting slots (dedicated + FLEX),
        in no guaranteed order.
    :param bench: Remaining players not in the starting lineup.
    :param total_projected_points: Sum of projected_points for all starters.
    """
    starters: list[NFLPlayer] = field(default_factory=list)
    bench: list[NFLPlayer] = field(default_factory=list)
    total_projected_points: float = 0.0


def optimize_lineup(players: list[NFLPlayer], roster_config: RosterConfig) -> LineupResult:
    """Determine the optimal starting lineup from a player pool.

    :param players: All players on the roster (starters + bench candidates).
    :param roster_config: League roster configuration.
    :return: :class:`LineupResult` with optimal starter assignment and bench.
        If the pool has fewer players than starting slots, all are assigned
        as starters and bench is empty.
    """
    if not players:
        return LineupResult()
    dedicated_slots: dict[Position, int] = {
        Position.QB: roster_config.qb,
        Position.RB: roster_config.rb,
        Position.WR: roster_config.wr,
        Position.TE: roster_config.te,
        Position.K: roster_config.k,
        Position.DEF: roster_config.def_,
    }
    by_position: dict[Position, list[NFLPlayer]] = {}
    for p in players:
        by_position.setdefault(p.position, []).append(p)
    for pos in by_position:
        by_position[pos].sort(key=lambda p: p.projected_points, reverse=True)
    starters: list[NFLPlayer] = []
    used_ids: set[str] = set()
    for pos, slots in dedicated_slots.items():
        for p in by_position.get(pos, [])[:slots]:
            starters.append(p)
            used_ids.add(p.player_id)
    flex_candidates = sorted(
        [p for p in players if p.player_id not in used_ids and p.position in roster_config.flex_eligible],
        key=lambda p: p.projected_points,
        reverse=True,
    )
    for p in flex_candidates[:roster_config.flex]:
        starters.append(p)
        used_ids.add(p.player_id)
    bench = [p for p in players if p.player_id not in used_ids]
    return LineupResult(
        starters=starters,
        bench=bench,
        total_projected_points=sum(p.projected_points for p in starters),
    )


def score_roster(players: list[NFLPlayer], roster_config: RosterConfig) -> float:
    """Return total projected points for the optimal starting lineup.

    :param players: All players on the roster.
    :param roster_config: League roster configuration.
    :return: Total projected points of the optimal starting lineup.
        Returns 0.0 for an empty player list.
    """
    return optimize_lineup(players, roster_config).total_projected_points
