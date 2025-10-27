# NFL GM Analytics Project - Getting Started Guide

## Overview
Build a comprehensive dataset to analyze NFL GM performance, focusing on drafting, roster management, and contract decisions.

---

## Phase 1: Foundation - nflverse Data (START HERE)
**Priority: HIGH | Difficulty: EASY | Time: 30 minutes**

### What to Get
- Play-by-play data (1999-present)
- Weekly rosters
- Draft picks
- Depth charts (weekly)
- Team schedules

### How to Get It
```bash
pip install nfl-data-py
```

```python
import nfl_data_py as nfl

# Download everything you need
pbp = nfl.import_pbp_data([2020, 2021, 2022, 2023])  # Play-by-play
rosters = nfl.import_weekly_rosters([2020, 2021, 2022, 2023])
draft = nfl.import_draft_picks()  # All years available
depth_charts = nfl.import_depth_charts([2020, 2021, 2022, 2023])
schedules = nfl.import_schedules([2020, 2021, 2022, 2023])

# Save locally for faster access
pbp.to_csv('pbp_data.csv', index=False)
rosters.to_csv('rosters.csv', index=False)
draft.to_csv('draft_picks.csv', index=False)
```

### What You'll Have
- **Every snap** with player participation (can calculate snap counts)
- **Player movements** week-by-week (signings, cuts, trades)
- **Draft history** with round/pick/position
- **Depth chart changes** throughout seasons

### Key Fields
- `play_id`, `game_id`, `posteam`, `defteam` - game/play identifiers
- Player columns: positions have their own fields (QB, RB, WR, etc.)
- Draft: `pfr_player_id`, `season`, `round`, `pick`, `position`, `team`

---

## Phase 2: Combine & Athletic Data
**Priority: HIGH | Difficulty: EASY | Time: 20 minutes**

### Option A: GitHub Repo (Easiest)
```bash
git clone https://github.com/leesharpe/nfldata
# Look in /data folder for combine.csv
```

### Option B: Scrape Pro Football Reference
**Target URL:** `https://www.pro-football-reference.com/draft/[YEAR]-combine.htm`

**What to Scrape:**
- 40-yard dash
- Bench press reps
- Vertical jump
- Broad jump
- 3-cone drill
- 20-yard shuttle
- Height, weight, arm length, hand size

**Scraping Strategy:**
```python
import pandas as pd
import requests
from bs4 import BeautifulSoup

years = range(2000, 2024)
all_combine = []

for year in years:
    url = f"https://www.pro-football-reference.com/draft/{year}-combine.htm"
    # Use pd.read_html() - PFR tables are clean
    tables = pd.read_html(url)
    combine_data = tables[0]  # First table is combine data
    combine_data['year'] = year
    all_combine.append(combine_data)

combine_df = pd.concat(all_combine)
combine_df.to_csv('combine_data.csv', index=False)
```

**Note:** Be respectful - add `time.sleep(1)` between requests

---

## Phase 3: RAS (Relative Athletic Score)
**Priority: MEDIUM | Difficulty: MEDIUM | Time: 30 minutes**

### Option A: GitHub Repo
Search GitHub for "NFL RAS" - several repos have scraped data:
- `https://github.com/arjunmenon10/NFL-Combine-RAS`
- `https://github.com/tefirman/RAS`

### Option B: MockDraftable (Alternative to RAS)
**Target:** `https://www.mockdraftable.com/`

Has similar athletic percentile scores. Requires scraping player pages individually.

**Skip this initially** - combine data alone is good enough to start. RAS adds polish later.

---

## Phase 4: GM/Coach History
**Priority: HIGH | Difficulty: MEDIUM | Time: 1-2 hours**

### Manual Compilation (Recommended for now)
Create a CSV manually with major GMs:

```csv
team,season,gm_name,hc_name
ARI,2019,Steve Keim,Kliff Kingsbury
ARI,2020,Steve Keim,Kliff Kingsbury
...
```

### Scraping Option: Pro Football Reference
**Target URL:** `https://www.pro-football-reference.com/teams/[TEAM]/[YEAR].htm`

Each team-year page lists GM and Head Coach. Would need to scrape 32 teams × ~15 years = 480 pages.

**Strategy:**
```python
teams = ['ari', 'atl', 'bal', ...]  # All 32 team codes
years = range(2010, 2024)

for team in teams:
    for year in years:
        url = f"https://www.pro-football-reference.com/teams/{team}/{year}.htm"
        # Parse page, extract GM and HC names
        time.sleep(1)  # Be respectful
```

**Note:** Week-by-week changes (mid-season firings) would need manual tracking for key events.

---

## Phase 5: Contract Data (Advanced)
**Priority: MEDIUM | Difficulty: HARD | Time: Several hours**

### Start Simple: Spotrac Team Cap Pages
**Target:** `https://www.spotrac.com/nfl/[team]/cap/[year]/`

**What to Get:**
- Player name
- Cap hit
- Dead money
- Contract years remaining

**Strategy:**
```python
teams = ['arizona-cardinals', 'atlanta-falcons', ...]
years = range(2015, 2024)  # Spotrac has good data from ~2011+

for team in teams:
    for year in years:
        url = f"https://www.spotrac.com/nfl/{team}/cap/{year}/"
        # Parse table - relatively clean HTML
        time.sleep(2)  # More respectful rate limiting
```

### Advanced: Over The Cap Dead Money
**Target:** `https://overthecap.com/dead-money/[year]/`

Pre-aggregated dead money by team/year. Much easier than player-by-player.

**Save this for last** - it's time-consuming and you can do a lot without it.

---

## Phase 6: Draft Pick Value Charts
**Priority: LOW | Difficulty: TRIVIAL | Time: 5 minutes**

