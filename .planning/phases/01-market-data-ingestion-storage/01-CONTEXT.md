# Phase 1: Market Data Ingestion & Storage — Context

**Gathered:** 2026-11-09
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 1 delivers the foundational market data infrastructure for Claude Trading. It ingests historical and live market data (OHLCV, quotes, volume) from Alpaca Markets (using the active paper credentials) and Yahoo Finance, normalizes bars into typed records, and caches them in a local SQLite database for fast querying by technical indicators and the strategy engine.
</domain>

<decisions>
## Implementation Decisions

### Data Providers
- Primary Provider: Alpaca Market Data v2 API (`https://data.alpaca.markets/v2`) using `APCA_API_KEY_ID` and `APCA_API_SECRET_KEY` from `.env`.
- Supplementary/Fallback Provider: Yahoo Finance (`yfinance` or direct HTTP) for historical daily/intraday bars and free relative volume (RVOL) calculations.

### Data Model & Standardization
- Normalized `Bar` schema: `timestamp` (ISO UTC), `open`, `high`, `low`, `close`, `volume`, `vwap`.
- Timeframes supported: `1m`, `5m`, `15m`, `1d`.

### Storage Engine
- Local SQLite database stored at `data/market_data.db`.
- Indexed on `(symbol, timeframe, timestamp)` with `INSERT OR REPLACE` upsert semantics.
- Fast query interface: `get_bars(symbol, timeframe, limit, start_time, end_time)`.

### Claude's Discretion
- Project structure: `src/data/` for data adapters, `src/storage/` for SQLite database operations.
</decisions>

<canonical_refs>
## Canonical References
- `.planning/REQUIREMENTS.md` — DATA-01, DATA-02
- `.planning/ROADMAP.md` — Phase 1 Goal & Success Criteria
- `.claude/skills/trader-scanner/scan.py` — Reference patterns for scanning and bar fetching
</canonical_refs>
