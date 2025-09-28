# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is an Implied Volatility (IV) Dashboard application that:
- Fetches and stores options/futures market data from Sensibull APIs
- Calculates IV metrics (rank, percentile, mean ratio)
- Provides a Streamlit web interface for analyzing IV data
- Uses SQLite database (sensibull.db) for data persistence

## Development Commands

### Running the application
```bash
# Run the Streamlit dashboard
uv run streamlit run app.py

# Download/update market data (fetches all FnO scripts)
uv run python download_data.py

# Run Jupyter notebook
uv run jupyter notebook
```

### Package management
```bash
# Install dependencies (uses uv package manager)
uv sync

# Add new dependencies
uv add <package-name>
```

### Python environment
- Python 3.12+ required (specified in .python-version)
- Virtual environment: `.venv/`
- Package manager: `uv` (not pip)

## Architecture

### Database Schema (SQLite - sensibull.db)
- **scripts**: FnO underlying instruments metadata (2166+ stocks/indices)
  - Primary key: instrument_token
  - Unique: tradingsymbol
- **iv**: Historical OHLC + IV data per script/date
  - Unique constraint: (script, date)
  - Contains: open, high, low, close, iv values
- **fno_scripts**: Options and futures contracts metadata
  - Unique constraint: (underlying, expiry, expiry_type, option_type, strike)
- Indexes optimized for symbol lookups and date range queries

### Key Components

**app.py**: Main Streamlit dashboard (port 8501 by default)
- `get_iv_summary()`: Calculates IV rank, percentile, and price returns over various timeframes (365-day lookback)
  - IV Rank: (current_iv - min_iv) / (max_iv - min_iv) * 100
  - IV Percentile: Percentage of days with IV <= current IV
  - Returns: 6-month, 1-month, 1-week price changes
- `plot_ohlc_iv()`: Creates candlestick charts with IV overlay using Plotly
- Renders interactive DataTable with links to Screener.in and TradingView

**download_data.py**: Data fetching and database management
- `get_io(script)`: Fetches IV/OHLC data from Sensibull API
- `get_options()`, `get_futures()`, `get_fno()`: Fetch derivatives metadata from instrument cache
- `DB` class: Handles SQLite operations with UPSERT logic (INSERT OR REPLACE)
- Tracks failures in download_errors.txt with progress bar showing success/failure counts

### External Dependencies
- Sensibull API endpoints (oxide.sensibull.com) for market data
- No authentication required for data fetching
- DataTables JS library loaded via CDN in the dashboard