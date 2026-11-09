# Requirements — Claude Trading

## v1 Requirements

### Data Ingestion & Storage
- [ ] **DATA-01**: Ingest real-time and historical OHLCV market data from standard APIs (e.g., Yahoo Finance, Alpaca, CCXT).
- [ ] **DATA-02**: Store market data and trade history securely in a local database (SQLite/PostgreSQL).

### Quantitative & Technical Analysis
- [ ] **IND-01**: Calculate core technical indicators (SMA, EMA, RSI, MACD, Bollinger Bands, ATR).
- [ ] **IND-02**: Provide modular strategy framework to plug in custom trading signals (moving average crossover, RSI mean reversion, etc.).

### AI & Sentiment Analysis
- [ ] **AI-01**: Fetch and analyze financial news/sentiment using Claude API to generate qualitative trading context scores.
- [ ] **AI-02**: Provide AI-driven trade justification and portfolio health summaries.

### Risk Management & Execution
- [ ] **RISK-01**: Enforce strict risk limits (maximum daily drawdown, position size caps, automated stop-loss and take-profit orders).
- [ ] **EXEC-01**: Connect to paper trading and live brokerage APIs (Alpaca API) for order submission and portfolio sync.

### User Interface & Monitoring
- [ ] **UI-01**: Real-time web dashboard displaying portfolio equity curve, open positions, active signals, and system logs.

## v2 Requirements (Deferred)
- Multi-broker support (Interactive Brokers, Binance, Coinbase Advanced).
- Advanced machine learning predictive price models.
- Telegram/Discord webhook alerts for trade executions.

## Out of Scope
- Sub-millisecond HFT execution.
- Options and derivatives complex multi-leg pricing models for v1.
