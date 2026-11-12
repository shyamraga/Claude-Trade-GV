import json
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

from src.data.models import Bar, Quote, TimeFrame


class YahooDataClient:
    """Free, lightweight Yahoo Finance market data client without dependencies."""

    BASE_URL = "https://query1.finance.yahoo.com/v8/finance/chart"

    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

    def _map_interval(self, timeframe: TimeFrame) -> tuple[str, str]:
        """Maps TimeFrame to Yahoo interval and range."""
        mapping = {
            TimeFrame.M1: ("1m", "5d"),
            TimeFrame.M5: ("5m", "1mo"),
            TimeFrame.M15: ("15m", "1mo"),
            TimeFrame.H1: ("60m", "3mo"),
            TimeFrame.D1: ("1d", "1y"),
        }
        return mapping.get(timeframe, ("1d", "1y"))

    def get_bars(self, symbol: str, timeframe: TimeFrame = TimeFrame.M15, limit: int = 100) -> List[Bar]:
        """Fetch historical bars from Yahoo Finance."""
        symbol = symbol.upper().strip()

        # Normalize metals symbols to Yahoo commodity futures tickers
        if symbol in ("XAU/USD", "XAU-USD", "XAUUSD", "XAU", "GOLD"):
            symbol = "GC=F"
        elif symbol in ("XAG/USD", "XAG-USD", "XAGUSD", "XAG", "SILVER"):
            symbol = "SI=F"
        # Normalize crypto slash notation (e.g. BTC/USDT, ETH/USD) to Yahoo ticker format
        elif "/" in symbol:
            parts = symbol.split("/", 1)
            base = parts[0]
            quote = parts[1]
            if quote in ("USDT", "USD", "USDC", "BUSD"):
                symbol = f"{base}-USD"
            else:
                symbol = f"{base}-{quote}"

        interval, default_range = self._map_interval(timeframe)
        url = f"{self.BASE_URL}/{symbol}?interval={interval}&range={default_range}"

        req = urllib.request.Request(url, headers=self.headers)
        try:
            with urllib.request.urlopen(req, timeout=12) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            raise RuntimeError(f"Yahoo Finance request failed for {symbol}: {e}") from e

        results = data.get("chart", {}).get("result", [])
        if not results:
            return []

        item = results[0]
        timestamps = item.get("timestamp", [])
        quote_data = item.get("indicators", {}).get("quote", [{}])[0]

        opens = quote_data.get("open", [])
        highs = quote_data.get("high", [])
        lows = quote_data.get("low", [])
        closes = quote_data.get("close", [])
        volumes = quote_data.get("volume", [])

        bars: List[Bar] = []
        for i, ts_epoch in enumerate(timestamps):
            # Skip invalid null bars (market halts, missing ticks)
            if (
                i >= len(opens)
                or opens[i] is None
                or highs[i] is None
                or lows[i] is None
                or closes[i] is None
            ):
                continue

            ts = datetime.fromtimestamp(ts_epoch, tz=timezone.utc)
            vol = float(volumes[i]) if i < len(volumes) and volumes[i] is not None else 0.0
            bars.append(Bar(
                symbol=symbol,
                timestamp=ts,
                open=float(opens[i]),
                high=float(highs[i]),
                low=float(lows[i]),
                close=float(closes[i]),
                volume=vol,
                vwap=None
            ))

        if limit and len(bars) > limit:
            return bars[-limit:]
        return bars

    def get_latest_quote(self, symbol: str) -> Optional[Quote]:
        """Derive latest quote from Yahoo Finance recent bars."""
        bars = self.get_bars(symbol, TimeFrame.M1, limit=2)
        if not bars:
            return None
        last = bars[-1]
        # Approximation for quote when live order book is unavailable
        return Quote(
            symbol=symbol,
            timestamp=last.timestamp,
            bid_price=last.close,
            ask_price=last.close * 1.0002,
            bid_size=100.0,
            ask_size=100.0
        )
