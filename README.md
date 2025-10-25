# gridiron-yampylytics

NFL and college football data analysis, scraping, and visualization toolkit

## Setup

Install dependencies:
```bash
uv sync
```

## Development

**Run tests:**
```bash
uv run pytest
```

**Check code style:**
```bash
uv run ruff check .
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
└── scripts/                # Utility scripts
```
