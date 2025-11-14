# NFL Data Architecture - gridiron-yampylytics

**Last Updated:** 2025-11-14
**Status:** Production-ready after major cleanup

## Executive Summary

This project uses **fully reproducible** NFL data sources covering the **modern era (1999-2025)** with comprehensive play-by-play, player stats, team performance, draft history, and executive tenure data. All data can be regenerated from source via two scripts.

**Total storage:** ~46 CSV/Parquet files
**Data sources:** nflreadpy (10 datasets) + PFR GM scraper (32 teams) + draft value charts (4 reference files)
**Coverage:** Modern salary cap era focus (1999-2025 for PBP, 2012-2025 for player stats, 1960-2025 for GMs)

---

## Data Sources

### 1. nflreadpy (nflverse) - PRIMARY SOURCE

**Script:** `C:\Users\shays\code\gridiron-yampylytics\scripts\cache_nflreadpy_data.py`
**Cache location:** `data/cached/nflreadpy/`
**Datasets:** 10 total

#### 1.1 Play-by-Play (1999-2025)
- **File:** `play_by_play/pbp_all.csv`
- **Coverage:** 26 seasons (1999-2025)
- **Granularity:** Every play in every game
- **Key fields:**
  - Game identifiers: `game_id`, `old_game_id`
  - Play context: `posteam`, `defteam`, `down`, `ydstogo`, `yardline_100`
  - Results: `yards_gained`, `touchdown`, `interception`, `fumble`
  - Advanced metrics: `epa`, `wpa`, `cpoe`, `air_yards`, `yac`
  - Player IDs: `passer_id`, `rusher_id`, `receiver_id` (gsis_id format)
- **Known quirks:**
  - NULL `yards_gained` on penalties (expected)
  - NULL advanced metrics on kneel-downs, end-of-half
  - `overtime` column indicates OT games (0/1)

#### 1.2 Player Stats (2012-2025)
- **File:** `player_stats/player_stats_all.csv`
- **Coverage:** 13 seasons (2012-2025)
- **Granularity:** Weekly + seasonal aggregates
- **Key fields:**
  - Identifiers: `player_id` (gsis_id), `player_name`, `position`, `team`
  - Passing: `completions`, `attempts`, `passing_yards`, `passing_tds`, `interceptions`
  - Rushing: `carries`, `rushing_yards`, `rushing_tds`
  - Receiving: `receptions`, `targets`, `receiving_yards`, `receiving_tds`
  - Fantasy: `fantasy_points`, `fantasy_points_ppr`
- **Usage:** Aggregated player performance by week/season

#### 1.3 Rosters (2006-2025)
- **File:** `rosters/rosters_all.csv`
- **Coverage:** 19 seasons (2006-2025)
- **Granularity:** Weekly rosters (active players per team per week)
- **Key fields:**
  - Identifiers: `gsis_id`, `player_name`, `position`, `team`, `season`, `week`
  - Bio: `birth_date`, `height`, `weight`, `college`, `years_exp`
  - Draft: `draft_year`, `draft_round`, `draft_pick`
  - Status: `status` (active, injured reserve, practice squad)
- **Usage:** Player tenure analysis, positional depth

#### 1.4 Schedules (1999-2025)
- **File:** `schedules/schedules_all.csv`
- **Coverage:** 26 seasons (1999-2025)
- **Granularity:** Every game (regular season + playoffs)
- **Key fields:**
  - Game ID: `game_id`, `old_game_id`, `pfr`, `espn`
  - Teams: `home_team`, `away_team`
  - Results: `home_score`, `away_score`, `result` (point differential from home perspective)
  - Context: `season`, `week`, `game_type` ('REG', 'WC', 'DIV', 'CON', 'SB')
  - **Coaches:** `home_coach`, `away_coach` (string names)
  - Stadium: `stadium`, `roof`, `surface`, `temp`, `wind`
  - Betting: `spread_line`, `total_line`, `home_moneyline`, `away_moneyline`
- **Critical for:**
  - Team performance (wins/losses)
  - Coach tenure extraction
  - Playoff appearances
  - Home/away splits

