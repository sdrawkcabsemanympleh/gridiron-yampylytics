# Performance & Parallelization Investigation

**Status:** ✅ COMPLETE - DataFrame optimization implemented (5.3x speedup!)
**Target:** YAS calculation performance optimization
**Date Started:** 2025-12-09
**Date Completed:** 2025-12-28

---

## Executive Summary

### Performance Improvement Achieved: **28.8x FASTER** 🚀🚀🚀

- **Original (DuckDB):** 24.49 seconds
- **DataFrame (loop positions):** 4.62 seconds (5.3x faster)
- **GroupBy (vectorized):** **0.85 seconds** (28.8x faster than original!)
- **Total speedup:** 28.8x (2,780% faster)
- **Time saved:** 23.64 seconds per run

### Key Changes

1. **Eliminated DuckDB queries** - Replaced 4,160+ queries with DataFrame filters
2. **Eliminated merge operations** - Calculate all percentiles in single DataFrame, no merging needed
3. **Eliminated position loops** - Use pandas groupby to process all positions vectorized
4. **Vectorized percentile calculations** - `groupby().rank()` instead of per-position rank
5. **Class-based architecture** - New `YasCalculator` class with static caching for reusability
6. **Simplified code** - Cleaner implementation, easier to maintain

### Bottleneck Analysis

**Original Bottleneck (DuckDB approach):**
```
DuckDB queries:    8.50s  (45.6%)  ← PRIMARY BOTTLENECK
DataFrame merges:  6.10s  (32.7%)  ← SECONDARY BOTTLENECK
Percentile calcs:  2.96s  (15.9%)
Final score calc:  1.10s  (5.9%)
Overhead/other:    5.84s  (23.8%)
```

**Second Bottleneck (DataFrame loop approach):**
```
Percentile calcs:  1.34s  (40.0%)  ← Now the bottleneck (but faster overall!)
Final score calc:  1.24s  (36.9%)
DataFrame filters: 0.77s  (23.1%)
Overhead/other:    1.27s  (27.5%)
```

**Final Bottleneck (GroupBy vectorized approach):**
```
Row expansion:     0.50s  (64.1%)  ← Expanding DataFrame for all positions
Percentile calcs:  0.17s  (22.5%)  ← Vectorized with groupby!
Final score calc:  0.09s  (11.1%)
DataFrame filters: 0.02s  (2.4%)   ← Nearly free!
Overhead/other:    0.08s  (9.0%)
```

### Decision: Parallelization NOT Needed (YAGNI)

With **0.85 second** total runtime (under 1 second!), parallelization would only save ~0.6 seconds. At this speed, the overhead of multiprocessing would likely SLOW IT DOWN rather than speed it up.

**Recommendation:** Ship it! This is blazing fast! 🎉

---

## The Opportunity

YAS calculation processes 26 years of combine data (2000-2025) sequentially. Each year involves:
1. Loading data into DuckDB
2. Calculating percentiles across multiple measurables
3. Merging and normalizing scores
4. Repeating for all positions

**Hypothesis:** Parallelization could significantly speed this up since years are independent.

## Python Parallelization Landscape

### The GIL Problem
- Python's Global Interpreter Lock (GIL) prevents true multithreading for CPU-bound tasks
- **Threading:** Only helps with I/O-bound operations (network, disk)
- **Multiprocessing:** Spawns separate processes, each with own GIL → true parallelism

### Is Multiprocessing Appropriate?
**YES!** It's the standard way to do parallel CPU work in Python.
- Used by pandas, scikit-learn, numpy
- Completely normal and expected
- Should be configurable (let users control worker count)

## Profiling Plan: Find the Bottlenecks

