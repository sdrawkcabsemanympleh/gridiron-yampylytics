import datetime
import duckdb
import pandas as pd
from dataclasses import dataclass
from enum import Enum


# For each position we calculate, we may need to include others, due to it being a superset, naming, nomenclature
# Ideally a player which contributes to more than one of these will have an entry for where they lie in each.
contributing_positions = {
    'QB': {'QB'},
    'RB': {'RB'},
    'FB': {'FB'},
    'OT': {'OT', 'LT', 'RT', 'T'},
    'OG': {'OG', 'LG', 'RG', 'G'},
    'C': {'C'},
    'OL': {'OT', 'LT', 'RT', 'OG', 'LG', 'RG', 'C'},
    'TE': {'TE'},
    'WR': {'WR', 'CB/WR'},  # Hunter gotta go make our lives harder...
    'CB': {'CB', 'CB/WR'},
    'S': {'S', 'SAF'},
    'DB': {'CB', 'CB/WR', 'S', 'SAF'},
    'LB': {'LB', 'ILB'},  # Standardize off-ball-ish linebackers here
    'EDGE': {'EDGE', 'OLB'},  # Edge didn't exist prior to 2018; most would have been OLB, some DE
    'DT': {'DT'},
    'DE': {'DE'},
    'DL': {'DL', 'DT', 'DE'},
    'K': {'K'},
    'P': {'P'},
    'LS': {'LS'}
}


class YasCalcType(Enum):
    """Denotes the calculation, whether including all players (current), or only previous ones (historical)"""
    HISTORICAL = 'historical'
    CURRENT = 'current'


class CombineMeasurables(Enum):
    """Various Combine drills and measurments included in the data, mirroring table column names"""
    BENCH = 'bench'
    BROAD_JUMP = 'broad_jump'
    CONE = 'cone'
    FORTY = 'forty'
    HEIGHT = 'ht'
    SHUTTLE = 'shuttle'
    VERTICAL = 'vertical'
    WEIGHT = 'wt'


def higher_is_better(measurable: CombineMeasurables) -> bool:
    """For some measurables, like height, a big number is good.  Some it is not.  This tells you if big number gud.

    :param measurable: A combine measurable
    :returns: True if the measurable is better, False otherwise
    """
    return measurable.value in {'ht', 'wt', 'bench', 'vertical', 'broad_jump'}


def standardize_position(position: str) -> str:
    """Standardizes the position codes for players.  Trying to be light handed, but still ensure the data has value
    by ensuring there are enough peers to calculate against and we get rid of oddballs like SAF

    :param str position: position code to standardize
    :return: standardized position code
    """
    if position in {'T','LT', 'RT'}:
        return 'OT'
    if position in {'LG', 'RG', 'G'}:
        return 'OG'
    if position == 'SAF':
        return 'S'
    if position in {'LB', 'ILB'}:
        return 'LB'
    if position in {'EDGE', 'OLB'}:
        return 'EDGE'
    return position


def get_percentiles(connection: duckdb.DuckDBPyConnection, position: str, measurable: CombineMeasurables,
                    calculation_year: int,  return_previous_classes: bool = False):
    """Queries DuckDB to get the percentile rank for a given position and measurable.  Uses the contributing_positions
    mapping to map to all positions to be queried for.

    :param str position: position code the calculation will be made for
    :param measurable: measureable to get data for
    :param calculation_year: calculates the percentile based on all players in this draft class or before
    :param return_previous_classes: returns players of previous draft classes for calculating current YAS
    """
    ordering = 'DESC' if higher_is_better(measurable) else 'ASC'
    query_string = f"""
        SELECT
            yamplayer_id
            , player_name
            , pos as drafted_position
            , {position} as calculation_position
            , {standardize_position(position)} as yas_position
            , draft_year as draft_year
            , {calculation_year} as calculation_year
            , {measurable.value}
            , 100 * PERCENT_RANK() OVER (ORDER BY {measurable.value} {ordering}) as {measurable.value}_percentile
        FROM
            nflverse.combine
        WHERE
            {measurable.value} IS NOT NULL
            AND pos in {contributing_positions[position]}
            AND draft_year <= {calculation_year}
        """
    if not return_previous_classes:
        query_string = f'SELECT * FROM ({query_string}) WHERE draft_year = {calculation_year}'
    df = connection.execute(query_string).df()
    return df


