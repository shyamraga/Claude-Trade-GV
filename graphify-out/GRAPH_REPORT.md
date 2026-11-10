# Graph Report - Claude Trading  (2026-11-10)

## Corpus Check
- 97 files · ~86,735 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 2 file(s) not represented in the graph (top: (none) 1, .css 1)

## Summary
- 1597 nodes · 3684 edges · 62 communities (44 shown, 18 thin omitted)
- Extraction: 90% EXTRACTED · 10% INFERRED · 0% AMBIGUOUS · INFERRED: 370 edges (avg confidence: 0.91)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `064a748c`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- Market Scanner & Universe Building
- Entry Signal Analysis
- Time Machine & Historical Backtesting
- Broker & Order Management
- Exit Strategy & Position Closing
- Position Sizing & Risk Allocation
- Trading Alerts & Notifications
- news.py
- Risk Management & Circuit Breakers
- Analyst Tools & Fact Analysis
- Congressional Insider Trading (PTR)
- Database & Storage Layer
- Bar
- Signal
- Technical Indicators (numpy)
- SentimentAnalysis
- TimeFrame
- VirtualBroker
- execution/engine.py
- CircuitBreaker
- NewsAPIClient
- NewsArticle
- ExecutionEngine
- TestDashboardAPIServer
- virtual_broker.py
- app.js
- DashboardAPIHandler
- TestAIMarketIntelligence
- MarketContext
- BaseBroker
- .create_post_mortem
- main
- news_client.py
- trader-scanner
- trader-alerts
- trader-budget
- trader-pelosi
- Implementation Decisions
- v1 Requirements
- trader-broker
- trader-risk
- Claude Trading
- TestSentimentAnalysis
- trader-entry
- trader-exit
- trader-timemachine
- Implementation Decisions
- Phase Breakdown
- trader-analyst
- trader-news
- to_eastern
- APIError
- Claude Trading Instructions
- Fetcher
- Project State

## God Nodes (most connected - your core abstractions)
1. `Bar` - 76 edges
2. `SentimentAnalysis` - 45 edges
3. `NewsArticle` - 39 edges
4. `TimeFrame` - 39 edges
5. `VirtualBroker` - 33 edges
6. `Signal` - 33 edges
7. `MarketDataRepository` - 32 edges
8. `ExecutionEngine` - 31 edges
9. `IndicatorCalculator` - 31 edges
10. `Order` - 28 edges

## Surprising Connections (you probably didn't know these)
- `Data Model & Standardization` --references--> `Bar`  [INFERRED]
  .planning/phases/01-market-data-ingestion-storage/01-CONTEXT.md → src/data/models.py
- `What Was Built` --references--> `DashboardAPIHandler`  [INFERRED]
  .planning/phases/05-real-time-dashboard-ui/05-SUMMARY.md → src/api/server.py
- `What Was Built` --references--> `Bar`  [INFERRED]
  .planning/phases/01-market-data-ingestion-storage/01-SUMMARY.md → src/data/models.py
- `What Was Built` --references--> `Quote`  [INFERRED]
  .planning/phases/01-market-data-ingestion-storage/01-SUMMARY.md → src/data/models.py
- `What Was Built` --references--> `TimeFrame`  [INFERRED]
  .planning/phases/01-market-data-ingestion-storage/01-SUMMARY.md → src/data/models.py

## Import Cycles
- None detected.

## Communities (62 total, 18 thin omitted)

### Community 0 - "Market Scanner & Universe Building"
Cohesion: 0.05
Nodes (52): _absorb(), build_universe(), chart_path(), classify(), clock_label(), cmd_daily(), cmd_orb(), confirm() (+44 more)

### Community 1 - "Entry Signal Analysis"
Cohesion: 0.06
Nodes (48): ampm(), bar_line(), chart_path(), chart_range(), cmd_check(), cmd_watch(), emit(), on_trigger() (+40 more)

### Community 2 - "Time Machine & Historical Backtesting"
Cohesion: 0.05
Nodes (43): build_pool(), cents_away(), chart_result(), chart_url(), clock12(), clock24(), cmd_chart(), cmd_run() (+35 more)

### Community 3 - "Broker & Order Management"
Cohesion: 0.09
Nodes (44): amount_numbers(), apply_fill(), _clock(), cmd_approve(), cmd_decline(), cmd_fill(), cmd_flatten(), cmd_log() (+36 more)

### Community 4 - "Exit Strategy & Position Closing"
Cohesion: 0.08
Nodes (39): ampm(), atr_of(), build_plan(), cents(), cmd_plan(), cmd_show(), compute(), D() (+31 more)

### Community 5 - "Position Sizing & Risk Allocation"
Cohesion: 0.07
Nodes (35): allocate(), bracket_order(), eastern_offset(), eastern_to_utc(), _f(), fresh_price(), load_config(), load_prices() (+27 more)

### Community 6 - "Trading Alerts & Notifications"
Cohesion: 0.09
Nodes (38): active(), AlertError, cmd_add(), cmd_check(), cmd_clock(), cmd_list(), cmd_quote(), cmd_reset() (+30 more)

