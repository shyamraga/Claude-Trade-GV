from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Dict, Any


class TimeFrame(str, Enum):
    M1 = "1m"
    M5 = "5m"
    M15 = "15m"
    H1 = "1h"
    D1 = "1d"

    @property
    def alpaca_timeframe(self) -> str:
        mapping = {
            TimeFrame.M1: "1Min",
            TimeFrame.M5: "5Min",
            TimeFrame.M15: "15Min",
            TimeFrame.H1: "1Hour",
            TimeFrame.D1: "1Day"
        }
        return mapping[self]

    @property
    def minutes(self) -> int:
        mapping = {
            TimeFrame.M1: 1,
            TimeFrame.M5: 5,
            TimeFrame.M15: 15,
            TimeFrame.H1: 60,
            TimeFrame.D1: 1440
        }
        return mapping[self]


@dataclass
class Bar:
    symbol: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    vwap: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "timestamp": self.timestamp.isoformat(),
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "vwap": self.vwap
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Bar":
        ts = data["timestamp"]
        if isinstance(ts, str):
            ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return cls(
            symbol=data["symbol"],
            timestamp=ts,
            open=float(data["open"]),
            high=float(data["high"]),
            low=float(data["low"]),
            close=float(data["close"]),
            volume=float(data["volume"]),
            vwap=float(data["vwap"]) if data.get("vwap") is not None else None
        )


@dataclass
class Quote:
    symbol: str
    timestamp: datetime
    bid_price: float
    ask_price: float
    bid_size: float
    ask_size: float

    @property
    def mid_price(self) -> float:
        return round((self.bid_price + self.ask_price) / 2.0, 4)

    @property
    def spread(self) -> float:
        return round(max(0.0, self.ask_price - self.bid_price), 4)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "timestamp": self.timestamp.isoformat(),
            "bid_price": self.bid_price,
            "ask_price": self.ask_price,
            "bid_size": self.bid_size,
            "ask_size": self.ask_size,
            "mid_price": self.mid_price,
            "spread": self.spread
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Quote":
        ts = data["timestamp"]
        if isinstance(ts, str):
            ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return cls(
            symbol=data["symbol"],
            timestamp=ts,
            bid_price=float(data["bid_price"]),
            ask_price=float(data["ask_price"]),
            bid_size=float(data["bid_size"]),
            ask_size=float(data["ask_size"])
        )
