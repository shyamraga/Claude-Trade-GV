# Graph Report - Claude Trading  (2026-11-10)

## Corpus Check
- 68 files · ~71,976 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 1 file(s) not represented in the graph (top: (none) 1)

## Summary
- 904 nodes · 2337 edges · 25 communities (18 shown, 7 thin omitted)
- Extraction: 94% EXTRACTED · 6% INFERRED · 0% AMBIGUOUS · INFERRED: 138 edges (avg confidence: 0.89)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- Market Scanner & Universe Building
- Entry Signal Analysis
- Time Machine & Historical Backtesting
- Broker & Order Management
- Exit Strategy & Position Closing
- Position Sizing & Risk Allocation
- Trading Alerts & Notifications
- News & Sentiment Analysis
- Risk Management & Circuit Breakers
- Analyst Tools & Fact Analysis
- Congressional Insider Trading (PTR)
- Database & Storage Layer
- Market Data Models & Bar Data
- Strategy Base Classes & Abstractions
- Technical Indicators (numpy)
- Strategy Execution Rationale
- Alpaca Data Client Integration
- Feed Manager & Quote Aggregation
- Data Serialization & Timeframes
- Data Transformation (Dict/Quote)
- Strategy Signal Generation

## God Nodes (most connected - your core abstractions)
1. `Bar` - 69 edges
2. `TimeFrame` - 34 edges
3. `IndicatorCalculator` - 30 edges
4. `Signal` - 30 edges
5. `cmd_orb()` - 23 edges
6. `Strategy` - 23 edges
7. `StrategyEngine` - 23 edges
8. `MarketDataRepository` - 22 edges
9. `evaluate()` - 20 edges
10. `build_plan()` - 20 edges

## Surprising Connections (you probably didn't know these)
- `TestDataClients` --uses--> `FeedManager`  [INFERRED]
  tests/test_data_feed.py → src/data/feed_manager.py
- `TestDataClients` --uses--> `TimeFrame`  [INFERRED]
  tests/test_data_feed.py → src/data/models.py
- `TestStorageAndRepository` --uses--> `TimeFrame`  [INFERRED]
  tests/test_storage.py → src/data/models.py
- `TestDataModels` --uses--> `Bar`  [INFERRED]
  tests/test_data_feed.py → src/data/models.py
- `TestStorageAndRepository` --uses--> `Bar`  [INFERRED]
  tests/test_storage.py → src/data/models.py

## Import Cycles
- None detected.

## Communities (25 total, 7 thin omitted)

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

### Community 7 - "News & Sentiment Analysis"
Cohesion: 0.08
Nodes (28): cik_map(), collect(), collect_moves(), dedupe(), eastern_offset(), Fetcher, fingerprint(), _json_ready() (+20 more)

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
Cohesion: 0.08
Nodes (3): Database, MarketDataRepository, TestStorageAndRepository

### Community 12 - "Market Data Models & Bar Data"
Cohesion: 0.11
Nodes (3): Bar, TestIndicatorCalculator, TestTrendPreview

### Community 13 - "Strategy Base Classes & Abstractions"
Cohesion: 0.19
Nodes (6): Signal, SignalAction, Strategy, OpeningRangeBreakoutStrategy, RSIMeanReversionStrategy, TrendFollowingStrategy

### Community 14 - "Technical Indicators (numpy)"
Cohesion: 0.11
Nodes (4): IndicatorCalculator, BollingerBandsResult, IndicatorSnapshot, MACDResult

### Community 15 - "Strategy Execution Rationale"
Cohesion: 0.13
Nodes (3): StrategyEngine, MACrossoverStrategy, TestStrategyEngine

### Community 16 - "Alpaca Data Client Integration"
Cohesion: 0.12
Nodes (3): AlpacaDataClient, load_env_file(), TestDataClients

### Community 18 - "Data Serialization & Timeframes"
Cohesion: 0.19
Nodes (3): TimeFrame, DataPipeline, main()

## Knowledge Gaps
- **7 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Bar` connect `Market Data Models & Bar Data` to `Database & Storage Layer`, `Strategy Base Classes & Abstractions`, `Technical Indicators (numpy)`, `Strategy Execution Rationale`, `Alpaca Data Client Integration`, `Feed Manager & Quote Aggregation`, `Data Serialization & Timeframes`, `Data Transformation (Dict/Quote)`, `Strategy Bar Management`?**
  _High betweenness centrality (0.114) - this node is a cross-community bridge._
- **Are the 16 inferred relationships involving `Bar` (e.g. with `AlpacaDataClient` and `FeedManager`) actually correct?**
  _`Bar` has 16 INFERRED edges - model-reasoned connections that need verification._
- **Should `Market Scanner & Universe Building` be split into smaller, more focused modules?**
  _Cohesion score 0.05238095238095238 - nodes in this community are weakly interconnected._
- **Why does `TimeFrame` connect `Data Serialization & Timeframes` to `Database & Storage Layer`, `Strategy Base Classes & Abstractions`, `Strategy Execution Rationale`, `Alpaca Data Client Integration`, `Feed Manager & Quote Aggregation`?**
  _High betweenness centrality (0.035) - this node is a cross-community bridge._
- **Are the 8 inferred relationships involving `TimeFrame` (e.g. with `AlpacaDataClient` and `FeedManager`) actually correct?**
  _`TimeFrame` has 8 INFERRED edges - model-reasoned connections that need verification._
- **Should `Entry Signal Analysis` be split into smaller, more focused modules?**
  _Cohesion score 0.06049213943950786 - nodes in this community are weakly interconnected._
- **Why does `MarketDataRepository` connect `Database & Storage Layer` to `Market Data Models & Bar Data`, `Strategy Base Classes & Abstractions`, `Strategy Execution Rationale`, `Feed Manager & Quote Aggregation`, `Data Serialization & Timeframes`?**
  _High betweenness centrality (0.024) - this node is a cross-community bridge._