### Community 7 - "news.py"
Cohesion: 0.14
Nodes (11): cik_map(), collect(), collect_moves(), _local(), NewsError, parse_chart(), parse_rss(), parse_sec_atom() (+3 more)

### Community 8 - "Risk Management & Circuit Breakers"
Cohesion: 0.08
Nodes (29): account(), business_days(), _cent(), check(), day_trades(), eastern_offset(), eastern_to_utc(), _f() (+21 more)

### Community 9 - "Analyst Tools & Fact Analysis"
Cohesion: 0.08
Nodes (24): analyse(), changes(), clean_title(), _date(), exhibit_name(), facts_for(), FactsError, Fetcher (+16 more)

### Community 10 - "Congressional Insider Trading (PTR)"
Cohesion: 0.10
Nodes (23): _amount(), describe(), download(), _fetch_and_read(), _finish(), iso(), load_index(), load_state() (+15 more)

### Community 11 - "Database & Storage Layer"
Cohesion: 0.06
Nodes (9): Phase 1 Summary: Market Data Ingestion & Storage, Verification, What Was Built, FeedManager, DataPipeline, main(), Database, MarketDataRepository (+1 more)

### Community 12 - "Bar"
Cohesion: 0.11
Nodes (5): Canonical References, Phase 2: Technical Indicators & Strategy Engine — Context, Phase Boundary, Bar, TestTrendPreview

### Community 13 - "Signal"
Cohesion: 0.08
Nodes (11): Strategy Framework & Engine, Signal, SignalAction, Strategy, StrategyEngine, MACrossoverStrategy, OpeningRangeBreakoutStrategy, RSIMeanReversionStrategy (+3 more)

### Community 14 - "Technical Indicators (numpy)"
Cohesion: 0.08
Nodes (7): Implementation Decisions, Mathematical Indicators Engine, IndicatorCalculator, BollingerBandsResult, IndicatorSnapshot, MACDResult, TestIndicatorCalculator

### Community 15 - "SentimentAnalysis"
Cohesion: 0.07
Nodes (5): ClaudeAnalyzer, AIMarketIntelligence, SentimentAnalysis, SentimentScorer, TestSentimentScorer

### Community 16 - "TimeFrame"
Cohesion: 0.07
Nodes (11): Automated Test Results, Phase 1 Verification: Market Data Ingestion & Storage, Requirements Verification, Success Criteria Verification, AlpacaDataClient, load_env_file(), Quote, TimeFrame (+3 more)

### Community 17 - "VirtualBroker"
Cohesion: 0.07
Nodes (5): AlpacaBroker, Order, Position, VirtualBroker, TestVirtualBroker

### Community 19 - "CircuitBreaker"
Cohesion: 0.07
Nodes (6): CircuitBreaker, RiskCheckResult, RiskConfig, TradeRecord, TradePostMortem, TestCircuitBreaker

### Community 23 - "NewsArticle"
Cohesion: 0.10
Nodes (3): NewsArticle, TestNewsArticle, TestClaudeAnalyzer

### Community 25 - "ExecutionEngine"
Cohesion: 0.08
Nodes (3): run_server(), ExecutionEngine, TestExecutionEngine

### Community 27 - "virtual_broker.py"
Cohesion: 0.17
Nodes (4): AccountInfo, OrderSide, OrderStatus, OrderType

### Community 28 - "app.js"
Cohesion: 0.19
Nodes (18): fetchAccountData(), fetchBarsData(), fetchCircuitBreakerData(), fetchPositionsData(), fetchPostMortemsData(), fetchTradesData(), FinancialChartRenderer, formatCurrency() (+10 more)

### Community 29 - "DashboardAPIHandler"
Cohesion: 0.13
Nodes (4): Phase 5 Summary: Real-Time Dashboard UI & Monitoring, Verification, What Was Built, DashboardAPIHandler

### Community 34 - "main"
Cohesion: 0.16
Nodes (11): dedupe(), fingerprint(), _json_ready(), load_json(), main(), mention_patterns(), remember(), sec_user_agent() (+3 more)

### Community 36 - "trader-scanner"
Cohesion: 0.17
Nodes (11): Data and limits, Example: the reel, Rules, Safety, Steps, The daily scan (before the open), The opening-range breakout scan (during the session), The universe (+3 more)

### Community 37 - "trader-alerts"
Cohesion: 0.18
Nodes (10): Example: the reel, Quotes, Rule types, Rules, Safety, Steps, The NYSE clock, trader-alerts (+2 more)

### Community 38 - "trader-budget"
Cohesion: 0.18
Nodes (10): Example: the reel, Rules, Safety, Step 1: set the rules once, Step 2: size the trade, Step 3: show the user, trader-budget, Weights mode (kept from v1) (+2 more)

### Community 39 - "trader-pelosi"
Cohesion: 0.18
Nodes (10): Example: a real alert, Safety, Step 1: what has been filed, Step 2: watch for new ones, Step 3: read a report, The rules, The Senate: the manual route, trader-pelosi (+2 more)

