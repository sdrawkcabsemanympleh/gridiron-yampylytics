"""Dataset groupings and configuration constants for gridiron-yampylytics.

This module auto-generates dataset collections from the configuration in nflverse.py.
Groups are defined by the 'groups' field in DATASET_CONFIG.
"""
from gridiron_yampylytics.loaders.nflverse import DATASET_CONFIG

# Auto-generate dataset groups from configuration
# Datasets can belong to multiple groups via the 'groups' field in DATASET_CONFIG
ESSENTIAL_DATASETS = frozenset({
    name for name, cfg in DATASET_CONFIG.items()
    if 'ESSENTIAL' in cfg['groups']
})

ANALYSIS_DATASETS = frozenset({
    name for name, cfg in DATASET_CONFIG.items()
    if 'ANALYSIS' in cfg['groups'] or 'ESSENTIAL' in cfg['groups']
})

LARGE_DATASETS = frozenset({
    name for name, cfg in DATASET_CONFIG.items()
    if 'LARGE' in cfg['groups']
})

# Maximum yampage - every available dataset
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
