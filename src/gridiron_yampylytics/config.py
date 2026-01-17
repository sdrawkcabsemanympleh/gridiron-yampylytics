"""Dataset groupings and configuration constants for gridiron-yampylytics.

This module defines reusable dataset collections for different use cases, from quick
setup to maximum performance. Using frozensets allows DRY superset relationships.
"""

# Essential datasets for quick exploration and minimal setup
# Focused on player evaluation and draft analysis
ESSENTIAL_DATASETS = frozenset({
    'combine',      # NFL Combine results (2000-2024)
    'draft_picks',  # Draft history (1967-2025)
    'players',      # Comprehensive player info + multi-platform IDs (all players)
    'rosters',      # Team rosters (2006-2025)
    'teams',        # Team metadata (abbr, names, colors, logos)
})

# Comprehensive analysis datasets - everything except the massive files
# Suitable for most analysis workflows without overwhelming download times
ANALYSIS_DATASETS = ESSENTIAL_DATASETS | frozenset({
    'player_stats',  # Weekly/seasonal stats (2012-2025)
    'schedules',     # Game schedules (1999-2025)
    'injuries',      # Injury reports (2009-2025)
    'depth_charts',  # Depth charts (2017-2025)
    'contracts',     # Player contracts (48K contracts)
    'ids',           # Player ID mappings (gsis_id, pfr_id, espn_id)
})

# Large datasets that require significant time and disk space
# Play-by-play is the behemoth (~1.2M rows, 1999-2025)
LARGE_DATASETS = frozenset({
    'pbp',  # Play-by-play data (WARNING: very large, takes time to download/process)
})

# Maximum yampage - every available dataset
# Use for comprehensive analysis or when building with tables + indexes
YAMPY_DATASETS = ANALYSIS_DATASETS | LARGE_DATASETS

# All available nflverse datasets
ALL_DATASETS = YAMPY_DATASETS


def get_dataset_description(dataset_name: str) -> str:
    """Get a human-readable description of a dataset group.

    :param dataset_name: Name of the dataset group (e.g., 'ESSENTIAL_DATASETS')
    :return: Description string
    """
    descriptions = {
        'ESSENTIAL_DATASETS': 'Quick exploration: combine, draft, rosters (~1-2 min)',
        'ANALYSIS_DATASETS': 'Comprehensive analysis without PBP (~5-10 min)',
        'LARGE_DATASETS': 'Large datasets (pbp) requiring significant time/space',
        'YAMPY_DATASETS': 'Maximum yampage - all available datasets',
        'ALL_DATASETS': 'All available nflverse datasets',
    }
    return descriptions.get(dataset_name, 'Unknown dataset group')