def calculate_position_yas_scores(connection: duckdb.DuckDBPyConnection, position: str, calculation_year: int,
                                  return_previous_classes: bool = True):
    """Queries DuckDB to get the percentile rank for a given position.  Uses the contributing_positions mapping to
    map to all positions to be queried for.

    :param str position: position code the calculation will be made for
    :param calculation_year: calculates the percentile based on all players in this draft class or before
    :param return_previous_classes: returns players of previous draft classes for calculating current YAS
    """
    yas_merged = pd.DataFrame({
        'yamplayer_id': [],
        'player_name': [],
        'drafted_position': [],
        'calculation_position': [],
        'yas_position': [],
        'calculation_year': [],
    })
    yas_merged = yas_merged.set_index(['yamplayer_id', 'calculation_position', 'calculation_year'])
    columns_to_average = [f'{measurable.value}_percentile' for measurable in CombineMeasurables]
    for measurable in CombineMeasurables:
        yas_merged = pd.merge(
            yas_merged,
            get_percentiles(connection, position, measurable, calculation_year, return_previous_classes),
            left_index=True,
            right_on=['yamplayer_id', 'calculation_position', 'calculation_year'],
            how='outer'
        )
    yas_merged['yas_score_unnormallized'] = yas_merged[columns_to_average].mean(axis=1)
    yas_merged['yas_score'] = yas_merged['yas_score_unnormallized'].rank(pct=True)
    return yas_merged


def calculate_year_yas(connection: duckdb.DuckDBPyConnection, calculation_year: int | None = None,
                              yas_calc_type: YasCalcType = YasCalcType.HISTORICAL):
    """Calculates YAS for a given year for all positions.  If historical is requested, only the players in the draft
    for that year are included, yielding the score compared to all players that year and before, like RAS.  If current,
    scores are calculated for all players in that year and before.  Defaults to this year so current need not have
    a year supplied.

    :param str position: position code the calculation will be made for
    :param measurable: measureable to get data for
    :param calculation_year: calculates the percentile based on all players in this draft class or before
    :param yas_calc_type: determines whether players of previous draft classes should be returned or not
    :return: Dataframe of the draft class YAS scores
    """
    if calculation_year is None:
        calculation_year = datetime.datetime.now().year
    yas_merged = pd.DataFrame({
        'yamplayer_id': [],
        'player_name': [],
        'drafted_position': [],
        'calculation_position': [],
        'yas_position': [],
        'calculation_year': [],
    })
    yas_merged = yas_merged.set_index(['yamplayer_id', 'calculation_position', 'calculation_year', 'calculation_type'])
    for position in contributing_positions.keys():
        position_yas = calculate_position_yas_scores(
            connection=connection,
            position=position,
            calculation_year=calculation_year,
            return_previous_classes=True if yas_calc_type == YasCalcType.CURRENT else False,
        )
        yas_merged = pd.merge(
            yas_merged,
            position_yas,
            left_index=True,
            #right_on=['yamplayer_id', 'calculation_position', 'calculation_year'],
            right_index=True,
            how='outer'
        )
    yas_merged['calculation_type'] = yas_calc_type.value
    yas_merged = yas_merged.set_index('calculation_type', append=True)
    return yas_merged


def calculate_all_yas(connection: duckdb.DuckDBPyConnection):
    """Generates all historical YAS data for all years from 2000 forward to now as well as the current years'.  It
    does have the inefficiency of querying for all combine data from 2000 to the calculation year at each iteration,
    which we can optimize by querying only for the new data each iteration and more integration of dataframe indexing.

    :param connection: duckdb.DuckDB connection object
    """
    calculation_year = datetime.datetime.now().year
    historical_years = list(range(2000, calculation_year + 1))
    yas_merged = pd.DataFrame({
        'yamplayer_id': [],
        'player_name': [],
        'drafted_position': [],
        'calculation_position': [],
        'yas_position': [],
        'calculation_year': [],
        'calculation_type': []
    })
    yas_merged = yas_merged.set_index(['yamplayer_id', 'calculation_position', 'calculation_year', 'calculation_type'])
    for year in historical_years:
        yas_scores = calculate_year_yas(connection=connection, calculation_year=year)
        yas_merged = pd.merge(
            yas_merged,
            yas_scores,
            left_index=True,
            #right_on=['yamplayer_id', 'calculation_position', 'calculation_year'],
            right_index=True,
            how='outer'
        )
    current_yas = calculate_year_yas(connection=connection, calculation_year=calculation_year,
                                     yas_calc_type=YasCalcType.CURRENT)
    yas_merged = pd.merge(
        yas_merged,
        current_yas,
        left_index=True,
        right_index=True,
        #right_on=['yamplayer_id', 'calculation_position', 'calculation_year', 'calculation_type'],
        how='outer'
    )
    return yas_merged


@dataclass
class YasPlayerScore:  # TODO:  Expand this for all combine attributes and make script to generate these
    """Will eventually change to pydantic model and move out, but can be used for fun coding bidness"""
    yamplayer_id: str
    draft_position: str
    draft_year: int
    calculated_position: str
    calculated_year: int
    combine_test: str
    combine_value: float
    yas_overall_current: float
    yas_overall_historical: float