### Community 40 - "Implementation Decisions"
Cohesion: 0.18
Nodes (10): API Rate Limiting & Caching, Canonical References, Claude API Integration, Implementation Decisions, Integration with Strategy Engine, News Data Sources, Phase 3: AI Sentiment & News Analysis — Context, Phase Boundary (+2 more)

### Community 41 - "v1 Requirements"
Cohesion: 0.18
Nodes (10): AI & Sentiment Analysis, Continuous Learning & Post-Mortem Memory, Data Ingestion & Storage, Out of Scope, Quantitative & Technical Analysis, Requirements — Claude Trading, Risk Management & Execution, User Interface & Monitoring (+2 more)

### Community 42 - "trader-broker"
Cohesion: 0.20
Nodes (9): Example: the reel, Safety, Setup A: Alpaca (official MCP server, Claude Desktop), Setup B: Interactive Brokers (connector in Claude's directory), Steps: the entry, Steps: while it is open, and out by the close, trader-broker, What it never does (+1 more)

### Community 43 - "trader-risk"
Cohesion: 0.20
Nodes (9): Entries and exits, Example: the reel, Rules, Safety, Steps, The checks, trader-risk, What it never does (+1 more)

### Community 44 - "Claude Trading"
Cohesion: 0.20
Nodes (9): Active, Claude Trading, Core Value, Evolution, Key Decisions, Out of Scope, Requirements, Validated (+1 more)

### Community 47 - "trader-entry"
Cohesion: 0.22
Nodes (8): Example: the reel, Rules, Safety, Steps, The rule, trader-entry, What it never does, What it reads and writes

### Community 48 - "trader-exit"
Cohesion: 0.22
Nodes (8): Example: the reel, Rules, Safety, Steps, Stops and targets, trader-exit, What it never does, What it reads and writes

### Community 49 - "trader-timemachine"
Cohesion: 0.22
Nodes (8): Example: the reel, How it works, Rules, Safety, Steps, trader-timemachine, What it never does, What it reads and writes

### Community 50 - "Implementation Decisions"
Cohesion: 0.22
Nodes (8): Canonical References, Claude's Discretion, Data Model & Standardization, Data Providers, Implementation Decisions, Phase 1: Market Data Ingestion & Storage — Context, Phase Boundary, Storage Engine

### Community 51 - "Phase Breakdown"
Cohesion: 0.22
Nodes (8): Overview, Phase 1: Market Data Ingestion & Storage, Phase 2: Technical Indicators & Strategy Engine, Phase 3: AI Sentiment & News Analysis, Phase 4: Risk Management, Dual Execution & Post-Mortem Learning Loop, Phase 5: Real-Time Dashboard UI & Monitoring, Phase Breakdown, Roadmap — Claude Trading

### Community 53 - "trader-analyst"
Cohesion: 0.25
Nodes (7): Example: the reel's stock, Safety, Steps, The rules, trader-analyst, What it never does, What it reads and writes

### Community 54 - "trader-news"
Cohesion: 0.25
Nodes (7): Example: the reel, Safety, Steps, The rules, trader-news, What it never does, What it reads and writes

### Community 55 - "to_eastern"
Cohesion: 0.33
Nodes (5): eastern_offset(), _nth_sunday(), render(), render_moves(), to_eastern()

### Community 58 - "Claude Trading Instructions"
Cohesion: 0.40
Nodes (4): Claude Trading Instructions, GSD Workflow Enforcement, Project, Technology Stack

### Community 60 - "Project State"
Cohesion: 0.50
Nodes (3): Current Position, Decisions, Project State

## Knowledge Gaps
- **18 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `SentimentAnalysis` connect `SentimentAnalysis` to `news_client.py`, `TestSentimentAnalysis`, `._get_from_cache`, `NewsArticle`, `TestAIMarketIntelligence`, `MarketContext`?**
  _High betweenness centrality (0.077) - this node is a cross-community bridge._
- **Are the 23 inferred relationships involving `Bar` (e.g. with `01-01-PLAN.md` and `01-02-PLAN.md`) actually correct?**
  _`Bar` has 23 INFERRED edges - model-reasoned connections that need verification._
- **Should `Market Scanner & Universe Building` be split into smaller, more focused modules?**
  _Cohesion score 0.05249569707401033 - nodes in this community are weakly interconnected._
- **Why does `Bar` connect `Bar` to `Database & Storage Layer`, `Signal`, `Technical Indicators (numpy)`, `TimeFrame`, `Implementation Decisions`?**
  _High betweenness centrality (0.065) - this node is a cross-community bridge._
- **Are the 9 inferred relationships involving `SentimentAnalysis` (e.g. with `03-01-PLAN.md` and `03-02-PLAN.md`) actually correct?**
  _`SentimentAnalysis` has 9 INFERRED edges - model-reasoned connections that need verification._
- **Should `Entry Signal Analysis` be split into smaller, more focused modules?**
  _Cohesion score 0.06260406260406261 - nodes in this community are weakly interconnected._
- **Why does `MarketDataRepository` connect `Database & Storage Layer` to `Bar`, `Signal`, `TimeFrame`, `execution/engine.py`, `ExecutionEngine`?**
  _High betweenness centrality (0.042) - this node is a cross-community bridge._