"""Execution engine orchestrating broker routing, risk checks, and trade post-mortems."""

import json
import logging
import uuid
from enum import Enum
from pathlib import Path
from typing import Optional, List, Dict
from datetime import datetime

from src.execution.broker_base import BaseBroker
from src.execution.virtual_broker import VirtualBroker
from src.execution.alpaca_broker import AlpacaBroker
from src.execution.models import Order, OrderSide, OrderType, OrderStatus, Position, AccountInfo
from src.risk.circuit_breaker import CircuitBreaker
from src.risk.post_mortem import PostMortemRepository
from src.risk.market_hours import MarketHoursManager
from src.risk.models import TradeRecord
from src.risk.trade_diagnostician import TradeDiagnostician

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
        trades_file: Optional[Path] = None,
    ):
        """Initialize execution engine."""
        self.mode = mode
        self.virtual_broker = virtual_broker or VirtualBroker()
        self.live_broker = live_broker or AlpacaBroker()
        self.circuit_breaker = circuit_breaker or CircuitBreaker()
        self.post_mortem_repo = post_mortem_repo or PostMortemRepository()
        self.trades_file = trades_file or (Path(__file__).resolve().parent.parent.parent / "data" / "trades" / "trades_history.json")
        self.trade_history: List[TradeRecord] = []
        self._entry_records: Dict[str, Order] = {}
        self._init_trades_storage()

    def _init_trades_storage(self) -> None:
        """Initialize persistent storage for trade history and load historical records."""
        self.trades_file.parent.mkdir(parents=True, exist_ok=True)
        self._load_trades_from_disk()

    def _load_trades_from_disk(self) -> None:
        """Load trade history from disk or reconstruct from post-mortem repository."""
        self.trade_history.clear()
        if self.trades_file.exists():
            try:
                data = json.loads(self.trades_file.read_text(encoding="utf-8"))
                for item in data:
                    self.trade_history.append(TradeRecord.from_dict(item))
            except Exception as e:
                logger.warning(f"Failed to read trades_history.json: {e}")

        # If trades file has fewer entries than post-mortems on disk, sync from post-mortems
        existing_ids = {t.trade_id for t in self.trade_history}
        if self.post_mortem_repo and hasattr(self.post_mortem_repo, "_cache"):
            for pm in self.post_mortem_repo._cache:
                tid = pm.post_mortem_id.replace("pm_", "tr_")
                if tid not in existing_ids:
                    tr = TradeRecord(
                        trade_id=tid,
                        symbol=pm.symbol,
                        side="BUY",
                        quantity=10,
                        entry_price=pm.entry_price,
                        exit_price=pm.exit_price,
                        pnl=pm.pnl,
                        pnl_pct=pm.pnl_pct,
                        entry_time=pm.entry_time,
                        exit_time=pm.exit_time,
                        strategy_name=pm.strategy_name,
                        reason=pm.outcome,
                    )
                    self.trade_history.append(tr)
                    existing_ids.add(tid)

        self.trade_history.sort(key=lambda t: t.exit_time)
        if self.trade_history:
            self._save_trades_to_disk()

    def _save_trades_to_disk(self) -> None:
        """Persist trade history to disk."""
        try:
            data = [t.to_dict() for t in self.trade_history]
            self.trades_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception as e:
            logger.warning(f"Failed to save trades to {self.trades_file}: {e}")

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

        # 0. Time-Zone & Market Session Guardian: Prevent opening trades when exchange is closed or on holidays
        if not bypass_risk and action in ("BUY", "SELL"):
            is_open, open_reason = MarketHoursManager.is_market_open(symbol)
            if not is_open:
                logger.warning(f"ORDER REJECTED BY MARKET HOURS GUARDIAN: {symbol} market is closed ({open_reason})")
                return None

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

            # If entry record is missing, reconstruct from existing position so closed trade is logged
            if symbol not in self._entry_records:
                entry_side = OrderSide.SELL if existing_pos.side.upper() == "SHORT" else OrderSide.BUY
                self._entry_records[symbol] = Order(
                    order_id=f"entry_{symbol}",
                    symbol=symbol,
                    side=entry_side,
                    order_type=OrderType.MARKET,
                    quantity=existing_pos.quantity,
                    average_fill_price=existing_pos.entry_price,
                    filled_at=existing_pos.opened_at or datetime.now(),
                    strategy_name=getattr(existing_pos, "strategy", strategy_name) or strategy_name,
                )

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
        Check if an active position has crossed its stop-loss, take-profit, or trailing stop.
        Dynamically adjusts stop-loss to breakeven once in profit and trails stops behind gains.
        If triggered, automatically execute exit with appropriate reason.
        """
        pos = self.broker.get_position(symbol)
        if not pos or pos.quantity <= 0:
            return None

        pos.update_price(current_price)

        # -------------------------------------------------------------
        # LONG Position: Breakeven, Trailing Stop & Exit Arbitration
        # -------------------------------------------------------------
        if pos.side.upper() == "LONG":
            entry = pos.entry_price
            if entry > 0:
                # 1. Breakeven Advancement: Move stop to entry once +1.2% in profit or 50% to TP
                be_trigger = entry + (pos.take_profit - entry) * 0.5 if pos.take_profit and pos.take_profit > entry else entry * 1.012
                if current_price >= be_trigger and not pos.is_breakeven_set:
                    be_stop = round(entry * 1.002, 2)  # Entry + 0.2% buffer
                    if pos.stop_loss is None or be_stop > pos.stop_loss:
                        pos.stop_loss = be_stop
                        pos.is_breakeven_set = True
                        logger.info(f"BREAKEVEN STOP ENGAGED for LONG {symbol}: Stop raised to ${be_stop:.2f} (Entry: ${entry:.2f})")

                # 2. Dynamic Trailing Stop: Trail 1.5% below highest price once gain >= 2.0%
                if pos.highest_price and (pos.highest_price - entry) / entry >= 0.02:
                    trail_stop = round(pos.highest_price * 0.985, 2)
                    if pos.stop_loss is None or trail_stop > pos.stop_loss:
                        pos.stop_loss = trail_stop
                        logger.info(f"TRAILING STOP ADVANCED for LONG {symbol}: Stop trailed to ${trail_stop:.2f} (Peak: ${pos.highest_price:.2f})")

            # 3. Check Stop-Loss / Trailing Exit
            if pos.stop_loss and current_price <= pos.stop_loss:
                exit_reason = "BREAKEVEN_STOP" if pos.is_breakeven_set and current_price >= entry else "TRAILING_STOP" if (pos.stop_loss and pos.stop_loss > entry) else "STOP_LOSS"
                logger.info(f"{exit_reason} TRIGGERED for LONG {symbol}: price ${current_price:.2f} <= SL ${pos.stop_loss:.2f}")
                return self.execute_signal(
                    symbol=symbol,
                    action="EXIT",
                    price=current_price,
                    quantity=pos.quantity,
                    strategy_name=pos.strategy,
                    bypass_risk=True,
                    exit_reason=exit_reason,
                )

            # 4. Check Take-Profit Exit
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

        # -------------------------------------------------------------
        # SHORT Position: Breakeven, Trailing Stop & Exit Arbitration
        # -------------------------------------------------------------
        elif pos.side.upper() == "SHORT":
            entry = pos.entry_price
            if entry > 0:
                # 1. Breakeven Advancement: Move stop to entry once +1.2% in profit or 50% to TP
                be_trigger = entry - (entry - pos.take_profit) * 0.5 if pos.take_profit and pos.take_profit < entry else entry * 0.988
                if current_price <= be_trigger and not pos.is_breakeven_set:
                    be_stop = round(entry * 0.998, 2)  # Entry - 0.2% buffer
                    if pos.stop_loss is None or be_stop < pos.stop_loss:
                        pos.stop_loss = be_stop
                        pos.is_breakeven_set = True
                        logger.info(f"BREAKEVEN STOP ENGAGED for SHORT {symbol}: Stop lowered to ${be_stop:.2f} (Entry: ${entry:.2f})")

                # 2. Dynamic Trailing Stop: Trail 1.5% above lowest price once gain >= 2.0%
                if pos.lowest_price and (entry - pos.lowest_price) / entry >= 0.02:
                    trail_stop = round(pos.lowest_price * 1.015, 2)
                    if pos.stop_loss is None or trail_stop < pos.stop_loss:
                        pos.stop_loss = trail_stop
                        logger.info(f"TRAILING STOP ADVANCED for SHORT {symbol}: Stop trailed to ${trail_stop:.2f} (Trough: ${pos.lowest_price:.2f})")

            # 3. Check Stop-Loss / Trailing Exit
            if pos.stop_loss and current_price >= pos.stop_loss:
                exit_reason = "BREAKEVEN_STOP" if pos.is_breakeven_set and current_price <= entry else "TRAILING_STOP" if (pos.stop_loss and pos.stop_loss < entry) else "STOP_LOSS"
                logger.info(f"{exit_reason} TRIGGERED for SHORT {symbol}: price ${current_price:.2f} >= SL ${pos.stop_loss:.2f}")
                return self.execute_signal(
                    symbol=symbol,
                    action="EXIT",
                    price=current_price,
                    quantity=pos.quantity,
                    strategy_name=pos.strategy,
                    bypass_risk=True,
                    exit_reason=exit_reason,
                )

            # 4. Check Take-Profit Exit
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
            self._save_trades_to_disk()
            self.circuit_breaker.record_trade(trade_record)

            # 6. Automatic Continuous Learning: Deep Analytical Post-Mortem on EVERY closed trade
            is_loss = trade_record.pnl < 0
            outcome = "LOSS" if is_loss else "WIN"
            root_cause, market_cond, rule, tags = TradeDiagnostician.diagnose_trade(trade_record)

            if is_loss:
                logger.warning(
                    f"DEEP LOSS POST-MORTEM GENERATED: -${abs(trade_record.pnl):.2f} on {symbol} ({trade_side}) | Root Cause: {root_cause[:75]}..."
                )
            else:
                logger.info(
                    f"WIN TRADE DEBRIEF GENERATED: +${abs(trade_record.pnl):.2f} on {symbol} ({trade_side}) | Rule: {rule[:75]}..."
                )

            self.post_mortem_repo.create_post_mortem(
                trade=trade_record,
                root_cause=root_cause,
                market_condition=market_cond,
                preventative_rule=rule,
                tags=tags,
                outcome=outcome,
            )
        else:
            # Opening new position (either LONG or SHORT)
            self._entry_records[symbol] = order