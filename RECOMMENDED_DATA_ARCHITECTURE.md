# Recommended Data Architecture for gridiron-yampylytics

## Architecture Diagram

```
gridiron-yampylytics/
│
├── Data Acquisition Layer
│   ├── [PRIMARY] nflreadpy (package dependency)
│   │   ├── load_pbp() -> Play-by-play data
│   │   ├── load_player_stats() -> Player statistics
│   │   ├── load_schedules() -> Game schedules
│   │   ├── load_rosters() -> Team rosters
│   │   ├── load_draft_picks() -> Draft data
│   │   ├── load_combine() -> Combine results
│   │   └── 15+ more load functions...
│   │
│   └── [SECONDARY] Direct downloads
│       └── nfldata reference files (teams, logos, colors)
│
├── Cached Data Layer (src/cached_data/)
│   ├── [PRIMARY] NFL Stats 2012-2024/ (209 MB)
│   │   ├── weekly_player_stats_offense.csv (101 MB)
│   │   ├── weekly_player_stats_defense.csv (63 MB)
│   │   ├── yearly_player_stats_offense.csv (27 MB)
│   │   ├── yearly_player_stats_defense.csv (13 MB)
│   │   └── team stats files (6 MB)
│   │
│   ├── [BACKUP] NFL_Scraper/ (256 MB)
│   │   └── Play-by-play 2017-2025 (current through Week 7)
│   │
│   ├── [HISTORICAL] nfl-draft-data/ (17 MB)
│   │   └── Draft prospects 1967-2021
│   │
│   └── [REFERENCE] nfldata-extract/ (10 MB) [TO CREATE]
│       ├── draft_picks.csv
│       ├── games.csv
│       ├── teams.csv
│       └── reference files
│
└── Data Processing Layer
    ├── data_loader.py [TO CREATE]
    │   ├── load_player_stats() -> Unified interface
    │   ├── load_draft_data() -> Combines multiple sources
    │   └── fetch_current_season() -> Uses nflreadpy
    │
    ├── player_id_mapper.py [TO CREATE]
    │   └── Map between nflverse, PFR, ESPN IDs
    │
    └── data_updater.py [TO CREATE]
        └── Refresh data from nflreadpy
```

## Data Flow

### Primary Use Cases

#### 1. Historical Player Analysis (2012-2024)
```
NFL Stats 2012-2024 cache
    ↓
Load weekly_player_stats_offense.csv
    ↓
Filter by player_id or position
    ↓
Analysis & visualization
```

#### 2. Current Season Analysis (2025)
```
nflreadpy.load_player_stats([2025])
    ↓
Polars DataFrame
    ↓
Combine with historical cache
    ↓
Analysis & visualization
```

#### 3. Draft Analysis
```
For 1967-2021:
    nfl-draft-data cache
        ↓
    Load nfl_draft_prospects.csv

For 2022-2025:
    nflreadpy.load_draft_picks([2022, 2023, 2024, 2025])
        ↓
    Polars DataFrame

Combine & analyze
```

#### 4. Play-by-Play Analysis
```
For recent (2025 Week 7):
    NFL_Scraper cache
        ↓
    Load 2025_plays.csv

For comprehensive:
    nflreadpy.load_pbp([2020, 2021, 2022, 2023, 2024, 2025])
        ↓
    Polars DataFrame with rich metadata
```

## Implementation Phases

### Phase 1: Setup (Week 1)
**Goal**: Get nflreadpy integrated and verify cached data

```bash
# Install nflreadpy
cd C:/Users/shays/code/gridiron-yampylytics
uv add nflreadpy

# Test basic functionality
uv run python -c "import nflreadpy as nfl; print(nfl.load_schedules([2024]))"

# Extract nfldata reference files
# (Download from GitHub, extract /data directory)
```

**Deliverables**:
- nflreadpy added to pyproject.toml
- Basic test of data loading
- nfldata-extract/ directory created

### Phase 2: Data Validation (Week 1-2)
**Goal**: Ensure cached data quality and compatibility

```python
# Create validation script
import polars as pl

# Test cached data
df_offense = pl.read_csv("cached_data/NFL Stats 2012-2024/weekly_player_stats_offense.csv")
print(f"Rows: {len(df_offense)}, Columns: {len(df_offense.columns)}")
print(f"Seasons: {df_offense['season'].unique().sort()}")
print(f"Player IDs: {df_offense['player_id'].n_unique()}")

# Test nflreadpy data
import nflreadpy as nfl
df_recent = nfl.load_player_stats([2024])
print(f"2024 stats: {len(df_recent)} rows")

# Check schema compatibility
print("Common columns:", set(df_offense.columns) & set(df_recent.columns))
```

**Deliverables**:
- Data validation script
- Schema compatibility report
- Data quality metrics

