import time
import logging
from datetime import datetime
from typing import Optional, List, Dict

from src.data.models import Bar, Quote, TimeFrame
from src.data.alpaca_client import AlpacaDataClient
from src.data.yahoo_client import YahooDataClient

logger = logging.getLogger("FeedManager")

CRYPTO_NORMALIZATION = {
    "BTC": "BTC-USD",
    "BITCOIN": "BTC-USD",
    "ETH": "ETH-USD",
    "ETHEREUM": "ETH-USD",
    "SOL": "SOL-USD",
    "SOLANA": "SOL-USD",
    "AVAX": "AVAX-USD",
    "AVALANCHE": "AVAX-USD",
    "DOGE": "DOGE-USD",
    "DOGECOIN": "DOGE-USD",
    "BNB": "BNB-USD",
    "XRP": "XRP-USD",
    "ADA": "ADA-USD",
    "LINK": "LINK-USD",
    "SUI": "SUI-USD",
    "NEAR": "NEAR-USD",
    "APT": "APT-USD",
}


class FeedManager:
    """Unified Market Data Feed Manager with automatic fallback and in-memory TTL bar cache."""

    def __init__(self, primary_provider: str = "alpaca", cache_ttl: float = 20.0):
        self.primary_provider = primary_provider.lower()
        self.alpaca: Optional[AlpacaDataClient] = None
        self.yahoo = YahooDataClient()
        self._cache: Dict[str, tuple[float, List[Bar]]] = {}
        self.cache_ttl = cache_ttl

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
        """Fetch historical bars with in-memory caching and automatic fallback."""
        symbol = symbol.upper().strip()

        # Normalize known crypto symbols to Yahoo -USD ticker
        if "/" in symbol:
            parts = symbol.split("/", 1)
            base = parts[0]
            quote = parts[1]
            if quote in ("USDT", "USD", "USDC", "BUSD"):
                symbol = f"{base}-USD"
            else:
                symbol = f"{base}-{quote}"
        elif symbol in CRYPTO_NORMALIZATION:
            symbol = CRYPTO_NORMALIZATION[symbol]

        cache_key = f"{symbol}:{timeframe.value}:{limit}"
        now = time.time()

        # Check in-memory TTL cache for non-ranged queries
        if not start and not end and cache_key in self._cache:
            cache_time, cached_bars = self._cache[cache_key]
            if now - cache_time < self.cache_ttl and cached_bars:
                return cached_bars

        bars: List[Bar] = []

        # Crypto pairs (e.g. BTC-USD) and Indian equities (.NS, .BO) are retrieved directly from Yahoo
        if "-USD" in symbol or "/" in symbol or symbol.endswith(".NS") or symbol.endswith(".BO") or ".NS" in symbol or ".BO" in symbol:
            try:
                bars = self.yahoo.get_bars(symbol, timeframe=timeframe, limit=limit)
            except Exception as e:
                logger.warning("Yahoo Finance get_bars failed for %s: %s", symbol, e)
        else:
            # Try Alpaca first for US equities
            if self.primary_provider == "alpaca" and self.alpaca:
                try:
                    bars = self.alpaca.get_bars(symbol, timeframe=timeframe, limit=limit, start=start, end=end)
                except Exception as e:
                    logger.warning("Alpaca get_bars failed for %s (%s). Falling back to Yahoo Finance.", symbol, e)

            # Fallback to Yahoo if Alpaca was unavailable or returned empty
            if not bars:
                try:
                    bars = self.yahoo.get_bars(symbol, timeframe=timeframe, limit=limit)
                except Exception as e:
                    logger.warning("Yahoo fallback get_bars failed for %s: %s", symbol, e)

        if bars:
            self._cache[cache_key] = (now, bars)
            return bars

        # Stale-while-revalidate: return last cached bars if available instead of failing completely
        if cache_key in self._cache and self._cache[cache_key][1]:
            logger.info("Serving last known cached bars for %s due to upstream provider delay.", symbol)
            return self._cache[cache_key][1]

        return []

    def get_bars_batch(
        self,
        symbols: List[str],
        timeframe: TimeFrame = TimeFrame.M15,
        limit: int = 100,
        max_workers: int = 16,
    ) -> Dict[str, List[Bar]]:
        """
        Fetch historical bars for multiple symbols concurrently using ThreadPoolExecutor.
        Ensures high throughput across broad multi-asset universes.
        """
        results: Dict[str, List[Bar]] = {}
        if not symbols:
            return results

        from concurrent.futures import ThreadPoolExecutor, as_completed

        def _fetch(sym: str):
            try:
                b = self.get_bars(sym, timeframe=timeframe, limit=limit)
                return sym, b
            except Exception as e:
                logger.debug("Failed to fetch bars for %s: %s", sym, e)
                return sym, []

        workers = min(max_workers, max(1, len(symbols)))
        with ThreadPoolExecutor(max_workers=workers) as executor:
            future_to_sym = {executor.submit(_fetch, s): s for s in symbols}
            for future in as_completed(future_to_sym):
                sym, bars = future.result()
                if bars:
                    results[sym] = bars
        return results

    def get_latest_bar(self, symbol: str) -> Optional[Bar]:
        """Fetch latest bar with fallback."""
        symbol = symbol.upper().strip()
        if symbol.endswith(".NS") or symbol.endswith(".BO") or "-USD" in symbol:
            bars = self.yahoo.get_bars(symbol, timeframe=TimeFrame.M1, limit=1)
            return bars[-1] if bars else None

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
        if symbol.endswith(".NS") or symbol.endswith(".BO") or "-USD" in symbol:
            return self.yahoo.get_latest_quote(symbol)

        if self.primary_provider == "alpaca" and self.alpaca:
            try:
                quote = self.alpaca.get_latest_quote(symbol)
                if quote and (quote.bid_price > 0 or quote.ask_price > 0):
                    return quote
            except Exception as e:
                logger.warning("Alpaca get_quote failed for %s (%s). Falling back.", symbol, e)

        return self.yahoo.get_latest_quote(symbol)
