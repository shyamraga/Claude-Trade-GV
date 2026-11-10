from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Dict, Any


@dataclass
class MACDResult:
    """Encapsulates Moving Average Convergence Divergence components."""
    macd: List[Optional[float]]
    signal: List[Optional[float]]
    histogram: List[Optional[float]]

    @property
    def latest_macd(self) -> Optional[float]:
        return self.macd[-1] if self.macd else None

    @property
    def latest_signal(self) -> Optional[float]:
        return self.signal[-1] if self.signal else None

    @property
    def latest_histogram(self) -> Optional[float]:
        return self.histogram[-1] if self.histogram else None


@dataclass
class BollingerBandsResult:
    """Encapsulates Bollinger Bands calculation results."""
    upper: List[Optional[float]]
    middle: List[Optional[float]]
    lower: List[Optional[float]]
    bandwidth: List[Optional[float]]
    percent_b: List[Optional[float]]

    @property
    def latest_upper(self) -> Optional[float]:
        return self.upper[-1] if self.upper else None

    @property
    def latest_middle(self) -> Optional[float]:
        return self.middle[-1] if self.middle else None

    @property
    def latest_lower(self) -> Optional[float]:
        return self.lower[-1] if self.lower else None

    @property
    def latest_percent_b(self) -> Optional[float]:
        return self.percent_b[-1] if self.percent_b else None


@dataclass
class IndicatorSnapshot:
    """Snapshot of technical indicators calculated at a specific bar."""
    symbol: str
    timestamp: datetime
    close: float
    sma_20: Optional[float] = None
    sma_50: Optional[float] = None
    ema_9: Optional[float] = None
    ema_21: Optional[float] = None
    ema_50: Optional[float] = None
    rsi_14: Optional[float] = None
    macd: Optional[float] = None
    macd_signal: Optional[float] = None
    macd_histogram: Optional[float] = None
    bb_upper: Optional[float] = None
    bb_middle: Optional[float] = None
    bb_lower: Optional[float] = None
    atr_14: Optional[float] = None
    vwap: Optional[float] = None
    custom: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "close": self.close,
            "sma_20": self.sma_20,
            "sma_50": self.sma_50,
            "ema_9": self.ema_9,
            "ema_21": self.ema_21,
            "ema_50": self.ema_50,
            "rsi_14": self.rsi_14,
            "macd": self.macd,
            "macd_signal": self.macd_signal,
            "macd_histogram": self.macd_histogram,
            "bb_upper": self.bb_upper,
            "bb_middle": self.bb_middle,
            "bb_lower": self.bb_lower,
            "atr_14": self.atr_14,
            "vwap": self.vwap,
            "custom": self.custom,
        }
