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

## Key Patterns

_Document important patterns, conventions, or decisions specific to this project here._