#### 1.5 Draft Picks (1967-2025)
- **File:** `draft_picks/draft_picks_all.csv`
- **Coverage:** 58+ drafts (1967-2025)
- **Granularity:** Every pick
- **Key fields:**
  - Pick info: `season`, `round`, `pick`, `team`
  - Player IDs: `gsis_id`, `pfr_player_id`, `cfb_player_id`
  - Bio: `pfr_player_name`, `position`, `college`, `age`
  - Performance metrics:
    - `allpro` - All-Pro selections count
    - `probowls` - Pro Bowl selections count
    - `w_av` - Weighted Approximate Value
    - `car_av` - Career Approximate Value
    - `dr_av` - Draft-relative Approximate Value
  - Career stats: `games`, `seasons_started`, `pass_yards`, `rush_yards`, `rec_yards`, etc.
- **Data quality notes:**
  - Performance metrics NULL for players who never played (busts)
  - Pre-2000 data has limited stat coverage
  - HOF designation has lag time (recent retirees not yet eligible)
- **Usage:** Draft efficiency analysis, GM draft success rates

#### 1.6 Combine (2000-2024)
- **File:** `combine/combine_all.csv`
- **Coverage:** 24+ years (2000-2024)
- **Granularity:** Players invited to NFL Combine
- **Key fields:**
  - Identifiers: `pfr_id`, `player_name`, `pos`, `school`
  - Measurements: `ht`, `wt`, `40yd`, `vertical`, `bench`, `broad_jump`, `3cone`, `shuttle`
  - Draft: `draft_year`, `draft_round`, `draft_pick`, `draft_team`
- **Usage:** Pre-draft evaluation, athleticism vs performance correlation

#### 1.7 Contracts (2000s-2025)
- **File:** `contracts/contracts_all.parquet` (Parquet format - nested data)
- **Coverage:** 48,632 contracts (comprehensive post-2010, spotty pre-2010)
- **Granularity:** Individual player contracts
- **Key fields:**
  - Player: `player`, `position`, `team`, `gsis_id`
  - Contract: `year_signed`, `years`, `value`, `apy`, `guaranteed`
  - Cap impact: `apy_cap_pct`
  - **Inflation-adjusted:** `inflated_value`, `inflated_apy`, `inflated_guaranteed` (USE THESE for cross-era analysis)
  - **Nested:** `cols` column contains year-by-year breakdown
- **Data quality notes:**
  - Pre-2010 incomplete (public reporting limited)
  - Missing some restructures/dead money details
- **Usage:** Salary cap management, spending efficiency, contract structure analysis
- **Schema:** 25 columns, 48,632 rows

#### 1.8 Player IDs (Cross-platform mapping)
- **File:** `player_ids/player_ids_all.csv`
- **Coverage:** 17,031+ players
- **Granularity:** Player-level crosswalk table
- **Key fields:**
  - **Primary IDs:** `gsis_id` (NFL official), `pfr_id` (Pro Football Reference)
  - **Fantasy platforms:** `sleeper_id`, `espn_id`, `yahoo_id`, `fantasypros_id`, `mfl_id`
  - **Other:** `sportradar_id`, `pff_id`, `stats_id`, `rotowire_id`
  - Bio: `name`, `merge_name`, `position`, `team`, `birthdate`, `age`
  - Draft: `draft_year`, `draft_round`, `draft_pick`, `draft_ovr`
- **CRITICAL:** Use this as universal crosswalk for joining datasets with different ID schemes
- **Usage:** Join draft_picks (pfr_id) to player_stats (gsis_id) via this table

#### 1.9 Injuries (2009-2025)
- **File:** `injuries/injuries_all.csv`
- **Coverage:** Auto-detected available years (script walks forward from 2009)
- **Granularity:** Weekly injury reports
- **Key fields:**
  - Identifiers: `gsis_id`, `player_name`, `position`, `team`
  - Status: `report_primary_injury`, `report_secondary_injury`, `report_status`
  - Timing: `season`, `week`
- **Usage:** Injury impact analysis, availability trends

#### 1.10 Depth Charts (2017-2025)
- **File:** `depth_charts/depth_charts_all.csv`
- **Coverage:** 8 seasons (2017-2025)
- **Granularity:** Weekly team depth charts
- **Key fields:**
  - Identifiers: `gsis_id`, `player_name`, `position`, `team`
  - Depth: `depth_position`, `formation` (e.g., "LWR", "RB", "LILB")
  - Timing: `season`, `week`
- **Usage:** Playing time prediction, positional competition

---

### 2. GM Executives Data (Pro Football Reference)

**Script:** `C:\Users\shays\code\gridiron-yampylytics\scripts\download_gm_data.py`
**Data location:** `data/raw/executives/`
**Files:** 32 team-specific CSVs (e.g., `nwe_executives.csv`)

