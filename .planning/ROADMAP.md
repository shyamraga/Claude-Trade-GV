# Roadmap — Claude Trading

## Overview

Claude Trading is structured into 5 vertical MVP phases, taking the platform from raw data ingestion to automated AI-driven execution and real-time UI monitoring.

## Phase Breakdown

### Phase 1: Market Data Ingestion & Storage
**Goal:** Establish robust real-time and historical market data pipelines and local database storage.
**Requirements:** DATA-01, DATA-02
**Success Criteria:**
1. Successfully fetch historical OHLCV data for test stocks/cryptos.
2. Ingest real-time market ticks/bars without data loss.
3. Store and query market data efficiently in local database.

### Phase 2: Technical Indicators & Strategy Engine
**Goal:** Implement technical indicators and a modular strategy execution framework.
**Requirements:** IND-01, IND-02
**Success Criteria:**
1. Accurate calculation of SMA, EMA, RSI, MACD, Bollinger Bands, and ATR.
2. Modular strategy runner generates buy/sell signals based on indicator thresholds.

### Phase 3: AI Sentiment & News Analysis
**Goal:** Integrate Claude API for financial news fetching and sentiment analysis to inform trade decisions.
**Requirements:** AI-01, AI-02
**Success Criteria:**
1. Fetch latest financial headlines for targeted assets.
2. Claude API correctly evaluates market sentiment and outputs structured confidence scores.
3. AI insights incorporated into trading signal decisions.

### Phase 4: Risk Management, Dual Execution & Post-Mortem Learning Loop
**Goal:** Build risk controls, dual-mode execution (Virtual & Live), and automated trade loss post-mortem continuous learning memory.
**Requirements:** RISK-01, EXEC-01, LEARN-01, LEARN-02
**Success Criteria:**
1. Automated stop-loss, take-profit, and max daily drawdown circuit breaker.
2. Secure API connection and order placement for both Virtual simulation and Live brokerage (Alpaca).
3. Automatic post-mortem generation for every losing trade with root-cause analysis stored in dedicated memory files.
4. Pre-trade memory filter that queries past loss post-mortems and prevents repeating known failure setups.

### Phase 5: Real-Time Dashboard UI & Monitoring
**Goal:** Build a responsive web dashboard for portfolio tracking, equity curves, and system control.
**Requirements:** UI-01
**Success Criteria:**
1. Real-time portfolio equity tracking and open position display.
2. Visual charts for price action, indicators, and trade fills.
3. Manual override and system status controls.
