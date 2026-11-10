from typing import List, Optional
from statistics import mean

from src.data.models import Bar
from src.indicators.calculator import IndicatorCalculator
from src.strategy.base import Strategy, Signal, SignalAction


class OpeningRangeBreakoutStrategy(Strategy):
    """Opening Range Breakout (ORB) Strategy.

    Identifies the high and low of the first N bars (opening range).
    Generates BUY signals when price breaks above the opening range high with above-average volume.
    Generates SELL/EXIT signals when price breaks below the opening range low.
    """

    def __init__(
        self,
        opening_bars: int = 3,
        volume_multiplier: float = 1.5,
        atr_multiplier: float = 2.0,
    ):
        super().__init__(
            name="ORB",
            parameters={
                "opening_bars": opening_bars,
                "volume_multiplier": volume_multiplier,
                "atr_multiplier": atr_multiplier,
            },
        )
        self.opening_bars = opening_bars
        self.volume_multiplier = volume_multiplier
        self.atr_multiplier = atr_multiplier

    def generate_signals(self, bars: List[Bar]) -> List[Signal]:
        if len(bars) < self.opening_bars + 2:
            return []

        # Calculate average volume from the opening range for baseline
        opening_range_volumes = [b.volume for b in bars[: self.opening_bars]]
        avg_opening_volume = mean(opening_range_volumes) if opening_range_volumes else 0

        # Determine opening range high/low
        opening_high = max(b.high for b in bars[: self.opening_bars])
        opening_low = min(b.low for b in bars[: self.opening_bars])

        atr_values = IndicatorCalculator.atr(bars, period=14)

        signals: List[Signal] = []
        position_open = False

        for i in range(self.opening_bars, len(bars)):
            bar = bars[i]
            prev_bar = bars[i - 1]

            # Calculate if we're in the opening range (first 15-30 mins typically)
            # Once we break out, we stay "broken out" until we exit

            # BUY: Break above opening range high with volume confirmation
            if not position_open and bar.close > opening_high and bar.volume >= avg_opening_volume * self.volume_multiplier:
                atr = atr_values[i] if i < len(atr_values) else None
                stop_loss = opening_low  # Stop at opposite side of range

                # Confidence based on volume strength
                volume_ratio = bar.volume / avg_opening_volume if avg_opening_volume > 0 else 1.0
                confidence = min(0.6 + (volume_ratio - 1.0) * 0.2, 0.90)

                signals.append(
                    Signal(
                        symbol=bar.symbol,
                        action=SignalAction.BUY,
                        timestamp=bar.timestamp,
                        price=bar.close,
                        confidence=round(confidence, 3),
                        strategy_name=self.name,
                        indicators={
                            "opening_high": opening_high,
                            "opening_low": opening_low,
                            "breakout_volume": bar.volume,
                            "avg_opening_volume": avg_opening_volume,
                            "atr": atr,
                        },
                        reason=f"ORB breakout: Price ({bar.close:.2f}) broke above opening range high ({opening_high:.2f}) with {volume_ratio:.1f}x volume",
                        stop_loss=round(stop_loss, 2),
                    )
                )
                position_open = True

            # EXIT/SELL: Break below opening range low (reversal)
            elif position_open and bar.close < opening_low:
                signals.append(
                    Signal(
                        symbol=bar.symbol,
                        action=SignalAction.EXIT,
                        timestamp=bar.timestamp,
                        price=bar.close,
                        confidence=0.85,
                        strategy_name=self.name,
                        indicators={
                            "opening_high": opening_high,
                            "opening_low": opening_low,
                        },
                        reason=f"ORB reversal: Price ({bar.close:.2f}) broke below opening range low ({opening_low:.2f})",
                    )
                )
                position_open = False

        return signals