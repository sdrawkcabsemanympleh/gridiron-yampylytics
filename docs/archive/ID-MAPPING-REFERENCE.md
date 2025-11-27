# ID Mapping Reference - gridiron-yampylytics

**Date:** 2025-11-14
**Status:** CRITICAL REFERENCE - Required for cross-dataset joins

---

## Overview

This document catalogs all identifier mismatches across NFL datasets and provides mapping strategies for joins. **Ignoring these mappings will result in failed joins and missing data.**

This ideally will only be a reference and sanity check.  While adding another ID into the mix risks just adding more to the mess, `yamplayer_id` and other universal ID's are being generated and can be inserted into all of the datasets to abstract all of this.  Ideally, this will all be abstracted and this document can just collect dust. 

---

## Player ID Systems

### Primary Issue: Multiple Player ID Schemes

Different data sources use completely different player identification systems. **You cannot directly join datasets with different ID schemes.**

### Player ID Types

| ID Type | Format | Example | Used By |
|---------|--------|---------|---------|
| **gsis_id** | `00-0XXXXXX` | `00-0033873` | Play-by-play, player stats, rosters, contracts, depth charts |
| **pfr_id** (PFR player ID) | `LastFiXX` | `BradTo00` | Draft picks, combine data |
| **espn_id** | Integer | `3918298` | Depth charts (modern), fantasy data |
| **elias_id** | `LLLNNNNN` | `BRA123456` | Depth charts (legacy), official NFL stats |
| **sleeper_id** | Integer | `4881` | Fantasy platforms |
| **yahoo_id** | Integer | `30123` | Fantasy platforms |

### Solution: Universal Crosswalk Table

**File:** `data/cached/nflreadpy/player_ids/player_ids_all.csv`
**Rows:** 17,031+ players
**Coverage:** All major ID systems

**Schema:**
```
gsis_id          - NFL official GameDay ID (PRIMARY KEY)
pfr_id           - Pro Football Reference ID
espn_id          - ESPN player ID
sleeper_id       - Sleeper fantasy ID
yahoo_id         - Yahoo fantasy ID
fantasypros_id   - FantasyPros ID
mfl_id           - MyFantasyLeague ID
sportradar_id    - Sportradar ID
pff_id           - Pro Football Focus ID
name             - Player name
position         - Position
team             - Current team
```

### Join Pattern: Draft Picks → Player Stats

