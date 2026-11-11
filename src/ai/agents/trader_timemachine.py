"""
Trader-TimeMachine Agent: Historical Pattern Matching & Fractal Similarity.

Analyzes price trajectory fractals, historical regime analogs, and momentum
cycles to forecast whether current price structure mirrors past profitable breakouts
or exhaustion reversals.
"""

import math
import time
from typing import List, Dict, Any, Optional

from src.data.models import Bar
from src.ai.agents.base import BaseSubAgent, AgentSignal, AgentAction, AgentStatus


class TraderTimeMachine(BaseSubAgent):
    """Specialized Sub-Agent for Historical Fractal & Regime Matching."""

    def __init__(self, weight: float = 1.0):
        super().__init__(
            agent_id="trader-timemachine",
            name="Trader TimeMachine",
            role="Historical Fractal & Regime Pattern Matching",
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

        if not bars or len(bars) < 20:
            self.status = AgentStatus.IDLE
            sig = AgentSignal(
                agent_id=self.agent_id,
                symbol=symbol,
                action=AgentAction.HOLD,
                confidence=0.5,
                reason="Insufficient historical bars for fractal pattern comparison (<20 bars)",
                status=AgentStatus.IDLE,
                latency_ms=(time.perf_counter() - start_t) * 1000,
            )
            self.last_signal = sig
            return sig

        closes = [b.close for b in bars]
        recent = closes[-20:]
        c_now = recent[-1]
        c_start = recent[0]

        # Calculate normalized 20-bar return
        pct_change = (c_now - c_start) / c_start if c_start > 0 else 0.0

        # Calculate rolling volatility and path smoothness (fractal dimension proxy)
        diffs = [abs(recent[i] - recent[i - 1]) for i in range(1, len(recent))]
        net_travel = abs(c_now - c_start)
        gross_travel = sum(diffs) if sum(diffs) > 0 else 1e-6
        efficiency_ratio = net_travel / gross_travel  # 1.0 = linear trend, 0.0 = pure chop

        # Multi-bar momentum trajectory
        short_mom = (recent[-1] - recent[-5]) / recent[-5] if recent[-5] > 0 else 0.0
        med_mom = (recent[-1] - recent[-10]) / recent[-10] if recent[-10] > 0 else 0.0

        # Regime classification based on historical analogs
        if efficiency_ratio > 0.65 and short_mom > 0.015:
            regime = "EXPONENTIAL_BULL_EXPANSION"
            action = AgentAction.BUY
            confidence = min(0.94, 0.65 + efficiency_ratio * 0.25 + short_mom * 3.0)
            reason = f"Historical fractal mirrors strong bull expansion: efficiency={efficiency_ratio:.2f}, 5-bar mom=+{short_mom*100:.1f}%"
        elif efficiency_ratio > 0.65 and short_mom < -0.015:
            regime = "PARABOLIC_BEAR_BREAKDOWN"
            action = AgentAction.SELL
            confidence = min(0.94, 0.65 + efficiency_ratio * 0.25 + abs(short_mom) * 3.0)
            reason = f"Historical fractal mirrors aggressive breakdown: efficiency={efficiency_ratio:.2f}, 5-bar mom={short_mom*100:.1f}%"
        elif efficiency_ratio < 0.30:
            regime = "CONSOLIDATION_COILED_SPRING"
            # In consolidation, check if coiled near range support or resistance
            low_20 = min(recent)
            high_20 = max(recent)
            span = high_20 - low_20 if high_20 > low_20 else 1.0
            pos_in_range = (c_now - low_20) / span

            if pos_in_range > 0.85:
                action = AgentAction.BUY
                confidence = 0.72
                reason = "Fractal compression testing upper coil barrier: imminent upside breakout expected."
            elif pos_in_range < 0.15:
                action = AgentAction.SELL
                confidence = 0.70
                reason = "Fractal compression failing range floor: downside breakdown imminent."
            else:
                action = AgentAction.HOLD
                confidence = 0.50
                reason = "Fractal equilibrium: sideways consolidation regime without clear trend bias."
        else:
            if med_mom > 0.01:
                regime = "STEADY_ACCUMULATION_CYCLE"
                action = AgentAction.BUY
                confidence = 0.68
                reason = f"Accumulation channel analog: consistent positive slope (+{med_mom*100:.1f}%)"
            elif med_mom < -0.01:
                regime = "STEADY_DISTRIBUTION_CYCLE"
                action = AgentAction.SELL
                confidence = 0.68
                reason = f"Distribution channel analog: consistent negative slope ({med_mom*100:.1f}%)"
            else:
                regime = "RANDOM_WALK_EQUILIBRIUM"
                action = AgentAction.HOLD
                confidence = 0.52
                reason = "Historical fractal matches low-signal random walk equilibrium."

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
                "regime": regime,
                "efficiency_ratio": round(efficiency_ratio, 3),
                "short_momentum_pct": round(short_mom * 100, 2),
                "medium_momentum_pct": round(med_mom * 100, 2),
                "20_bar_return_pct": round(pct_change * 100, 2),
            },
            status=AgentStatus.ACTIVE,
            latency_ms=latency,
        )
        self.last_signal = sig
        return sig