**Before optimizing, measure!** (YAGNI - You Ain't Gonna Need It)

### Level 1: Per-Year Timing
```python
import time

# Time a single year
start = time.time()
calculate_year_yas(connection, 2024)
print(f"One year: {time.time() - start:.2f}s")

# Extrapolate: 26 years × time_per_year = total_time
```

**Decision point:** If one year < 1 second, total is ~26 seconds → maybe good enough?

### Level 2: Within-Year Breakdown
Need to profile **where time is spent within each year:**

```python
import time

def calculate_year_yas_profiled(connection, year):
    timings = {}

    # 1. DuckDB data loading
    start = time.time()
    # ... data loading logic ...
    timings['duckdb_load'] = time.time() - start

    # 2. Position calculations loop
    start = time.time()
    for position in positions:
        # ... position logic ...
    timings['position_calculations'] = time.time() - start

    # 3. Percentile calculations
    start = time.time()
    # ... percentile logic ...
    timings['percentiles'] = time.time() - start

    # 4. Merging/normalization
    start = time.time()
    # ... merge logic ...
    timings['merge_normalize'] = time.time() - start

    return result, timings
```

**Questions to answer:**
- Is DuckDB loading the bottleneck?
- Are percentile calculations the bottleneck?
- Are pandas operations (merging, normalizing) the bottleneck?
- Does DuckDB already parallelize internally?

### Key Question: DuckDB vs Pandas Performance
**Need to investigate:**
- DuckDB may already parallelize queries internally
- Loading into DuckDB in parallel might not help (or might conflict)
- Percentile calculations in pandas might be the real bottleneck

**Alternative approach:** Skip DuckDB entirely
- Load combine data into pandas DataFrame once
- Use `groupby()` operations for filtering by position/year
- Gives us full control over where to fork/parallelize
- Memory: 8,649 rows × ~20 columns = negligible (< 10MB)
- Probably won't blow up memory unless running on a potato 🥔

**Where to fork matters:**
- Option A: Fork before DuckDB load (each process has own connection)
- Option B: Fork after DuckDB load (shared data, parallel calculations)
- Option C: Fork per-position within year (finer granularity)

## Implementation Plan

### Phase 1: Profile Current Implementation ✋ START HERE
1. Add timing instrumentation to `calculate_year_yas()`
2. Run on representative data (full 2000-2025 range)
3. Collect metrics:
   - Total time
   - Per-year time
   - Within-year breakdown (DuckDB, calculations, merges)
4. Identify actual bottleneck

### Phase 2: Design Parallelization Strategy
Based on profiling results:
- **If DuckDB is bottleneck:** Consider alternatives or accept it
- **If calculations are bottleneck:** Parallelize per-year or per-position
- **If already fast enough:** Stop here (YAGNI)

### Phase 3: Implement Parallel Version (if needed)
```python
def calculate_yas(
    combine_csv: Path | None = None,
    output_file: Path | None = None,
    base_dir: Path | None = None,
    workers: int | None = None  # None = auto, 1 = serial, N = parallel
) -> dict[str, Any]:
    """
    :param workers: Number of parallel workers (None = os.cpu_count(), 1 = no parallelism)
    """
    import os
    import concurrent.futures

    if workers is None:
        workers = os.cpu_count()  # Default: use all cores

    if workers > 1:
        # Parallel execution
        with concurrent.futures.ProcessPoolExecutor(max_workers=workers) as executor:
            futures = [
                executor.submit(calculate_year_yas, connection, year)
                for year in range(2000, 2026)
            ]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]
    else:
        # Serial execution (debugging, low resources, profiling)
        results = [calculate_year_yas(connection, year) for year in range(2000, 2026)]

    # Combine results...
    return combined_results
```

### Phase 4: Benchmark & Validate
- Compare serial vs parallel performance
- Verify results match (bit-for-bit identical)
- Test on different hardware (2-core, 8-core, 16-core)
- Ensure memory usage is reasonable

## Other Parallelization Candidates

### High Value
- **`calculate_yas.py`** - CPU-bound, independent years → **multiprocessing**

### Medium Value
- **`cache_nflreadpy_data.py`** - I/O-bound, multiple datasets → **threading** or **asyncio**
  - Could download combine, rosters, stats concurrently
  - Network latency is bottleneck, not CPU

### Low Value (Don't Bother)
- **`generate_yamplayer_id.py`** - DuckDB already optimized internally
- **`download_gm_data.py`** - Has intentional rate limiting (don't be rude to server)

## Technical Considerations

### DuckDB Parallelism
- DuckDB parallelizes queries internally by default
- Creating multiple connections might not help (or might hurt)
- Need to test: shared connection vs per-process connection

### Memory Constraints
- Each process duplicates memory
- Combine dataset: ~8,649 rows (small, not a concern)
- But duplicating DuckDB connections × N processes could add up
- Monitor with `workers=2` first, then scale

### Error Handling
- Process crashes should be caught
- Use `concurrent.futures` (cleaner error handling than raw `multiprocessing`)
- Log which year/position failed

### Configurability
Best practices:
- Default: `workers=None` → auto-detect (`os.cpu_count()`)
- Allow: `workers=1` → force serial (debugging, profiling)
- Allow: `workers=N` → user-specified (CI/CD, resource limits)

## Success Criteria

**Optimization is worth it if:**
- Speedup ≥ 2x with parallelization
- Memory increase is reasonable (< 2GB total)
- Results are identical to serial version
- Code complexity increase is justified

**Stop if:**
- Current performance is "fast enough" (< 1 minute total)
- Bottleneck is I/O or DuckDB (parallelization won't help)
- Speedup < 1.5x (not worth maintenance burden)

## Next Steps

1. **Create profiling branch:** `feature/yas-profiling`
2. **Add timing instrumentation** to `calculate_year_yas()`
3. **Run profiling** on full dataset
4. **Analyze results** and decide on strategy
5. **Document findings** here
6. **Implement if justified**

---

## Implementation Results (2025-12-28)

### Phase 1: Profiling the DuckDB Approach ✅

**Branch:** `feature/yas-profiling`

**Level 1 Profiling Results (Per-Year Timing):**
```
Total time:    24.49s
Average/year:  0.90s
Min time:      0.62s
Max time:      1.23s
Years:         26

Parallelization Potential:
  CPU cores:         8
  Estimated parallel: 5.47s
  Estimated speedup: 4.48x
  Time savings:      19.02s
```

**Level 2 Profiling Results (Within-Year Breakdown):**
```
DuckDB queries:    8.50s  (45.6%)  ← PRIMARY BOTTLENECK
DataFrame merges:  6.10s  (32.7%)  ← SECONDARY BOTTLENECK
Percentile calcs:  2.96s  (15.9%)
Final score calc:  1.10s  (5.9%)
Overhead/other:    5.84s  (23.8%)
---
Total profiled:    18.65s
Actual total:      24.49s
```

**Key Finding:** DuckDB queries were the bottleneck, NOT percentile calculations!

### Phase 2: DataFrame Optimization Implementation ✅

**Hypothesis:** Eliminate DuckDB queries by using pure pandas DataFrame operations.

**Implementation Details:**

1. **Created `YasCalculator` class** with class-level data caching
2. **Replaced query loop** with single DataFrame filter per position/year
3. **Eliminated merge operations** by calculating all percentiles in same DataFrame
4. **Kept legacy functions** for backward compatibility

**Code Changes:**
- Added `YasCalculator` class with methods:
  - `get_combine_data()` - Lazy load combine CSV with caching
  - `refresh_combine_data()` - Force reload and clear cache
  - `calculate_position_yas_scores()` - DataFrame filtering + vectorized percentiles
  - `calculate_year_yas()` - Loop positions, no DuckDB
  - `calculate_all_yas()` - Main entry point with profiling
- Updated `calculate_yas()` function to use new class
- Kept old DuckDB functions as "Legacy" (backward compatible)

**Architecture Benefits:**
- ✅ Thread-safe (returns `.copy()` of data)
- ✅ Reusable across multiple calculations
- ✅ Can cache results in future
- ✅ Simpler code (no SQL generation)

### Phase 3: Benchmark Results ✅

**DataFrame Approach Performance:**
```
Total time:    4.62s  ← 5.3x FASTER!
Average/year:  0.17s  ← 5.3x FASTER!
Min time:      0.15s
Max time:      0.21s
Years:         26

Parallelization Potential:
  CPU cores:         8
  Estimated parallel: 1.03s
  Estimated speedup: 4.48x
  Time savings:      3.59s
```

**DataFrame Approach Breakdown:**
```
DataFrame filters: 0.77s  (23.1%)  ← Replaced 8.50s of DuckDB queries!
Percentile calcs:  1.34s  (40.0%)  ← Now the bottleneck
Final score calc:  1.24s  (36.9%)
Overhead/other:    1.27s  (27.5%)
---
Total profiled:    3.35s
Actual total:      4.62s
```

### Performance Comparison Table

| Metric | DuckDB Approach | DataFrame Approach | Improvement |
|--------|----------------|-------------------|-------------|
| **Total Time** | 24.49s | 4.62s | **5.3x faster** |
| **Avg/Year** | 0.90s | 0.17s | **5.3x faster** |
| **Query Time** | 8.50s | 0.77s (filters) | **11x faster** |
| **Merge Time** | 6.10s | 0s (eliminated!) | **∞ faster** |
| **Percentile Calc** | 2.96s | 1.34s | **2.2x faster** |
| **Primary Bottleneck** | DuckDB queries (45.6%) | Percentile calcs (40.0%) | Shifted! |

### What We Eliminated

1. **4,160+ DuckDB queries** (20 positions × 8 measurables × 26 years)
   - Each query involved parsing SQL, executing, converting to DataFrame
   - Replaced with simple DataFrame mask operations

2. **Thousands of DataFrame merge operations**
   - Each position/year had 7 merge operations (8 measurables - 1)
   - 20 positions × 26 years × 7 merges = 3,640 merges
   - Replaced with in-place column creation

3. **DuckDB connection overhead**
   - In-memory database creation, schema setup, table registration
   - Replaced with direct CSV → DataFrame load

### Phase 4: GroupBy Vectorization ✅ **GAME CHANGER!**

**Hypothesis:** Use pandas groupby to eliminate position loop and vectorize percentile calculations.

**Implementation Details:**

1. **Single filter for all positions** - Filter once per year instead of 20 times
2. **Row expansion** - Create expanded DataFrame where each player appears once per calculation_position
3. **Vectorized groupby operations** - Use `df.groupby('calculation_position')[col].rank()` instead of per-position rank
4. **Eliminated concat operations** - All positions calculated in one DataFrame

**Code Changes:**
- Rewrote `calculate_year_yas()` to use groupby instead of position loop
- Single filter + expand rows → groupby percentiles → groupby final scores
- Added `expand_time` profiling metric

### Phase 4: Benchmark Results ✅

**GroupBy Vectorized Performance:**
```
Total time:    0.85s  ← 5.4x FASTER than Phase 3!
Average/year:  0.03s  ← 5.7x FASTER per year!
Min time:      0.02s
Max time:      0.04s
Years:         26

Parallelization Potential:
  CPU cores:         8
  Estimated parallel: 0.21s
  Estimated speedup: 3.99x
  Time savings:      0.64s
```

**GroupBy Approach Breakdown:**
```
Row expansion:     0.50s  (64.1%)  ← Expanding rows for all positions
Percentile calcs:  0.17s  (22.5%)  ← Vectorized groupby!
Final score calc:  0.09s  (11.1%)
DataFrame filters: 0.02s  (2.4%)   ← Nearly instant!
Overhead/other:    0.08s  (9.0%)
---
Total profiled:    0.77s
Actual total:      0.85s
```

### Cumulative Performance Comparison Table

| Metric | DuckDB | DataFrame (loop) | GroupBy (vectorized) | Total Improvement |
|--------|--------|-----------------|---------------------|-------------------|
| **Total Time** | 24.49s | 4.62s | **0.85s** | **28.8x faster** |
| **Avg/Year** | 0.90s | 0.17s | **0.03s** | **30x faster** |
| **Filters** | 8.50s (queries) | 0.77s | **0.02s** | **425x faster** |
| **Percentile Calc** | 2.96s | 1.34s | **0.17s** | **17.4x faster** |
| **Primary Bottleneck** | Queries (45.6%) | Percentile (40.0%) | Row expand (64.1%) | Shifted twice! |

### What Phase 4 Eliminated

1. **20 position loops per year** (520 total loops for 26 years)
   - Replaced with single groupby operation per year
   - Vectorized percentile calculations across all positions simultaneously

2. **520 DataFrame filter operations** (20 positions × 26 years)
   - Reduced to 26 filter operations (one per year)
   - 20x reduction in filter overhead

3. **519 DataFrame concat operations** (20-1 per year × 26 years + 1 for current)
   - Eliminated entirely - all positions in one DataFrame from the start

### Final Decision: YAGNI on Parallelization

**Rationale:**
- **0.85 seconds is INSANELY fast** for processing 26 years of data
- Multiprocessing would save only ~0.6 seconds
- At this speed, multiprocessing overhead would likely SLOW IT DOWN
- Added complexity absolutely not justified

**We achieved sub-second performance WITHOUT parallelization!** 🎉

### Lessons Learned

1. **Profile before optimizing** - Our initial assumption (percentile calcs) was wrong
2. **Database queries are expensive** - Even in-memory DuckDB has overhead
3. **Pure pandas is often fastest** - For small-to-medium data, avoid query layers
4. **Vectorization > Parallelization** - GroupBy vectorization (5.4x) beat what multiprocessing could offer
5. **Eliminate loops when possible** - Pandas groupby can replace many manual loops
6. **YAGNI applies to performance** - 28.8x speedup made parallelization unnecessary
7. **Simplicity wins** - Fewer abstractions = faster and more maintainable
8. **Trust your intuition** - The groupby idea was spot-on and led to massive gains
9. **Multiple optimization passes compound** - 5.3x × 5.4x = 28.8x total improvement

---

## Glossary

- **GIL:** Global Interpreter Lock - Python's mechanism that prevents true multithreading
- **CPU-bound:** Operations limited by CPU speed (calculations, data processing)
- **I/O-bound:** Operations limited by I/O (network, disk, database queries)
- **YAGNI:** You Ain't Gonna Need It - don't optimize prematurely
- **ProcessPoolExecutor:** Modern Python API for multiprocessing (cleaner than raw `multiprocessing`)

## Resources

- Python `concurrent.futures` docs: https://docs.python.org/3/library/concurrent.futures.html
- DuckDB parallelism: https://duckdb.org/docs/guides/performance/environment
- Profiling with cProfile: https://docs.python.org/3/library/profile.html
