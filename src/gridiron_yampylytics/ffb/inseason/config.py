"""Configuration constants for the YampGM in-season tool."""

# Sleeper username for the tool owner.  Single-user assumption — this tool
# is built for one person running their own instance.
SLEEPER_USERNAME: str = "CarlCCryMoar"

# How many recent weeks of actual performance to include in consistency scoring.
# Fewer weeks = more reactive to recent form; more weeks = more stable signal.
LOOKBACK_WEEKS: int = 4

# Number of upcoming weeks to evaluate for schedule/matchup quality.
SCHEDULE_LOOKAHEAD_WEEKS: int = 3

# Sleeper trending endpoint parameters.
TRENDING_LOOKBACK_HOURS: int = 24
TRENDING_LIMIT: int = 50

# Positions included in the FA pool scorer.  IDP out of scope.
SCORED_POSITIONS: frozenset[str] = frozenset({"QB", "RB", "WR", "TE", "K", "DEF"})
