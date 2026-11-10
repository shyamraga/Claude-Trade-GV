# Phase 3: AI Sentiment & News Analysis — Context

**Gathered:** 2026-11-10
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 3 integrates Claude API to provide qualitative intelligence for trade decisions. It fetches financial news headlines for target symbols, analyzes sentiment and market context using Claude's reasoning capabilities, and generates structured confidence scores that feed into the multi-strategy decision engine built in Phase 2.

This phase bridges quantitative technical signals with qualitative AI-driven market sentiment, enabling the trading bot to avoid trades during negative news events and boost confidence during positive catalysts.
</domain>

<decisions>
## Implementation Decisions

### News Data Sources
- **Primary:** Financial news APIs (Alpha Vantage News API, NewsAPI, Finnhub News)
- **Backup:** RSS feeds from major financial outlets (Reuters, Bloomberg, CNBC)
- **Free Tier:** NewsAPI.org with stock symbol filtering

### Claude API Integration
- **Model:** Claude 3.5 Sonnet or Claude Opus 4 (latest available)
- **API Endpoint:** `https://api.anthropic.com/v1/messages`
- **Authentication:** API key from `.env` (`ANTHROPIC_API_KEY`)
- **Prompt Engineering:**
  - System prompt: Financial analyst role with focus on risk assessment
  - User prompt: Structured JSON output for sentiment scores (bullish/bearish/neutral), confidence (0-1), key themes, risk factors
  - Output format: `{"sentiment": "bullish|bearish|neutral", "confidence": 0.85, "themes": ["earnings beat", "guidance raise"], "risks": ["regulatory"], "summary": "..."}`

### Sentiment Scoring Architecture
- Target directory: `src/ai/`
- Components:
  - `src/ai/news_client.py`: Fetches news headlines for symbols
  - `src/ai/claude_analyzer.py`: Claude API wrapper for sentiment analysis
  - `src/ai/sentiment_scorer.py`: Aggregates news + sentiment into actionable confidence scores
  - `src/ai/models.py`: Dataclasses for NewsArticle, SentimentAnalysis, MarketContext

### Integration with Strategy Engine
- Sentiment scores modulate strategy signal confidence:
  - Positive sentiment (bullish): Boost BUY signal confidence by 10-15%
  - Negative sentiment (bearish): Reduce BUY confidence or elevate EXIT signals
  - Neutral: No adjustment
- Cache sentiment results for 15-30 minutes to avoid redundant API calls

### API Rate Limiting & Caching
- Claude API rate limits respected with exponential backoff
- News cache TTL: 15 minutes (stale news tolerance)
- Sentiment cache TTL: 30 minutes per symbol

### Testing Strategy
- Mock Claude API responses for unit tests
- Validate JSON parsing and error handling
- Test sentiment score aggregation with multi-article scenarios
</decisions>

<canonical_refs>
## Canonical References
- `.planning/REQUIREMENTS.md` — AI-01, AI-02
- `.planning/ROADMAP.md` — Phase 3 Goal & Success Criteria
- `src/strategy/base.py` — Signal confidence scoring integration points
- `src/strategy/engine.py` — StrategyEngine for signal modulation
</canonical_refs>
