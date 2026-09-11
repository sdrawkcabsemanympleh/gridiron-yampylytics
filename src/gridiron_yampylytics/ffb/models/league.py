"""League configuration models for fantasy football.

Captures scoring rules, roster configuration, and format settings
for a specific fantasy football league. All settings are configurable
so the tool works across different league formats.
"""
from enum import StrEnum
from typing import Literal
from pydantic import BaseModel, Field, model_validator
from .player import Position


class ScoringType(StrEnum):
    """Standard fantasy football scoring formats.

    :cvar STANDARD: No points for receptions.
    :cvar HALF_PPR: 0.5 points per reception.
    :cvar PPR: 1.0 point per reception.
    """
    STANDARD = "standard"
    HALF_PPR = "half_ppr"
    PPR = "ppr"


class ScoringConfig(BaseModel):
    """Per-stat point values for fantasy scoring.

    Defaults to full PPR. Use the class methods for common presets,
    or override individual fields for custom leagues.

    :param scoring_type: The broad scoring format label.
    :param passing_yards_per_point: Passing yards required for one point
        (e.g. 25.0 means 1 pt per 25 passing yards).
    :param passing_td: Points per passing touchdown.
    :param passing_int: Points per interception thrown (typically negative).
    :param rushing_yards_per_point: Rushing yards required for one point.
    :param rushing_td: Points per rushing touchdown.
    :param receiving_yards_per_point: Receiving yards required for one point.
    :param receiving_td: Points per receiving touchdown.
    :param reception: Points per reception (0.0, 0.5, or 1.0 for standard/half/PPR).
    :param fumble_lost: Points per fumble lost (typically negative).
    """
    scoring_type: ScoringType = ScoringType.PPR
    passing_yards_per_point: float = Field(default=25.0, gt=0.0)
    passing_td: float = 4.0
    passing_int: float = -2.0
    rushing_yards_per_point: float = Field(default=10.0, gt=0.0)
    rushing_td: float = 6.0
    receiving_yards_per_point: float = Field(default=10.0, gt=0.0)
    receiving_td: float = 6.0
    reception: float = 1.0
    fumble_lost: float = -2.0

    @classmethod
    def ppr(cls) -> "ScoringConfig":
        """Create a full PPR scoring configuration.

        :return: ``ScoringConfig`` with 1.0 points per reception.
        """
        return cls(scoring_type=ScoringType.PPR, reception=1.0)

    @classmethod
    def half_ppr(cls) -> "ScoringConfig":
        """Create a half-PPR scoring configuration.

        :return: ``ScoringConfig`` with 0.5 points per reception.
        """
        return cls(scoring_type=ScoringType.HALF_PPR, reception=0.5)

    @classmethod
    def standard(cls) -> "ScoringConfig":
        """Create a standard (no-PPR) scoring configuration.

        :return: ``ScoringConfig`` with 0.0 points per reception.
        """
        return cls(scoring_type=ScoringType.STANDARD, reception=0.0)


class RosterConfig(BaseModel):
    """Roster spot counts by position for a fantasy league.

    Defines how many starters and bench spots exist, and which positions
    are eligible to fill flex slots.

    :param qb: Number of QB starter slots.
    :param rb: Number of RB starter slots.
    :param wr: Number of WR starter slots.
    :param te: Number of TE starter slots.
    :param flex: Number of FLEX starter slots.
    :param flex_eligible: Positions that can fill a FLEX slot.
        Defaults to RB, WR, TE (standard). Set to include QB for SUPERFLEX.
    :param k: Number of kicker slots.
    :param def_: Number of team defense/special teams slots.
    :param bench: Number of bench spots.
    :param ir_slots: Number of injured reserve slots. IR slots sit outside the
        regular roster and do not count toward draft rounds — they are relevant
        for in-season roster management (placing injured players on IR to free
        up a regular spot). Defaults to 0.
    """
    qb: int = Field(default=1, ge=0)
    rb: int = Field(default=2, ge=0)
    wr: int = Field(default=3, ge=0)
    te: int = Field(default=1, ge=0)
    flex: int = Field(default=1, ge=0)
    flex_eligible: list[Position] = Field(
        default_factory=lambda: [Position.RB, Position.WR, Position.TE]
    )
    k: int = Field(default=1, ge=0)
    def_: int = Field(default=1, ge=0)
    bench: int = Field(default=6, ge=0)
    ir_slots: int = Field(default=0, ge=0)

    @property
    def total_starters(self) -> int:
        """Total number of starting roster spots (excludes bench and IR).

        :return: Sum of all positional starter slots.
        """
        return self.qb + self.rb + self.wr + self.te + self.flex + self.k + self.def_

    @property
    def total_spots(self) -> int:
        """Regular roster spots including bench, excluding IR.

        This is the number of draft rounds — IR slots are not drafted into
        directly and do not add rounds.

        :return: ``total_starters + bench``.
        """
        return self.total_starters + self.bench

    @property
    def total_capacity(self) -> int:
        """Maximum players a manager can hold including IR slots.

        Use this for in-season roster checks. For draft purposes, use
        ``total_spots``.

        :return: ``total_spots + ir_slots``.
        """
        return self.total_spots + self.ir_slots

    @property
    def total_rounds(self) -> int:
        """Number of draft rounds required to fill rosters.

        :return: Equals ``total_spots`` since IR slots are not drafted.
        """
        return self.total_spots


class League(BaseModel):
    """Fantasy football league configuration.

    Combines roster settings, scoring rules, and draft format into
    a single configurable object. A ``League`` is the root config that
    all other models depend on.

    :param league_id: Sleeper league ID, if integrating with the Sleeper API.
        ``None`` for manual / standalone use.
    :param name: Human-readable league name.
    :param team_count: Number of teams (managers) in the league.
    :param roster: Roster spot configuration.
    :param scoring: Per-stat scoring configuration.
    :param draft_type: Draft format. Only ``"snake"`` is supported currently.
    """
    league_id: str | None = None
    name: str = "My League"
    team_count: int = Field(default=12, ge=2)
    roster: RosterConfig = Field(default_factory=RosterConfig)
    scoring: ScoringConfig = Field(default_factory=ScoringConfig)
    draft_type: Literal["snake"] = "snake"

    @model_validator(mode="after")
    def draft_position_range_is_valid(self) -> "League":
        """Validate that roster config is internally consistent.

        :return: The validated ``League`` instance.
        :raises ValueError: If total roster spots would be zero.
        """
        if self.roster.total_spots == 0:
            raise ValueError("Roster must have at least one spot.")
        return self
