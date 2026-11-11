"""
Trader-Entry Agent: Precision Execution Timing & Slippage Minimization.

Calculates intraday VWAP proximity, bar range stretch, and micro-structure pullback
sweet-spots to identify the ideal entry price and avoid chasing extended moves.
"""

import time
from typing import List, Dict, Any, Optional

from src.data.models import Bar
from src.ai.agents.base import BaseSubAgent, AgentSignal, AgentAction, AgentStatus


class TraderEntry(BaseSubAgent):
    """Specialized Sub-Agent for Precision Execution Timing & Micro-entry Optimization."""

    def __init__(self, weight: float = 1.0):
        super().__init__(
            agent_id="trader-entry",
            name="Trader Entry",
            role="Precision Timing, VWAP Alignment & Slippage Control",
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
                reason="Insufficient bars to compute VWAP and entry micro-structure (<15 bars)",
                status=AgentStatus.IDLE,
                latency_ms=(time.perf_counter() - start_t) * 1000,
            )
            self.last_signal = sig
            return sig

        curr_bar = bars[-1]
        curr_price = curr_bar.close

        # Intraday VWAP estimate over available bars
        cum_vol = sum(b.volume for b in bars)
        cum_vp = sum(((b.high + b.low + b.close) / 3.0) * b.volume for b in bars)
        vwap = (cum_vp / cum_vol) if cum_vol > 0 else curr_price

        # Distance from VWAP
        vwap_dist_pct = (curr_price - vwap) / vwap if vwap > 0 else 0.0

        # ATR estimate (14 period)
        tr_list = []
        for i in range(1, len(bars[-15:])):
            b = bars[-15 + i]
            b_prev = bars[-15 + i - 1]
            tr = max(b.high - b.low, abs(b.high - b_prev.close), abs(b.low - b_prev.close))
            tr_list.append(tr)
        atr = sum(tr_list) / len(tr_list) if tr_list else (curr_price * 0.01)

        # Bar extension check (is the current bar overstretched?)
        bar_range = curr_bar.high - curr_bar.low
        is_extended = bar_range > (1.8 * atr)

        # Micro-structure entry recommendation
        if vwap_dist_pct > 0.001 and vwap_dist_pct < 0.015 and not is_extended:
            # Healthy bounce off VWAP for Long entry
            action = AgentAction.BUY
            confidence = 0.88
            entry_type = "PATIENT_LIMIT"
            optimal_price = max(vwap, curr_price - 0.2 * atr)
            reason = f"Optimal long entry: Price hovering +{vwap_dist_pct*100:.2f}% above VWAP with controlled range."
        elif vwap_dist_pct < -0.001 and vwap_dist_pct > -0.015 and not is_extended:
            # Healthy rejection off VWAP for Short entry
            action = AgentAction.SELL
            confidence = 0.88
            entry_type = "PATIENT_LIMIT"
            optimal_price = min(vwap, curr_price + 0.2 * atr)
            reason = f"Optimal short entry: Price rejecting -{abs(vwap_dist_pct)*100:.2f}% below VWAP without exhaustion."
        elif is_extended:
            # Price moved too far in a single bar — high risk of pullback/slippage
            action = AgentAction.HOLD
            confidence = 0.40
            entry_type = "PULLBACK_ENTRY"
            optimal_price = vwap
            reason = f"Entry paused: Price overextended (bar range {bar_range:.2f} > 1.8x ATR). Wait for retracement."
        elif vwap_dist_pct >= 0.015:
            # Chasing long when far above VWAP
            action = AgentAction.HOLD
            confidence = 0.45
            entry_type = "PULLBACK_ENTRY"
            optimal_price = curr_price - 0.5 * atr
            reason = f"Price stretched +{vwap_dist_pct*100:.2f}% above VWAP. Chasing entry not recommended."
        elif vwap_dist_pct <= -0.015:
            # Chasing short when far below VWAP
            action = AgentAction.HOLD
            confidence = 0.45
            entry_type = "PULLBACK_ENTRY"
            optimal_price = curr_price + 0.5 * atr
            reason = f"Price stretched -{abs(vwap_dist_pct)*100:.2f}% below VWAP. Overdue for mean-reversion bounce."
        else:
            action = AgentAction.HOLD
            confidence = 0.50
            entry_type = "AGGRESSIVE_MARKET"
            optimal_price = curr_price
            reason = "Price right at VWAP equilibrium; awaiting breakout direction."

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
                "vwap": round(vwap, 2),
                "vwap_dist_pct": round(vwap_dist_pct * 100, 2),
                "atr": round(atr, 2),
                "entry_type": entry_type,
                "optimal_entry_price": round(optimal_price, 2),
                "is_extended": is_extended,
            },
            status=AgentStatus.ACTIVE,
            latency_ms=latency,
        )
        self.last_signal = sig
        return sig