#### Schema
- **Person:** Executive name (string)
- **Teams:** Team name(s) - may list multiple if moved between teams
- **From:** Start year (integer)
- **To:** End year (integer or empty string for current)
- **Titles:** Role/title (string - various formats)
- **Notes:** Additional context (string)

#### Coverage
- **Historical range:** 1960-2025 (65+ years)
- **Teams:** All 32 current NFL teams
- **Format:** PFR team codes (nwe, dal, kan, etc.)

#### Data Quality Concerns
1. **Title variations:** "General Manager" vs "Vice President of Football Operations" vs "President"
   - **Recommendation:** Filter on titles containing "General Manager" or flag for manual review
2. **Team code mapping needed:** PFR uses 'nwe', nflverse uses 'NE'
   - **TODO:** Create mapping table at `data/reference/team_code_mapping.csv`
3. **Tenure gaps:** Some teams have years with no listed GM
4. **Overlapping roles:** Multiple executives may be listed for same period

#### Usage
- GM tenure analysis (who ran team when)
- Correlate GM tenures with team performance (from schedules)
- Calculate GM draft success (from draft_picks)
- Analyze coaching stability under specific GMs

---

### 3. Draft Value Charts (Reference Data)

**Location:** `data/reference/draft_value_charts/`
**Files:** 4 industry-standard value charts

#### 3.1 Jimmy Johnson Draft Values (1991)
- **File:** `jimmy_johnson_draft_values.csv`
- **Coverage:** Picks 1-224 (7 rounds)
- **Context:** Classic trade value chart, used by NFL teams 1990s-2000s
- **Best for:** Historical draft trade analysis (1999-2011)
- **Formula:** Exponential decay from pick 1 (3000 points)

#### 3.2 Rich Hill Draft Values (2014)
- **File:** `rich_hill_draft_values.csv`
- **Coverage:** Picks 1-256 (7 rounds)
- **Context:** Modern analytics, accounts for rookie wage scale (2011 CBA)
- **Best for:** Post-2011 draft analysis (rookie contracts capped)
- **Formula:** Based on surplus value of rookie contracts

#### 3.3 Fitzgerald-Spielberger Draft Values (2016)
- **File:** `fitzgerald_spielberger_draft_values.csv`
- **Coverage:** Picks 1-256 (7 rounds)
- **Context:** Academic research, based on expected career AV
- **Best for:** Performance expectation baselines
- **Formula:** Regression on historical AV by pick

#### 3.4 Harvard Draft Values (2013)
- **File:** `harvard_draft_values.csv`
- **Coverage:** Picks 1-256 (7 rounds)
- **Context:** Sabermetric approach, based on starter probability
- **Best for:** Risk-adjusted draft strategy
- **Formula:** Expected probability of becoming quality starter

#### Usage Strategy
```python
# Modern era (2012+)
draft_efficiency = draft_picks.join(
    rich_hill_values,  # Accounts for rookie wage scale
    on='pick'
).with_columns(
    surplus_value = car_av - expected_av
)

# Historical (1999-2011)
trade_value = draft_picks.join(
    jimmy_johnson_values,  # Industry standard
    on='pick'
)
```

---

## Data Flow & Scripts

### Reproducibility Architecture

All data can be regenerated from source:

```
scripts/load_all_data.py (unified loader)
├── scripts/cache_nflreadpy_data.py --all
│   └── Downloads 10 nflreadpy datasets → data/cached/nflreadpy/
└── scripts/download_gm_data.py
    └── Scrapes PFR for 32 teams → data/raw/executives/
```

**Runtime:** ~10-15 minutes total
**Dependencies:** uv, nflreadpy, selenium, pandas

---

## Player ID Strategy (CRITICAL)

### Primary Key Recommendation

**Use `gsis_id` as primary identifier for all analysis**

**Why gsis_id:**
- NFL official GameDay ID
- Used in: play_by_play (passer_id, rusher_id, receiver_id), player_stats, rosters, contracts
- Most comprehensive coverage for modern era (2000+)

**Fallback strategy:**
- Use `pfr_id` for historical players (pre-2000) or when gsis_id missing
- Use `player_ids_all.csv` as universal crosswalk

### Join Pattern Example

```python
# Joining datasets with different ID schemes
draft_analysis = (
    draft_picks
    .join(
        player_ids,
        left_on='pfr_player_id',  # Draft uses PFR format
        right_on='pfr_id',
        how='left'
    )
    .join(
        player_stats,
        on='gsis_id',  # Now linked via crosswalk
        how='left'
    )
)
```

