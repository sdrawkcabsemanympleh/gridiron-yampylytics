# gridiron-yampylytics

NFL analytics toolkit with GM performance analysis, athletic scoring (YAS), and comprehensive NFL data from 1999-2025.

## Why Does This Exist?

Let's get this out of the way right off the bat.  nflreadpy and other sources already exist, so why use this?  The goal is to take off sharp edges and provide a toolkit for exploring with NFL data and make it as easy as possible to get started.  Ideally, it is a simple tool that will pull the data you want and save them locally for you to explore with whatever tooling you want.  It provides a nice SQL exploration tool to help.  It has some useful queries stored.  Maybe some visualization, too.  That means you can do what you like how you like.  Want to use Pandas?  Cool, we've got `nflreadpy` here.  Love SQL?  Got you some CSV's.  

For datasets of reasonable size, which take a long time to gather, or are static, I've tried to include here without having to gather them yourself.  I can't guarantee they're up to date, though, so please make sure to check them for the most recent data if they're included and not static.

### Yamplayer ID
As an example of sharp edges, like the wide array of various ID's that may or may not exist for any given player.  On that, I decided to add another ID (yamplayer_id)--though I was reticent to throw another into the ring.  However, the goal is to utilize the others, hash them, and create a unique ID which you can reliably join on without having to worry about it.  It is injected into every data table except for very large ones by default.

### YAS Data? 
This is much like RAS data, and uses the same calculations to generate the data.  However, it's done using the data available here through `nflreadpy`'s combine data.  The numbers differ in a couple ways.  
1.  The data available does omit two of the drills and appears to contain Senior Day data in place of combine data.
2.  RAS is not re-calculated every year to adjust the historical scores.  That means that it is a measure of that player against everyone who came before.  A 40 time that would score a 10 in 2004, would be far lower in 2024.  So, I have two versions.  One is calculated like RAS, named historical, which is calculated using players only of that year and before.  The other calculates their score based on all NFL players in the data, regardless of their draft year.  


### Other Notes
On depth charts, you'll notice there's a legacy and modern.  The schema in `nflreadpy` changed after the 2024 year for some reason, and is now completely different.  I have them as different datasets.  I may attempt to reconcilethem at some point, but at time of writing, have not.  It might be worth double checking whether I did since writing this, since it's easy to forget updating a readme.

Large datasets like Play-by-Play (PBP) are not always included depending on your setup options.  You can check those with `uv run list` and `uv run setup-WHICHEVER`.

## Installation

**New to command-line tools? No worries!** Here's everything you need:

### Prerequisites

**1. Git** - For downloading the project
- **Download:** https://git-scm.com/downloads
- Click through the installer (defaults are fine)
- This also installs "Git Bash" - a good terminal option for Windows

**2. UV** - Python package manager (handles Python installation automatically!)
You can download and install or run a simple terminal command below

- **Download:** https://docs.astral.sh/uv/getting-started/installation/
- **Command Line:**
  - **Windows:** Download the installer or run in PowerShell:
    ```powershell
    powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
    ```
  - **Mac:** Download the installer or run in Terminal:
    ```bash
    curl -LsSf https://astral.sh/uv/install.sh | sh
    ```
  - **Linux:** Run in terminal:
    ```bash
    curl -LsSf https://astral.sh/uv/install.sh | sh
    ```

**That's it!** UV will automatically install Python when you run the project.

### Getting the Code

**Option 1: GitHub Desktop (Easiest for beginners)**
1. Download GitHub Desktop: https://desktop.github.com/
2. Go to the project page on GitHub
3. Click the green **"Code"** button → **"Open with GitHub Desktop"**
4. Choose where to save it on your computer
5. Done! GitHub Desktop handles everything

**Option 2: Command Line**
```bash
# Clone the repository
git clone https://github.com/YOUR-USERNAME/gridiron-yampylytics.git

# Navigate into the folder
cd gridiron-yampylytics
```

### Which Terminal Should I Use?

- **Windows:** PowerShell (built-in) or Git Bash (comes with Git)
- **Mac:** Terminal (built-in)
- **Linux:** Any terminal

## Quick Start

**Get up and running in 3 commands:**

```bash
# 1. Install dependencies
uv sync

# 2. Load and process all NFL data
uv run setup-analysis

# 3. Explore with SQL
uv run sql
```

That's it! You now have as many as ~3M+ rows of NFL data (1999-2025) ready to query depending on setup choice used (quick, analysis, full, yampy)

**Want more control?** Run `uv run list` to see all available commands for:
- Selective loading (specific datasets or seasons)
- Database options (views vs tables, include/exclude large datasets)
- Individual processing steps
- Status checks and more

### Refreshing Data

To update your local data to the latest available, re-run the same setup command you used originally (e.g. `uv run setup-yampy`). The setup commands always use `--all-seasons`, which re-downloads each multi-season dataset as a single combined CSV and overwrites the previous file — so you always get a clean, deduplicated result.

**Important: `--seasons <year>` vs `--all-seasons`**

When running `uv run load-data` directly, the `--seasons` flag behaves differently than you might expect:

| Flag | File written | Effect on existing data |
|------|-------------|------------------------|
| `--all-seasons` | `player_stats.csv` | Overwrites the main combined file — this is what the database reads |
| `--seasons 2025` | `player_stats_2025.csv` | Creates a new year-specific file; the main `player_stats.csv` is **not updated** |

If you use `--seasons 2025` expecting to refresh your data, the database will still read stale data from the unchanged main CSV. **Always use `--all-seasons` when refreshing season-based datasets** (`player_stats`, `rosters`, `schedules`, `injuries`, etc.).

Non-season datasets (`ff_rankings`, `players`, `ff_playerids`, etc.) always overwrite their single file regardless of the seasons flag.


## References

### nflverse data
See the data dictionary for the [nflverse data here](https://nflreadr.nflverse.com/articles/index.html)

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
SELECT * FROM reference.yamplayer_mapping;  -- Unified player IDs (43K players)
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


