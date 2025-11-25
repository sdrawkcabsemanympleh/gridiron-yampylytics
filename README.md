# gridiron-yampylytics

NFL analytics toolkit with GM performance analysis, athletic scoring (YAS), and comprehensive NFL data from 1999-2025.

## Quick Start

**1. Install dependencies:**
```bash
uv sync
```
This installs all required packages including `nflreadpy`, `pandas`, `harlequin`, and `duckdb`.

**2. Load all NFL data:**
```bash
uv run python -m scripts.load_all_data
```
Downloads ~3M+ rows of NFL data:
- nflreadpy datasets (play-by-play, player stats, rosters, combine, etc.)
- GM/executive data for all 32 teams (1960-2025)

Runtime: ~10-15 minutes

**3. Process and transform data:**
```bash
# Clean depth charts (fixes schema changes between 2024/2025)
uv run python -m scripts.clean_depth_charts

# Combine GM data into single table
uv run python -m scripts.combine_gm_data

# Calculate Yampy Athletic Scores (YAS) from combine data
uv run python -m scripts.calculate_yas
```

**4. Explore data with SQL:**
```bash
# Create DuckDB database
uv run python -m scripts.create_duckdb

# Launch interactive SQL explorer (Harlequin)
uv run harlequin gridiron_yampylytics.db
```

## Development

**Run tests:**
```bash
uv run pytest
```

**Check code style:**
```bash
uv run ruff check .
uv run mypy src/
```

**Format code:**
```bash
uv run ruff format .
```

## Data Overview

After running the setup scripts, you'll have access to:

**NFL Data (via nflreadpy):**
- Play-by-play: 1.25M rows (1999-2025)
- Player stats: 465K rows (2012-2025)
- Rosters: 139K rows (2006-2025)
- Combine results: 8.6K players (2000-2025)
- Draft picks, contracts, injuries, depth charts, schedules

**Custom Datasets:**
- GM tenures: 369 records (32 teams, 1960-2025)
- Yampy Athletic Scores (YAS): Calculated from combine data with position-specific normalization

## SQL Schemas

Data is organized into clean DuckDB schemas:

```sql
-- NFL data from nflverse
SELECT * FROM nflverse.pbp;
SELECT * FROM nflverse.player_stats;
SELECT * FROM nflverse.combine;

-- Reference data
SELECT * FROM reference.gm_tenures;
SELECT * FROM reference.draft_values_jimmy_johnson;

-- Athletic scores
SELECT * FROM yas.yas_2025;           -- All-years normalization
SELECT * FROM yas.yas_historical;     -- Prior-years-only normalization
```

## Project Structure

```
gridiron-yampylytics/
├── data/
│   ├── nflverse/          # Cached NFL data (gitignored)
│   ├── reference/         # Reference tables (draft values, GM tenures)
│   ├── yas/               # Yampy Athletic Scores (gitignored)
│   └── raw/               # Raw scraped data (gitignored)
├── scripts/               # Data acquisition and processing
├── src/
│   └── gridiron_yampylytics/  # Main package code
└── tests/                 # Test files
```

## Key Scripts

**Data Acquisition:**
- `load_all_data.py` - Download all data sources (one command to rule them all)
- `cache_nflreadpy_data.py` - Cache nflreadpy datasets locally
- `download_gm_data.py` - Scrape GM/executive data from Pro Football Reference

**Data Processing:**
- `combine_gm_data.py` - Merge 32 team GM files into single table
- `clean_depth_charts.py` - Fix depth chart schema changes and newline issues
- `calculate_yas.py` - Calculate Yampy Athletic Scores from combine data

**Database:**
- `create_duckdb.py` - Generate DuckDB database with clean schemas
