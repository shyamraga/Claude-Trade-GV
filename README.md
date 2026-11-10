# Claude-Trade-GV: Autonomous Algorithmic Trading & Portfolio Engine

An intelligent, automated algorithmic trading and portfolio management platform powered by Claude AI, quantitative technical strategies, and continuous risk management.

![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)
![License](https://img.shields.io/badge/License-MIT-green.svg)
![Tests](https://img.shields.io/badge/Tests-97%20Passed-brightgreen.svg)

---

## Key Features

- **Autonomous Market Scanning**:
  - Continuously scans 200+ tradable US equities and liquid cryptocurrency pairs (`BTC-USD`, `ETH-USD`, `SOL-USD`, `AVAX-USD`, `DOGE-USD`).
  - Runs periodic multi-timeframe analysis (1m, 5m, 15m, 1h, 1D).

- **Bi-Directional Trading (Long & Short)**:
  - Supports both **Long** breakout entries and **Short** breakdown entries with margin reservation and automated covering.
  - Symmetrical P&L accounting for long equity positions and short sell positions.

- **Multi-Strategy Quantitative Ensemble**:
  - **Opening Range Breakout (ORB)**: Volatility expansion beyond opening ranges with volume confirmation.
  - **EMA / MACD Trend Following**: Multi-timeframe trend alignment with momentum filtering.
  - **RSI Mean Reversion**: Overbought/oversold extreme exhaustions.
  - **Moving Average Crossover**: Fast/Slow EMA golden and death crosses.

- **Claude AI Market Intelligence & Sentiment Modulation**:
  - Integrates news sentiment analysis with technical confidence scores.
  - Aligned signals receive confidence boosts (+15%), while counter-sentiment setups are penalized (-20%).

- **Risk Guardian & Circuit Breakers**:
  - **Daily Drawdown Cap**: Maximum allowed daily loss (5%) halts new entries.
  - **Consecutive Loss Cooldown**: Automatic 4-hour trading pause after 3 consecutive losses.
  - **Pre-Trade Memory & Continuous Learning**: Automatically generates post-mortem analyses for closed losing trades and stores them in memory; future signals matching historical loss patterns are autonomously filtered.

- **Strict 10-Position Portfolio Cap & Timestamps**:
  - Enforces a strict maximum of **10 concurrent live trades** across the entire portfolio.
  - Each trade records an exact entry timestamp (`opened_at`) and target exit criteria (`stop_loss` and `take_profit`).
  - Automated continuous monitoring checks every price tick against stop-loss and take-profit thresholds to trigger exits immediately.

- **Real-Time OLED Dashboard & REST API**:
  - High-performance web UI with Candlestick/Line charts, OHLC summary, interactive order dispatch, active positions table, and a dedicated **Live Trade View** with real-time scanner terminal logs.

---

## Architecture Overview

```
                               ┌────────────────────────────────┐
                               │  Market Data Ingestion Engine  │
                               │  • Alpaca Market Data / CCXT   │
                               │  • Equities & Crypto Datafeeds │
                               └───────────────┬────────────────┘
                                               │
                                               ▼
                               ┌────────────────────────────────┐
                               │ Multi-Strategy Technical Engine│
                               │ • ORB • EMA Crossover • RSI    │
                               │ (Generates Long & Short Setups)│
                               └───────────────┬────────────────┘
                                               │ Raw Signals
                                               ▼
                               ┌────────────────────────────────┐
                               │  Claude AI Sentiment Scorer    │
                               │  • News & Sentiment Analysis   │
                               │  • Confidence Modulation       │
                               └───────────────┬────────────────┘
                                               │ Modulated Setups
                                               ▼
                               ┌────────────────────────────────┐
                               │     Risk & Memory Guardian     │
                               │  • Circuit Breaker Drawdown    │
                               │  • Max 10 Positions Cap        │
                               │  • Pre-Trade Loss Filter       │
                               └───────────────┬────────────────┘
                                               │ Approved Orders
                                               ▼
                               ┌────────────────────────────────┐
                               │     Dual Execution Engine      │
                               │  • Virtual Broker / Alpaca API │
                               │  • Position & Margin Tracker   │
                               │  • Automated SL / TP Trigger   │
                               └───────────────┬────────────────┘
                                               │
                                               ▼
                               ┌────────────────────────────────┐
                               │ Real-Time OLED Dashboard & API │
                               │ • REST API Server (Port 8000)  │
                               │ • Live Trade View & Terminal   │
                               └────────────────────────────────┘
```

---

## Directory Structure

```
├── dashboard/               # Real-Time OLED Web Dashboard
│   ├── index.html           # Dashboard UI with Overview and Live Trade View tabs
│   ├── styles.css           # Premium OLED dark-mode responsive stylesheet
│   └── app.js               # Canvas chart renderer & REST API client
├── src/
│   ├── ai/                  # Claude AI Sentiment & News Analysis
│   │   ├── analyzer.py      # Claude model interface & caching
│   │   ├── integration.py   # Multi-source AI aggregator
│   │   ├── news_client.py   # NewsAPI client
│   │   └── sentiment_scorer.py # Dynamic confidence modulation
│   ├── api/                 # REST API & Web Server
│   │   └── server.py        # Endpoints: /api/account, /api/positions, /api/trades, /api/bars
│   ├── data/                # Market Data & Ingestion
│   │   ├── feed_manager.py  # WebSocket & polling datafeed manager
│   │   └── models.py        # Bar, Quote, TimeFrame models
│   ├── execution/           # Order Execution & Broker Adapters
│   │   ├── alpaca_broker.py # Live/Paper Alpaca integration
│   │   ├── base.py          # Abstract broker base class
│   │   ├── engine.py        # Central execution orchestrator
│   │   ├── models.py        # Order, Position, TradeRecord dataclasses
│   │   └── virtual_broker.py# Simulated broker with short selling & margin
│   ├── risk/                # Risk Management & Post-Mortem Learning
│   │   ├── circuit_breaker.py # Drawdown & consecutive loss protection
│   │   ├── models.py        # Circuit breaker configurations
│   │   └── post_mortem.py   # Autonomous loss analysis & pre-trade memory
│   ├── storage/             # Database Repositories
│   │   ├── db.py            # SQLite / SQLite WAL storage
│   │   └── repository.py    # Market data querying
│   └── strategy/            # Quantitative Trading Strategies
│       ├── base.py          # Strategy interface
│       ├── ma_crossover.py  # EMA crossover (Golden / Death Cross)
│       ├── orb.py           # Opening Range Breakout (Long & Short)
│       ├── rsi_reversion.py # RSI mean reversion (Oversold / Overbought)
│       └── trend_following.py # Multi-timeframe trend momentum
├── tests/                   # Comprehensive Test Suite (97 Tests)
├── run_bot.py               # Autonomous Universal Trading Bot entrypoint
├── run_dashboard.py         # Local Dashboard HTTP server entrypoint
└── requirements.txt         # Project dependencies
```

---

## Quick Start

### 1. Installation

Clone the repository and install dependencies:

```bash
git clone https://github.com/shyamraga/Claude-Trade-GV.git
cd Claude-Trade-GV
pip install -r requirements.txt
```

### 2. Configure Environment (Optional)

Create a `.env` file in the root directory for live data and AI sentiment integration:

```ini
ALPACA_API_KEY=your_alpaca_api_key
ALPACA_SECRET_KEY=your_alpaca_secret_key
ANTHROPIC_API_KEY=your_claude_api_key
NEWS_API_KEY=your_news_api_key
```

*(Note: The system seamlessly falls back to virtual paper trading and simulated market feeds if API keys are not provided.)*

### 3. Launch the Dashboard

```bash
python run_dashboard.py
```
Open **`http://localhost:8000/`** in your browser.

### 4. Run the Autonomous Bot

```bash
python run_bot.py
```
The bot will initialize services, start the HTTP dashboard at `http://localhost:8000/`, scan the multi-asset universe every 45 seconds, rank candidate setups by confidence, enforce the 10-position portfolio cap, and automatically monitor stop-loss and take-profit targets.

---

## Running Tests

Execute the full unit test suite:

```bash
pytest tests/ -v
```

All 97 unit tests verify execution mechanics, bi-directional shorting, circuit breaker cooldowns, post-mortem learning, REST API endpoints, and quantitative strategies.

---

## License

This project is licensed under the [MIT License](LICENSE).
