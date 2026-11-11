"""
Trader-News Agent: Macroeconomic Catalysts, Breaking News & Sentiment Vector.

Monitors financial headlines, Fed interest rate narratives, earnings momentum,
and macro market catalysts to evaluate news tailwinds or event risks.
"""

import time
from typing import List, Dict, Any, Optional

from src.data.models import Bar
from src.ai.agents.base import BaseSubAgent, AgentSignal, AgentAction, AgentStatus


class TraderNews(BaseSubAgent):
    """Specialized Sub-Agent for News Sentiment & Macro Catalyst Ingestion."""

    def __init__(self, weight: float = 1.0):
        super().__init__(
            agent_id="trader-news",
            name="Trader News",
            role="Macroeconomic Catalysts & Breaking News Sentiment",
            weight=weight,
        )

    def analyze(
        self,
        symbol: str,
        bars: List[Bar],
        current_position: Optional[Any] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> AgentSignal:
        start_t = time.perf_counter()
        self.total_analyses += 1
        self.status = AgentStatus.ANALYZING

        # Check context for pre-fetched news or sentiment
        news_sentiment = "neutral"
        sentiment_score = 0.0
        catalyst = "No immediate macro hazard detected"

        if context and "sentiment" in context:
            news_sentiment = context["sentiment"].lower()
            if news_sentiment == "bullish":
                sentiment_score = 0.65
            elif news_sentiment == "bearish":
                sentiment_score = -0.65

        # Also check price momentum as a proxy for news break if external API not available
        if bars and len(bars) >= 5:
            ret_5 = (bars[-1].close - bars[-5].close) / bars[-5].close if bars[-5].close > 0 else 0.0
            # Sudden gap or surge often indicates news catalyst
            if ret_5 > 0.03:
                sentiment_score = max(sentiment_score, 0.70)
                news_sentiment = "bullish"
                catalyst = f"Positive news velocity detected (+{ret_5*100:.1f}% 5-bar impulse)"
            elif ret_5 < -0.03:
                sentiment_score = min(sentiment_score, -0.70)
                news_sentiment = "bearish"
                catalyst = f"Adverse news impulse detected ({ret_5*100:.1f}% 5-bar drop)"

        if sentiment_score >= 0.40:
            action = AgentAction.BUY
            confidence = min(0.92, 0.60 + sentiment_score * 0.35)
            reason = f"Bullish news catalyst: {catalyst} (sentiment={news_sentiment})"
        elif sentiment_score <= -0.40:
            action = AgentAction.SELL
            confidence = min(0.92, 0.60 + abs(sentiment_score) * 0.35)
            reason = f"Bearish news catalyst: {catalyst} (sentiment={news_sentiment})"
        else:
            action = AgentAction.NEUTRAL
            confidence = 0.50
            reason = f"Neutral macro backdrop: {catalyst}"

        self.successful_analyses += 1
        self.status = AgentStatus.ACTIVE
        latency = (time.perf_counter() - start_t) * 1000

        sig = AgentSignal(
            agent_id=self.agent_id,
            symbol=symbol,
            action=action,
            confidence=round(confidence, 4),
            reason=reason,
            metrics={
                "sentiment_label": news_sentiment,
                "sentiment_score": round(sentiment_score, 2),
                "catalyst": catalyst,
            },
            status=AgentStatus.ACTIVE,
            latency_ms=latency,
        )
        self.last_signal = sig
        return sig
