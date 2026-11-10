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
        """Calculate and return account info taking into account both long and short positions."""
        # For long positions: value is current_price * quantity
        # For short positions: value is entry_price * quantity + unrealized_pnl (collateral + pnl)
        positions_val = sum(
            (pos.entry_price * pos.quantity) + pos.unrealized_pnl
            for pos in self.positions.values()
        )
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
        """Process and simulate fill for submitted order (supports LONG and SHORT)."""
        symbol = order.symbol.upper()
        market_price = self.market_prices.get(symbol, order.limit_price or 100.0)

        # Apply slippage
        if order.side == OrderSide.BUY:
            fill_price = market_price * (1.0 + self.slippage_pct)
        else:
            fill_price = market_price * (1.0 - self.slippage_pct)

        fill_price = round(fill_price, 2)
        current_pos = self.positions.get(symbol)

        if order.side == OrderSide.BUY:
            # Case 1: BUY to COVER an existing SHORT position
            if current_pos and current_pos.side.upper() == "SHORT":
                shares_to_cover = min(order.quantity, current_pos.quantity)
                realized_pnl = (current_pos.entry_price - fill_price) * shares_to_cover
                # Return margin collateral plus/minus realized P&L to cash
                margin_returned = (current_pos.entry_price * shares_to_cover) + realized_pnl
                self.cash += margin_returned

                current_pos.quantity -= shares_to_cover
                if current_pos.quantity == 0:
                    del self.positions[symbol]
                else:
                    current_pos.update_price(market_price)

            # Case 2: BUY to open or add to a LONG position
            else:
                cost = fill_price * order.quantity
                if cost > self.cash:
                    order.status = OrderStatus.REJECTED
                    order.rejection_reason = f"Insufficient funds: required ${cost:,.2f}, available ${self.cash:,.2f}"
                    self.orders[order.order_id] = order
                    return order

                self.cash -= cost
                if current_pos and current_pos.side.upper() == "LONG":
                    total_shares = current_pos.quantity + order.quantity
                    avg_price = ((current_pos.entry_price * current_pos.quantity) + cost) / total_shares
                    current_pos.quantity = total_shares
                    current_pos.entry_price = round(avg_price, 2)
                    if order.stop_loss:
                        current_pos.stop_loss = order.stop_loss
                    if order.take_profit:
                        current_pos.take_profit = order.take_profit
                    current_pos.update_price(market_price)
                else:
                    new_pos = Position(
                        symbol=symbol,
                        quantity=order.quantity,
                        entry_price=fill_price,
                        current_price=market_price,
                        side="LONG",
                        opened_at=order.filled_at or datetime.now(),
                        stop_loss=order.stop_loss,
                        take_profit=order.take_profit,
                        strategy=order.strategy_name or "MANUAL",
                    )
                    new_pos.update_price(market_price)
                    self.positions[symbol] = new_pos

        elif order.side == OrderSide.SELL:
            # Case 1: SELL to CLOSE an existing LONG position
            if current_pos and current_pos.side.upper() == "LONG":
                shares_to_sell = min(order.quantity, current_pos.quantity)
                proceeds = fill_price * shares_to_sell
                self.cash += proceeds
                current_pos.quantity -= shares_to_sell

                if current_pos.quantity == 0:
                    del self.positions[symbol]
                else:
                    current_pos.update_price(market_price)

            # Case 2: SELL to open or add to a SHORT position
            else:
                margin_required = fill_price * order.quantity
                if margin_required > self.cash:
                    order.status = OrderStatus.REJECTED
                    order.rejection_reason = f"Insufficient margin for short: required ${margin_required:,.2f}, available ${self.cash:,.2f}"
                    self.orders[order.order_id] = order
                    return order

                self.cash -= margin_required
                if current_pos and current_pos.side.upper() == "SHORT":
                    total_shares = current_pos.quantity + order.quantity
                    avg_price = ((current_pos.entry_price * current_pos.quantity) + margin_required) / total_shares
                    current_pos.quantity = total_shares
                    current_pos.entry_price = round(avg_price, 2)
                    if order.stop_loss:
                        current_pos.stop_loss = order.stop_loss
                    if order.take_profit:
                        current_pos.take_profit = order.take_profit
                    current_pos.update_price(market_price)
                else:
                    new_pos = Position(
                        symbol=symbol,
                        quantity=order.quantity,
                        entry_price=fill_price,
                        current_price=market_price,
                        side="SHORT",
                        opened_at=order.filled_at or datetime.now(),
                        stop_loss=order.stop_loss,
                        take_profit=order.take_profit,
                        strategy=order.strategy_name or "MANUAL",
                    )
                    new_pos.update_price(market_price)
                    self.positions[symbol] = new_pos

        # Mark order filled
        order.status = OrderStatus.FILLED
        order.filled_quantity = order.quantity
        order.average_fill_price = fill_price
        order.filled_at = datetime.now()

        self.orders[order.order_id] = order
        action_name = "SHORT" if (order.side == OrderSide.SELL and (not current_pos or current_pos.side == "SHORT")) else order.side.value
        logger.info(f"Virtual order filled: {action_name} {order.quantity} {symbol} @ ${fill_price:.2f}")
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
        """Close full position at market (sells long or covers short)."""
        pos = self.get_position(symbol)
        if not pos:
            return None

        # To close short, submit BUY; to close long, submit SELL
        side = OrderSide.BUY if pos.side.upper() == "SHORT" else OrderSide.SELL
        order = Order(
            order_id=f"close_{uuid.uuid4().hex[:8]}",
            symbol=pos.symbol,
            side=side,
            order_type=OrderType.MARKET,
            quantity=pos.quantity,
        )
        return self.submit_order(order)