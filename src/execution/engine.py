"""Execution engine orchestrating broker routing, risk checks, and trade post-mortems."""

import logging
import uuid
from enum import Enum
from typing import Optional, List, Dict
from datetime import datetime

from src.execution.broker_base import BaseBroker
from src.execution.virtual_broker import VirtualBroker
from src.execution.alpaca_broker import AlpacaBroker
from src.execution.models import Order, OrderSide, OrderType, OrderStatus, Position, AccountInfo
from src.risk.circuit_breaker import CircuitBreaker
from src.risk.post_mortem import PostMortemRepository
from src.risk.models import TradeRecord

logger = logging.getLogger(__name__)


class ExecutionMode(str, Enum):
    VIRTUAL = "VIRTUAL"
    LIVE = "LIVE"


class ExecutionEngine:
    """
    Unified execution engine routing orders to Virtual or Live brokers,
    enforcing pre-trade risk checks, and creating loss post-mortems.
    """

    def __init__(
        self,
        mode: ExecutionMode = ExecutionMode.VIRTUAL,
        virtual_broker: Optional[VirtualBroker] = None,
        live_broker: Optional[AlpacaBroker] = None,
        circuit_breaker: Optional[CircuitBreaker] = None,
        post_mortem_repo: Optional[PostMortemRepository] = None,
    ):
        """Initialize execution engine."""
        self.mode = mode
        self.virtual_broker = virtual_broker or VirtualBroker()
        self.live_broker = live_broker or AlpacaBroker()
        self.circuit_breaker = circuit_breaker or CircuitBreaker()
        self.post_mortem_repo = post_mortem_repo or PostMortemRepository()
        self.trade_history: List[TradeRecord] = []
        self._entry_records: Dict[str, Order] = {}

    @property
    def broker(self) -> BaseBroker:
        """Get active broker instance according to mode."""
        return self.live_broker if self.mode == ExecutionMode.LIVE else self.virtual_broker

    def set_mode(self, mode: ExecutionMode) -> None:
        """Switch execution mode."""
        self.mode = mode
        logger.info(f"Execution engine mode switched to: {mode.value}")

    def execute_signal(
        self,
        symbol: str,
        action: str,  # "BUY", "SELL", "EXIT"
        price: float,
        quantity: int,
        strategy_name: str = "MANUAL",
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        bypass_risk: bool = False,
        exit_reason: str = "SIGNAL_EXIT",
    ) -> Optional[Order]:
        """
        Execute a trading signal through full risk & memory safety checks.
        """
        symbol = symbol.upper()
        action = action.upper()

        if action not in ("BUY", "SELL", "EXIT"):
            logger.info(f"Signal action {action} requires no execution.")
            return None

        # Update virtual broker market price if running in virtual mode
        if isinstance(self.broker, VirtualBroker):
            self.broker.set_market_price(symbol, price)

        # 1. Pre-trade Memory Filter Check (prevent repeating past mistake setups)
        if not bypass_risk and action in ("BUY", "SELL"):
            allowed, block_reason = self.post_mortem_repo.check_pre_trade_filter(
                symbol=symbol, strategy_name=strategy_name
            )
            if not allowed:
                logger.warning(f"ORDER REJECTED BY PRE-TRADE MEMORY: {block_reason}")
                return None

        # 2. Circuit Breaker & Position Risk Check
        if not bypass_risk:
            risk_check = self.circuit_breaker.validate_pre_trade(
                symbol=symbol,
                side="BUY" if action == "BUY" else "SELL",
                price=price,
                proposed_shares=quantity,
            )
            if not risk_check.approved:
                logger.warning(f"ORDER BLOCKED BY CIRCUIT BREAKER: {risk_check.reason}")
                return None

            quantity = risk_check.max_allowed_shares
            if stop_loss is None:
                stop_loss = risk_check.calculated_stop_loss
            if take_profit is None:
                take_profit = risk_check.calculated_take_profit

        # 3. Handle EXIT vs BUY/SELL order
        if action == "EXIT":
            existing_pos = self.broker.get_position(symbol)
            if not existing_pos:
                logger.info(f"No open position to exit for {symbol}.")
                return None

            # To exit a SHORT position, submit BUY (cover); to exit a LONG position, submit SELL
            exit_side = OrderSide.BUY if existing_pos.side.upper() == "SHORT" else OrderSide.SELL
            order = Order(
                order_id=f"ord_{uuid.uuid4().hex[:8]}",
                symbol=symbol,
                side=exit_side,
                order_type=OrderType.MARKET,
                quantity=existing_pos.quantity,
                strategy_name=strategy_name,
                exit_reason=exit_reason,
            )
        elif action == "SELL":
            # Short entry order
            order = Order(
                order_id=f"ord_{uuid.uuid4().hex[:8]}",
                symbol=symbol,
                side=OrderSide.SELL,
                order_type=OrderType.MARKET,
                quantity=quantity,
                strategy_name=strategy_name,
                stop_loss=stop_loss,
                take_profit=take_profit,
            )
        else:  # BUY
            # Long entry order
            order = Order(
                order_id=f"ord_{uuid.uuid4().hex[:8]}",
                symbol=symbol,
                side=OrderSide.BUY,
                order_type=OrderType.MARKET,
                quantity=quantity,
                strategy_name=strategy_name,
                stop_loss=stop_loss,
                take_profit=take_profit,
            )

        # 4. Dispatch Order to Broker
        executed_order = self.broker.submit_order(order)

        # 5. Track Fill and Check for Trade Completion
        if executed_order.status == OrderStatus.FILLED:
            self._handle_fill(executed_order, price)

        return executed_order

    def check_position_stops(self, symbol: str, current_price: float) -> Optional[Order]:
        """
        Check if an active position has crossed its stop-loss or take-profit price.
        If triggered, automatically execute exit with appropriate reason.
        """
        pos = self.broker.get_position(symbol)
        if not pos or pos.quantity <= 0:
            return None

        pos.update_price(current_price)

        # LONG position check: stop below entry, take-profit above entry
        if pos.side.upper() == "LONG":
            if pos.stop_loss and current_price <= pos.stop_loss:
                logger.info(f"STOP LOSS TRIGGERED for LONG {symbol}: price ${current_price:.2f} <= SL ${pos.stop_loss:.2f}")
                return self.execute_signal(
                    symbol=symbol,
                    action="EXIT",
                    price=current_price,
                    quantity=pos.quantity,
                    strategy_name=pos.strategy,
                    bypass_risk=True,
                    exit_reason="STOP_LOSS",
                )
            elif pos.take_profit and current_price >= pos.take_profit:
                logger.info(f"TAKE PROFIT TRIGGERED for LONG {symbol}: price ${current_price:.2f} >= TP ${pos.take_profit:.2f}")
                return self.execute_signal(
                    symbol=symbol,
                    action="EXIT",
                    price=current_price,
                    quantity=pos.quantity,
                    strategy_name=pos.strategy,
                    bypass_risk=True,
                    exit_reason="TAKE_PROFIT",
                )

        # SHORT position check: stop above entry, take-profit below entry
        elif pos.side.upper() == "SHORT":
            if pos.stop_loss and current_price >= pos.stop_loss:
                logger.info(f"STOP LOSS TRIGGERED for SHORT {symbol}: price ${current_price:.2f} >= SL ${pos.stop_loss:.2f}")
                return self.execute_signal(
                    symbol=symbol,
                    action="EXIT",
                    price=current_price,
                    quantity=pos.quantity,
                    strategy_name=pos.strategy,
                    bypass_risk=True,
                    exit_reason="STOP_LOSS",
                )
            elif pos.take_profit and current_price <= pos.take_profit:
                logger.info(f"TAKE PROFIT TRIGGERED for SHORT {symbol}: price ${current_price:.2f} <= TP ${pos.take_profit:.2f}")
                return self.execute_signal(
                    symbol=symbol,
                    action="EXIT",
                    price=current_price,
                    quantity=pos.quantity,
                    strategy_name=pos.strategy,
                    bypass_risk=True,
                    exit_reason="TAKE_PROFIT",
                )

        return None

    def _handle_fill(self, order: Order, current_price: float) -> None:
        """Handle order fill and record completed trades for both long and short."""
        symbol = order.symbol
        existing_pos = self.broker.get_position(symbol)

        # Check if this order closed out an entry
        if symbol in self._entry_records and (existing_pos is None or existing_pos.quantity == 0):
            entry_order = self._entry_records.pop(symbol)

            if entry_order.side == OrderSide.BUY:
                # Closed a LONG position: profit when exit > entry
                pnl = (order.average_fill_price - entry_order.average_fill_price) * order.quantity
                pnl_pct = (order.average_fill_price - entry_order.average_fill_price) / entry_order.average_fill_price if entry_order.average_fill_price > 0 else 0.0
                trade_side = "BUY"
            else:
                # Covered a SHORT position: profit when exit (buy) < entry (sell)
                pnl = (entry_order.average_fill_price - order.average_fill_price) * order.quantity
                pnl_pct = (entry_order.average_fill_price - order.average_fill_price) / entry_order.average_fill_price if entry_order.average_fill_price > 0 else 0.0
                trade_side = "SELL"

            reason = getattr(order, "exit_reason", None) or "SIGNAL_EXIT"
            trade_record = TradeRecord(
                trade_id=f"trade_{uuid.uuid4().hex[:8]}",
                symbol=symbol,
                side=trade_side,
                quantity=order.quantity,
                entry_price=entry_order.average_fill_price,
                exit_price=order.average_fill_price,
                pnl=round(pnl, 2),
                pnl_pct=round(pnl_pct, 4),
                entry_time=entry_order.filled_at or datetime.now(),
                exit_time=order.filled_at or datetime.now(),
                strategy_name=order.strategy_name,
                reason=reason,
            )
            self.trade_history.append(trade_record)
            self.circuit_breaker.record_trade(trade_record)

            # 6. Automatic Continuous Learning: Generate Post-Mortem on Loss
            if trade_record.pnl < 0:
                logger.warning(
                    f"AUTOMATIC LOSS POST-MORTEM TRIGGERED: -${abs(trade_record.pnl):.2f} on {symbol} ({trade_side})"
                )
                self.post_mortem_repo.create_post_mortem(
                    trade=trade_record,
                    root_cause=f"Adverse price movement following {order.strategy_name} {trade_side} entry",
                    market_condition="Live market conditions deviated from entry hypothesis",
                    preventative_rule=f"Exercise caution with {order.strategy_name} on {symbol}; verify higher-timeframe trend alignment",
                    tags=[symbol, order.strategy_name, "automated_loss", trade_side.lower()],
                )
        else:
            # Opening new position (either LONG or SHORT)
            self._entry_records[symbol] = order