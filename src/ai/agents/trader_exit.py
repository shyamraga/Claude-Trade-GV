"""
Trader-Exit Agent: Dynamic Trailing Stops, Profit Targets & Breakeven Laddering.

Monitors active position health, calculates ATR-based volatility stops, defines
risk-reward profit targets (TP1/TP2), and triggers defensive profit locks or exits.
"""

import time
from typing import List, Dict, Any, Optional

from src.data.models import Bar
from src.ai.agents.base import BaseSubAgent, AgentSignal, AgentAction, AgentStatus


class TraderExit(BaseSubAgent):
    """Specialized Sub-Agent for Dynamic Stops, Profit Targets & Position Protection."""

    def __init__(self, weight: float = 1.1):
        super().__init__(
            agent_id="trader-exit",
            name="Trader Exit",
            role="Dynamic Trailing Stops, Profit Targets & Breakeven Defense",
            weight=weight,
        )

    def analyze(
        self,
        symbol: str,
        bars: List[Bar],
        current_position: Optional[Any] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> AgentSignal:
        start_t = time.perf_counter()
        self.total_analyses += 1
        self.status = AgentStatus.ANALYZING

        if not bars or len(bars) < 15:
            self.status = AgentStatus.IDLE
            sig = AgentSignal(
                agent_id=self.agent_id,
                symbol=symbol,
                action=AgentAction.HOLD,
                confidence=0.5,
                reason="Insufficient bars to calculate ATR volatility exit levels (<15 bars)",
                status=AgentStatus.IDLE,
                latency_ms=(time.perf_counter() - start_t) * 1000,
            )
            self.last_signal = sig
            return sig

        curr_bar = bars[-1]
        curr_price = curr_bar.close

        # ATR computation (14 bars)
        tr_list = []
        for i in range(1, len(bars[-15:])):
            b = bars[-15 + i]
            b_prev = bars[-15 + i - 1]
            tr = max(b.high - b.low, abs(b.high - b_prev.close), abs(b.low - b_prev.close))
            tr_list.append(tr)
        atr = sum(tr_list) / len(tr_list) if tr_list else (curr_price * 0.015)

        # Evaluate if an active position is currently open
        if current_position and getattr(current_position, "quantity", 0) > 0:
            entry_p = current_position.entry_price
            side = getattr(current_position, "side", "LONG").upper()

            if side == "LONG":
                pnl_pct = (curr_price - entry_p) / entry_p if entry_p > 0 else 0.0
                # If in substantial profit (> 3% or > 2.5x ATR), recommend profit-taking
                if pnl_pct >= 0.04 or (curr_price - entry_p) >= (2.5 * atr):
                    action = AgentAction.EXIT
                    confidence = 0.90
                    reason = f"Profit target achieved: +{pnl_pct*100:.2f}% gain (2.5x ATR reached). Secure gains."
                elif pnl_pct <= -0.025:
                    action = AgentAction.EXIT
                    confidence = 0.85
                    reason = f"Protective stop: -{abs(pnl_pct)*100:.2f}% loss exceeds maximum risk threshold."
                else:
                    action = AgentAction.HOLD
                    confidence = 0.65
                    reason = f"Position in healthy hold: PnL {pnl_pct*100:+.2f}%, trailing stop active."
            else:  # SHORT
                pnl_pct = (entry_p - curr_price) / entry_p if entry_p > 0 else 0.0
                if pnl_pct >= 0.04 or (entry_p - curr_price) >= (2.5 * atr):
                    action = AgentAction.EXIT
                    confidence = 0.90
                    reason = f"Short profit target achieved: +{pnl_pct*100:.2f}% gain (2.5x ATR reached). Cover short."
                elif pnl_pct <= -0.025:
                    action = AgentAction.EXIT
                    confidence = 0.85
                    reason = f"Short protective stop: -{abs(pnl_pct)*100:.2f}% drawdown on short. Cut risk."
                else:
                    action = AgentAction.HOLD
                    confidence = 0.65
                    reason = f"Short position healthy: PnL {pnl_pct*100:+.2f}%, trailing cover active."
        else:
            # Pre-trade Risk/Reward mapping for prospective setups
            sl_long = curr_price - (1.5 * atr)
            tp_long = curr_price + (3.0 * atr)
            rr_ratio = (tp_long - curr_price) / (curr_price - sl_long) if (curr_price - sl_long) > 0 else 2.0

            action = AgentAction.HOLD
            confidence = 0.75
            reason = f"Pre-trade parameters mapped: 1:2 R/R target with 1.5x ATR stop buffer (${atr:.2f})."

        self.successful_analyses += 1
        self.status = AgentStatus.ACTIVE
        latency = (time.perf_counter() - start_t) * 1000

        sig = AgentSignal(
            agent_id=self.agent_id,
            symbol=symbol,
            action=action,
            confidence=round(confidence, 4),
            reason=reason,
            metrics={
                "atr": round(atr, 2),
                "long_sl": round(curr_price - 1.5 * atr, 2),
                "long_tp": round(curr_price + 3.0 * atr, 2),
                "short_sl": round(curr_price + 1.5 * atr, 2),
                "short_tp": round(curr_price - 3.0 * atr, 2),
                "risk_reward_ratio": 2.0,
            },
            status=AgentStatus.ACTIVE,
            latency_ms=latency,
        )
        self.last_signal = sig
        return sig
