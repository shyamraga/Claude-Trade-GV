"""AI data models for news and sentiment analysis."""

from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional


@dataclass
class NewsArticle:
    """Represents a financial news article."""

    symbol: str
    title: str
    source: str
    published_at: datetime
    url: str
    description: Optional[str] = None
    content_snippet: Optional[str] = None

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        data = asdict(self)
        data["published_at"] = self.published_at.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "NewsArticle":
        """Deserialize from dictionary."""
        if isinstance(data.get("published_at"), str):
            data["published_at"] = datetime.fromisoformat(data["published_at"])
        return cls(**data)


@dataclass
class SentimentAnalysis:
    """Claude-generated sentiment analysis for a symbol."""

    symbol: str
    sentiment: str  # bullish, bearish, neutral
    confidence: float  # 0.0 - 1.0
    themes: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    summary: str = ""
    analyzed_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        data = asdict(self)
        data["analyzed_at"] = self.analyzed_at.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "SentimentAnalysis":
        """Deserialize from dictionary."""
        if isinstance(data.get("analyzed_at"), str):
            data["analyzed_at"] = datetime.fromisoformat(data["analyzed_at"])
        return cls(**data)

    def to_signal_modulation(self) -> float:
        """
        Convert sentiment to signal confidence modulation.
        Returns multiplier from 0.5 to 1.5 based on sentiment.
        """
        if self.sentiment == "bullish":
            return 1.0 + (self.confidence * 0.15)  # 1.0 - 1.15
        elif self.sentiment == "bearish":
            return 1.0 - (self.confidence * 0.20)  # 0.8 - 1.0
        return 1.0  # neutral: no change


@dataclass
class MarketContext:
    """Aggregated market context for a symbol."""

    symbol: str
    news_articles: list[NewsArticle] = field(default_factory=list)
    sentiment: Optional[SentimentAnalysis] = None
    cached_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "symbol": self.symbol,
            "news_articles": [a.to_dict() for a in self.news_articles],
            "sentiment": self.sentiment.to_dict() if self.sentiment else None,
            "cached_at": self.cached_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "MarketContext":
        """Deserialize from dictionary."""
        return cls(
            symbol=data["symbol"],
            news_articles=[
                NewsArticle.from_dict(a) for a in data.get("news_articles", [])
            ],
            sentiment=(
                SentimentAnalysis.from_dict(data["sentiment"])
                if data.get("sentiment")
                else None
            ),
            cached_at=datetime.fromisoformat(data["cached_at"])
            if isinstance(data.get("cached_at"), str)
            else datetime.now(),
        )

    def is_stale(self, ttl_minutes: int = 30) -> bool:
        """Check if cached data is stale."""
        age = datetime.now() - self.cached_at
        return age.total_seconds() > (ttl_minutes * 60)