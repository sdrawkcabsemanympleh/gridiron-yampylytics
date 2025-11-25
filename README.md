# gridiron-yampylytics

NFL analytics toolkit with GM performance analysis, athletic scoring (YAS), and comprehensive NFL data from 1999-2025.

## Why Does This Exist?

Let's get this out of the way right off the bat.  nflreadpy and other sources already exist, so why use this?  The goal is to take off sharp edges and provide a comprehensive toolkit for playing around with NFL data--to make this as easy as possible to get started.  The idea is to make a simple tool that will pull the data you want and save them locally for you to explore with whatever tooling you want.  It provides a nice SQL exploration tool to help.  It has some useful queries stored.  Maybe some visualization, too.  That means you can do what you like how you like.  Want to use Pandas?  Cool, we've got `nflreadpy` here.  Love SQL?  Got you some CSV's.  

With it, there's effort to try to take off sharp edges, like the wide array of various ID's that may or may not exist for any given player.  On that, I decided to add another ID (yamplayer_id)--though I was reticent to throw another into the ring.  However, the goal is to utilize the others, hash them, and create a unique ID which you can reliably join on without having to worry about it.  It is injected into every data table.

For datasets of reasonable size, which take a long time to gather, or are static, I've tried to include here without having to gather them yourself.  I can't guarantee they're up to date, though, so please make sure to check them for the most recent data if they're included and not static.

### YAS Data? 
Originally, I'd planned to include RAS data, but the links to download it directly are broken, and I didn't want to scrape it when most of the combine data used is available through `nflreadpy`.  It does mean that it misses two of the drills of the ten.  Rather than try to find less reliable data sources or scraping RAS, I decided to compute it without those two, but add some other tweaks.  

Firstly, I only use combine data.  That's primarily because it's more difficult to source Pro-day data and be confident that source will continue to be available.  But there's also a justification in methodology.  As recognized by RAS, there's a clear trend where the Pro-Day performance tends not to align with Combine data.  Given that players consistently perform differently (I believe better in the Pro-Day), it is not an exact 1:1 replacement.  RAS's methodology is that it is considered close enough.  With YAS, I've made the decision (at least so far) to use only Combine data for the calculations.  The criteria that only two may be missing is still there, so potentially this could mean fewer players have full data.  However, I compute it even if that's missing but flag it as partial.

There's a quirk about RAS data; it isn't recomputed every year.  The idea is that it ranks players by their percentile for their position, but if it isn't refreshed yearly with every new class, the meaning of the metric changes.  It is not a measure of a player's athletic score given all known players in draft classes before _and_ after, but only with respect to the players who have come before them.  So, I have two versions.  One is calculated like RAS, named historical, which calculates based on the players who have gone through the combine at the time that player does their testing.  The other calculates their score based on every player, regardless of whether they came before.  So, all of that is to say that YAS should ideally follow RAS and is heavily inspired by it, but is not exactly the same.

On depth charts, you'll notice there's a legacy and modern.  The schema in `nflreadpy` changed after the 2024 year for some reason, and is now completely different.  I have them as different datasets.  I may attempt to reconcilethem at some point, but at time of writing, have not.  It might be worth double checking whether I did since writing this, since it's easy to forget updating a readme.


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
If you are using Windows, you may run into a time zone formatting issue.  If you do, you will need to add `--no-download-tzdata` onto the end of the command.  This shouldn't cause issues given the data included.  Full command:
```bash
uv run harlequin gridiron_yampylytics.db --no-download-tzdata
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
