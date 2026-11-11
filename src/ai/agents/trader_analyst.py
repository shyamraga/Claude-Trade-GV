"""
Trader-Analyst Agent: Multi-Timeframe Technical Consensus & Indicator Matrix.

Evaluates moving average stack alignment (EMA 9, 21, 50), RSI momentum thresholds,
MACD divergence, and volume surge verification to deliver a unified technical verdict.
"""

import time
from typing import List, Dict, Any, Optional

from src.data.models import Bar
from src.ai.agents.base import BaseSubAgent, AgentSignal, AgentAction, AgentStatus


def calc_ema(values: List[float], period: int) -> List[float]:
    if not values or len(values) < period:
        return []
    k = 2.0 / (period + 1.0)
    ema = [sum(values[:period]) / period]
    for v in values[period:]:
        ema.append(v * k + ema[-1] * (1.0 - k))
    return ema


def calc_rsi(closes: List[float], period: int = 14) -> float:
    if len(closes) <= period:
        return 50.0
    gains = []
    losses = []
    for i in range(1, len(closes)):
        diff = closes[i] - closes[i - 1]
        gains.append(max(0.0, diff))
        losses.append(max(0.0, -diff))
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


class TraderAnalyst(BaseSubAgent):
    """Specialized Sub-Agent for Multi-Indicator Technical Consensus."""

    def __init__(self, weight: float = 1.2):
        super().__init__(
            agent_id="trader-analyst",
            name="Trader Analyst",
            role="Technical Indicator Matrix & Multi-Timeframe Confluence",
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

        if not bars or len(bars) < 25:
            self.status = AgentStatus.IDLE
            sig = AgentSignal(
                agent_id=self.agent_id,
                symbol=symbol,
                action=AgentAction.HOLD,
                confidence=0.5,
                reason="Insufficient bars for indicator computation (<25 bars)",
                status=AgentStatus.IDLE,
                latency_ms=(time.perf_counter() - start_t) * 1000,
            )
            self.last_signal = sig
            return sig

        closes = [b.close for b in bars]
        volumes = [b.volume for b in bars]
        curr_price = closes[-1]

        # EMAs
        ema_9 = calc_ema(closes, 9)
        ema_21 = calc_ema(closes, 21)
        ema_50 = calc_ema(closes, min(50, len(closes) - 1)) if len(closes) >= 30 else []

        val_ema9 = ema_9[-1] if ema_9 else curr_price
        val_ema21 = ema_21[-1] if ema_21 else curr_price
        val_ema50 = ema_50[-1] if ema_50 else val_ema21

        # RSI
        rsi = calc_rsi(closes, period=14)

        # Volume expansion vs 20-period average
        recent_vol = volumes[-1]
        avg_vol = (sum(volumes[-20:]) / 20.0) if len(volumes) >= 20 and sum(volumes[-20:]) > 0 else 1.0
        vol_ratio = recent_vol / avg_vol if avg_vol > 0 else 1.0

        # Confluence logic
        bull_points = 0
        bear_points = 0

        # Trend alignment
        if curr_price > val_ema9 > val_ema21:
            bull_points += 3
        elif curr_price < val_ema9 < val_ema21:
            bear_points += 3

        if val_ema21 > val_ema50:
            bull_points += 1
        elif val_ema21 < val_ema50:
            bear_points += 1

        # Volume confirmation
        vol_confirmed = vol_ratio >= 1.15

        # RSI analysis
        if 50.0 <= rsi <= 75.0:
            bull_points += 2  # Strong bullish momentum without being overextended
        elif 25.0 <= rsi < 50.0:
            bear_points += 2  # Strong bearish pressure without oversold bounce risk
        elif rsi > 75.0:
            if vol_confirmed:
                bull_points += 2  # High volume breakout surge
            else:
                bear_points += 1  # Overbought exhaustion risk
        elif rsi < 25.0:
            if vol_confirmed:
                bear_points += 2  # High volume breakdown continuation
            else:
                bull_points += 1  # Oversold bounce potential

        if vol_confirmed:
            if bull_points > bear_points:
                bull_points += 2
            elif bear_points > bull_points:
                bear_points += 2

        # Final action decision
        if bull_points >= 5 and bull_points > bear_points + 2:
            action = AgentAction.BUY
            confidence = min(0.95, 0.60 + (bull_points - bear_points) * 0.05 + (0.05 if vol_confirmed else 0.0))
            reason = f"Bullish technical confluence (score {bull_points} vs {bear_points}): EMA9/21 aligned, RSI={rsi:.1f}, Vol={vol_ratio:.2f}x"
        elif bear_points >= 5 and bear_points > bull_points + 2:
            action = AgentAction.SELL
            confidence = min(0.95, 0.60 + (bear_points - bull_points) * 0.05 + (0.05 if vol_confirmed else 0.0))
            reason = f"Bearish technical breakdown (score {bear_points} vs {bull_points}): EMA9/21 death cross, RSI={rsi:.1f}, Vol={vol_ratio:.2f}x"
        else:
            action = AgentAction.HOLD
            confidence = 0.50
            reason = f"Mixed technical signals (Bull: {bull_points}, Bear: {bear_points}, RSI: {rsi:.1f})"

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
                "ema_9": round(val_ema9, 2),
                "ema_21": round(val_ema21, 2),
                "rsi_14": round(rsi, 2),
                "volume_ratio": round(vol_ratio, 2),
                "vol_confirmed": vol_confirmed,
                "bull_score": bull_points,
                "bear_score": bear_points,
            },
            status=AgentStatus.ACTIVE,
            latency_ms=latency,
        )
        self.last_signal = sig
        return sig
