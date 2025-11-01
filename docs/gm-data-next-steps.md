# GM Data - Next Steps

## What We Tried

Created `scripts/download_gm_data.py` to download executive data from Pro Football Reference team pages.

**Problem:** PFR returns 403 Forbidden even with User-Agent headers.

**Reason:** PFR likely has anti-scraping measures (Cloudflare, rate limiting, etc.)

## Alternative Approaches

### Option 1: Manual Download (EASIEST)
1. Visit `https://www.pro-football-reference.com/executives/`
2. Click each team link
3. Download CSV manually from each team's executive page
4. Save to `data/raw/executives/`

**Pros:** Simple, respectful, works immediately
**Cons:** Manual work (but only ~32 teams, one-time)

### Option 2: Use Coach Data from games.csv (ALREADY HAVE THIS!)
We already have coach data in `nfldata/games.csv`:
- `away_coach` and `home_coach` columns
- Coverage: 2006-present
- Can extract coach tenure from game-by-game data

**Script to extract:**
```python
import pandas as pd

games = pd.read_csv('nfldata/data/games.csv')

# Extract home coach tenure
home_coaches = games[['season', 'home_team', 'home_coach']].rename(
    columns={'home_team': 'team', 'home_coach': 'coach'}
)

# Extract away coach tenure
away_coaches = games[['season', 'away_team', 'away_coach']].rename(
    columns={'away_team': 'team', 'away_coach': 'coach'}
)

# Combine and get unique coach-team-season combinations
all_coaches = pd.concat([home_coaches, away_coaches])
coach_tenure = all_coaches.drop_duplicates()

# Calculate tenure ranges
tenure_summary = coach_tenure.groupby(['team', 'coach']).agg(
    start_year=('season', 'min'),
    end_year=('season', 'max')
).reset_index()
```

**Pros:** We already have the data! No scraping needed.
**Cons:** Only covers coaches, not GMs. But coaches are also valuable for analysis.

### Option 3: Search for Existing Dataset
- Check Kaggle for GM/executive datasets
- Check other GitHub repos
- Someone may have already compiled this

## Recommendation

**Start with Option 2** - Extract coach data from games.csv we already have!

This gets us:
- Coach tenure by team (2006-present)
- Can analyze "coach + GM" combos later
- Zero additional work needed

**Then pursue Option 3** - Search for existing GM datasets

**Finally Option 1 if needed** - Manual download from PFR (only if we really need GM data)

## Coach Data Is Valuable Too!

Many "GM" decisions involve collaboration with coaches:
- Draft picks (GM + Coach input)
- Free agent signings (GM + Coach fit)
- Roster construction (GM builds, Coach uses)

Having coach tenure lets us analyze:
- Coach + GM pairing success
- Coaching stability vs roster churn
- Which coaches maximize draft picks
