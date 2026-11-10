"""Execution models for orders, positions, and accounts."""

from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import Optional, List


class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"
    STOP_LIMIT = "STOP_LIMIT"


class OrderStatus(str, Enum):
    PENDING = "PENDING"
    FILLED = "FILLED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"


@dataclass
class Order:
    """Represents a trading order."""

    order_id: str
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: int
    limit_price: Optional[float] = None
    stop_price: Optional[float] = None
    status: OrderStatus = OrderStatus.PENDING
    filled_quantity: int = 0
    average_fill_price: float = 0.0
    created_at: datetime = field(default_factory=datetime.now)
    filled_at: Optional[datetime] = None
    strategy_name: str = "MANUAL"
    rejection_reason: Optional[str] = None

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        d = asdict(self)
        d["side"] = self.side.value
        d["order_type"] = self.order_type.value
        d["status"] = self.status.value
        d["created_at"] = self.created_at.isoformat()
        if self.filled_at:
            d["filled_at"] = self.filled_at.isoformat()
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "Order":
        """Deserialize from dictionary."""
        d = dict(data)
        d["side"] = OrderSide(d["side"])
        d["order_type"] = OrderType(d["order_type"])
        d["status"] = OrderStatus(d["status"])
        if isinstance(d.get("created_at"), str):
            d["created_at"] = datetime.fromisoformat(d["created_at"])
        if isinstance(d.get("filled_at"), str):
            d["filled_at"] = datetime.fromisoformat(d["filled_at"])
        return cls(**d)


@dataclass
class Position:
    """Active open position."""

    symbol: str
    quantity: int
    entry_price: float
    current_price: float
    unrealized_pnl: float = 0.0
    unrealized_pnl_pct: float = 0.0
    opened_at: datetime = field(default_factory=datetime.now)

    def update_price(self, new_price: float) -> None:
        """Update current price and recalculate unrealized P&L."""
        self.current_price = new_price
        self.unrealized_pnl = (new_price - self.entry_price) * self.quantity
        if self.entry_price > 0:
            self.unrealized_pnl_pct = (new_price - self.entry_price) / self.entry_price


@dataclass
class AccountInfo:
    """Broker account balances and status."""

    cash: float
    portfolio_value: float
    buying_power: float
    currency: str = "USD"
    day_trades_remaining: int = 3
    is_pattern_day_trader: bool = False
    open_positions: List[Position] = field(default_factory=list)