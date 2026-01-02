# Script-to-Function Refactor Plan

## Goal
Move script logic into reusable functions while keeping scripts as thin CLI wrappers.

## Prototype: clean_depth_charts.py

**Why this one first:**
- Simple, focused task (CSV splitting)
- No external dependencies (no Selenium, web APIs, etc.)
- Clear inputs/outputs
- Fast to test

## Step-by-Step Plan

### 1. Create processors module structure
```
src/gridiron_yampylytics/
├── processors/
│   ├── __init__.py
│   └── depth_charts.py  (NEW - contains the actual logic)
```

### 2. Extract logic to function
**File:** `src/gridiron_yampylytics/processors/depth_charts.py`

**Function signature:**
```python
def clean_depth_charts(
    input_file: Path | None = None,
    output_dir: Path | None = None
) -> dict[str, Any]:
    """Split depth charts into legacy and modern schemas.

    :param input_file: Path to depth_charts.csv (default: data/nflverse/depth_charts.csv)
    :param output_dir: Output directory (default: data/nflverse/)
    :return: Summary dict with counts and file paths
    """
```

**Return value example:**
```python
{
    'legacy_rows': 869185,
    'modern_rows': 297750,
    'legacy_file': Path('data/nflverse/depth_charts_legacy.csv'),
    'modern_file': Path('data/nflverse/depth_charts_modern.csv'),
    'legacy_size_bytes': 78679461,
    'modern_size_bytes': 28422686,
}
```

### 3. Update script to thin wrapper
**File:** `scripts/clean_depth_charts.py`

**New implementation:**
```python
"""CLI wrapper for depth charts cleaning."""
import sys
from gridiron_yampylytics.processors.depth_charts import clean_depth_charts

def main() -> None:
    """CLI entry point."""
    sys.stdout.reconfigure(encoding='utf-8')
    clean_depth_charts()

if __name__ == "__main__":
    main()
```

### 4. Update invoke task
**File:** `tasks.py`

**Change from:**
```python
@task
def clean_depth_charts(c):
    """..."""
    c.run('uv run python -m scripts.clean_depth_charts')
```

**Change to:**
```python
from gridiron_yampylytics.processors.depth_charts import clean_depth_charts as clean_depth_charts_fn

@task
def clean_depth_charts(c):
    """The depth charts change schema in 2024-2025 and need to be separated into legacy and modern datasets to be
    usable.  This completes that operation.
    """
    result = clean_depth_charts_fn()
    print(f"\n✓ Split complete: {result['legacy_rows']:,} legacy + {result['modern_rows']:,} modern rows")
```

### 5. Test the refactor
```bash
# Test via invoke
inv clean-depth-charts

# Test via script (should still work)
uv run python -m scripts.clean_depth_charts

# Test via direct import (new capability!)
uv run python -c "from gridiron_yampylytics.processors.depth_charts import clean_depth_charts; clean_depth_charts()"
```

## Benefits Achieved

1. ✅ Stdout visible in invoke (no subprocess)
2. ✅ Reusable function (can import elsewhere)
3. ✅ Testable (unit test the function)
4. ✅ Type hints work (IDE autocomplete)
5. ✅ Returns structured data (not just prints)
6. ✅ Script still works (backward compatible)

## Future Scope

Once this prototype is proven, apply same pattern to:

**Processors (data transformation):**
- combine_gm_data.py → processors/gm_data.py
- generate_yamplayer_id.py → processors/yamplayer_id.py
- calculate_yas.py → processors/yas.py

**Loaders (data acquisition):**
- download_gm_data.py → loaders/gm_data.py
- cache_nflreadpy_data.py → loaders/nflverse.py
- load_all_data.py → loaders/all_data.py

**Database creators:**
- create_duckdb_views.py → database/views.py
- create_duckdb_tables.py → database/tables.py

## Decision: Keep or Remove Scripts?

**For now:** Keep scripts as thin CLI wrappers (backward compatibility)

**Long term:** Likely remove once invoke is the primary interface
- Invoke provides better discoverability (`inv --list`)
- Invoke provides help text (`inv --help clean-depth-charts`)
- Invoke allows composition (tasks can call other tasks)

## Success Criteria

- ✅ Script runs identically to before
- ✅ Invoke task shows output
- ✅ Function can be imported and used elsewhere
- ✅ Function has proper type hints
- ✅ Function returns structured data (not just prints)
- ✅ Manifest updates still work
