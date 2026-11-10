"""Sentiment scoring aggregator and signal modulation logic."""

import logging
from typing import List

from src.ai.models import SentimentAnalysis

logger = logging.getLogger(__name__)


class SentimentScorer:
    """Aggregates sentiment analyses and modulates trading signal confidence."""

    # Confidence boost/dampen percentages
    BULLISH_BUY_BOOST = 0.15  # 15% boost for bullish + buy signal
    BEARISH_BUY_DAMPEN = 0.20  # 20% reduction for bearish + buy
    BEARISH_EXIT_BOOST = 0.10  # 10% boost for bearish + exit signal
    BULLISH_EXIT_DAMPEN = 0.10  # 10% reduction for bullish + exit

    def aggregate_sentiment(
        self, analyses: List[SentimentAnalysis], min_confidence_threshold: float = 0.3
    ) -> SentimentAnalysis:
        """
        Aggregate multiple sentiment analyses into a unified score.

        Args:
            analyses: List of SentimentAnalysis objects
            min_confidence_threshold: Minimum confidence to consider a signal

        Returns:
            Single aggregated SentimentAnalysis
        """
        if not analyses:
            return SentimentAnalysis(
                symbol="UNKNOWN",
                sentiment="neutral",
                confidence=0.5,
                summary="No analyses available",
            )

        if len(analyses) == 1:
            return analyses[0]

        # Weight by confidence scores
        total_weight = 0.0
        bullish_score = 0.0
        bearish_score = 0.0

        for analysis in analyses:
            weight = analysis.confidence
            if analysis.sentiment == "bullish":
                bullish_score += weight
            elif analysis.sentiment == "bearish":
                bearish_score += weight

            total_weight += weight

        if total_weight == 0:
            return SentimentAnalysis(
                symbol=analyses[0].symbol,
                sentiment="neutral",
                confidence=0.5,
                summary="Low confidence in all analyses",
            )

        # Determine aggregate sentiment
        avg_confidence = total_weight / len(analyses)

        if bullish_score > bearish_score:
            sentiment = "bullish"
            # Normalize confidence based on how much bullish exceeds bearish
            confidence = min(1.0, avg_confidence * (1 + (bullish_score - bearish_score) / total_weight))
        elif bearish_score > bullish_score:
            sentiment = "bearish"
            confidence = min(1.0, avg_confidence * (1 + (bearish_score - bullish_score) / total_weight))
        else:
            sentiment = "neutral"
            confidence = avg_confidence

        # Collect unique themes and risks
        themes = list(set(t for a in analyses for t in a.themes))
        risks = list(set(r for a in analyses for r in a.risks))

        # Combine summaries
        summaries = [a.summary for a in analyses if a.summary]
        summary = " | ".join(summaries[:3]) if summaries else "Multiple analyses combined"

        return SentimentAnalysis(
            symbol=analyses[0].symbol,
            sentiment=sentiment,
            confidence=confidence,
            themes=themes,
            risks=risks,
            summary=summary,
        )

    def modulate_signal_confidence(
        self,
        base_confidence: float,
        sentiment: SentimentAnalysis,
        action: str,
    ) -> float:
        """
        Modulate trading signal confidence based on market sentiment.

        Args:
            base_confidence: Original signal confidence (0.0 - 1.0)
            sentiment: Market sentiment analysis
            action: Trading action ("BUY", "SELL", "EXIT", "HOLD")

        Returns:
            Modulated confidence score (0.0 - 1.0)
        """
        action = action.upper()

        # For HOLD signals, no modulation needed
        if action == "HOLD":
            return base_confidence

        # Determine modulation based on sentiment and action
        if sentiment.sentiment == "bullish":
            if action == "BUY":
                # Boost confidence for bullish + buy
                modulation = 1.0 + (sentiment.confidence * self.BULLISH_BUY_BOOST)
            elif action == "SELL":
                # Significantly reduce short sell confidence when bullish (shorting against bull trend)
                modulation = 1.0 - (sentiment.confidence * self.BEARISH_BUY_DAMPEN)
            elif action == "EXIT":
                # Slightly reduce exit confidence when bullish
                modulation = 1.0 - (sentiment.confidence * self.BULLISH_EXIT_DAMPEN)
            else:
                modulation = 1.0

        elif sentiment.sentiment == "bearish":
            if action == "BUY":
                # Significantly reduce buy confidence when bearish
                modulation = 1.0 - (sentiment.confidence * self.BEARISH_BUY_DAMPEN)
            elif action == "SELL":
                # Boost confidence for bearish + short sell (shorting with bear trend)
                modulation = 1.0 + (sentiment.confidence * self.BULLISH_BUY_BOOST)
            elif action == "EXIT":
                # Boost exit confidence when bearish
                modulation = 1.0 + (sentiment.confidence * self.BEARISH_EXIT_BOOST)
            else:
                modulation = 1.0

        else:  # neutral
            modulation = 1.0

        # Apply modulation and clamp to valid range
        modulated = base_confidence * modulation
        return max(0.0, min(1.0, modulated))

    def get_trade_recommendation(
        self, symbol: str, sentiment: SentimentAnalysis
    ) -> str:
        """
        Generate human-readable trade recommendation.

        Args:
            symbol: Stock ticker symbol
            sentiment: Market sentiment analysis

        Returns:
            Human-readable recommendation string
        """
        conf = sentiment.confidence
        sentiment_str = sentiment.sentiment.upper()

        if conf < 0.3:
            confidence_desc = "low"
        elif conf < 0.6:
            confidence_desc = "moderate"
        else:
            confidence_desc = "high"

        if sentiment_str == "BULLISH":
            recommendation = f"BUY signal for {symbol}"
        elif sentiment_str == "BEARISH":
            recommendation = f"AVOID or EXIT {symbol}"
        else:
            recommendation = f"HOLD {symbol}"

        return (
            f"{recommendation} — {confidence_desc} confidence ({conf:.0%}) "
            f"based on {sentiment_str} market sentiment. {sentiment.summary}"
        )