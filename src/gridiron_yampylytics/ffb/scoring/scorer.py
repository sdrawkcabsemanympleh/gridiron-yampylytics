"""Weighted linear scorer for YampGM draft recommendations.

Combines VOR, VONA, positional scarcity, and roster need into a single sortable
recommendation score. All raw component values are normalized to [0.0, 1.0]
across the available player pool before weighting, so no single component
dominates due to scale.
"""
from dataclasses import dataclass, field
from gridiron_yampylytics.ffb.models.draft import DraftState, Roster
from gridiron_yampylytics.ffb.models.league import RosterConfig
from gridiron_yampylytics.ffb.models.player import NFLPlayer, Position
from gridiron_yampylytics.ffb.scoring.scarcity import ScarcityAnalyzer, TierScarcityAnalyzer
from gridiron_yampylytics.ffb.scoring.vona import AdpVonaApproximation, VonaCalculator
from gridiron_yampylytics.ffb.scoring.vor import compute_vor


@dataclass
class ScorerWeights:
    """Component weights for the weighted linear scorer.

    Weights need not sum to 1.0 — they are applied as-is to the normalized
    component scores. The default allocation emphasizes VOR and VONA over
    scarcity and roster need.

    :param vor: Weight for VOR (Value Over Replacement). Default 0.40.
    :param vona: Weight for VONA (Value Over Next Available). Default 0.30.
    :param scarcity: Weight for positional scarcity. Default 0.20.
    :param roster_need: Weight for roster slot need. Default 0.10.
    """
    vor: float = 0.40
    vona: float = 0.30
    scarcity: float = 0.20
    roster_need: float = 0.10


@dataclass
class PlayerScore:
    """Scored draft recommendation for a single player.

    :param player: The evaluated player.
    :param total_score: Weighted composite score.
    :param vor: Raw VOR in fantasy points.
    :param vona: Raw VONA in fantasy points.
    :param scarcity_score: Normalized positional scarcity in [0.0, 1.0].
    :param roster_need_score: Normalized roster need in [0.0, 1.0].
    """
    player: NFLPlayer
    total_score: float
    vor: float
    vona: float
    scarcity_score: float
    roster_need_score: float


class WeightedLinearScorer:
    """Combines VOR, VONA, scarcity, and roster need into draft recommendations.

    Each component is normalized to [0.0, 1.0] across the current available
    player pool before the weighted sum is computed, ensuring no single signal
    dominates due to raw scale differences.

    :param weights: Component weights. Defaults to :class:`ScorerWeights`.
    :param vona_calculator: VONA implementation. Defaults to
        :class:`~gridiron_yampylytics.ffb.scoring.vona.AdpVonaApproximation`.
    :param scarcity_analyzer: Scarcity implementation. Defaults to
        :class:`~gridiron_yampylytics.ffb.scoring.scarcity.TierScarcityAnalyzer`.
    """

    def __init__(
        self,
        weights: ScorerWeights | None = None,
        vona_calculator: VonaCalculator | None = None,
        scarcity_analyzer: ScarcityAnalyzer | None = None,
    ) -> None:
        """Initialise scorer with optional component overrides.

        :param weights: Component weights. ``None`` uses :class:`ScorerWeights` defaults.
        :param vona_calculator: VONA implementation. ``None`` uses
            :class:`AdpVonaApproximation`.
        :param scarcity_analyzer: Scarcity implementation. ``None`` uses
            :class:`TierScarcityAnalyzer`.
        """
        self.weights = weights or ScorerWeights()
        self.vona_calculator: VonaCalculator = vona_calculator or AdpVonaApproximation()
        self.scarcity_analyzer: ScarcityAnalyzer = scarcity_analyzer or TierScarcityAnalyzer()

    def score(
        self,
        draft_state: DraftState,
        replacement_levels: dict[Position, float],
    ) -> list[PlayerScore]:
        """Score all available players for the current draft pick.

        :param draft_state: Current draft state snapshot.
        :param replacement_levels: Pre-computed VOR replacement levels from
            :func:`~gridiron_yampylytics.ffb.scoring.vor.compute_replacement_levels`.
        :return: :class:`PlayerScore` list sorted by ``total_score`` descending.
            Empty list if no players are available.
        """
        available = draft_state.available_players
        if not available:
            return []
        picks_until_user = draft_state.picks_until_user()
        user_roster = draft_state.user_roster
        roster_config = draft_state.league.roster
        scarcity_by_player: dict[str, float] = {}
        for pos in {p.position for p in available}:
            for result in self.scarcity_analyzer.analyze(available, pos):
                scarcity_by_player[result.player.player_id] = result.scarcity_score
        raw_vors = [compute_vor(p, replacement_levels) for p in available]
        raw_vonas = [self.vona_calculator.compute_vona(p, available, picks_until_user) for p in available]
        vor_min, vor_max = min(raw_vors), max(raw_vors)
        vona_min, vona_max = min(raw_vonas), max(raw_vonas)
        vor_denom = vor_max - vor_min if vor_max != vor_min else 1.0
        vona_denom = vona_max - vona_min if vona_max != vona_min else 1.0
        need_by_pos = self._compute_roster_need(user_roster, roster_config)
        scores = []
        for i, player in enumerate(available):
            vor_norm = (raw_vors[i] - vor_min) / vor_denom
            vona_norm = (raw_vonas[i] - vona_min) / vona_denom
            scarcity = scarcity_by_player.get(player.player_id, 0.0)
            need = need_by_pos.get(player.position, 0.0)
            total = (
                self.weights.vor * vor_norm
                + self.weights.vona * vona_norm
                + self.weights.scarcity * scarcity
                + self.weights.roster_need * need
            )
            scores.append(PlayerScore(
                player=player,
                total_score=total,
                vor=raw_vors[i],
                vona=raw_vonas[i],
                scarcity_score=scarcity,
                roster_need_score=need,
            ))
        scores.sort(key=lambda s: s.total_score, reverse=True)
        return scores

    def _compute_roster_need(
        self,
        roster: Roster,
        roster_config: RosterConfig,
    ) -> dict[Position, float]:
        """Compute [0.0, 1.0] roster need score for each position.

        Dedicated need: fraction of dedicated starter slots still empty.
        FLEX need: fraction of FLEX slots not yet covered by surplus flex-eligible
        players (those beyond their dedicated count). Each FLEX-eligible position
        receives the higher of its dedicated need and the FLEX need.

        :param roster: The user's current roster.
        :param roster_config: League roster configuration.
        :return: Mapping of :class:`~gridiron_yampylytics.ffb.models.player.Position`
            → need score in [0.0, 1.0].
        """
        dedicated_slots: dict[Position, int] = {
            Position.QB: roster_config.qb,
            Position.RB: roster_config.rb,
            Position.WR: roster_config.wr,
            Position.TE: roster_config.te,
            Position.K: roster_config.k,
            Position.DEF: roster_config.def_,
        }
        need: dict[Position, float] = {}
        for pos, slots in dedicated_slots.items():
            if slots == 0:
                need[pos] = 0.0
            else:
                filled = roster.count_at_position(pos)
                need[pos] = max(0.0, 1.0 - filled / slots)
        if roster_config.flex > 0:
            overage = sum(
                max(0, roster.count_at_position(pos) - dedicated_slots.get(pos, 0))
                for pos in roster_config.flex_eligible
            )
            flex_need = max(0.0, 1.0 - overage / roster_config.flex)
            for pos in roster_config.flex_eligible:
                need[pos] = max(need.get(pos, 0.0), flex_need)
        return need
