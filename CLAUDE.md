# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**gridiron-yampylytics** - NFL and college football data analysis, scraping, and visualization toolkit

## Development Commands

**Install dependencies:**
```bash
uv sync
```

**Run tests:**
```bash
uv run pytest
uv run pytest tests/test_specific.py  # Run specific test file
```

**Check code style:**
```bash
uv run ruff check .
uv run ruff check . --fix  # Auto-fix issues
uv run mypy src/
```

**Format code:**
```bash
uv run ruff format .
```

## Project Structure

```
gridiron-yampylytics/
├── src/
│   └── gridiron_yampylytics/     # Main package code
├── tests/                  # Test files
├── scripts/                # Utility scripts (if present)
└── README.md
```

## Style Guidelines

Follow the Python style guidelines:
- Full reST docstrings on every function, method, and class
- Type annotations on everything
- Minimal whitespace (PEP8 required only)
- No multi-line or nested list comprehensions
- Descriptive variable names
- No lazy imports without good reason

## Architecture Notes

_Add project-specific architectural decisions and patterns here as the project develops._

## Custom Agents

### NFL Data Expert Agent

**Purpose:** Deep expertise on all NFL data sources, schemas, coverage, and usage patterns

**When to use:**
- Before loading data from any source
- When unsure about dataset schemas or field names
- Need to know which dataset contains specific data
- Planning data joins (which player IDs to use)
- Questions about data quality, coverage gaps, or quirks

**How to invoke:**
```
Use the Skill tool with: nfl-data-expert
```

**What the agent knows:**
- All nflreadpy functions and their outputs
- nfldata CSV files (games.csv, draft_picks.csv, etc.)
- Cached datasets and their coverage
- Player ID linking strategy (gsis_id vs pfr_id vs espn_id)
- Data quality issues and known gaps
- Code examples for common data operations

**Response format:**
The agent provides: direct answer, source dataset(s), code example, caveats, and alternatives

**Recommended workflow:**
1. Encounter data task
2. Ask agent for best approach
3. Get schema + code example
4. Implement with confidence

This agent saves time and prevents errors when working with NFL data.

## Key Patterns

_Document important patterns, conventions, or decisions specific to this project here._