### ID Coverage by Dataset

| Dataset | Primary ID | Secondary IDs |
|---------|-----------|---------------|
| play_by_play | gsis_id (passer_id, rusher_id, receiver_id) | - |
| player_stats | player_id (gsis_id) | - |
| rosters | gsis_id | - |
| draft_picks | pfr_player_id | gsis_id, cfb_player_id |
| contracts | gsis_id | - |
| combine | pfr_id | - |
| player_ids | gsis_id, pfr_id | 15+ platform IDs |

---

## Team Code Standardization

### Issue
Different data sources use different team abbreviation schemes:

- **nflreadpy (nflverse):** NE, DAL, KC, etc. (standard 2-3 letter)
- **PFR (GM executives):** nwe, dal, kan, etc. (lowercase 3 letter)

### Solution Required

**Create mapping table:** `data/reference/team_code_mapping.csv`

```csv
pfr_code,nflverse_code,team_name,conference,division
nwe,NE,New England Patriots,AFC,East
dal,DAL,Dallas Cowboys,NFC,East
kan,KC,Kansas City Chiefs,AFC,West
...
```

### Known Mappings
- nwe → NE (Patriots)
- dal → DAL (Cowboys)
- kan → KC (Chiefs)
- sdg → LAC (Chargers - relocated)
- ram → LA (Rams - relocated)
- rai → LV (Raiders - relocated)
- crd → ARI (Cardinals)
- rav → BAL (Ravens)
- clt → IND (Colts)
- gnb → GB (Packers)
- htx → HOU (Texans)
- nor → NO (Saints)
- nwe → NE (Patriots)
- nyg → NYG (Giants)
- nyj → NYJ (Jets)
- oti → TEN (Titans)
- sfo → SF (49ers)
- tam → TB (Buccaneers)

---

## Data Quality Testing Checklist

### Automated Validation (TODO: Create script)

1. **NULL patterns**
   - ✓ Expected: yards_gained NULL on penalties
   - ✓ Expected: passer_id NULL on run plays
   - ✗ Unexpected: gsis_id NULL in player_stats (flag for review)

2. **Date ranges**
   - ✓ No future dates beyond current season
   - ✓ Draft picks season <= current year
   - ✓ GM "To" year <= current year (unless empty/ongoing)

3. **Referential integrity**
   - ✓ All gsis_id in player_stats exist in player_ids
   - ✓ All team codes in schedules match known teams
   - ✓ All game_id references are consistent across datasets

4. **Value ranges**
   - ✓ Scores are positive integers
   - ✓ Draft picks are 1-262 (7 rounds max)
   - ✓ Years are reasonable (1960-2025)

---

## Known Limitations by Dataset

### Play-by-Play (1999-2025)
- **Pre-1999 unavailable:** Would need NFL-Statistics-Scrape repo for 1970-1998
- **Advanced metrics accuracy:** EPA/WPA models may differ from other sources
- **Special teams:** Kick/punt return IDs may have gaps

### Player Stats (2012-2025)
- **Limited historical range:** Only 13 seasons
- **Pre-2012 analysis:** Must use play-by-play aggregations instead

### Draft Picks (1967-2025)
- **Performance metrics:** NULL for players who never played
- **Pre-2000 stats:** Limited stat coverage for old players
- **HOF lag:** Recent retirees not yet eligible for Hall of Fame

### Contracts (2000s-2025)
- **Pre-2010 incomplete:** Public contract reporting was limited
- **Restructures:** May not capture all mid-contract changes
- **Dead money:** Full cap accounting may have gaps

### GM Executives (1960-2025)
- **Title variations:** Must filter/normalize "General Manager" vs other executives
- **Tenure gaps:** Some teams have years without listed GM
- **Team codes:** Require mapping to nflverse format

### Schedules (1999-2025)
- **Coach names:** String-based (no coach IDs) - watch for spelling variations
- **Interim coaches:** Mid-season changes create tenure ambiguity

---

## Recommended Join Patterns

### 1. GM Performance Analysis

```python
# GM tenure with team performance
gm_performance = (
    gm_executives
    .join(team_code_mapping, on='pfr_team_code')
    .join(
        schedules.group_by(['team', 'season']).agg(
            wins = count_where(win_condition),
            playoff_games = count_where(game_type != 'REG')
        ),
        on=['nflverse_code', 'season_in_tenure_range']
    )
)
```

### 2. Draft Efficiency by GM

