"""In-memory virtual paper broker simulating fills and balances."""

import logging
from datetime import datetime
from typing import Dict, List, Optional
import uuid

from src.execution.broker_base import BaseBroker
from src.execution.models import Order, OrderSide, OrderStatus, OrderType, Position, AccountInfo

logger = logging.getLogger(__name__)


class VirtualBroker(BaseBroker):
    """
    Virtual paper trading broker.
    Maintains in-memory cash, positions, order books, and realistic fill simulation.
    """

    def __init__(self, initial_cash: float = 100000.0, slippage_pct: float = 0.0005):
        """Initialize with starting cash and slippage model."""
        self.initial_cash = initial_cash
        self.cash = initial_cash
        self.slippage_pct = slippage_pct
        self.positions: Dict[str, Position] = {}
        self.orders: Dict[str, Order] = {}
        self.market_prices: Dict[str, float] = {}

    def set_market_price(self, symbol: str, price: float) -> None:
        """Update simulated market price for a symbol."""
        symbol = symbol.upper()
        self.market_prices[symbol] = price
        if symbol in self.positions:
            self.positions[symbol].update_price(price)

    def get_account(self) -> AccountInfo:
        """Calculate and return account info."""
        positions_val = sum(pos.current_price * pos.quantity for pos in self.positions.values())
        portfolio_val = self.cash + positions_val
        buying_power = self.cash * 2.0  # 2x margin simulation

        return AccountInfo(
            cash=round(self.cash, 2),
            portfolio_value=round(portfolio_val, 2),
            buying_power=round(buying_power, 2),
            open_positions=list(self.positions.values()),
        )

    def get_positions(self) -> List[Position]:
        """Get all active positions."""
        return list(self.positions.values())

    def get_position(self, symbol: str) -> Optional[Position]:
        """Get position for a specific symbol."""
        return self.positions.get(symbol.upper())

    def submit_order(self, order: Order) -> Order:
        """Process and simulate fill for submitted order."""
        symbol = order.symbol.upper()
        market_price = self.market_prices.get(symbol, order.limit_price or 100.0)

        # Apply slippage
        if order.side == OrderSide.BUY:
            fill_price = market_price * (1.0 + self.slippage_pct)
        else:
            fill_price = market_price * (1.0 - self.slippage_pct)

        fill_price = round(fill_price, 2)
        cost = fill_price * order.quantity

        if order.side == OrderSide.BUY:
            if cost > self.cash:
                order.status = OrderStatus.REJECTED
                order.rejection_reason = f"Insufficient funds: required ${cost:,.2f}, available ${self.cash:,.2f}"
                self.orders[order.order_id] = order
                return order

            # Deduct cash, add position
            self.cash -= cost
            if symbol in self.positions:
                pos = self.positions[symbol]
                total_shares = pos.quantity + order.quantity
                avg_price = ((pos.entry_price * pos.quantity) + cost) / total_shares
                pos.quantity = total_shares
                pos.entry_price = round(avg_price, 2)
                pos.update_price(market_price)
            else:
                new_pos = Position(
                    symbol=symbol,
                    quantity=order.quantity,
                    entry_price=fill_price,
                    current_price=market_price,
                )
                new_pos.update_price(market_price)
                self.positions[symbol] = new_pos

        elif order.side == OrderSide.SELL:
            current_pos = self.positions.get(symbol)
            if not current_pos or current_pos.quantity < order.quantity:
                order.status = OrderStatus.REJECTED
                order.rejection_reason = f"Cannot sell {order.quantity} shares of {symbol}: position size is {current_pos.quantity if current_pos else 0}"
                self.orders[order.order_id] = order
                return order

            # Add proceeds, reduce position
            proceeds = fill_price * order.quantity
            self.cash += proceeds
            current_pos.quantity -= order.quantity

            if current_pos.quantity == 0:
                del self.positions[symbol]
            else:
                current_pos.update_price(market_price)

        # Mark order filled
        order.status = OrderStatus.FILLED
        order.filled_quantity = order.quantity
        order.average_fill_price = fill_price
        order.filled_at = datetime.now()

        self.orders[order.order_id] = order
        logger.info(f"Virtual order filled: {order.side.value} {order.quantity} {symbol} @ ${fill_price:.2f}")
        return order

    def cancel_order(self, order_id: str) -> bool:
        """Cancel an open order."""
        if order_id in self.orders:
            order = self.orders[order_id]
            if order.status == OrderStatus.PENDING:
                order.status = OrderStatus.CANCELLED
                return True
        return False

    def get_order(self, order_id: str) -> Optional[Order]:
        """Fetch order by ID."""
        return self.orders.get(order_id)

    def close_position(self, symbol: str) -> Optional[Order]:
        """Close full position at market."""
        pos = self.get_position(symbol)
        if not pos:
            return None

        order = Order(
            order_id=f"close_{uuid.uuid4().hex[:8]}",
            symbol=pos.symbol,
            side=OrderSide.SELL,
            order_type=OrderType.MARKET,
            quantity=pos.quantity,
        )
        return self.submit_order(order)