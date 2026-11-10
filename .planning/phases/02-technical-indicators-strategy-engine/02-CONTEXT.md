# Phase 2: Technical Indicators & Strategy Engine — Context

**Gathered:** 2026-11-10
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 2 builds the core quantitative and algorithmic decision-making engine for Claude Trading. It takes the standardized OHLCV `Bar` data produced and stored in Phase 1, computes technical indicators (SMA, EMA, RSI, MACD, Bollinger Bands, ATR, VWAP), and feeds them into a modular, pluggable Strategy Framework that generates discrete, structured trading `Signal` instances (BUY, SELL, EXIT, HOLD) with confidence ratings and execution justifications.
</domain>

<decisions>
## Implementation Decisions

### Mathematical Indicators Engine
- Target directory: `src/indicators/`
- Architecture: Pure numerical computations using Python 3 standard library and NumPy for maximum performance, determinism, and portability (avoiding external pandas C-extension incompatibilities).
- Core Indicators:
  - **SMA** (Simple Moving Average): Rolling window mean.
  - **EMA** (Exponential Moving Average): Multiplier-weighted smoothing `k = 2 / (period + 1)`.
  - **RSI** (Relative Strength Index): 14-period Wilder's smoothed gains/losses `100 - (100 / (1 + RS))`.
  - **MACD** (Moving Average Convergence Divergence): 12-period fast EMA, 26-period slow EMA, 9-period signal line EMA, and MACD histogram.
  - **Bollinger Bands**: 20-period SMA middle band with upper/lower bands at ± `num_std` standard deviations, bandwidth, and `%B`.
  - **ATR** (Average True Range): 14-period Wilder's smoothed True Range `max(H-L, |H-Cp|, |L-Cp|)`.
  - **VWAP** (Volume Weighted Average Price): Cumulative `(Typical Price * Volume) / Cumulative Volume`.
- Dataclass containers: `MACDResult`, `BollingerBandsResult`, `IndicatorBundle`.

### Strategy Framework & Engine
- Target directory: `src/strategy/`
- Architecture: Modular abstract base `Strategy` interface with uniform `generate_signals(bars: List[Bar]) -> List[Signal]` signature.
- Standardized `Signal` model:
  - `action`: `SignalAction` enum (`BUY`, `SELL`, `EXIT`, `HOLD`)
  - `symbol`: Ticker string
  - `timestamp`: Bar timestamp
  - `price`: Recommended entry/exit reference price
  - `confidence`: Normalized float from 0.0 to 1.0
  - `strategy_name`: Identifier of generating strategy
  - `indicators`: Snapshot dictionary of indicator values at trigger time
  - `reason`: Crisp text explanation of the setup
- Core Built-in Strategies:
  1. `MACrossoverStrategy`: Fast EMA / Slow EMA crossover with trend and ATR filtering.
  2. `RSIMeanReversionStrategy`: RSI oversold (<30) + reversal bounce for BUY, overbought (>70) for SELL/EXIT, with ATR-based volatility envelope.
  3. `OpeningRangeBreakoutStrategy` (ORB): First 15m/30m opening range high/low breakout with volume confirmation.
  4. `TrendFollowingStrategy`: Multi-factor trend confluence (EMA 20 > EMA 50, MACD positive cross, RSI > 50).
- `StrategyRunner` / `StrategyEngine`:
  - Orchestrator that loads bars from `MarketDataRepository`, applies active strategies, deduplicates signals, and exposes evaluation feeds.
</decisions>

<canonical_refs>
## Canonical References
- `.planning/REQUIREMENTS.md` — IND-01, IND-02
- `.planning/ROADMAP.md` — Phase 2 Goal & Success Criteria
- `src/data/models.py` — `Bar`, `TimeFrame`, `Quote`
- `src/storage/repository.py` — `MarketDataRepository`
</canonical_refs>
