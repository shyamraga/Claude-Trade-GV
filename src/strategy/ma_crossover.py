from typing import List, Optional

from src.data.models import Bar
from src.indicators.calculator import IndicatorCalculator
from src.strategy.base import Strategy, Signal, SignalAction


class MACrossoverStrategy(Strategy):
    """Moving Average Crossover Strategy.

    Generates BUY signals when fast EMA crosses above slow EMA (golden cross),
    and EXIT/SELL signals when fast EMA crosses below slow EMA (death cross).
    Uses ATR for dynamic stop-loss calculation.
    """

    def __init__(
        self,
        fast_period: int = 9,
        slow_period: int = 21,
        atr_period: int = 14,
        atr_multiplier: float = 2.0,
    ):
        super().__init__(
            name="MA_Crossover",
            parameters={
                "fast_period": fast_period,
                "slow_period": slow_period,
                "atr_period": atr_period,
                "atr_multiplier": atr_multiplier,
            },
        )
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.atr_period = atr_period
        self.atr_multiplier = atr_multiplier

    def generate_signals(self, bars: List[Bar]) -> List[Signal]:
        if len(bars) < self.slow_period:
            return []

        closes = IndicatorCalculator.extract_closes(bars)
        highs = IndicatorCalculator.extract_highs(bars)
        lows = IndicatorCalculator.extract_lows(bars)

        fast_ema = IndicatorCalculator.ema(closes, self.fast_period)
        slow_ema = IndicatorCalculator.ema(closes, self.slow_period)
        atr_values = IndicatorCalculator.atr(bars, self.atr_period)

        signals: List[Signal] = []
        prev_fast = None
        prev_slow = None

        for i in range(1, len(bars)):
            curr_fast = fast_ema[i]
            curr_slow = slow_ema[i]
            bar = bars[i]
            prev_bar = bars[i - 1]

            if curr_fast is None or curr_slow is None:
                prev_fast = curr_fast
                prev_slow = curr_slow
                continue

            if prev_fast is not None and prev_slow is not None:
                # Golden Cross: Fast crosses above Slow -> BUY
                if prev_fast <= prev_slow and curr_fast > curr_slow:
                    atr = atr_values[i]
                    stop_loss = bar.close - (atr * self.atr_multiplier) if atr else bar.close * 0.98

                    # Calculate confidence based on EMA separation
                    ema_separation = (curr_fast - curr_slow) / curr_slow
                    confidence = min(0.7 + ema_separation * 10, 0.95)

                    signals.append(
                        Signal(
                            symbol=bar.symbol,
                            action=SignalAction.BUY,
                            timestamp=bar.timestamp,
                            price=bar.close,
                            confidence=round(confidence, 3),
                            strategy_name=self.name,
                            indicators={
                                "fast_ema": curr_fast,
                                "slow_ema": curr_slow,
                                "atr": atr,
                            },
                            reason=f"Golden cross: EMA{self.fast_period} ({curr_fast:.2f}) crossed above EMA{self.slow_period} ({curr_slow:.2f})",
                            stop_loss=round(stop_loss, 2),
                        )
                    )

                # Death Cross: Fast crosses below Slow -> SELL/EXIT
                elif prev_fast >= prev_slow and curr_fast < curr_slow:
                    signals.append(
                        Signal(
                            symbol=bar.symbol,
                            action=SignalAction.EXIT,
                            timestamp=bar.timestamp,
                            price=bar.close,
                            confidence=0.85,
                            strategy_name=self.name,
                            indicators={
                                "fast_ema": curr_fast,
                                "slow_ema": curr_slow,
                            },
                            reason=f"Death cross: EMA{self.fast_period} ({curr_fast:.2f}) crossed below EMA{self.slow_period} ({curr_slow:.2f})",
                        )
                    )

            prev_fast = curr_fast
            prev_slow = curr_slow

        return signals