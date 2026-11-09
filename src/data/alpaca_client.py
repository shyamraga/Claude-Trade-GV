import os
import json
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, Dict, Any

from src.data.models import Bar, Quote, TimeFrame


def load_env_file(filepath: Optional[str] = None) -> None:
    """Lightweight .env loader that does not require external dependencies."""
    if filepath is None:
        filepath = Path(__file__).resolve().parent.parent.parent / ".env"
    path = Path(filepath)
    if not path.exists():
        return
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip("'\"")
                if k not in os.environ:
                    os.environ[k] = v


class AlpacaDataClient:
    """Client for Alpaca Market Data API v2."""

    BASE_URL = "https://data.alpaca.markets/v2"

    def __init__(self, key_id: Optional[str] = None, secret_key: Optional[str] = None):
        load_env_file()
        self.key_id = key_id or os.environ.get("APCA_API_KEY_ID")
        self.secret_key = secret_key or os.environ.get("APCA_API_SECRET_KEY")

        if not self.key_id or not self.secret_key:
            raise ValueError("Alpaca API credentials missing. Set APCA_API_KEY_ID and APCA_API_SECRET_KEY in .env or environment.")

    def _request(self, endpoint: str, params: Optional[Dict[str, Any]] = None, max_retries: int = 3) -> Dict[str, Any]:
        """Perform authenticated HTTP GET request to Alpaca Market Data API."""
        query_str = ""
        if params:
            query_parts = []
            for k, v in params.items():
                if v is not None:
                    query_parts.append(f"{k}={urllib.parse.quote(str(v))}")
            if query_parts:
                query_str = "?" + "&".join(query_parts)

        url = f"{self.BASE_URL}{endpoint}{query_str}"
        headers = {
            "APCA-API-KEY-ID": self.key_id,
            "APCA-API-SECRET-KEY": self.secret_key,
            "Content-Type": "application/json"
        }

        last_error = None
        for attempt in range(max_retries):
            req = urllib.request.Request(url, headers=headers)
            try:
                with urllib.request.urlopen(req, timeout=15) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                last_error = e
                # Handle rate limiting (429)
                if e.code == 429:
                    sleep_time = 1.0 * (2 ** attempt)
                    time.sleep(sleep_time)
                    continue
                # If resource not found or bad request, re-raise immediately
                raise RuntimeError(f"Alpaca API HTTP Error {e.code}: {e.read().decode('utf-8')}") from e
            except Exception as e:
                last_error = e
                time.sleep(0.5 * (attempt + 1))

        raise RuntimeError(f"Alpaca API request failed after {max_retries} attempts: {last_error}")

    def get_bars(
        self,
        symbol: str,
        timeframe: TimeFrame = TimeFrame.M15,
        limit: int = 100,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None
    ) -> List[Bar]:
        """Fetch historical OHLCV bars for a symbol."""
        symbol = symbol.upper().strip()
        params: Dict[str, Any] = {
            "timeframe": timeframe.alpaca_timeframe,
            "limit": min(limit, 10000),
            "adjustment": "all",
            "feed": "iex"  # Free paper tier uses IEX feed
        }
        if start:
            params["start"] = start.isoformat()
        if end:
            params["end"] = end.isoformat()

        data = self._request(f"/stocks/{symbol}/bars", params=params)
        raw_bars = data.get("bars", []) or []

        bars: List[Bar] = []
        for b in raw_bars:
            ts_str = b.get("t")
            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00")) if ts_str else datetime.now(timezone.utc)
            bars.append(Bar(
                symbol=symbol,
                timestamp=ts,
                open=float(b.get("o", 0.0)),
                high=float(b.get("h", 0.0)),
                low=float(b.get("l", 0.0)),
                close=float(b.get("c", 0.0)),
                volume=float(b.get("v", 0.0)),
                vwap=float(b["vw"]) if b.get("vw") is not None else None
            ))
        return bars

    def get_latest_bar(self, symbol: str) -> Optional[Bar]:
        """Fetch the most recent completed bar for a symbol."""
        symbol = symbol.upper().strip()
        params = {"feed": "iex"}
        try:
            data = self._request(f"/stocks/{symbol}/bars/latest", params=params)
            raw = data.get("bar")
            if not raw:
                return None
            ts_str = raw.get("t")
            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00")) if ts_str else datetime.now(timezone.utc)
            return Bar(
                symbol=symbol,
                timestamp=ts,
                open=float(raw.get("o", 0.0)),
                high=float(raw.get("h", 0.0)),
                low=float(raw.get("l", 0.0)),
                close=float(raw.get("c", 0.0)),
                volume=float(raw.get("v", 0.0)),
                vwap=float(raw["vw"]) if raw.get("vw") is not None else None
            )
        except Exception:
            return None

    def get_latest_quote(self, symbol: str) -> Optional[Quote]:
        """Fetch the latest real-time quote (bid/ask) for a symbol."""
        symbol = symbol.upper().strip()
        params = {"feed": "iex"}
        try:
            data = self._request(f"/stocks/{symbol}/quotes/latest", params=params)
            raw = data.get("quote")
            if not raw:
                return None
            ts_str = raw.get("t")
            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00")) if ts_str else datetime.now(timezone.utc)
            return Quote(
                symbol=symbol,
                timestamp=ts,
                bid_price=float(raw.get("bp", 0.0)),
                ask_price=float(raw.get("ap", 0.0)),
                bid_size=float(raw.get("bs", 0.0)),
                ask_size=float(raw.get("as", 0.0))
            )
        except Exception:
            return None