### Phase 3: Build Data Loading Layer (Week 2-3)
**Goal**: Create unified interface for all data sources

```python
# src/gridiron_yampylytics/data_loader.py

import polars as pl
import nflreadpy as nfl
from pathlib import Path
from typing import List, Optional

class NFLDataLoader:
    """Unified interface for loading NFL data from multiple sources."""

    def __init__(self, cache_dir: Path):
        self.cache_dir = cache_dir
        self.nfldata_extract = cache_dir / "nfldata-extract"
        self.stats_cache = cache_dir / "NFL Stats 2012-2024"

    def load_player_stats(
        self,
        seasons: List[int],
        stat_type: str = "offense",
        frequency: str = "weekly"
    ) -> pl.DataFrame:
        """Load player statistics, combining cache and live data."""

        # Separate cached vs live seasons
        cached_seasons = [s for s in seasons if s <= 2024]
        live_seasons = [s for s in seasons if s > 2024]

        dfs = []

        # Load from cache for 2012-2024
        if cached_seasons:
            cache_file = self.stats_cache / f"{frequency}_player_stats_{stat_type}.csv"
            df_cache = pl.read_csv(cache_file)
            df_cache = df_cache.filter(pl.col("season").is_in(cached_seasons))
            dfs.append(df_cache)

        # Load from nflreadpy for 2025+
        if live_seasons:
            df_live = nfl.load_player_stats(live_seasons)
            # Transform to match cache schema if needed
            dfs.append(df_live)

        # Combine
        return pl.concat(dfs) if dfs else pl.DataFrame()

    def load_draft_picks(self, seasons: List[int]) -> pl.DataFrame:
        """Load draft picks, combining historical cache with recent data."""

        # Historical (1967-2021) from cache
        historical_seasons = [s for s in seasons if s <= 2021]
        recent_seasons = [s for s in seasons if s > 2021]

        dfs = []

        if historical_seasons:
            df_hist = pl.read_csv(self.cache_dir / "nfl-draft-data" / "nfl_draft_prospects.csv")
            df_hist = df_hist.filter(pl.col("year").is_in(historical_seasons))
            dfs.append(df_hist)

        if recent_seasons:
            df_recent = nfl.load_draft_picks(recent_seasons)
            dfs.append(df_recent)

        return pl.concat(dfs) if dfs else pl.DataFrame()

    def load_schedules(self, seasons: List[int]) -> pl.DataFrame:
        """Load game schedules with betting lines."""
        return nfl.load_schedules(seasons)

    def load_reference_data(self, data_type: str) -> pl.DataFrame:
        """Load reference data (teams, logos, etc.) from nfldata extract."""
        file_map = {
            "teams": "teams.csv",
            "logos": "logos.csv",
            "colors": "teamcolors.csv",
            "draft_values": "draft_values.csv",
        }

        if data_type not in file_map:
            raise ValueError(f"Unknown reference data type: {data_type}")

        file_path = self.nfldata_extract / file_map[data_type]
        return pl.read_csv(file_path)
```

**Deliverables**:
- NFLDataLoader class
- Unified data loading interface
- Schema transformation utilities
- Unit tests

### Phase 4: Fill Data Gaps (Week 3-4)
**Goal**: Fetch missing data for 2022-2025

```python
# Update script to fill gaps
import nflreadpy as nfl

# Fetch 2022-2025 drafts
draft_2022_2025 = nfl.load_draft_picks([2022, 2023, 2024, 2025])
draft_2022_2025.write_csv("cached_data/draft_picks_2022_2025.csv")

# Fetch current combine data
combine_recent = nfl.load_combine()
combine_recent.write_csv("cached_data/combine_recent.csv")

# Fetch 2025 player stats (weekly updates)
stats_2025 = nfl.load_player_stats([2025])
stats_2025.write_csv("cached_data/player_stats_2025_current.csv")
```

**Deliverables**:
- 2022-2025 draft data
- Recent combine data
- 2025 current season stats
- Update script for future use

### Phase 5: Player ID Mapping (Week 4)
**Goal**: Create unified player identification system

