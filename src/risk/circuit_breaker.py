"""Circuit breaker system for portfolio protection and drawdown control."""

import logging
from datetime import datetime, timedelta
from typing import Optional, List

from src.risk.models import RiskConfig, RiskCheckResult, TradeRecord

logger = logging.getLogger(__name__)


class CircuitBreaker:
    """
    Monitors trading activity and enforces risk circuit breakers:
    - Max daily drawdown limit
    - 3-consecutive-loss 4-hour cooldown pause
    """

    def __init__(self, config: Optional[RiskConfig] = None):
        """Initialize circuit breaker with configuration."""
        self.config = config or RiskConfig()
        self.daily_starting_equity: float = 100000.0  # Defaults to 100k
        self.current_equity: float = 100000.0
        self.completed_trades_today: List[TradeRecord] = []
        self.consecutive_losses: int = 0
        self.cooldown_until: Optional[datetime] = None
        self.cooldown_reason: str = ""
        self.manual_override: bool = False

    def reset_daily_metrics(self, starting_equity: float) -> None:
        """Reset daily tracking counters at market open."""
        self.daily_starting_equity = starting_equity
        self.current_equity = starting_equity
        self.completed_trades_today.clear()
        self.manual_override = False
        logger.info(f"Circuit breaker daily reset. Starting equity: ${starting_equity:,.2f}")

    def update_equity(self, current_equity: float) -> None:
        """Update current portfolio equity and check drawdown."""
        self.current_equity = current_equity

    def is_cooldown_active(self) -> bool:
        """Check if trading is currently paused due to cooldown."""
        if self.manual_override:
            return False

        if self.cooldown_until and datetime.now() < self.cooldown_until:
            return True

        # Cooldown expired
        if self.cooldown_until and datetime.now() >= self.cooldown_until:
            logger.info("Circuit breaker cooldown expired. Normal trading resumed.")
            self.cooldown_until = None
            self.cooldown_reason = ""
            self.consecutive_losses = 0

        return False

    def trigger_cooldown(self, hours: float, reason: str) -> None:
        """Trigger an emergency trading cooldown pause."""
        self.cooldown_until = datetime.now() + timedelta(hours=hours)
        self.cooldown_reason = reason
        logger.warning(
            f"CIRCUIT BREAKER TRIGGERED: {reason}. Trading paused for {hours} hours (until {self.cooldown_until.strftime('%H:%M:%S')})"
        )

    def record_trade(self, trade: TradeRecord) -> None:
        """Record a completed trade and update consecutive loss counter."""
        self.completed_trades_today.append(trade)
        self.current_equity += trade.pnl

        if trade.pnl < 0:
            self.consecutive_losses += 1
            logger.warning(
                f"Trade loss recorded: ${trade.pnl:.2f} on {trade.symbol}. Consecutive losses: {self.consecutive_losses}"
            )
            if self.consecutive_losses >= self.config.consecutive_loss_limit:
                self.trigger_cooldown(
                    hours=self.config.cooldown_duration_hours,
                    reason=f"{self.consecutive_losses} consecutive trade losses hit limit",
                )
        else:
            # Win resets consecutive losses
            self.consecutive_losses = 0
            logger.info(f"Trade win recorded: +${trade.pnl:.2f} on {trade.symbol}. Consecutive losses reset to 0.")

        # Check daily drawdown
        drawdown_pct = (self.daily_starting_equity - self.current_equity) / self.daily_starting_equity
        if drawdown_pct >= self.config.max_daily_drawdown_pct:
            self.trigger_cooldown(
                hours=24.0,  # Pause remainder of the day
                reason=f"Daily drawdown limit exceeded: {drawdown_pct:.1%} >= {self.config.max_daily_drawdown_pct:.1%}",
            )

    def validate_pre_trade(
        self,
        symbol: str,
        side: str,
        price: float,
        proposed_shares: int,
    ) -> RiskCheckResult:
        """Evaluate pre-trade safety before placing an order."""
        if self.is_cooldown_active():
            return RiskCheckResult(
                approved=False,
                reason=f"Circuit breaker active: {self.cooldown_reason} until {self.cooldown_until.strftime('%H:%M:%S')}",
                risk_level="BLOCKED",
            )

        position_val = price * proposed_shares
        max_allowed_val = self.current_equity * self.config.max_position_pct

        stop_loss = round(price * (1.0 - self.config.stop_loss_pct), 2) if side == "BUY" else round(price * (1.0 + self.config.stop_loss_pct), 2)
        take_profit = round(price * (1.0 + self.config.take_profit_pct), 2) if side == "BUY" else round(price * (1.0 - self.config.take_profit_pct), 2)

        if position_val > max_allowed_val:
            adjusted_shares = int(max_allowed_val / price)
            return RiskCheckResult(
                approved=True,
                reason=f"Position size scaled down from {proposed_shares} to {adjusted_shares} (max 10% allocation)",
                risk_level="ELEVATED",
                max_allowed_shares=adjusted_shares,
                calculated_stop_loss=stop_loss,
                calculated_take_profit=take_profit,
            )

        return RiskCheckResult(
            approved=True,
            reason="Risk checks passed",
            risk_level="NORMAL",
            max_allowed_shares=proposed_shares,
            calculated_stop_loss=stop_loss,
            calculated_take_profit=take_profit,
        )

    def set_manual_override(self, override: bool = True) -> None:
        """Allow user to manually resume trading during a cooldown."""
        self.manual_override = override
        if override:
            logger.warning("USER MANUAL OVERRIDE ACTIVATED: Circuit breaker cooldown bypassed.")
        else:
            logger.info("Manual override deactivated.")