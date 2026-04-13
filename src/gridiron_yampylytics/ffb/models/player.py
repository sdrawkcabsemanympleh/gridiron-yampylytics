"""NFL player model for fantasy football draft analysis.

Represents an NFL player as a draftable entity with projected statistics,
ADP data, and positional metadata.
"""
from enum import StrEnum
from pydantic import BaseModel, Field, model_validator


class Position(StrEnum):
    """NFL fantasy football positions.

    Covers all positions used in standard fantasy formats.
    IDP (individual defensive player) positions are out of scope for now.
    """
    QB = "QB"
    RB = "RB"
    WR = "WR"
    TE = "TE"
    K = "K"
    DEF = "DEF"


class NFLPlayer(BaseModel):
    """An NFL player available for fantasy football drafting.

    :param player_id: Unique player identifier (yamplayer_id preferred; gsis_id fallback).
    :param name: Player's full display name.
    :param position: Primary fantasy position. Used for VOR/VONA calculations,
        scarcity modeling, and display. Determines which positional pool the
        player competes in analytically.
    :param eligible_positions: All roster slots this player can fill. Defaults to
        ``{position}``. Use for multi-eligibility players (e.g. RB/WR eligible
        CMC-types): set ``position=RB`` and ``eligible_positions={RB, WR}``.
    :param team: NFL team abbreviation (e.g. ``"KC"``, ``"BUF"``).
    :param projected_points: Projected fantasy points for the full season.
    :param adp: Average draft position from consensus source.
    :param adp_std: Standard deviation of ADP across drafters, used for opponent
        pick probability modeling. Defaults to 5.0; should be calibrated from data.
    :param bye_week: Team's bye week (1–18). ``None`` if not yet available.
    :param ecr_rank: Expert consensus rank across all positions, if available.
    :param injury_status: Current injury designation. ``None`` means healthy.
        Typical Sleeper values: ``"Q"`` (questionable), ``"D"`` (doubtful),
        ``"O"`` (out), ``"IR"`` (injured reserve), ``"PUP"``.
    """
    player_id: str
    name: str
    position: Position
    eligible_positions: set[Position] = Field(default_factory=set)
    team: str
    projected_points: float
    adp: float
    adp_std: float = Field(default=5.0, ge=0.0)
    bye_week: int | None = None
    ecr_rank: int | None = None
    injury_status: str | None = None

    @model_validator(mode="after")
    def ensure_primary_position_is_eligible(self) -> "NFLPlayer":
        """Ensure ``position`` is always included in ``eligible_positions``.

        :return: The validated ``NFLPlayer`` instance.
        """
        self.eligible_positions = self.eligible_positions | {self.position}
        return self
