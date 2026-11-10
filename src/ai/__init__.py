"""AI module for sentiment analysis and news ingestion."""

from src.ai.models import NewsArticle, SentimentAnalysis, MarketContext
from src.ai.news_client import NewsAPIClient

__all__ = [
    "NewsArticle",
    "SentimentAnalysis",
    "MarketContext",
    "NewsAPIClient",
]