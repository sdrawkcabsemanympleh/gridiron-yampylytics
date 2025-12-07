"""This file implements the various console commands so that you don't have to memorize lengthy uv commands and such"""


from invoke import task
from typing import List, Optional

@task(help={
    'all_datasets': 'Will load all datasets if supplied, including very large ones.',
    'data_sets': 'Allows you to specify which datasets to load.  Pass list as comma separated string: my_set1,my_set2'
})
def load_data(c, all_datasets: bool = False, data_sets: Optional[List[str]] = None):
    """Used to load datasets.  By default, will load a number of reasonably sized datasets."""
    if all_datasets:  # TODO:  Implement these flags in load_all_data or make a modular script for loading each
        c.run('uv run python -m scripts.load_all_data --all_datasets')
    elif data_sets:
        c.run(f'uv run python -m scripts.load_all_data --data_sets={data_sets}')
    else:
        c.run('uv run python -m scripts.load_all_data')


@task
def clean_depth_charts(c):
    """The depth charts change schema in 2024-2025 and need to be separated into legacy and modern datasets to be
    usable.  This completes that operation.
    """
    c.run('uv run python -m scripts.clean_depth_charts')


@task
def combine_gm_data(c):
    """The GM data is scraped into a bunch of messy datafiles.  This script combines them into something more usable."""
    c.run('uv run python -m scripts.combine_gm_data')


@task(help={
    'all_datasets': 'Will load all datasets if supplied, including very large ones.',
})
def generate_yamplayer_id(c, all_datasets=False):
    """Generates universal yamplayer ID's and applies them to datasets.  Applies only to reasonable sized sests by
    default."""
    if all_datasets:
        c.run('uv run python -m scripts.generate_yamplayer_id --all_datasets')
    c.run('uv run python -m scripts.generate_yamplayer_id')


@task
def calculate_yas(c):
    """Calculates the yampylytics Athletic Score (YAS), similar to the Relative Athletic Score by MathBomb"""
    c.run('uv run python -m scripts.calculate_yas')


@task(help={
    'all_datasets': 'Will load all datasets if supplied, including very large ones.',
})
def process_data(c, all_datasets: bool = False):
    """Process the raw data gathered from load_data, including operations like cleaning depth chart data, injecting
    universal yamplayer_id's into tables, and processing GM scrape data.
    """
    c.invoke(clean_depth_charts, all_datasets=all_datasets)
    c.invoke(combine_gm_data, all_datasets=all_datasets)
    c.invoke(generate_yamplayer_id, all_datasets=all_datasets)
    c.iinvoke(calculate_yas, all_datasets=all_datasets)

@task(help={
    'all_datasets': 'Will load all datasets if supplied, including very large ones.',
    'as_tables': 'If true, CSVs are loaded as tables indexes, otherwise as lighterweight views.',
    'include_pbp':  'Includes one particular large dataset, Play-by-Play data.  Only applies when loading as table.'
})
def create_duckdb(c, all_datasets: bool = False, include_pbp: bool = False, as_tables: bool = False):
    """Creates a local DuckDB with the loaded data.  CSV's loaded as views as default, but can be loaded as tables
    which include useful indexes at the cost of taking up disk space.  Also note that tables do not change when the
    source CSV's do."""
    if as_tables:
        if all_datasets:
            suffix = ' --all_datasets'
        elif include_pbp:
            suffix = ' --include_pbp'
        else:
            suffix = ''
        c.run(f'uv run python -m scripts.create_duckdb_tables{suffix}')
    else:
        c.run('uv run python -m scripts.create_duckdb_views')


@task(help={
    'unix':  'Denotes that this is a unix system so that --no-download-tzdata is not supplied.'
})
def sql(c, unix=False):
    """Starts Harlequin command line SQL explorer.  Uses --no-download-tzdata unless overridden for compatibility
    with Windows."""
    suffix = ' --no-download-tzdata' if unix else ''
    c.run(f'uv run harlequin gridiron_yampylytics.db{suffix}')


@task
def setup(c):
    """Completes all setup steps with default settings, including fetching all data, processing, and database
    creation using .  This may take some time depending on your system and internet connection."""
    c.invoke(load_data)
    c.invoke(process_data)
    c.invoke(create_duckdb)


@task
def yampy_setup(c):
    """Setup with Yampy option set for maximum yampage."""
    c.invoke(load_data)
    c.invoke(process_data)
    c.invoke(create_duckdb, as_tables=True)