```python
# GM draft success rates
gm_draft_success = (
    draft_picks
    .join(player_ids, left_on='pfr_player_id', right_on='pfr_id')
    .join(
        gm_executives,
        on=['team', 'draft_year_in_tenure']
    )
    .with_columns(
        draft_value = rich_hill_value,
        actual_value = car_av,
        surplus_value = car_av - expected_av
    )
    .group_by('gm_name').agg(
        avg_surplus = mean('surplus_value'),
        hit_rate = count_where(car_av > threshold)
    )
)
```

### 3. Salary Cap Efficiency

```python
# Cap spending vs team success
cap_efficiency = (
    contracts.explode('cols')  # Expand year-by-year
    .group_by(['team', 'year']).agg(
        total_cap = sum('cap_hit'),
        star_spending = sum_where(top_10_player)
    )
    .join(
        team_performance,
        on=['team', 'year']
    )
)
```

### 4. Coach Tenure Extraction

```python
# Extract coach tenures from schedules
coach_tenures = (
    schedules
    .select(['season', 'week', 'home_team', 'home_coach'])
    .union(schedules.select(['season', 'week', 'away_team', 'away_coach']))
    .group_by(['team', 'coach']).agg(
        min_season = min('season'),
        max_season = max('season'),
        games_coached = count()
    )
)
```

---

## Schema Documentation

### High-Priority Documentation (TODO)

1. **Field-level data dictionary** for each dataset
   - Field name, type, description, example values
   - NULL handling expectations
   - Valid value ranges

2. **Calculated metrics guide**
   - How to calculate wins/losses from schedules
   - EPA vs WPA vs CPOE definitions
   - AV (Approximate Value) interpretation

3. **Historical context notes**
   - Rule changes affecting data (e.g., 2011 rookie wage scale)
   - Data collection improvements over time
   - Known reporting gaps by era

---

## Usage Patterns & Best Practices

### Loading Data

```python
# Load specific dataset
import polars as pl

pbp = pl.read_csv('data/cached/nflreadpy/play_by_play/pbp_all.csv')
schedules = pl.read_csv('data/cached/nflreadpy/schedules/schedules_all.csv')
player_ids = pl.read_csv('data/cached/nflreadpy/player_ids/player_ids_all.csv')

# Load contracts (Parquet)
contracts = pl.read_parquet('data/cached/nflreadpy/contracts/contracts_all.parquet')
```

### Filtering Data

```python
# Modern era only (2000+)
modern_pbp = pbp.filter(pl.col('season') >= 2000)

# Regular season only
reg_season = schedules.filter(pl.col('game_type') == 'REG')

# Specific team
patriots = schedules.filter(
    (pl.col('home_team') == 'NE') | (pl.col('away_team') == 'NE')
)
```

### Joining Across Datasets

```python
# Always use player_ids as crosswalk
draft_with_stats = (
    draft_picks
    .join(player_ids, left_on='pfr_player_id', right_on='pfr_id', how='left')
    .join(player_stats, on='gsis_id', how='left')
)
```

### Calculating Team Performance

```python
# Wins by season
team_wins = (
    schedules
    .filter(pl.col('game_type') == 'REG')
    .with_columns([
        # Home team perspective
        pl.when(pl.col('result') > 0).then(1).otherwise(0).alias('home_win'),
        # Away team perspective
        pl.when(pl.col('result') < 0).then(1).otherwise(0).alias('away_win')
    ])
    # Pivot to team-level (combine home and away games)
    .group_by(['home_team', 'season']).agg(
        wins = pl.sum('home_win')
    )
)
```

---

## Future Enhancements

### Potentially Useful (Not Critical)

1. **Trade data** - Track picks/players exchanged
   - No comprehensive source available
   - Partial reconstruction from draft picks (drafted by Team A, roster shows Team B)

2. **Pro Bowl / All-Pro selections** - Already in draft_picks dataset (allpro, probowls columns)
   - Consider extracting to separate reference table for non-draftees

3. **Team salary cap space** - Annual cap room available
   - Would require OverTheCap.com scraping
   - Current contracts data shows spending, not cap space

4. **Advanced defensive metrics** - Coverage stats, pressure rates
   - Available in PFF (subscription required)
   - Partial reconstruction from play-by-play possible

5. **Weather data** - Game-day conditions
   - Partially in schedules (temp, wind for some games)
   - More comprehensive weather API integration possible

---

## Change Log