```python
# src/gridiron_yampylytics/player_id_mapper.py

import polars as pl
from pathlib import Path

class PlayerIDMapper:
    """Map between different player ID systems."""

    def __init__(self, cache_dir: Path):
        self.mapping = self._build_mapping(cache_dir)

    def _build_mapping(self, cache_dir: Path) -> pl.DataFrame:
        """Build comprehensive ID mapping from multiple sources."""

        mappings = []

        # From NFL Stats cache (nflverse player_id)
        stats = pl.read_csv(
            cache_dir / "NFL Stats 2012-2024" / "yearly_player_stats_offense.csv"
        ).select(["player_id", "player_name", "position"])
        mappings.append(stats)

        # From draft data (ESPN IDs)
        draft = pl.read_csv(
            cache_dir / "nfl-draft-data" / "nfl_draft_prospects.csv"
        ).select(["player_id", "guid", "player_name"])
        draft = draft.rename({"player_id": "espn_player_id"})
        mappings.append(draft)

        # From nfldata (PFR IDs)
        draft_pfr = pl.read_csv(
            cache_dir / "nfldata-extract" / "draft_picks.csv"
        ).select(["playerid", "name"])
        draft_pfr = draft_pfr.rename({"playerid": "pfr_id", "name": "player_name"})
        mappings.append(draft_pfr)

        # Join on player name (fuzzy matching would be better)
        # This is simplified - production would need fuzzy matching
        base = mappings[0]
        for df in mappings[1:]:
            base = base.join(df, on="player_name", how="outer")

        return base

    def get_nflverse_id(self, espn_id: str = None, pfr_id: str = None) -> Optional[str]:
        """Convert other ID systems to nflverse player_id."""
        if espn_id:
            result = self.mapping.filter(pl.col("espn_player_id") == espn_id)
        elif pfr_id:
            result = self.mapping.filter(pl.col("pfr_id") == pfr_id)
        else:
            return None

        return result["player_id"][0] if len(result) > 0 else None
```

**Deliverables**:
- PlayerIDMapper class
- ID mapping table
- Fuzzy matching for player names
- Tests for ID conversion

### Phase 6: Automation & Cleanup (Week 5)
**Goal**: Set up automated updates and clean up old repos

```python
# data_updater.py - Weekly update script

import nflreadpy as nfl
from datetime import datetime
from pathlib import Path

def update_current_season(cache_dir: Path):
    """Update current season data weekly."""

    current_season = nfl.get_current_season()
    current_week = nfl.get_current_week()

    print(f"Updating data for {current_season} season, week {current_week}")

    # Update player stats
    stats = nfl.load_player_stats([current_season])
    output_file = cache_dir / f"player_stats_{current_season}_week{current_week}.csv"
    stats.write_csv(output_file)

    # Update schedules
    schedules = nfl.load_schedules([current_season])
    schedules.write_csv(cache_dir / f"schedules_{current_season}.csv")

    # Update rosters
    rosters = nfl.load_rosters([current_season])
    rosters.write_csv(cache_dir / f"rosters_{current_season}.csv")

    print(f"Update complete: {datetime.now()}")

if __name__ == "__main__":
    cache_dir = Path("src/cached_data")
    update_current_season(cache_dir)
```

**Cleanup Tasks**:
1. Archive repositories:
   - historical-nfl-draft-data
   - NFL-Combine-Data
   - NFL-Statistics-Scrape
   - nflscrapy
   - nfl-draft-data (keep cache)
   - NFL_Scraper (keep cache)

2. Create zip backups if needed
3. Delete local clones (save 7.8 GB)
4. Update documentation

**Deliverables**:
- Automated update script
- Cron job / scheduled task setup
- Archived repositories (zipped)
- Final documentation

## Data Quality Checks

### Automated Validation
```python
def validate_data_quality(df: pl.DataFrame, data_type: str) -> dict:
    """Run quality checks on loaded data."""

    checks = {
        "row_count": len(df),
        "null_percentage": df.null_count().sum() / (len(df) * len(df.columns)),
        "duplicate_rows": df.is_duplicated().sum(),
        "date_range": (df["season"].min(), df["season"].max()) if "season" in df.columns else None,
    }

    if data_type == "player_stats":
        checks["unique_players"] = df["player_id"].n_unique()
        checks["positions_covered"] = df["position"].n_unique()

    return checks
```

### Monitoring
- Weekly data freshness check
- Schema consistency validation
- ID mapping coverage metrics
- Data completeness reports

## Benefits of This Architecture

1. **Efficiency**: Use existing cached data (209 MB) for 2012-2024 analysis
2. **Current**: nflreadpy provides up-to-date data for current season
3. **Flexible**: Easy to switch between cached and live data sources
4. **Maintainable**: Single unified interface, minimal custom scraping
5. **Storage-Optimized**: 590 MB vs 8.5 GB (93% reduction)
6. **Professional**: Leverage nflverse's data quality and automation

## Future Enhancements

1. **Add Polars-native operations** throughout pipeline
2. **Implement fuzzy player name matching** for ID mapping
3. **Add data versioning** (track schema changes over time)
4. **Build data lineage tracking** (know source of each data point)
5. **Create data catalog** (searchable inventory of available data)
6. **Add data validation tests** (automated quality checks on updates)

---

**Created:** 2025-10-27
**Status:** Recommended Architecture - Ready for Implementation
