# NFL Data Sources - Quick Reference

## Summary Table

| Source | Type | Size | Last Updated | Coverage | Quality | Recommendation | Priority |
|--------|------|------|--------------|----------|---------|----------------|----------|
| **nflreadpy** | Package | 1.5MB | 2025-10-26 | 2000-present | Excellent | PRIMARY DEPENDENCY | HIGH |
| **NFL Stats 2012-2024 (cached)** | Dataset | 209MB | 2024 | 2012-2024 | Excellent | PRIMARY DATASET | HIGH |
| **NFL_Scraper (cached)** | Dataset | 256MB | 2025-10-21 | 2017-2025 (Week 7) | Good | Keep for 2025 current | MEDIUM |
| **nfldata** | Reference | 10MB* | 2025-10-28 | 2000-present | Excellent | Extract data files only | MEDIUM |
| **nfl-draft-data (cached)** | Dataset | 17MB | 2021-05-05 | 1967-2021 | Very Good | Keep for historical | MEDIUM |
| **NFL-Statistics-Scrape (cached)** | Dataset | 94MB | ~2017 | Through 2017 | Mixed | Keep for reference | LOW |
| **Spotrac.com-NFL-Scrap** | Scraper | 165KB | 2024-11-25 | Current | Unknown | Test for salaries | LOW |
| **historical-nfl-draft-data** | Dataset | 6.5MB | 2023-10-02 | 2015-2023 | Good | Skip - redundant | SKIP |
| **NFL-Combine-Data** | Dataset | 1.2MB | 2018-02-12 | Through 2018 | Outdated | Skip - use nflreadpy | SKIP |
| **nflscrapy** | Package | 301KB | 2023-05-06 | 2000-present | Good | Skip - redundant | SKIP |

*nfldata actual data is 10MB; full repo with git history is 7.2GB

## Data Coverage by Type

### Play-by-Play Data
- **nflreadpy**: 2000-present (PRIMARY)
- **NFL_Scraper cached**: 2017-2025 Week 7 (BACKUP)

### Player Statistics
- **NFL Stats 2012-2024 cached**: Weekly & yearly, 2012-2024 (PRIMARY)
- **nflreadpy**: Game & season stats, all years (SUPPLEMENT)

### Draft Data
- **nfl-draft-data cached**: 1967-2021 comprehensive (HISTORICAL)
- **nfldata**: 2000-present (REFERENCE)
- **nflreadpy**: Current (for 2022-2025 gap)

### Combine Data
- **nflreadpy**: Current and historical (USE THIS)

### Schedules & Games
- **nfldata**: 2006-present with betting lines (REFERENCE)
- **nflreadpy**: Current schedules (PRIMARY)

### Salary/Contract Data
- **Spotrac scraper**: Unknown quality (TEST)
- **nflreadpy load_contracts()**: Available (COMPARE)

### Rosters & Depth Charts
- **nfldata**: 2006-present (REFERENCE)
- **nflreadpy**: Current and weekly (PRIMARY)

## Quick Action Items

### Immediate (Do Now)
1. Add nflreadpy to project dependencies
2. Extract nfldata /data directory (10MB)
3. Verify NFL Stats 2012-2024 cached data quality

### Short Term (This Week)
4. Test nflreadpy data fetching for 2022-2025 drafts
5. Validate cached datasets have compatible schemas
6. Create player ID mapping strategy

### Medium Term (This Month)
7. Test Spotrac scraper vs nflreadpy contracts
8. Set up automated nflreadpy data refreshes
9. Archive 6 redundant repositories

### Cleanup
10. Remove archived repo clones (save 7.8GB)
11. Document final data architecture
12. Create unified data loading utilities

## Player ID Mapping

| ID Type | Used In | Coverage | Primary? |
|---------|---------|----------|----------|
| nflverse player_id | NFL Stats cache, nflreadpy | Most comprehensive | YES |
| PFR pfr_id | nfldata files | 2000+ | Secondary |
| ESPN player_id/guid | nfl-draft-data | Draft prospects | Secondary |
| NFL.com URL | NFL-Statistics-Scrape | Historical | Archive only |

**Strategy**: Use nflverse player_id as primary key, maintain mapping table to other systems.

## Storage Optimization

**Current State:**
- 9 repositories: 7.9 GB
- 4 cached datasets: 576 MB
- **Total: 8.5 GB**

**After Cleanup:**
- Keep nflreadpy repo: 1.5 MB
- Extract nfldata data: 10 MB
- Keep cached datasets: 576 MB
- **Total: ~590 MB (93% reduction)**

## Data Freshness

| Source | Update Frequency | Action Required |
|--------|-----------------|-----------------|
| nflreadpy | Daily (automated) | Set up periodic fetches |
| NFL Stats cache | Manual (2024) | Update for 2025 season |
| NFL_Scraper cache | Manual (Week 7 2025) | Monitor for updates |
| nfldata | Daily (automated) | Download periodically |
| Draft data cache | Static (2021) | Fetch 2022-2025 from nflreadpy |

## Integration Priority

1. **Phase 1**: Integrate nflreadpy + use existing cached datasets
2. **Phase 2**: Fill data gaps (2022-2025 drafts, current season)
3. **Phase 3**: Set up automated updates
4. **Phase 4**: Build unified data loading layer
5. **Phase 5**: Clean up and archive old repos

---

**Document Created:** 2025-10-27
**Related:** `NFL_DATA_INVENTORY.md` (comprehensive analysis)
