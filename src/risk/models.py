"""Risk models and configuration definitions."""

from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional


@dataclass
class RiskConfig:
    """Risk management parameters and thresholds."""

    max_daily_drawdown_pct: float = 0.03  # 3% max portfolio loss per day
    max_position_pct: float = 0.10  # 10% max allocation per position
    max_portfolio_risk_pct: float = 0.01  # 1% risk per trade
    stop_loss_pct: float = 0.02  # 2% standard stop loss
    take_profit_pct: float = 0.04  # 4% standard profit target (2:1 R:R)
    consecutive_loss_limit: int = 3  # 3 consecutive losses triggers cooldown
    cooldown_duration_hours: float = 4.0  # 4-hour trading pause


@dataclass
class RiskCheckResult:
    """Result of a pre-trade risk assessment."""

    approved: bool
    reason: str
    risk_level: str = "NORMAL"  # NORMAL, ELEVATED, BLOCKED
    max_allowed_shares: int = 0
    calculated_stop_loss: Optional[float] = None
    calculated_take_profit: Optional[float] = None


@dataclass
class TradeRecord:
    """Summary of a completed trade for risk tracking."""

    trade_id: str
    symbol: str
    side: str  # BUY or SELL
    quantity: int
    entry_price: float
    exit_price: float
    pnl: float
    pnl_pct: float
    entry_time: datetime
    exit_time: datetime
    strategy_name: str
    reason: str = "NORMAL_EXIT"  # STOP_LOSS, TAKE_PROFIT, SIGNAL_EXIT

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        d = asdict(self)
        d["entry_time"] = self.entry_time.isoformat()
        d["exit_time"] = self.exit_time.isoformat()
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "TradeRecord":
        """Deserialize from dictionary."""
        d = dict(data)
        if isinstance(d.get("entry_time"), str):
            d["entry_time"] = datetime.fromisoformat(d["entry_time"])
        if isinstance(d.get("exit_time"), str):
            d["exit_time"] = datetime.fromisoformat(d["exit_time"])
        return cls(**d)