Just create a small CSV manually or find one online:

```csv
pick,jimmy_johnson_value,rich_hill_value
1,3000,885.4
2,2600,838.2
3,2200,790.9
...
```

**Resources:**
- Search "Jimmy Johnson draft chart CSV"
- PFR has them listed
- Only ~260 rows (7 rounds × ~37 picks)

---

## Recommended Order of Attack

### Week 1: Get Core Data
1. **Install nfl-data-py** and download play-by-play, rosters, draft picks (30 min)
2. **Clone Lee Sharpe's repo** or scrape PFR for combine data (20 min)
3. **Manually create GM/coach CSV** for teams you care about most (1 hour)
4. **Explore the data** - load into pandas, see what's there (2-3 hours)

### Week 2: Calculate Basic Metrics
1. **Calculate snap counts** from play-by-play by player/season/team
2. **Link draft picks to careers** using player IDs
3. **Build first metric:** "Draft pick career snaps by GM"
4. **Visualize it** with retro report or termgraph

### Week 3: Add Depth
1. **Scrape combine data** if you didn't use GitHub repo
2. **Add contract data** from Spotrac (start with just a few teams/years)
3. **Calculate advanced metrics:** rookie contract retention, wasted draft capital
4. **Build comprehensive dashboard**

### Week 4+: Polish & Explore
1. **Add RAS/athletic scores** if desired
2. **Scrape full contract history** if you want dead money analysis
3. **Create funny metrics** - get creative!
4. **Share your findings** on Twitter/blog

---

## Data Storage Strategy

### Local Files
```
nfl_project/
├── data/
│   ├── raw/
│   │   ├── pbp_2020_2023.csv
│   │   ├── rosters_2020_2023.csv
│   │   ├── draft_picks_all.csv
│   │   ├── combine_data.csv
│   │   └── gm_history.csv
│   ├── processed/
│   │   ├── player_snap_counts.csv
│   │   ├── draft_player_careers.csv
│   │   └── gm_metrics.csv
├── scripts/
│   ├── 01_download_nflverse.py
│   ├── 02_scrape_combine.py
│   ├── 03_calculate_snap_counts.py
│   └── 04_generate_metrics.py
└── visualizations/
    ├── retro_report.py
    └── outputs/
```

### Key Joins/Links
- **Player ID:** nflverse uses `gsis_id` and `pfr_player_id` - use these to link across datasets
- **Team codes:** 3-letter codes (ARI, ATL, BAL, etc.) - consistent across sources
- **Seasons:** Calendar year (2023 season = 2023-2024 games)

---

## Quick Wins - Metrics You Can Calculate Immediately

With just nflverse data (Phase 1), you can calculate:

1. **Snap Count Totals** - Career snaps by draft pick
2. **Draft Hit Rate** - % of picks who played >1000 career snaps
3. **Positional Drafting Patterns** - Which GMs over/under-draft positions
4. **Roster Churn Rate** - Players added/dropped per season
5. **Depth Chart Velocity** - How fast rookies climb to starter

Add combine data (Phase 2):
6. **Athletic Profile by Position** - Do certain GMs draft faster/stronger players?
7. **Combine Score vs Production** - Which metrics predict success?

Add GM history (Phase 4):
8. **GM Rankings** - Sort all your metrics by GM tenure

Add contracts (Phase 5):
9. **Dead Money Disaster Index** - % of cap that became dead money
10. **Rookie Contract Efficiency** - Snaps per dollar on rookie deals

---

## Tools You'll Need

```bash
pip install nfl-data-py pandas requests beautifulsoup4 lxml matplotlib seaborn plotly termgraph rich
```

**Optional but helpful:**
```bash
pip install jupyter notebook  # For exploration
pip install streamlit  # For dashboards
```

---

## Data Quality Notes

- **nflverse play-by-play:** Extremely reliable, well-maintained
- **nflverse rosters:** Very good, weekly granularity
- **nflverse draft:** Complete, goes back to 1936
- **Combine data:** Spotty before 2000, excellent 2000+
- **GM history:** No single good source, manual work required
- **Contracts:** Incomplete before ~2011, good 2011+

---

## Next Steps After Data Collection

1. **Data Cleaning:** Handle missing values, standardize player names
2. **Feature Engineering:** Calculate derived metrics (snap share %, positional value, etc.)
3. **Metric Development:** Build your "bad GM" formulas
4. **Visualization:** Use retro reports or other styles
5. **Analysis:** Find patterns, outliers, funny insights
6. **Sharing:** Blog posts, Twitter threads, GitHub repo

---

## Resources & Documentation

- **nfl-data-py docs:** https://github.com/nfl-data-py/nfl_data_py
- **nflverse data dictionary:** https://nflreadr.nflverse.com/articles/dictionary.html
- **Pro Football Reference:** https://www.pro-football-reference.com/
- **Spotrac:** https://www.spotrac.com/nfl/
- **Over The Cap:** https://overthecap.com/

---

## Questions to Answer with Your Data

- Which GM drafted the most players who became starters... for OTHER teams?
- What % of draft capital results in production during rookie contracts?
- Do GMs who spend more on free agents draft worse?
- Which positions have the highest "bust rate" by draft round?
- How long does it take rookie picks to crack the starting lineup by position?
- Which GMs are best at finding late-round gems?
- What's the correlation between combine scores and career snap counts?
- Which team has the highest roster turnover year-over-year?
- Do teams with more dead money win fewer games?

**The fun part: Come up with absurd metrics that technically measure something real!**

---

Good luck! Start with Phase 1, get comfortable with the data, then build from there. You can have interesting metrics within a few hours of starting.