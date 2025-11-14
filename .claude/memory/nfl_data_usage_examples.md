# NFL Data Usage Examples - Common Analysis Patterns

**Last Updated:** 2025-11-14
**Companion to:** nfl_data_architecture.md

This document provides concrete code examples for common NFL data analysis tasks in the gridiron-yampylytics project.

---

## Table of Contents

1. [GM Performance Analysis](#gm-performance-analysis)
2. [Draft Efficiency Analysis](#draft-efficiency-analysis)
3. [Team Performance Metrics](#team-performance-metrics)
4. [Coach Tenure Analysis](#coach-tenure-analysis)
5. [Salary Cap Analysis](#salary-cap-analysis)
6. [Player Career Analysis](#player-career-analysis)
7. [Advanced Play-by-Play Queries](#advanced-play-by-play-queries)

---

## GM Performance Analysis

### 1. Calculate GM Win-Loss Records

```python
import polars as pl

# Load data
schedules = pl.read_csv('data/cached/nflreadpy/schedules/schedules_all.csv')
gm_files = list(Path('data/raw/executives').glob('*_executives.csv'))

# Load all GM data
gm_executives = pl.concat([
    pl.read_csv(f).with_columns(pl.lit(f.stem.split('_')[0]).alias('pfr_team_code'))
    for f in gm_files
])

# Parse GM tenures
gm_tenures = (
    gm_executives
    .filter(pl.col('Titles').str.contains('General Manager'))
    .select([
        pl.col('Person').alias('gm_name'),
        pl.col('pfr_team_code'),
        pl.col('From').cast(pl.Int64).alias('start_year'),
        pl.when(pl.col('To') == '').then(2025).otherwise(pl.col('To').cast(pl.Int64)).alias('end_year')
    ])
)

# Map PFR team codes to nflverse (manual mapping for now)
team_mapping = {
    'nwe': 'NE', 'dal': 'DAL', 'kan': 'KC', 'gnb': 'GB',
    'nwe': 'NE', 'sfo': 'SF', 'tam': 'TB', 'rav': 'BAL',
    'clt': 'IND', 'htx': 'HOU', 'nor': 'NO', 'crd': 'ARI',
    'oti': 'TEN', 'sdg': 'LAC', 'ram': 'LA', 'rai': 'LV'
    # ... (add remaining teams)
}

gm_tenures = gm_tenures.with_columns(
    pl.col('pfr_team_code').replace(team_mapping).alias('team')
)

# Calculate team records by season
team_records = (
    schedules
    .filter(pl.col('game_type') == 'REG')
    .select([
        pl.col('season'),
        # Home games
        pl.col('home_team').alias('team'),
        pl.when(pl.col('result') > 0).then(1).otherwise(0).alias('home_win'),
        pl.when(pl.col('result') < 0).then(1).otherwise(0).alias('home_loss'),
        pl.when(pl.col('result') == 0).then(1).otherwise(0).alias('home_tie'),
    ])
    # Combine with away games (union pattern)
    .union(
        schedules
        .filter(pl.col('game_type') == 'REG')
        .select([
            pl.col('season'),
            pl.col('away_team').alias('team'),
            pl.when(pl.col('result') < 0).then(1).otherwise(0).alias('home_win'),
            pl.when(pl.col('result') > 0).then(1).otherwise(0).alias('home_loss'),
            pl.when(pl.col('result') == 0).then(1).otherwise(0).alias('home_tie'),
        ])
    )
    .group_by(['team', 'season'])
    .agg([
        pl.sum('home_win').alias('wins'),
        pl.sum('home_loss').alias('losses'),
        pl.sum('home_tie').alias('ties')
    ])
)

# Join GM tenures with team records
gm_performance = (
    team_records
    .join(
        gm_tenures,
        on='team',
        how='left'
    )
    .filter(
        (pl.col('season') >= pl.col('start_year')) &
        (pl.col('season') <= pl.col('end_year'))
    )
    .group_by('gm_name')
    .agg([
        pl.sum('wins').alias('total_wins'),
        pl.sum('losses').alias('total_losses'),
        pl.sum('ties').alias('total_ties'),
        pl.count().alias('seasons'),
        (pl.sum('wins') / (pl.sum('wins') + pl.sum('losses'))).alias('win_pct')
    ])
    .sort('win_pct', descending=True)
)

print(gm_performance.head(10))
```

### 2. GM Playoff Success Rate

```python
# Calculate playoff appearances by GM
playoff_appearances = (
    schedules
    .filter(pl.col('game_type').is_in(['WC', 'DIV', 'CON', 'SB']))
    .select([
        pl.col('season'),
        pl.col('home_team').alias('team')
    ])
    .union(
        schedules
        .filter(pl.col('game_type').is_in(['WC', 'DIV', 'CON', 'SB']))
        .select([
            pl.col('season'),
            pl.col('away_team').alias('team')
        ])
    )
    .unique()
    .join(gm_tenures, on='team', how='left')
    .filter(
        (pl.col('season') >= pl.col('start_year')) &
        (pl.col('season') <= pl.col('end_year'))
    )
    .group_by('gm_name')
    .agg([
        pl.count().alias('playoff_seasons'),
        pl.n_unique('season').alias('unique_playoff_years')
    ])
)

# Calculate Super Bowl wins
superbowl_wins = (
    schedules
    .filter(pl.col('game_type') == 'SB')
    .with_columns([
        # Winner is home team if result > 0, else away team
        pl.when(pl.col('result') > 0).then(pl.col('home_team')).otherwise(pl.col('away_team')).alias('winner')
    ])
    .select(['season', 'winner'])
    .join(gm_tenures, left_on='winner', right_on='team', how='left')
    .filter(
        (pl.col('season') >= pl.col('start_year')) &
        (pl.col('season') <= pl.col('end_year'))
    )
    .group_by('gm_name')
    .agg(pl.count().alias('sb_wins'))
)

# Combine metrics
gm_complete = (
    gm_performance
    .join(playoff_appearances, on='gm_name', how='left')
    .join(superbowl_wins, on='gm_name', how='left')
    .with_columns([
        (pl.col('playoff_seasons') / pl.col('seasons')).alias('playoff_rate'),
        pl.col('sb_wins').fill_null(0)
    ])
)
```

---

## Draft Efficiency Analysis

### 1. GM Draft Success with Rich Hill Values

```python
# Load draft data
draft_picks = pl.read_csv('data/cached/nflreadpy/draft_picks/draft_picks_all.csv')
rich_hill_values = pl.read_csv('data/reference/draft_value_charts/rich_hill_draft_values.csv')

# Analyze draft efficiency (post-2011 rookie wage scale era)
draft_efficiency = (
    draft_picks
    .filter(pl.col('season') >= 2012)  # Rich Hill values optimized for post-2011
    .join(
        rich_hill_values,
        left_on='pick',
        right_on='pick_number',
        how='left'
    )
    .with_columns([
        # Normalize career AV to expected value scale
        # Rich Hill values are in "surplus value" terms, need conversion
        pl.col('car_av').fill_null(0).alias('actual_av'),
        pl.col('value').alias('expected_value'),
        # Calculate surplus value (actual performance vs draft cost)
        (pl.col('car_av').fill_null(0) - (pl.col('value') / 100)).alias('surplus_value')  # Adjust scale
    ])
)

# Join with GM tenures
gm_draft_success = (
    draft_efficiency
    .join(gm_tenures, on='team', how='left')
    .filter(
        (pl.col('season') >= pl.col('start_year')) &
        (pl.col('season') <= pl.col('end_year'))
    )
    .group_by('gm_name')
    .agg([
        pl.count().alias('total_picks'),
        pl.mean('surplus_value').alias('avg_surplus_value'),
        pl.sum('actual_av').alias('total_av_drafted'),
        # Hit rate: players with car_av > 20 (quality starter threshold)
        (pl.col('car_av').filter(pl.col('car_av') > 20).count() / pl.count()).alias('hit_rate'),
        # Bust rate: first round picks with car_av < 10
        (pl.col('car_av').filter((pl.col('round') == 1) & (pl.col('car_av') < 10)).count() /
         pl.col('round').filter(pl.col('round') == 1).count()).alias('first_round_bust_rate')
    ])
    .sort('avg_surplus_value', descending=True)
)
```

### 2. Draft Position Value Analysis

```python
# Compare actual vs expected performance by draft position
draft_position_analysis = (
    draft_picks
    .filter(pl.col('season') >= 2000)
    .group_by(['round', 'position'])
    .agg([
        pl.count().alias('picks'),
        pl.mean('car_av').alias('avg_av'),
        pl.median('car_av').alias('median_av'),
        pl.quantile('car_av', 0.75).alias('p75_av'),
        (pl.col('car_av').filter(pl.col('car_av') > 20).count() / pl.count()).alias('starter_rate'),
        (pl.col('probowls').filter(pl.col('probowls') > 0).count() / pl.count()).alias('probowl_rate')
    ])
    .sort('round', 'avg_av')
)

# Identify best value positions by round
print("Best value positions by round:")
print(draft_position_analysis.filter(pl.col('round') <= 3).head(20))
```

---

## Team Performance Metrics

### 1. Comprehensive Team Performance by Season

```python
# Calculate point differential, home/away splits, playoff success
team_performance = (
    schedules
    .filter(pl.col('game_type') == 'REG')
    # Home games perspective
    .select([
        pl.col('season'),
        pl.col('home_team').alias('team'),
        pl.col('home_score').alias('points_for'),
        pl.col('away_score').alias('points_against'),
        pl.col('result'),
        pl.when(pl.col('result') > 0).then(1).otherwise(0).alias('win'),
        pl.lit('home').alias('location')
    ])
    .union(
        # Away games perspective
        schedules
        .filter(pl.col('game_type') == 'REG')
        .select([
            pl.col('season'),
            pl.col('away_team').alias('team'),
            pl.col('away_score').alias('points_for'),
            pl.col('home_score').alias('points_against'),
            pl.col('result').mul(-1).alias('result'),  # Flip result for away team
            pl.when(pl.col('result') < 0).then(1).otherwise(0).alias('win'),
            pl.lit('away').alias('location')
        ])
    )
    .group_by(['team', 'season'])
    .agg([
        pl.sum('win').alias('wins'),
        pl.len().alias('games'),
        pl.sum('points_for').alias('points_for'),
        pl.sum('points_against').alias('points_against'),
        (pl.sum('points_for') - pl.sum('points_against')).alias('point_diff'),
        # Home record
        pl.col('win').filter(pl.col('location') == 'home').sum().alias('home_wins'),
        # Away record
        pl.col('win').filter(pl.col('location') == 'away').sum().alias('away_wins')
    ])
)

# Add playoff indicator
playoff_teams = (
    schedules
    .filter(pl.col('game_type').is_in(['WC', 'DIV', 'CON', 'SB']))
    .select([
        pl.col('season'),
        pl.col('home_team').alias('team')
    ])
    .union(
        schedules
        .filter(pl.col('game_type').is_in(['WC', 'DIV', 'CON', 'SB']))
        .select([
            pl.col('season'),
            pl.col('away_team').alias('team')
        ])
    )
    .unique()
    .with_columns(pl.lit(1).alias('made_playoffs'))
)

team_performance_complete = (
    team_performance
    .join(playoff_teams, on=['team', 'season'], how='left')
    .with_columns([
        pl.col('made_playoffs').fill_null(0),
        (pl.col('wins') / pl.col('games')).alias('win_pct')
    ])
    .sort(['season', 'wins'], descending=True)
)
```

### 2. Strength of Schedule Calculation

```python
# Calculate opponent win percentage for each team
opponent_records = (
    schedules
    .filter(pl.col('game_type') == 'REG')
    .join(
        team_performance.select(['team', 'season', 'win_pct']),
        left_on=['away_team', 'season'],
        right_on=['team', 'season'],
        how='left'
    )
    .rename({'win_pct': 'opponent_win_pct'})
    .group_by(['home_team', 'season'])
    .agg(pl.mean('opponent_win_pct').alias('sos'))
)

team_performance_with_sos = (
    team_performance_complete
    .join(opponent_records, left_on=['team', 'season'], right_on=['home_team', 'season'])
)
```

---

## Coach Tenure Analysis

### 1. Extract Coach Tenures from Schedules

```python
# Extract unique coach-team combinations
coaches_home = (
    schedules
    .select(['season', 'week', 'home_team', 'home_coach'])
    .rename({'home_team': 'team', 'home_coach': 'coach'})
)

coaches_away = (
    schedules
    .select(['season', 'week', 'away_team', 'away_coach'])
    .rename({'away_team': 'team', 'away_coach': 'coach'})
)

all_coaches = pl.concat([coaches_home, coaches_away])

# Calculate coach tenures
coach_tenures = (
    all_coaches
    .group_by(['team', 'coach'])
    .agg([
        pl.min('season').alias('first_season'),
        pl.max('season').alias('last_season'),
        pl.n_unique('season').alias('seasons'),
        pl.count().alias('games')
    ])
    .filter(pl.col('coach').is_not_null())
)

# Calculate coach win records
coach_records = (
    schedules
    .filter(pl.col('game_type') == 'REG')
    # Home games
    .select([
        pl.col('home_team').alias('team'),
        pl.col('home_coach').alias('coach'),
        pl.when(pl.col('result') > 0).then(1).otherwise(0).alias('win')
    ])
    .union(
        # Away games
        schedules
        .filter(pl.col('game_type') == 'REG')
        .select([
            pl.col('away_team').alias('team'),
            pl.col('away_coach').alias('coach'),
            pl.when(pl.col('result') < 0).then(1).otherwise(0).alias('win')
        ])
    )
    .group_by(['team', 'coach'])
    .agg([
        pl.sum('win').alias('wins'),
        pl.len().alias('games'),
        (pl.sum('win') / pl.len()).alias('win_pct')
    ])
)

coach_complete = (
    coach_tenures
    .join(coach_records, on=['team', 'coach'])
    .sort('win_pct', descending=True)
)

print("Top coaches by win percentage (min 32 games):")
print(coach_complete.filter(pl.col('games') >= 32).head(20))
```

### 2. Coach-GM Pairings

```python
# Analyze which GM-coach pairings were most successful
gm_coach_pairings = (
    schedules
    .filter(pl.col('game_type') == 'REG')
    .select(['season', 'home_team', 'home_coach'])
    .union(
        schedules
        .filter(pl.col('game_type') == 'REG')
        .select(['season', 'away_team', 'away_coach'])
        .rename({'away_team': 'home_team', 'away_coach': 'home_coach'})
    )
    .unique()
    .join(gm_tenures, left_on=['home_team', 'season'], right_on=['team', 'season'])
    .filter(
        (pl.col('season') >= pl.col('start_year')) &
        (pl.col('season') <= pl.col('end_year'))
    )
    .join(
        team_performance.select(['team', 'season', 'wins', 'made_playoffs']),
        left_on=['home_team', 'season'],
        right_on=['team', 'season']
    )
    .group_by(['gm_name', 'home_coach'])
    .agg([
        pl.n_unique('season').alias('seasons_together'),
        pl.sum('wins').alias('total_wins'),
        pl.sum('made_playoffs').alias('playoff_seasons'),
        pl.mean('wins').alias('avg_wins_per_season')
    ])
    .filter(pl.col('seasons_together') >= 3)  # Min 3 seasons
    .sort('avg_wins_per_season', descending=True)
)
```

---

## Salary Cap Analysis

### 1. Team Salary Cap Usage by Year

```python
# Load contracts (Parquet format)
contracts = pl.read_parquet('data/cached/nflreadpy/contracts/contracts_all.parquet')

# Explode year-by-year contract details
# Note: 'cols' contains nested year-by-year data
# For this example, we'll aggregate at the contract level

team_cap_by_year = (
    contracts
    .with_columns([
        # Generate year range for each contract
        pl.int_range(pl.col('year_signed'), pl.col('year_signed') + pl.col('years'))
        .alias('contract_years')
    ])
    .explode('contract_years')
    .rename({'contract_years': 'year'})
    .group_by(['team', 'year'])
    .agg([
        pl.sum('apy').alias('total_apy'),  # Average per year (approximation)
        pl.sum('inflated_apy').alias('total_inflated_apy'),  # Use this for cross-era comparison
        pl.count().alias('num_contracts'),
        pl.sum('guaranteed').alias('total_guaranteed')
    ])
    .sort(['year', 'total_inflated_apy'], descending=True)
)

# Analyze cap efficiency (spending vs performance)
cap_efficiency = (
    team_cap_by_year
    .join(
        team_performance.select(['team', 'season', 'wins', 'made_playoffs']),
        left_on=['team', 'year'],
        right_on=['team', 'season'],
        how='left'
    )
    .with_columns([
        # Dollars per win (inflation-adjusted)
        (pl.col('total_inflated_apy') / pl.col('wins')).alias('dollars_per_win')
    ])
    .filter(pl.col('wins') > 0)  # Avoid division by zero
)
```

### 2. GM Spending Patterns

```python
# Analyze how GMs allocate cap space
gm_spending = (
    contracts
    .join(gm_tenures, on='team', how='left')
    .filter(
        (pl.col('year_signed') >= pl.col('start_year')) &
        (pl.col('year_signed') <= pl.col('end_year'))
    )
    .group_by('gm_name')
    .agg([
        pl.count().alias('contracts_signed'),
        pl.mean('inflated_apy').alias('avg_contract_apy'),
        pl.mean('years').alias('avg_contract_length'),
        pl.mean('guaranteed').alias('avg_guaranteed'),
        # Percentage of high-value contracts (>$10M APY)
        (pl.col('apy').filter(pl.col('apy') > 10_000_000).count() / pl.count()).alias('high_value_pct'),
        # Position allocation
        pl.col('position').value_counts().alias('position_spending')
    ])
)
```

---

## Player Career Analysis

### 1. Career Trajectory by Draft Position

```python
# Load player IDs and stats
player_ids = pl.read_csv('data/cached/nflreadpy/player_ids/player_ids_all.csv')
player_stats = pl.read_csv('data/cached/nflreadpy/player_stats/player_stats_all.csv')

# Join draft picks with career stats
player_careers = (
    draft_picks
    .filter(pl.col('season') >= 2012)  # Player stats start 2012
    .join(
        player_ids.select(['pfr_id', 'gsis_id']),
        left_on='pfr_player_id',
        right_on='pfr_id',
        how='left'
    )
    .join(
        player_stats.group_by('player_id').agg([
            pl.n_unique('season').alias('seasons_played'),
            pl.sum('passing_yards').alias('career_pass_yds'),
            pl.sum('rushing_yards').alias('career_rush_yds'),
            pl.sum('receiving_yards').alias('career_rec_yds'),
            pl.sum('passing_tds').alias('career_pass_tds'),
            pl.sum('rushing_tds').alias('career_rush_tds'),
            pl.sum('receiving_tds').alias('career_rec_tds')
        ]),
        left_on='gsis_id',
        right_on='player_id',
        how='left'
    )
)

# Analyze QB success by draft round
qb_draft_analysis = (
    player_careers
    .filter(pl.col('position') == 'QB')
    .group_by('round')
    .agg([
        pl.count().alias('qbs_drafted'),
        pl.mean('career_pass_yds').alias('avg_pass_yds'),
        pl.mean('seasons_played').alias('avg_seasons'),
        (pl.col('career_pass_yds').filter(pl.col('career_pass_yds') > 10000).count() /
         pl.count()).alias('10k_yard_rate')
    ])
    .sort('round')
)
```

### 2. Positional Value Over Time

```python
# Analyze which positions provide best value by draft round
positional_value = (
    draft_picks
    .filter(pl.col('season') >= 2000)
    .group_by(['round', 'position'])
    .agg([
        pl.count().alias('picks'),
        pl.mean('car_av').alias('avg_av'),
        pl.mean('probowls').alias('avg_probowls'),
        (pl.col('car_av').filter(pl.col('car_av') > 30).count() / pl.count()).alias('star_rate')
    ])
    .filter(pl.col('picks') >= 20)  # Minimum sample size
    .sort(['round', 'avg_av'], descending=[False, True])
)

print("Best value positions by round:")
for round_num in range(1, 8):
    print(f"\nRound {round_num}:")
    print(positional_value.filter(pl.col('round') == round_num).head(5))
```

---

## Advanced Play-by-Play Queries

### 1. QB Performance Metrics from PBP

```python
# Load play-by-play
pbp = pl.read_csv('data/cached/nflreadpy/play_by_play/pbp_all.csv')

# Calculate QB efficiency metrics
qb_efficiency = (
    pbp
    .filter(
        (pl.col('season') >= 2020) &
        (pl.col('play_type') == 'pass') &
        (pl.col('passer_id').is_not_null())
    )
    .join(
        player_ids.select(['gsis_id', 'name']),
        left_on='passer_id',
        right_on='gsis_id',
        how='left'
    )
    .group_by(['season', 'passer_id', 'name'])
    .agg([
        pl.count().alias('attempts'),
        pl.col('complete_pass').sum().alias('completions'),
        pl.col('yards_gained').sum().alias('pass_yards'),
        pl.col('touchdown').sum().alias('pass_tds'),
        pl.col('interception').sum().alias('ints'),
        pl.col('epa').mean().alias('epa_per_play'),
        pl.col('cpoe').mean().alias('avg_cpoe'),
        pl.col('air_yards').mean().alias('avg_air_yards'),
        pl.col('yards_after_catch').mean().alias('avg_yac'),
        # Success rate (EPA > 0)
        (pl.col('epa').filter(pl.col('epa') > 0).count() / pl.count()).alias('success_rate')
    ])
    .filter(pl.col('attempts') >= 100)  # Minimum attempts
    .sort('epa_per_play', descending=True)
)

print("Top QBs by EPA/play (2020+):")
print(qb_efficiency.head(20))
```

### 2. Team Offensive Tendencies

```python
# Analyze play-calling by down and distance
play_calling = (
    pbp
    .filter(
        (pl.col('season') == 2024) &
        (pl.col('down').is_in([1, 2, 3])) &
        (pl.col('play_type').is_in(['run', 'pass']))
    )
    .group_by(['posteam', 'down', 'ydstogo'])
    .agg([
        pl.count().alias('plays'),
        (pl.col('play_type').filter(pl.col('play_type') == 'pass').count() / pl.count()).alias('pass_rate'),
        pl.col('epa').mean().alias('avg_epa')
    ])
)

# Identify most pass-heavy teams on 1st down
first_down_tendencies = (
    play_calling
    .filter((pl.col('down') == 1) & (pl.col('ydstogo') == 10))
    .sort('pass_rate', descending=True)
)

print("Most pass-heavy teams on 1st & 10 (2024):")
print(first_down_tendencies.head(10))
```

### 3. Red Zone Efficiency

```python
# Analyze red zone performance
red_zone_efficiency = (
    pbp
    .filter(
        (pl.col('season') >= 2022) &
        (pl.col('yardline_100') <= 20) &
        (pl.col('yardline_100') > 0) &
        (pl.col('play_type').is_in(['run', 'pass']))
    )
    .group_by('posteam')
    .agg([
        pl.count().alias('red_zone_plays'),
        pl.col('touchdown').sum().alias('red_zone_tds'),
        (pl.col('touchdown').sum() / pl.n_unique('drive')).alias('td_per_drive'),
        pl.col('epa').mean().alias('avg_epa'),
        # Pass vs run split
        (pl.col('play_type').filter(pl.col('play_type') == 'pass').count() / pl.count()).alias('rz_pass_rate')
    ])
    .sort('td_per_drive', descending=True)
)
```

---

## Common Pitfalls & Solutions

### Pitfall 1: Incorrect Win Calculation

**WRONG:**
```python
# Don't use home_score > away_score without considering team perspective
wins = schedules.filter(pl.col('home_score') > pl.col('away_score'))
```

**RIGHT:**
```python
# Use result column and team perspective
home_wins = schedules.filter(pl.col('result') > 0).select([pl.col('home_team').alias('winner')])
away_wins = schedules.filter(pl.col('result') < 0).select([pl.col('away_team').alias('winner')])
all_wins = pl.concat([home_wins, away_wins])
```

### Pitfall 2: Missing Player ID Crosswalk

**WRONG:**
```python
# Direct join without ID mapping
draft_picks.join(player_stats, left_on='pfr_player_id', right_on='player_id')  # Won't work!
```

**RIGHT:**
```python
# Use player_ids as crosswalk
draft_picks.join(
    player_ids, left_on='pfr_player_id', right_on='pfr_id'
).join(
    player_stats, on='gsis_id'
)
```

### Pitfall 3: Not Using Inflation-Adjusted Contract Values

**WRONG:**
```python
# Comparing raw contract values across eras
contract_analysis = contracts.group_by('season').agg(pl.mean('value'))
```

**RIGHT:**
```python
# Use inflated values for cross-era comparison
contract_analysis = contracts.group_by('season').agg(pl.mean('inflated_value'))
```

### Pitfall 4: Ignoring NULL Handling in Performance Metrics

**WRONG:**
```python
# Assuming all drafted players have car_av
draft_success = draft_picks.filter(pl.col('car_av') > 20)  # Excludes busts/non-players
```

**RIGHT:**
```python
# Explicitly handle NULLs (fill with 0 for busts)
draft_success = draft_picks.with_columns(
    pl.col('car_av').fill_null(0).alias('car_av')
).filter(pl.col('car_av') > 20)
```

---

## Performance Optimization Tips

### 1. Filter Early
```python
# GOOD: Filter before joins
pbp_2024 = pbp.filter(pl.col('season') == 2024)
pbp_2024.join(player_ids, ...)

# BAD: Filter after joins
pbp.join(player_ids, ...).filter(pl.col('season') == 2024)
```

### 2. Select Only Needed Columns
```python
# GOOD: Select specific columns
schedules.select(['season', 'home_team', 'away_team', 'result'])

# BAD: Keep all columns unnecessarily
schedules  # 45+ columns loaded into memory
```

### 3. Use Lazy Evaluation When Possible
```python
# For very large datasets, use lazy API
pbp_lazy = pl.scan_csv('data/cached/nflreadpy/play_by_play/pbp_all.csv')
result = pbp_lazy.filter(...).group_by(...).agg(...).collect()  # Execute only once
```

---

## Next Steps

After running these analyses, consider:

1. **Validation**: Cross-check results with public sources (PFR, ESPN)
2. **Visualization**: Create charts/dashboards for insights
3. **Documentation**: Save findings to project documentation
4. **Automation**: Convert one-off queries to reusable functions
5. **Testing**: Add unit tests for critical calculations

---

**For more information:**
- See `nfl_data_architecture.md` for schema details
- Check nflreadpy documentation: https://github.com/nflverse/nflreadpy
- Pro Football Reference: https://www.pro-football-reference.com/
