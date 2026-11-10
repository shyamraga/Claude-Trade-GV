from typing import List

from src.data.models import Bar
from src.indicators.calculator import IndicatorCalculator
from src.strategy.base import Strategy, Signal, SignalAction


class RSIMeanReversionStrategy(Strategy):
    """RSI Mean Reversion Strategy.

    Generates BUY signals when RSI exits oversold territory (< 30) with upward momentum.
    Generates EXIT/SELL signals when RSI enters overbought territory (> 70).
    Uses ATR for volatility-adjusted stop-loss.
    """

    def __init__(
        self,
        rsi_period: int = 14,
        oversold_threshold: float = 30.0,
        overbought_threshold: float = 70.0,
        atr_period: int = 14,
        atr_multiplier: float = 2.0,
    ):
        super().__init__(
            name="RSI_MeanReversion",
            parameters={
                "rsi_period": rsi_period,
                "oversold_threshold": oversold_threshold,
                "overbought_threshold": overbought_threshold,
                "atr_period": atr_period,
                "atr_multiplier": atr_multiplier,
            },
        )
        self.rsi_period = rsi_period
        self.oversold_threshold = oversold_threshold
        self.overbought_threshold = overbought_threshold
        self.atr_period = atr_period
        self.atr_multiplier = atr_multiplier

    def generate_signals(self, bars: List[Bar]) -> List[Signal]:
        if len(bars) < self.rsi_period + 1:
            return []

        closes = IndicatorCalculator.extract_closes(bars)
        rsi_values = IndicatorCalculator.rsi(closes, self.rsi_period)
        atr_values = IndicatorCalculator.atr(bars, self.atr_period)

        signals: List[Signal] = []
        prev_rsi = None

        for i in range(1, len(bars)):
            curr_rsi = rsi_values[i]
            bar = bars[i]

            if curr_rsi is None:
                prev_rsi = curr_rsi
                continue

            # BUY: RSI crosses above oversold threshold from below
            if prev_rsi is not None and prev_rsi < self.oversold_threshold and curr_rsi > self.oversold_threshold:
                atr = atr_values[i]
                stop_loss = bar.close - (atr * self.atr_multiplier) if atr else bar.close * 0.97

                # Confidence based on how deep the oversold was and how fast it recovered
                oversold_depth = (self.oversold_threshold - min(prev_rsi, curr_rsi)) / self.oversold_threshold
                confidence = min(0.65 + oversold_depth * 0.35, 0.95)

                signals.append(
                    Signal(
                        symbol=bar.symbol,
                        action=SignalAction.BUY,
                        timestamp=bar.timestamp,
                        price=bar.close,
                        confidence=round(confidence, 3),
                        strategy_name=self.name,
                        indicators={
                            "rsi": curr_rsi,
                            "atr": atr,
                        },
                        reason=f"RSI mean reversion: RSI ({curr_rsi:.1f}) exited oversold zone (< {self.oversold_threshold})",
                        stop_loss=round(stop_loss, 2),
                    )
                )

            # SELL (Short Entry): RSI crosses below overbought threshold from above (bearish reversion)
            elif prev_rsi is not None and prev_rsi > self.overbought_threshold and curr_rsi < self.overbought_threshold:
                atr = atr_values[i]
                stop_loss = bar.close + (atr * self.atr_multiplier) if atr else bar.close * 1.03

                # Confidence based on how deep the overbought peak was
                overbought_depth = (max(prev_rsi, curr_rsi) - self.overbought_threshold) / (100.0 - self.overbought_threshold) if self.overbought_threshold < 100.0 else 0.1
                confidence = min(0.65 + overbought_depth * 0.35, 0.95)

                signals.append(
                    Signal(
                        symbol=bar.symbol,
                        action=SignalAction.SELL,
                        timestamp=bar.timestamp,
                        price=bar.close,
                        confidence=round(confidence, 3),
                        strategy_name=self.name,
                        indicators={
                            "rsi": curr_rsi,
                            "atr": atr,
                        },
                        reason=f"RSI bearish reversion: RSI ({curr_rsi:.1f}) crossed back below overbought zone (> {self.overbought_threshold})",
                        stop_loss=round(stop_loss, 2),
                    )
                )

            # EXIT: RSI crosses above overbought threshold (potential top)
            elif prev_rsi is not None and curr_rsi > self.overbought_threshold and prev_rsi < self.overbought_threshold:
                signals.append(
                    Signal(
                        symbol=bar.symbol,
                        action=SignalAction.EXIT,
                        timestamp=bar.timestamp,
                        price=bar.close,
                        confidence=0.80,
                        strategy_name=self.name,
                        indicators={"rsi": curr_rsi},
                        reason=f"RSI overbought: RSI ({curr_rsi:.1f}) entered overbought zone (> {self.overbought_threshold})",
                    )
                )

            prev_rsi = curr_rsi

        return signals