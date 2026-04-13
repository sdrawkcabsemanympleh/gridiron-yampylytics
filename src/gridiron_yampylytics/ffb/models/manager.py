"""Fantasy football manager model.

Named ``Manager`` to reflect the general manager role and stay useful
beyond drafting (trades, lineup decisions, etc.).
"""
from pydantic import BaseModel, Field


class Manager(BaseModel):
    """A fantasy football manager (league participant).

    :param manager_id: Unique identifier. Maps to Sleeper ``user_id`` when
        integrated with the Sleeper API.
    :param name: Display name for this manager.
    :param draft_slot: 1-indexed permanent pick slot assigned at the draft draw
        (e.g. slot 3 means this manager picks 3rd in round 1, 10th in round 2
        of a 12-team league, etc.).
    :param is_user: ``True`` if this manager represents the person running the
        tool. Exactly one ``Manager`` per ``DraftState`` should be the user.
    """
    manager_id: str
    name: str
    draft_slot: int = Field(ge=1)
    is_user: bool = False
