# Fancy Console UI Implementation Plan

**Created:** 2025-12-31
**Status:** Planning → Implementation
**Goal:** Transform parallel data loader console output from verbose logging to beautiful rich-based UI

---

## Why We're Doing This

The current parallel loader works great but dumps a wall of logs. For a polished tool, we want:
- Live-updating status table showing parallel progress
- Clear visual feedback (what's running, what's done, what failed)
- Professional appearance (this is a toolkit we're proud of)
- Verbose fallback for debugging and non-TTY environments

This is also a learning opportunity - exploring rich library capabilities and thread-safe UI updates.

---

## What We're Building - Visual Reference

### Download Phase (Mid-Progress)
```
╭──────────────────────────────────────────────────────────────────────────────╮
│                     🏈 NFL DATA DOWNLOAD - PARALLEL MODE                      │
├──────────────────────────────────────────────────────────────────────────────┤
│ Configuration:                                                                │
│   • Datasets: combine, rosters, draft_picks, player_stats, injuries + GM     │
│   • Seasons: all available                                                    │
│   • Workers: 8 parallel threads                                               │
╰──────────────────────────────────────────────────────────────────────────────╯

┏━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━┓
┃ Dataset         ┃ Status         ┃ Rows     ┃ Progress              ┃ Time   ┃
┡━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━┩
│ combine         │ ✅ Complete    │    8,649 │ ████████████████████  │   2.3s │
│ rosters         │ ⚙️  Downloading │  139,681 │ ███████████████░░░░░  │   5.1s │
│ draft_picks     │ ✅ Complete    │   12,670 │ ████████████████████  │   1.8s │
│ player_stats    │ ⚙️  Downloading │  474,207 │ ████████░░░░░░░░░░░░  │   8.7s │
│ injuries        │ ⚙️  Downloading │   84,684 │ ██████████░░░░░░░░░░  │   4.2s │
│ gm_data         │ ⚙️  Scraping    │   18/32  │ ███████████░░░░░░░░░  │  67.3s │
└─────────────────┴────────────────┴──────────┴───────────────────────┴────────┘

NFLverse: 2/5 complete │ GM: 18/32 teams │ Elapsed: 68.4s │ ETA: ~45s
```

### Processing Phase
```
╭──────────────────────────────────────────────────────────────────────────────╮
│                        🔧 PROCESSING DATA PIPELINE                            │
├──────────────────────────────────────────────────────────────────────────────┤
│ Configuration: [same as above]                                               │
╰──────────────────────────────────────────────────────────────────────────────╯

┏━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━┓
┃ Step                   ┃ Status         ┃ Progress              ┃ Time   ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━┩
│ clean_depth_charts     │ ✅ Complete    │ ████████████████████  │   3.2s │
│ combine_gm_data        │ ✅ Complete    │ ████████████████████  │   0.8s │
│ generate_yamplayer_id  │ ⚙️  Processing  │ ██████████░░░░░░░░░░  │  12.4s │
│ calculate_yas          │ ⏳ Pending     │ ░░░░░░░░░░░░░░░░░░░░  │   0.0s │
└────────────────────────┴────────────────┴───────────────────────┴────────┘

Processing yamplayer_id: 25,431/43,110 players matched (59%)
```

**Key User Feedback:** Keep configuration header visible through all phases (not just initial state)

---

## Architecture

```
download_data.py (CLI)
    │
    ├─> Parse --verbose flag
    ├─> Build config dict
    └─> Create ConsoleUI(mode, config)
            │
            ├─> if TTY and not verbose: fancy mode
            ├─> else: verbose mode (fallback)
            │
            └─> Pass ui to parallel_loader
                    │
                    └─> Worker threads emit status updates
                            │
                            └─> ui.update_dataset() [thread-safe]
                                    │
                                    └─> rich.Live refreshes display
```

### Key Components

**1. ConsoleUI Class** (`src/gridiron_yampylytics/ui/console.py`)
- Manages rich Console, Table, Live instances
- Tracks dataset/task states
- Thread-safe update methods
- Context manager for clean setup/teardown
- Mode detection (TTY, verbose flag)

**2. TaskStatus Enum**
- PENDING: ⏳ Gray
- RUNNING: ⚙️  Yellow
- COMPLETE: ✅ Green
- FAILED: ❌ Red
- PARTIAL: ⚠️  Orange

**3. Update Flow**
```python
# Worker thread (safe to call from any thread)
ui.update_dataset(
    name="combine",
    status=TaskStatus.RUNNING,
    rows=8649,
    progress=1.0
)

# UI updates internal state, rich.Live handles refresh
```

---

## Critical Technical Considerations

### Thread Safety
- **Challenge:** Multiple worker threads updating UI simultaneously
- **Solution:** rich.Live handles display refresh locking internally
- **Pattern:** Worker threads call ui.update_dataset(), which updates internal state
- **Refresh:** rich.Live periodically redraws (default 4 FPS)
- **Need to verify:** Whether we need additional locks for state dict updates

### TTY Detection
```python
import sys
is_tty = sys.stdout.isatty()

# Auto-fallback to verbose if:
# - Not a TTY (piped output, file redirect)
# - User passes --verbose flag
# - rich.Live fails to initialize
```

### Progress Calculation
- **NFLverse datasets:** 0.0 → 1.0 (binary: pending → complete)
- **GM scraper:** teams_scraped / 32 (incremental progress)
- **yamplayer_id:** players_matched / total_players

### Error Handling
- Don't crash if rich fails - fallback to verbose
- Handle Ctrl+C gracefully (show final table before exit)
- Display partial results if some downloads fail

---

## Implementation Phases

### ✅ Phase 0: Planning
- [x] Create visual mockups
- [x] Get user feedback
- [x] Write implementation plan
- [x] Create this document

### ✅ Phase 1: Foundation (Low Risk) - COMPLETE
**Goal:** Get infrastructure in place without breaking anything

- [x] Add `rich = "^13.7.0"` to pyproject.toml dependencies
- [x] Run `uv sync` to install rich
- [x] Create `src/gridiron_yampylytics/ui/__init__.py`
- [x] Create `src/gridiron_yampylytics/ui/console.py` (skeleton)
- [x] Implement basic ConsoleUI class:
  - `__init__(mode, config)`
  - `__enter__` / `__exit__` (context manager)
  - Mode detection (TTY check)
  - Stub methods for update_dataset(), update_processing()
- [x] Add `--verbose` flag to scripts/download_data.py
- [x] Test: Download still works with and without --verbose flag (no changes yet)

**Success Criteria:** ✅ Verbose mode unchanged, infrastructure in place
**Completion Date:** 2025-12-31

### ⬜ Phase 2: Download Display (Core Feature)
**Goal:** Show live table during parallel downloads

- [ ] Implement ConsoleUI.update_dataset():
  - Track dataset states in dict
  - Build rich.Table from current state
  - Return table for Live display
- [ ] Implement ConsoleUI._create_download_table()
  - Configuration panel at top
  - Dataset status table
  - Summary footer
- [ ] Modify parallel_loader.py:
  - Accept optional `ui` parameter
  - Add ui.update_dataset() calls at key points:
    - Start download: status=RUNNING
    - Download complete: status=COMPLETE, rows=count
    - Download failed: status=FAILED, error=msg
  - Keep print() fallback if ui=None
- [ ] Test with small dataset: `inv load-data --datasets=combine`
- [ ] Test verbose fallback: `inv load-data --datasets=combine --verbose`
- [ ] Test error handling: disconnect network mid-download

**Success Criteria:** Live table updates during download, verbose mode still works

### ⬜ Phase 3: Processing Display (Extension)
**Goal:** Show processing pipeline tasks

- [ ] Implement ConsoleUI.update_processing():
  - Similar to update_dataset but for processing tasks
  - Track: clean_depth_charts, combine_gm_data, etc.
- [ ] Implement ConsoleUI._create_processing_table()
- [ ] Modify tasks in tasks.py:
  - Pass ui to process_data()
  - Add ui.update_processing() calls in each task
  - Handle ui=None gracefully
- [ ] Test full pipeline: `inv setup-quick`

**Success Criteria:** Processing steps show in table after download completes

### ⬜ Phase 4: Polish (Nice-to-Haves)
**Goal:** Make it feel professional

- [ ] Add ETA calculation:
  - Track start time per dataset
  - Estimate remaining time based on completed tasks
- [ ] Add final summary panel:
  - Total rows downloaded
  - Success/failure counts
  - Total elapsed time
- [ ] Improve GM scraper progress:
  - Show "18/32 teams" instead of just percentage
  - Update incrementally as teams complete
- [ ] Add spinner for long-running tasks
- [ ] Handle edge cases:
  - Window resize (rich handles this)
  - Ctrl+C interrupt (show final state)
  - Very long dataset names (truncate)

**Success Criteria:** Polished, professional appearance

---

## Open Questions & Decisions

### Q1: Thread Safety for State Updates
**Question:** Do we need locks when updating self.datasets dict from worker threads?
**Current Thinking:** Python GIL might protect us for simple dict updates, but should verify
**Decision:** TBD - test with parallel downloads and watch for race conditions
**Action:** Add logging to detect concurrent updates in Phase 2 testing

### Q2: Progress Bar Granularity
**Question:** Do we want actual progress bars (rich.Progress) or just filled/unfilled blocks?
**Current Thinking:** Blocks are simpler and cleaner for our use case
**Decision:** TBD - implement blocks first, can add rich.Progress later if needed

### Q3: GM Scraper Integration
**Question:** How to get incremental progress from GM scraper (currently opaque)?
**Current Thinking:** Modify download_gm_data() to yield progress events
**Decision:** TBD - might be Phase 4 enhancement
**Action:** Check gm_data.py structure in Phase 2

### Q4: Configuration Panel Persistence
**Question:** Keep config header through all phases or just download?
**Decision:** ✅ DECIDED - Keep it visible throughout (user feedback)
**Implementation:** Include config in both download and processing table builders

---

## Key Code Patterns

### Pattern 1: Thread-Safe Status Updates
```python
# In worker thread (parallel_loader.py)
def download_combine(ui: Optional[ConsoleUI] = None):
    if ui:
        ui.update_dataset("combine", TaskStatus.RUNNING)

    # ... download logic ...

    if ui:
        ui.update_dataset("combine", TaskStatus.COMPLETE, rows=8649)
    else:
        print("✓ Saved 8,649 rows to combine.csv")
```

### Pattern 2: ConsoleUI Context Manager
```python
# In download_data.py
with ConsoleUI(mode="fancy", config=config) as ui:
    result = download_datasets_parallel(
        nflverse_datasets=datasets,
        ui=ui
    )
# Auto-cleanup happens in __exit__
```

### Pattern 3: Graceful Fallback
```python
class ConsoleUI:
    def __init__(self, mode: str = "fancy", config: dict = None):
        self.mode = mode

        # Force verbose if not TTY
        if not sys.stdout.isatty():
            self.mode = "verbose"

        # Try to initialize rich, fallback on failure
        try:
            if self.mode == "fancy":
                self.console = Console()
                self.live = Live(...)
        except Exception:
            self.mode = "verbose"  # Graceful degradation
```

---

## Testing Checklist

### Unit Tests
- [ ] ConsoleUI mode detection (TTY vs non-TTY)
- [ ] Status updates don't crash with concurrent calls
- [ ] Table generation with various states
- [ ] Graceful fallback when rich unavailable

### Integration Tests
- [ ] Small download (combine only) - fancy mode
- [ ] Small download - verbose mode
- [ ] Full download with failures - fancy mode
- [ ] Processing pipeline - fancy mode
- [ ] Ctrl+C interrupt - clean exit

### Manual Testing Scenarios
- [ ] Run in PyCharm terminal (TTY)
- [ ] Run in CMD/PowerShell (TTY)
- [ ] Pipe to file: `inv load-data > output.log` (non-TTY)
- [ ] SSH session (might not be TTY)
- [ ] Disconnect network mid-download (error handling)

---

## Progress Tracking

**Current Phase:** Phase 1 (Foundation) ✅
**Next Phase:** Phase 2 (Download Display)
**Estimated Total Time:** ~4 hours
**Actual Time:** TBD

### Session Log
- **2025-12-31 (Session 1):** Created implementation plan, discussed with user, aligned on approach
- **2025-12-31 (Session 1):** Completed Phase 1 - Infrastructure in place, no breaking changes

---

## Notes & Learnings

### Design Decisions
- User feedback: Keep configuration header visible through all phases
- Prioritize clarity over fancy animations
- Verbose mode must work identically to current behavior (no regressions)

### Things to Watch Out For
- Thread safety in state updates (verify during Phase 2 testing)
- TTY detection edge cases (SSH, PyCharm, WSL)
- Performance impact of Live display refresh (probably negligible)
- Long dataset names breaking table layout

### Future Enhancements (Post-V1)
- Color customization via config file
- JSON output mode for programmatic use
- Detailed timing breakdowns (network vs disk I/O)
- Progress persistence (resume interrupted downloads)

---

## References

- rich documentation: https://rich.readthedocs.io/
- rich.Live examples: https://rich.readthedocs.io/en/stable/live.html
- ThreadPoolExecutor + UI: https://github.com/Textualize/rich/discussions/1381

---

**Last Updated:** 2025-12-31
**Next Review:** After Phase 1 completion