### 2025-11-14: Major Data Cleanup
**Deleted (559 MB non-reproducible cached data):**
- cached_nfl_stats (209 MB) - Redundant with nflreadpy
- cached_nfl_scraper (256 MB) - Redundant with nflreadpy (inferior coverage)
- cached_historical_stats (94 MB) - Pre-2000 data, out of scope for modern-era focus

**Kept (fully reproducible):**
- nflreadpy (10 datasets via cache_nflreadpy_data.py)
- GM executives (32 teams via download_gm_data.py)
- Draft value charts (4 reference files in git)

**Created:**
- scripts/load_all_data.py - Unified data loader

**Rationale:**
- Modern-era focus (2000+) for GM analysis
- Reproducibility > cached convenience
- nflreadpy provides superior coverage (1999-2025) vs NFL-Scraper (2017-2025)

---

## Quick Reference

### Coverage Summary
| Dataset | Coverage | Granularity | Primary Use |
|---------|----------|-------------|-------------|
| Play-by-play | 1999-2025 | Every play | Advanced analytics, custom metrics |
| Player stats | 2012-2025 | Weekly/seasonal | Aggregated player performance |
| Rosters | 2006-2025 | Weekly | Tenure, depth analysis |
| Schedules | 1999-2025 | Every game | Team performance, coach tenure |
| Draft picks | 1967-2025 | Every pick | Draft efficiency, GM success |
| Combine | 2000-2024 | Invited players | Pre-draft evaluation |
| Contracts | 2000s-2025 | Individual contracts | Salary cap management |
| Player IDs | All | Player-level | Cross-platform linking |
| Injuries | 2009-2025 | Weekly | Availability analysis |
| Depth charts | 2017-2025 | Weekly | Playing time prediction |
| GM executives | 1960-2025 | Tenure-level | Executive performance |
| Draft values | N/A (reference) | Pick-level | Trade value, efficiency |

### Key File Paths
```
C:\Users\shays\code\gridiron-yampylytics\
├── data\
│   ├── cached\nflreadpy\
│   │   ├── play_by_play\pbp_all.csv
│   │   ├── player_stats\player_stats_all.csv
│   │   ├── rosters\rosters_all.csv
│   │   ├── schedules\schedules_all.csv
│   │   ├── draft_picks\draft_picks_all.csv
│   │   ├── combine\combine_all.csv
│   │   ├── contracts\contracts_all.parquet
│   │   ├── player_ids\player_ids_all.csv
│   │   ├── injuries\injuries_all.csv
│   │   └── depth_charts\depth_charts_all.csv
│   ├── raw\executives\
│   │   └── [team]_executives.csv (32 files)
│   └── reference\draft_value_charts\
│       ├── jimmy_johnson_draft_values.csv
│       ├── rich_hill_draft_values.csv
│       ├── fitzgerald_spielberger_draft_values.csv
│       └── harvard_draft_values.csv
└── scripts\
    ├── load_all_data.py
    ├── cache_nflreadpy_data.py
    └── download_gm_data.py
```

### Common Questions

**Q: Which player ID should I use?**
A: Use `gsis_id` as primary. Use `player_ids_all.csv` to map between ID schemes.

**Q: How do I calculate team wins?**
A: Use schedules dataset, filter game_type='REG', check `result` column (>0 = home win, <0 = away win).

**Q: Where is coach data?**
A: In schedules dataset: `home_coach` and `away_coach` fields (string names, no IDs).

**Q: How do I handle inflation for contract comparisons?**
A: Use `inflated_value`, `inflated_apy`, `inflated_guaranteed` fields in contracts dataset.

**Q: Which draft value chart should I use?**
A: Rich Hill for post-2011 (rookie wage scale), Jimmy Johnson for 1999-2011.

**Q: How do I link draft picks to player stats?**
A: Join draft_picks → player_ids (on pfr_player_id = pfr_id) → player_stats (on gsis_id).

**Q: What if I need pre-1999 data?**
A: NFL-Statistics-Scrape repo covers 1970-2016 (documented but not implemented).

**Q: How do I standardize PFR team codes to nflverse?**
A: Create mapping table at `data/reference/team_code_mapping.csv` (TODO).

---

## Contact & Maintenance

**Data architecture owner:** NFL Data Expert Agent
**Last validated:** 2025-11-14
**Next review:** When adding new data sources or encountering data quality issues

**For questions about:**
- Data schemas → Check this document first
- Missing data → Verify coverage ranges above
- Data quality → Review "Known Limitations" section
- New data needs → Consult "Future Enhancements" section
