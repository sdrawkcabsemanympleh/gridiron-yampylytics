# Data Reorganization Summary

**Date:** 2025-11-19
**Status:** Scripts updated, ready for file reorganization

---

## New Data Directory Structure

```
data/
├── nflverse/              # Schema: nflverse
│   ├── pbp.csv
│   ├── player_stats.csv
│   ├── rosters.csv
│   ├── schedules.csv
│   ├── injuries.csv
│   ├── depth_charts.csv          # Raw combined format
│   ├── depth_charts_legacy.csv   # Clean 2001-2024 format
│   ├── depth_charts_modern.csv   # Clean 2025+ format
│   ├── draft_picks.csv
│   ├── combine.csv
│   ├── contracts.parquet
│   └── player_ids.csv
│
├── reference/             # Schema: reference
│   ├── draft_value_charts/
│   └── gm_tenures.csv
│
├── yas/                   # Schema: yas (YamPy Athletic Score)
│   ├── ras_2025.csv
│   └── ras_historical.csv
│
└── raw/                   # Schema: raw
    └── executives/
```

---

## Scripts Updated

### 1. `scripts/cache_nflreadpy_data.py`
**Changes:**
- Output directory: `data/cached/nflreadpy/` → `data/nflverse/`
- Removed `_all` suffix from filenames
  - `pbp_all.csv` → `pbp.csv`
  - `player_stats_all.csv` → `player_stats.csv`
  - etc.
- No subdirectories (all files directly in `data/nflverse/`)

### 2. `scripts/clean_depth_charts.py`
**Changes:**
- Input: `data/cached/nflreadpy/depth_charts/depth_charts_all.csv` → `data/nflverse/depth_charts.csv`
- Output: `data/processed/` → `data/nflverse/`
- Files: `depth_charts_legacy.csv`, `depth_charts_modern.csv`

### 3. `scripts/combine_gm_data.py`
**Changes:**
- Output: `data/processed/gm_tenures.csv` → `data/reference/gm_tenures.csv`

### 4. `scripts/load_all_data.py`
**Changes:**
- Updated documentation to reflect `data/nflverse/` location

---

## User Actions Required

1. **Move/rename files** to match new structure:
   ```bash
   # Move nflreadpy data
   mv data/cached/nflreadpy/* data/nflverse/

   # Rename files (remove _all suffix)
   cd data/nflverse
   mv pbp_all.csv pbp.csv
   mv player_stats_all.csv player_stats.csv
   mv rosters_all.csv rosters.csv
   # ... etc for all files

   # Move GM tenures
   mv data/processed/gm_tenures.csv data/reference/

   # Move depth charts
   mv data/processed/depth_charts_*.csv data/nflverse/
   ```

2. **Delete old directories** (optional):
   ```bash
   rm -rf data/cached/
   rm -rf data/processed/
   ```

3. **Re-run data loaders** to generate clean files:
   ```bash
   uv run python -m scripts.cache_nflreadpy_data --all
   uv run python -m scripts.clean_depth_charts
   uv run python -m scripts.combine_gm_data
   ```

---

## DuckDB Schema Names

After reorganization, `create_duckdb.py` will create these schemas:

```sql
-- nflverse schema
SELECT * FROM nflverse.pbp;
SELECT * FROM nflverse.player_stats;
SELECT * FROM nflverse.rosters;
SELECT * FROM nflverse.schedules;
SELECT * FROM nflverse.injuries;
SELECT * FROM nflverse.depth_charts_legacy;
SELECT * FROM nflverse.depth_charts_modern;
SELECT * FROM nflverse.draft_picks;
SELECT * FROM nflverse.combine;
SELECT * FROM nflverse.contracts;
SELECT * FROM nflverse.player_ids;

-- reference schema
SELECT * FROM reference.gm_tenures;

-- yas schema (after RAS calculator runs)
SELECT * FROM yas.ras_2025;
SELECT * FROM yas.ras_historical;

-- raw schema
SELECT * FROM raw_executives.atl_executives;
-- ... etc
```

---

## Benefits

1. **Clean table names:** `nflverse.pbp` instead of `cached_nflreadpy.pbp_all`
2. **Logical grouping:** All nflverse data together
3. **Clear purpose:** Schema names indicate data source
4. **Simpler filenames:** No redundant `_all` suffixes
5. **Future-proof:** Easy to add new schemas (e.g., `analytics`, `models`)

---

## Next Steps

1. User reorganizes files
2. Test DuckDB loading: `uv run python -m scripts.create_duckdb`
3. Verify schemas in Harlequin: `uv run harlequin gridiron_yampylytics.db`
4. Proceed with RAS calculator implementation
