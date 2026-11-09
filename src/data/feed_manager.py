import logging
from datetime import datetime
from typing import Optional, List, Dict

from src.data.models import Bar, Quote, TimeFrame
from src.data.alpaca_client import AlpacaDataClient
from src.data.yahoo_client import YahooDataClient

logger = logging.getLogger("FeedManager")


class FeedManager:
    """Unified Market Data Feed Manager with automatic fallback to secondary provider."""

    def __init__(self, primary_provider: str = "alpaca"):
        self.primary_provider = primary_provider.lower()
        self.alpaca: Optional[AlpacaDataClient] = None
        self.yahoo = YahooDataClient()

        try:
            self.alpaca = AlpacaDataClient()
        except Exception as e:
            logger.warning("AlpacaDataClient could not be initialized (%s); fallback to Yahoo enabled.", e)

    def get_bars(
        self,
        symbol: str,
        timeframe: TimeFrame = TimeFrame.M15,
        limit: int = 100,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None
    ) -> List[Bar]:
        """Fetch historical bars with automatic fallback."""
        symbol = symbol.upper().strip()

        # Try Alpaca first
        if self.primary_provider == "alpaca" and self.alpaca:
            try:
                bars = self.alpaca.get_bars(symbol, timeframe=timeframe, limit=limit, start=start, end=end)
                if bars:
                    return bars
            except Exception as e:
                logger.warning("Alpaca get_bars failed for %s (%s). Falling back to Yahoo Finance.", symbol, e)

        # Fallback to Yahoo
        return self.yahoo.get_bars(symbol, timeframe=timeframe, limit=limit)

    def get_latest_bar(self, symbol: str) -> Optional[Bar]:
        """Fetch latest bar with fallback."""
        symbol = symbol.upper().strip()
        if self.primary_provider == "alpaca" and self.alpaca:
            try:
                bar = self.alpaca.get_latest_bar(symbol)
                if bar:
                    return bar
            except Exception as e:
                logger.warning("Alpaca get_latest_bar failed for %s (%s). Falling back.", symbol, e)

        bars = self.yahoo.get_bars(symbol, timeframe=TimeFrame.M1, limit=1)
        return bars[-1] if bars else None

    def get_quote(self, symbol: str) -> Optional[Quote]:
        """Fetch latest quote with fallback."""
        symbol = symbol.upper().strip()
        if self.primary_provider == "alpaca" and self.alpaca:
            try:
                quote = self.alpaca.get_latest_quote(symbol)
                if quote and (quote.bid_price > 0 or quote.ask_price > 0):
                    return quote
            except Exception as e:
                logger.warning("Alpaca get_quote failed for %s (%s). Falling back.", symbol, e)

        return self.yahoo.get_latest_quote(symbol)
