# Claude Trading

## What This Is

Claude Trading is an intelligent, automated algorithmic trading and portfolio management platform powered by Claude AI. It combines real-time market data ingestion, quantitative technical analysis, AI-driven sentiment and news analysis, rigorous risk management, and execution adapters for brokerages and exchanges (such as Alpaca and crypto exchanges) to execute trades autonomously or provide decision support.

## Core Value

Accurate, real-time automated trading decision support and risk-managed execution driven by AI insights and quantitative indicators.

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] **DATA-01**: Real-time and historical market data ingestion (OHLCV, order book) for stocks/crypto
- [ ] **IND-01**: Technical indicator calculation engine (SMA, EMA, RSI, MACD, Bollinger Bands, ATR)
- [ ] **AI-01**: AI-powered market sentiment and news analysis using Claude API
- [ ] **RISK-01**: Automated risk management (stop-loss, take-profit, position sizing, daily drawdown limits, and 3-consecutive-loss 4-hour trading pause circuit breaker unless overridden by user)
- [ ] **EXEC-01**: Brokerage execution adapter (Alpaca / paper trading support)
- [ ] **LEARN-01**: Automated trade loss post-mortem generator (crisp root-cause analysis stored in dedicated memory files) and pre-trade memory check loop to continuously improve setups
- [ ] **UI-01**: Real-time dashboard for portfolio monitoring, performance tracking, and manual override

### Out of Scope

- High-frequency trading (HFT) sub-millisecond latency execution — focus is on swing and intraday algorithmic trading.
- Proprietary exchange creation or market making.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Python backend + React/TypeScript frontend | Rich ecosystem for quantitative finance (pandas, numpy, ccxt) and robust UI framework. | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.
