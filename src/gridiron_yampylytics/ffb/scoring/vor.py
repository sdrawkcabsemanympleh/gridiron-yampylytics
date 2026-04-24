"""VOR (Value Over Replacement) computation for YampGM.

Replacement level is the projected points of the first waiver-wire-caliber player
at each position, accounting for dedicated starter slots and FLEX slots.

FLEX-eligible positions have a deeper effective replacement level because FLEX
slots extend the total number of starters at those positions league-wide. The FLEX
split is controlled by ``flex_shares``, defaulting to the PPR heuristic
RB=0.50, WR=0.35, TE=0.15 — a reasonable estimate that accounts for the higher
variance in real FLEX usage across years and player pools.
"""
from dataclasses import dataclass
from gridiron_yampylytics.ffb.models.league import RosterConfig
from gridiron_yampylytics.ffb.models.player import NFLPlayer, Position


DEFAULT_FLEX_SHARES: dict[Position, float] = {
    Position.RB: 0.50,
    Position.WR: 0.35,
    Position.TE: 0.15,
}


@dataclass
class PlayerVor:
    """VOR result for a single player.

    :param player: The evaluated player.
    :param vor: Value Over Replacement (projected_points − replacement_level).
    :param replacement_level: Replacement-level projected points for this position.
    """
    player: NFLPlayer
    vor: float
    replacement_level: float


def compute_replacement_levels(
    players: list[NFLPlayer],
    roster_config: RosterConfig,
    team_count: int,
    flex_shares: dict[Position, float] | None = None,
) -> dict[Position, float]:
    """Compute the replacement-level projected points for each position.

    The replacement-level player at position P is the player at rank
    ``effective_depth(P) + 1`` in the league-wide pool — the first player who
    will not be a starter in any format (dedicated or FLEX). Players above that
    rank are starters; players at or below it are on waivers.

    Effective depth formula::

        effective_depth(P) = team_count × dedicated_starters(P)
                           + round(roster_config.flex × team_count × flex_shares[P])

    :param players: Player pool (any order; sorted internally).
    :param roster_config: Roster configuration for the league.
    :param team_count: Number of teams in the league.
    :param flex_shares: Fraction of total FLEX slots per team allocated to each
        FLEX-eligible position. Missing keys default to 0.0.
        Defaults to ``DEFAULT_FLEX_SHARES`` (PPR heuristic).
    :return: Mapping of :class:`~gridiron_yampylytics.ffb.models.player.Position`
        → replacement-level projected points. Positions absent from the player
        pool return 0.0.
    """
    if flex_shares is None:
        flex_shares = DEFAULT_FLEX_SHARES
    dedicated: dict[Position, int] = {
        Position.QB: roster_config.qb,
        Position.RB: roster_config.rb,
        Position.WR: roster_config.wr,
        Position.TE: roster_config.te,
        Position.K: roster_config.k,
        Position.DEF: roster_config.def_,
    }
    effective_depth: dict[Position, int] = {}
    for pos, starters in dedicated.items():
        flex_contrib = round(roster_config.flex * team_count * flex_shares.get(pos, 0.0))
        effective_depth[pos] = team_count * starters + flex_contrib
    by_position: dict[Position, list[float]] = {}
    for p in players:
        by_position.setdefault(p.position, []).append(p.projected_points)
    for pos in by_position:
        by_position[pos].sort(reverse=True)
    replacement_levels: dict[Position, float] = {}
    for pos, depth in effective_depth.items():
        pool = by_position.get(pos, [])
        replacement_levels[pos] = pool[depth] if depth < len(pool) else 0.0
    return replacement_levels


def compute_vor(player: NFLPlayer, replacement_levels: dict[Position, float]) -> float:
    """Compute VOR for a single player.

    :param player: The player to evaluate.
    :param replacement_levels: Pre-computed from :func:`compute_replacement_levels`.
    :return: VOR in fantasy points. Positive = above replacement; negative = below.
    """
    return player.projected_points - replacement_levels.get(player.position, 0.0)


def annotate_vor(
    players: list[NFLPlayer],
    replacement_levels: dict[Position, float],
) -> list[PlayerVor]:
    """Annotate each player with their VOR score, sorted descending.

    :param players: Player pool.
    :param replacement_levels: Pre-computed from :func:`compute_replacement_levels`.
    :return: :class:`PlayerVor` list sorted by VOR descending.
    """
    results = []
    for p in players:
        results.append(PlayerVor(
            player=p,
            vor=compute_vor(p, replacement_levels),
            replacement_level=replacement_levels.get(p.position, 0.0),
        ))
    results.sort(key=lambda r: r.vor, reverse=True)
    return results