**WRONG (Won't work):**
```sql
-- ❌ FAILS - Different ID systems
SELECT * FROM draft_picks d
JOIN player_stats p ON d.pfr_player_id = p.player_id;
```

**CORRECT (Uses crosswalk):**
```sql
-- ✅ SUCCESS - Maps PFR → GSIS
SELECT
    d.*,
    p.passing_yards,
    p.rushing_yards
FROM draft_picks d
LEFT JOIN player_ids x ON d.pfr_player_id = x.pfr_id
LEFT JOIN player_stats p ON x.gsis_id = p.player_id;
```

### Join Pattern: Combine → Rosters

**WRONG:**
```sql
-- ❌ FAILS - Combine uses pfr_id, rosters use gsis_id
SELECT * FROM combine c
JOIN rosters r ON c.pfr_id = r.gsis_id;
```

**CORRECT:**
```sql
-- ✅ SUCCESS
SELECT
    c.player_name,
    c.40yd,
    c.vertical,
    r.team,
    r.years_exp
FROM combine c
LEFT JOIN player_ids x ON c.pfr_id = x.pfr_id
LEFT JOIN rosters r ON x.gsis_id = r.gsis_id;
```

### Best Practice: Always Use gsis_id

**Recommendation:** Standardize all queries on `gsis_id` as the primary player identifier.

**Why gsis_id:**
- ✅ Official NFL GameDay ID
- ✅ Most comprehensive coverage (2000+)
- ✅ Used by majority of nflverse datasets
- ✅ Stable (doesn't change when player moves teams)

---

## Team Code Systems

### Primary Issue: PFR vs nflverse Codes

Pro Football Reference uses different 3-letter lowercase codes than the nflverse standard uppercase codes.

### Complete Team Code Mapping

| Team Name | PFR Code | nflverse Code | Notes |
|-----------|----------|---------------|-------|
| Arizona Cardinals | `crd` | `ARI` | |
| Atlanta Falcons | `atl` | `ATL` | Same (case difference) |
| Baltimore Ravens | `rav` | `BAL` | Different base |
| Buffalo Bills | `buf` | `BUF` | Same (case difference) |
| Carolina Panthers | `car` | `CAR` | Same (case difference) |
| Chicago Bears | `chi` | `CHI` | Same (case difference) |
| Cincinnati Bengals | `cin` | `CIN` | Same (case difference) |
| Cleveland Browns | `cle` | `CLE` | Same (case difference) |
| Dallas Cowboys | `dal` | `DAL` | Same (case difference) |
| Denver Broncos | `den` | `DEN` | Same (case difference) |
| Detroit Lions | `det` | `DET` | Same (case difference) |
| Green Bay Packers | `gnb` | `GB` | Different base |
| Houston Texans | `htx` | `HOU` | Different base |
| Indianapolis Colts | `clt` | `IND` | Different base |
| Jacksonville Jaguars | `jax` | `JAX` | Same (case difference) |
| Kansas City Chiefs | `kan` | `KC` | Different base |
| Las Vegas Raiders | `rai` | `LV` | Different base, relocation |
| Los Angeles Chargers | `sdg` | `LAC` | Different base, relocation (was San Diego) |
| Los Angeles Rams | `ram` | `LA` | Different base, relocation |
| Miami Dolphins | `mia` | `MIA` | Same (case difference) |
| Minnesota Vikings | `min` | `MIN` | Same (case difference) |
| New England Patriots | `nwe` | `NE` | Different base |
| New Orleans Saints | `nor` | `NO` | Different base |
| New York Giants | `nyg` | `NYG` | Same (case difference) |
| New York Jets | `nyj` | `NYJ` | Same (case difference) |
| Philadelphia Eagles | `phi` | `PHI` | Same (case difference) |
| Pittsburgh Steelers | `pit` | `PIT` | Same (case difference) |
| San Francisco 49ers | `sfo` | `SF` | Different base |
| Seattle Seahawks | `sea` | `SEA` | Same (case difference) |
| Tampa Bay Buccaneers | `tam` | `TB` | Different base |
| Tennessee Titans | `oti` | `TEN` | Different base |
| Washington Commanders | `was` | `WAS` | Same (case difference) |

### Datasets Affected

**Uses PFR codes:**
- GM executives data (`data/raw/executives/*.csv`)
- Pro Football Reference scraped data

**Uses nflverse codes:**
- All nflreadpy datasets (play-by-play, schedules, rosters, etc.)
- Depth charts
- Player stats

### Solution: Team Mapping Built Into GM Combiner

**File:** `data/processed/gm_tenures.csv`

The `combine_gm_data.py` script already includes team code mapping. The output includes both:
- `pfr_team_code` - Original PFR code
- `nflverse_code` - Mapped nflverse code
- `team_name` - Full team name

**No additional mapping needed for GM data!**

### Join Pattern: GM Data → Schedules

**WRONG:**
```sql
-- ❌ FAILS - Different team codes
SELECT * FROM gm_tenures g
JOIN schedules s ON g.pfr_team_code = s.home_team;
```

**CORRECT:**
```sql
-- ✅ SUCCESS - Use mapped nflverse_code
SELECT
    g.Person as gm_name,
    g.From as gm_start_year,
    s.season,
    s.home_score,
    s.away_score
FROM gm_tenures g
JOIN schedules s ON g.nflverse_code = s.home_team
WHERE s.season BETWEEN g.From AND COALESCE(g.To, 2025);
```

---

## Position Code Systems

### Primary Issue: Multiple Granularity Levels

Position codes vary wildly in specificity across datasets.

### Position Code Formats by Dataset

**Draft Picks (Generic):**
- `QB`, `RB`, `WR`, `TE`, `OL`, `DL`, `LB`, `DB`, `K`, `P`
- Very broad groupings

**Player Stats (Fantasy-focused):**
- `QB`, `RB`, `WR`, `TE`, `K`, `P`, `DEF`
- Offensive skill positions emphasized

**Rosters (Standard NFL):**
- `QB`, `RB`, `WR`, `TE`, `FB`, `OL`, `DL`, `LB`, `CB`, `S`, `K`, `P`, `LS`
- More detailed than draft picks

**Depth Charts Legacy (Specific):**
- Offense: `QB`, `RB`, `FB`, `WR`, `TE`, `LT`, `LG`, `C`, `RG`, `RT`
- Defense: `LDE`, `LDT`, `RDT`, `RDE`, `LOLB`, `MLB`, `ROLB`, `LCB`, `RCB`, `SS`, `FS`
- Special: `K`, `P`, `KR`, `PR`, `LS`, `H`
- Very granular, position-specific

**Depth Charts Modern (Formation-based):**
- Full names: `Left Defensive End`, `Right Defensive Tackle`, `Slot Cornerback`
- Position groups: `Base 4-3 D`, `Nickel`, `3WR 1TE`
- Extremely detailed

### The Problem

**Cannot reliably join on position codes** because granularity differs:

| Dataset | Position Code | Meaning |
|---------|---------------|---------|
| Draft picks | `OL` | Any offensive lineman |
| Depth charts | `LT` | Specifically left tackle |
| Depth charts | `RT` | Specifically right tackle |
| Depth charts | `LG` | Specifically left guard |

**Joining draft picks (`OL`) with depth charts (`LT`) won't match**, even though left tackles are offensive linemen.

### Solution: Create Position Mapping Table

**Recommended approach:** Build a position hierarchy table

```sql
CREATE TABLE position_mapping AS
SELECT * FROM (VALUES
    -- (specific_position, general_position, position_group, full_name)
    ('QB', 'QB', 'OFFENSE', 'Quarterback'),
    ('RB', 'RB', 'OFFENSE', 'Running Back'),
    ('FB', 'RB', 'OFFENSE', 'Fullback'),
    ('WR', 'WR', 'OFFENSE', 'Wide Receiver'),
    ('TE', 'TE', 'OFFENSE', 'Tight End'),
    ('LT', 'OL', 'OFFENSE', 'Left Tackle'),
    ('LG', 'OL', 'OFFENSE', 'Left Guard'),
    ('C', 'OL', 'OFFENSE', 'Center'),
    ('RG', 'OL', 'OFFENSE', 'Right Guard'),
    ('RT', 'OL', 'OFFENSE', 'Right Tackle'),
    ('LDE', 'DL', 'DEFENSE', 'Left Defensive End'),
    ('LDT', 'DL', 'DEFENSE', 'Left Defensive Tackle'),
    ('RDT', 'DL', 'DEFENSE', 'Right Defensive Tackle'),
    ('RDE', 'DL', 'DEFENSE', 'Right Defensive End'),
    ('LOLB', 'LB', 'DEFENSE', 'Left Outside Linebacker'),
    ('MLB', 'LB', 'DEFENSE', 'Middle Linebacker'),
    ('ROLB', 'LB', 'DEFENSE', 'Right Outside Linebacker'),
    ('LCB', 'DB', 'DEFENSE', 'Left Cornerback'),
    ('RCB', 'DB', 'DEFENSE', 'Right Cornerback'),
    ('SS', 'DB', 'DEFENSE', 'Strong Safety'),
    ('FS', 'DB', 'DEFENSE', 'Free Safety')
    -- ... etc
) AS t(specific_pos, general_pos, pos_group, full_name);
```

**Join pattern:**
```sql
-- Join draft picks (OL) with depth charts (LT, LG, etc.)
SELECT
    d.pfr_player_name,
    d.position as draft_position,
    dc.depth_position as depth_chart_position,
    pm.full_name as position_name
FROM draft_picks d
LEFT JOIN player_ids x ON d.pfr_player_id = x.pfr_id
LEFT JOIN depth_charts_legacy dc ON x.gsis_id = dc.gsis_id
LEFT JOIN position_mapping pm ON dc.depth_position = pm.specific_pos
WHERE pm.general_pos = d.position OR d.position = dc.depth_position;
```

### Best Practice: Don't Join on Position

**Recommendation:** Use position for **filtering** and **grouping**, not for joining.

**Good usage:**
```sql
-- Filter by position
SELECT * FROM player_stats WHERE position = 'QB';

-- Group by position
SELECT position, AVG(passing_yards) FROM player_stats GROUP BY position;
```

**Bad usage:**
```sql
-- ❌ Don't join datasets on position
SELECT * FROM draft_picks d
JOIN player_stats p ON d.position = p.position;  -- Too generic, won't be meaningful
```

---

## Format Inconsistencies

### Case Sensitivity

**Team codes:**
- PFR: lowercase (`nwe`, `kan`, `sdg`)
- nflverse: uppercase (`NE`, `KC`, `LAC`)

**Solution:** Normalize to uppercase or use mapping table (already done in GM combiner)

### Player Name Variations

**Different formats across datasets:**
- `Tom Brady` (First Last)
- `Brady, Tom` (Last, First)
- `T.Brady` (Initial.Last)
- `T. Brady` (Initial. Last)
- `Thomas Brady` (Full first name)

**Solution:** **Never join on player names.** Always use IDs.

```sql
-- ❌ BAD - Name matching is unreliable
SELECT * FROM draft_picks d
JOIN player_stats p ON d.pfr_player_name = p.player_name;

-- ✅ GOOD - Use IDs
SELECT * FROM draft_picks d
LEFT JOIN player_ids x ON d.pfr_player_id = x.pfr_id
LEFT JOIN player_stats p ON x.gsis_id = p.player_id;
```

### Date Format Variations

**Different formats across datasets:**
- Integer year: `2024`
- Date string: `2024-11-14`
- ISO timestamp: `2025-11-02T07:13:47Z`

**Solution:** Cast appropriately in queries

```sql
-- Standardize to integer year
SELECT
    season,                           -- Already integer
    YEAR(dt::TIMESTAMP) as year,      -- Extract from timestamp
    CAST(game_date AS INTEGER) as year -- Cast from string
FROM various_tables;
```

---

## Recommendations for Future Work

### Option 1: Create Universal ID Tables

**Create reference tables** that store all ID mappings:

```
data/reference/
├── player_id_mapping.csv      (Already exists as player_ids_all.csv)
├── team_code_mapping.csv      (TODO - extract from GM combiner)
├── position_mapping.csv       (TODO - create hierarchy)
└── game_id_mapping.csv        (TODO - if needed)
```

### Option 2: Add Universal IDs to Processed Data

**When creating processed datasets**, add all relevant IDs:

Example for processed depth charts:
```
depth_charts_legacy.csv:
  - Original fields
  + nflverse_team_code (mapped from club_code)
  + espn_id (looked up from player_ids)
  + pfr_id (looked up from player_ids)
```

This makes joins easier downstream but requires more processing upfront.

### Option 3: Create Database Views

**In DuckDB/SQL**, create views that handle mapping automatically:

```sql
CREATE VIEW players_unified AS
SELECT
    p.gsis_id,
    p.pfr_id,
    p.espn_id,
    p.name,
    p.position,
    p.team
FROM player_ids p;

-- Use this view for all joins instead of raw tables
```

---

## Critical Joining Rules

### ✅ DO

1. **Always use player_ids_all.csv** for cross-dataset player joins
2. **Always use gsis_id** as primary player key when possible
3. **Always use nflverse_code** when joining GM data with nflreadpy data
4. **Always normalize team codes** to uppercase
5. **Always cast dates** to consistent format before joining

### ❌ DON'T

1. **Don't join on player names** - use IDs
2. **Don't join on positions** unless you've built a mapping table
3. **Don't mix PFR and nflverse team codes** without mapping
4. **Don't assume case-insensitive matching** - SQL is case-sensitive by default
5. **Don't ignore NULL IDs** - they indicate missing crosswalk data

---

## Quick Reference: Common Joins

### Draft Picks → Player Stats
```sql
SELECT * FROM draft_picks d
LEFT JOIN player_ids x ON d.pfr_player_id = x.pfr_id
LEFT JOIN player_stats p ON x.gsis_id = p.player_id;
```

### GM Data → Schedules
```sql
SELECT * FROM gm_tenures g
JOIN schedules s ON g.nflverse_code = s.home_team;
```

### Combine → Rosters
```sql
SELECT * FROM combine c
LEFT JOIN player_ids x ON c.pfr_id = x.pfr_id
LEFT JOIN rosters r ON x.gsis_id = r.gsis_id;
```

### Play-by-Play → Player Stats
```sql
-- No crosswalk needed - both use gsis_id
SELECT * FROM play_by_play pbp
JOIN player_stats ps ON pbp.passer_id = ps.player_id;
```

---

## Validation Queries

### Check Player ID Crosswalk Coverage

```sql
-- How many draft picks have missing gsis_id mappings?
SELECT COUNT(*) as missing_gsis_mappings
FROM draft_picks d
LEFT JOIN player_ids x ON d.pfr_player_id = x.pfr_id
WHERE x.gsis_id IS NULL;
```

### Check Team Code Mapping Coverage

```sql
-- Are all GM team codes mapped?
SELECT pfr_team_code, COUNT(*)
FROM gm_tenures
WHERE nflverse_code IS NULL
GROUP BY pfr_team_code;
```

### Check Position Consistency

```sql
-- What positions exist in each dataset?
SELECT 'draft_picks' as source, position, COUNT(*)
FROM draft_picks GROUP BY position
UNION ALL
SELECT 'player_stats', position, COUNT(*)
FROM player_stats GROUP BY position
UNION ALL
SELECT 'depth_charts', depth_position, COUNT(*)
FROM depth_charts_legacy GROUP BY depth_position;
```

---

## Files Reference

**Player ID Crosswalk:**
```
data/cached/nflreadpy/player_ids/player_ids_all.csv
```

**GM Data (includes team mapping):**
```
data/processed/gm_tenures.csv
```

**Team Mapping (built into GM combiner):**
```python
# See scripts/combine_gm_data.py, load_team_code_mapping() function
```

**Position Mapping:**
```
TODO - Create data/reference/position_mapping.csv
```

---

## Contact

For questions about ID mapping:
- Reference this document
- Check nfl_data_architecture.md for dataset schemas
- Consult nfl_data_expert agent for complex mapping scenarios

**Last Updated:** 2025-11-14
**Maintained By:** Data Engineering Team
**Version:** 1.0
