"""Positional scarcity analyzers for YampGM.

Both analyzers produce a scarcity score in [0.0, 1.0] for each available player
at a position. A higher score means drafting that player now is more urgent because
the position drops off steeply below them.

Two implementations:

- :class:`TierScarcityAnalyzer` — gap detection in the sorted projection curve.
  Interpretable: players just before a cliff get scores near 1.0.
- :class:`GradientScarcityAnalyzer` — slope and curvature of the projection curve.
  Smooth and normalizable; captures the rate of talent dropoff rather than hard tiers.

Both satisfy the :class:`ScarcityAnalyzer` protocol and are interchangeable at the
:class:`~gridiron_yampylytics.ffb.scoring.scorer.WeightedLinearScorer` call site.
"""
from dataclasses import dataclass
from typing import Protocol, runtime_checkable
from gridiron_yampylytics.ffb.models.player import NFLPlayer, Position


@dataclass
class ScarcityResult:
    """Scarcity result for a single player.

    :param position: The player's position.
    :param player: The evaluated player.
    :param scarcity_score: Urgency score in [0.0, 1.0]. Higher = more scarce.
    :param tier: Tier number from :class:`TierScarcityAnalyzer`. ``None`` for
        gradient-based results.
    :param rank_in_position: 1-indexed rank within the available position pool.
    """
    position: Position
    player: NFLPlayer
    scarcity_score: float
    tier: int | None = None
    rank_in_position: int | None = None


@runtime_checkable
class ScarcityAnalyzer(Protocol):
    """Protocol for positional scarcity analyzers."""

    def analyze(
        self,
        available_players: list[NFLPlayer],
        position: Position,
    ) -> list[ScarcityResult]:
        """Analyze positional scarcity for all available players at a position.

        :param available_players: All players currently on the board.
        :param position: The position to analyze.
        :return: :class:`ScarcityResult` list sorted by projected_points descending.
            Empty list if no players at this position are available.
        """
        ...


class TierScarcityAnalyzer:
    """Detects positional tiers from gaps in the sorted projection curve.

    The scarcity score for each player equals the normalized drop from that
    player to the next in the pool. A player just before a large cliff gets
    a score near 1.0 — drafting them is urgent because missing them means
    falling to the next tier.

    :param gap_threshold: Minimum projected-point drop between adjacent players
        to constitute a tier boundary. Defaults to 10.0.
    """

    def __init__(self, gap_threshold: float = 10.0) -> None:
        """Initialise with the gap threshold for tier boundary detection.

        :param gap_threshold: Minimum projected-point drop between adjacent
            players to open a new tier. Defaults to 10.0.
        """
        self.gap_threshold = gap_threshold

    def analyze(
        self,
        available_players: list[NFLPlayer],
        position: Position,
    ) -> list[ScarcityResult]:
        """Compute tier-based scarcity scores for all available players at a position.

        :param available_players: All players currently on the board.
        :param position: The position to analyze.
        :return: :class:`ScarcityResult` list sorted by projected_points descending.
            Empty list if no players at this position are available.
        """
        pool = sorted(
            [p for p in available_players if p.position == position],
            key=lambda p: p.projected_points,
            reverse=True,
        )
        if not pool:
            return []
        drops = [pool[i].projected_points - pool[i + 1].projected_points for i in range(len(pool) - 1)]
        drops.append(0.0)
        max_drop = max(drops) if max(drops) > 0 else 1.0
        tiers = [1]
        for i in range(len(pool) - 1):
            tiers.append(tiers[-1] + (1 if drops[i] >= self.gap_threshold else 0))
        results = []
        for i, player in enumerate(pool):
            results.append(ScarcityResult(
                position=position,
                player=player,
                scarcity_score=drops[i] / max_drop,
                tier=tiers[i],
                rank_in_position=i + 1,
            ))
        return results


class GradientScarcityAnalyzer:
    """Computes scarcity from the local slope and curvature of the projection curve.

    The projection curve is the sorted sequence of projected points. For each
    player at rank i, the raw scarcity signal is::

        raw[i] = slope[i] + |curvature[i]|

    where slope and curvature are approximated by central finite differences.
    High slope (large drop rate) and high curvature (accelerating drop) both
    indicate a positional cliff. The raw signal is min-max normalized to [0.0, 1.0]
    across the position pool.
    """

    def analyze(
        self,
        available_players: list[NFLPlayer],
        position: Position,
    ) -> list[ScarcityResult]:
        """Compute gradient-based scarcity scores for all available players at a position.

        :param available_players: All players currently on the board.
        :param position: The position to analyze.
        :return: :class:`ScarcityResult` list sorted by projected_points descending.
            Empty list if no players at this position are available.
        """
        pool = sorted(
            [p for p in available_players if p.position == position],
            key=lambda p: p.projected_points,
            reverse=True,
        )
        if not pool:
            return []
        pts = [p.projected_points for p in pool]
        n = len(pts)
        slopes = []
        for i in range(n):
            if i == 0:
                slopes.append(pts[0] - pts[1] if n > 1 else 0.0)
            elif i == n - 1:
                slopes.append(pts[-2] - pts[-1])
            else:
                slopes.append((pts[i - 1] - pts[i + 1]) / 2.0)
        curvatures = []
        for i in range(n):
            if i == 0 or i == n - 1:
                curvatures.append(0.0)
            else:
                curvatures.append(pts[i - 1] - 2 * pts[i] + pts[i + 1])
        raw = [slopes[i] + abs(curvatures[i]) for i in range(n)]
        raw_min, raw_max = min(raw), max(raw)
        denom = raw_max - raw_min if raw_max != raw_min else 1.0
        results = []
        for i, player in enumerate(pool):
            results.append(ScarcityResult(
                position=position,
                player=player,
                scarcity_score=(raw[i] - raw_min) / denom,
                rank_in_position=i + 1,
            ))
        return results
