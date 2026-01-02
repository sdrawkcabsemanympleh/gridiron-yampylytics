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

- Full reST docstrings on every function, method, and class.  This should almost always include the list of paramaters and such.
- Type annotations on everything.  I plan to utilize mypy and ruff on everything we work on.
- Keep whitespace to minimum; only that which is required by pep8.  No other line breaks within functions or methods.  
  - There's wiggle room on this in scripts and test files :)
  - Inline comments should be kept on the same line as the code they refer to if they can fit
- Never create multi-line or nested list comprehension.
- Use descriptive names.  We don't get dinged for character count, but we will be angry at ourselves later if we don't know what we did.  This doesn't necessarily mean no one letter variables--use those when one letter communicates the purpose of a variable.  Examples:
  - i, j for indexes - These are still descriptive even as one letter.  They communicate an index.
  - x or similar in list comprehension or lambdas.  Another case where lack of description is a description.
- Lazy loading shouldn't be done without a very good reason

## Working Agreement

First and foremost, remember that we're working together.  This is collaborative, and your thoughts and observations matter.  I'd like to be very conversational about things.  Some key points:
- I try to be clear if I want you to make changes or go do something.  I like to ask questions and understand what you're doing, what you're seeing, and why.  So remember that questions are actually questions, and to err on the side of answering rather than doing.
- With that, don't feel pressure to go and do a thing immediately.  It's natural to think of that as the instruction, but I want you to always consider coming back partway through with questions, thoughts, suggestions, concerns, or pushback just as valid.  In fact, it's frequently more important that you do.
- We aren't in a hurry, and we can take a few more prompts to do it, and do it right.  The process is what matters, and it's what will get us our best work.
- Your opinion matters, and your judgement is both sound and important.

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
