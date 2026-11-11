from typing import List

from src.data.models import Bar
from src.indicators.calculator import IndicatorCalculator
from src.strategy.base import Strategy, Signal, SignalAction


class TrendFollowingStrategy(Strategy):
    """Multi-Factor Trend Following Strategy.

    Generates BUY signals when multiple factors confirm an uptrend:
    - EMA 20 > EMA 50 (primary trend direction)
    - MACD line > Signal line (momentum positive)
    - RSI between 50 and 70 (healthy trend, not overextended)

    Generates EXIT/SELL when trend weakens or reverses.
    """

    def __init__(
        self,
        fast_ema: int = 20,
        slow_ema: int = 50,
        rsi_period: int = 14,
        rsi_lower: float = 50.0,
        rsi_upper: float = 70.0,
        atr_period: int = 14,
        atr_multiplier: float = 1.5,
        take_profit_multiplier: float = 3.0,
    ):
        super().__init__(
            name="TrendFollowing",
            parameters={
                "fast_ema": fast_ema,
                "slow_ema": slow_ema,
                "rsi_period": rsi_period,
                "rsi_lower": rsi_lower,
                "rsi_upper": rsi_upper,
                "atr_period": atr_period,
                "atr_multiplier": atr_multiplier,
                "take_profit_multiplier": take_profit_multiplier,
            },
        )
        self.fast_ema_period = fast_ema
        self.slow_ema_period = slow_ema
        self.rsi_period = rsi_period
        self.rsi_lower = rsi_lower
        self.rsi_upper = rsi_upper
        self.atr_period = atr_period
        self.atr_multiplier = atr_multiplier
        self.take_profit_multiplier = take_profit_multiplier

    def generate_signals(self, bars: List[Bar]) -> List[Signal]:
        if len(bars) < self.slow_ema_period + 1:
            return []

        closes = IndicatorCalculator.extract_closes(bars)

        ema_fast = IndicatorCalculator.ema(closes, self.fast_ema_period)
        ema_slow = IndicatorCalculator.ema(closes, self.slow_ema_period)
        rsi_values = IndicatorCalculator.rsi(closes, self.rsi_period)
        macd_result = IndicatorCalculator.macd(closes, 12, 26, 9)
        atr_values = IndicatorCalculator.atr(bars, self.atr_period)

        signals: List[Signal] = []
        position_open: Optional[str] = None  # None, "LONG", or "SHORT"

        for i in range(self.slow_ema_period, len(bars)):
            bar = bars[i]
            prev_bar = bars[i - 1] if i > 0 else None

            ema_f = ema_fast[i]
            ema_s = ema_slow[i]
            rsi = rsi_values[i]
            macd_line = macd_result.macd[i]
            macd_signal = macd_result.signal[i]
            atr = atr_values[i] if i < len(atr_values) else None

            if ema_f is None or ema_s is None or rsi is None:
                continue

            # Check all trend factors for Long
            trend_aligned = ema_f > ema_s  # EMA 20 > EMA 50
            momentum_positive = macd_line is not None and macd_signal is not None and macd_line > macd_signal
            rsi_healthy = self.rsi_lower <= rsi <= self.rsi_upper  # RSI in sweet spot

            # Check all trend factors for Short
            downtrend_aligned = ema_f < ema_s  # EMA 20 < EMA 50
            momentum_negative = macd_line is not None and macd_signal is not None and macd_line < macd_signal
            rsi_downtrend_healthy = (100.0 - self.rsi_upper) <= rsi <= (100.0 - self.rsi_lower)  # RSI 30-50

            prev_ema_f = ema_fast[i - 1] if i > 0 else None
            prev_ema_s = ema_slow[i - 1] if i > 0 else None

            # BUY: All three factors align for uptrend
            if position_open is None and trend_aligned and momentum_positive and rsi_healthy:
                was_trending = prev_ema_f is not None and prev_ema_s is not None and prev_ema_f > prev_ema_s

                if not was_trending:  # Fresh signal, not continuation
                    stop_loss = bar.close - (atr * self.atr_multiplier) if atr else bar.close * 0.97
                    take_profit = bar.close + (atr * self.take_profit_multiplier) if atr else bar.close * 1.05

                    # Confidence based on factor strength
                    ema_separation = (ema_f - ema_s) / ema_s
                    rsi_strength = (rsi - self.rsi_lower) / (self.rsi_upper - self.rsi_lower)
                    confidence = self._calculate_confidence(0.5, ema_separation * 5 + 0.3, rsi_strength * 0.2)
                    confidence = min(confidence, 0.95)

                    signals.append(
                        Signal(
                            symbol=bar.symbol,
                            action=SignalAction.BUY,
                            timestamp=bar.timestamp,
                            price=bar.close,
                            confidence=round(confidence, 3),
                            strategy_name=self.name,
                            indicators={
                                "ema_fast": ema_f,
                                "ema_slow": ema_s,
                                "macd": macd_line,
                                "macd_signal": macd_signal,
                                "rsi": rsi,
                                "atr": atr,
                            },
                            reason=f"Trend following: EMA{self.fast_ema_period} ({ema_f:.2f}) > EMA{self.slow_ema_period} ({ema_s:.2f}), MACD positive, RSI {rsi:.1f} in healthy range",
                            stop_loss=round(stop_loss, 2),
                            take_profit=round(take_profit, 2),
                        )
                    )
                    position_open = "LONG"

            # SELL (Short Entry): All three factors align for downtrend
            elif position_open is None and downtrend_aligned and momentum_negative and rsi_downtrend_healthy:
                was_downtrending = prev_ema_f is not None and prev_ema_s is not None and prev_ema_f < prev_ema_s

                if not was_downtrending:  # Fresh signal, not continuation
                    stop_loss = bar.close + (atr * self.atr_multiplier) if atr else bar.close * 1.03
                    take_profit = bar.close - (atr * self.take_profit_multiplier) if atr else bar.close * 0.95

                    # Confidence based on factor strength
                    ema_separation = (ema_s - ema_f) / ema_s
                    rsi_strength = ((100.0 - self.rsi_lower) - rsi) / (self.rsi_upper - self.rsi_lower)
                    confidence = self._calculate_confidence(0.5, ema_separation * 5 + 0.3, rsi_strength * 0.2)
                    confidence = min(confidence, 0.95)

                    signals.append(
                        Signal(
                            symbol=bar.symbol,
                            action=SignalAction.SELL,
                            timestamp=bar.timestamp,
                            price=bar.close,
                            confidence=round(confidence, 3),
                            strategy_name=self.name,
                            indicators={
                                "ema_fast": ema_f,
                                "ema_slow": ema_s,
                                "macd": macd_line,
                                "macd_signal": macd_signal,
                                "rsi": rsi,
                                "atr": atr,
                            },
                            reason=f"Bearish trend following: EMA{self.fast_ema_period} ({ema_f:.2f}) < EMA{self.slow_ema_period} ({ema_s:.2f}), MACD negative, RSI {rsi:.1f} in healthy downtrend range",
                            stop_loss=round(stop_loss, 2),
                            take_profit=round(take_profit, 2),
                        )
                    )
                    position_open = "SHORT"

            # EXIT LONG: Trend breaks or RSI becomes overbought
            elif position_open == "LONG":
                # Exit if EMA alignment breaks
                if ema_f < ema_s:
                    signals.append(
                        Signal(
                            symbol=bar.symbol,
                            action=SignalAction.EXIT,
                            timestamp=bar.timestamp,
                            price=bar.close,
                            confidence=0.85,
                            strategy_name=self.name,
                            indicators={"ema_fast": ema_f, "ema_slow": ema_s},
                            reason=f"Trend reversal: EMA{self.fast_ema_period} ({ema_f:.2f}) crossed below EMA{self.slow_ema_period} ({ema_s:.2f})",
                        )
                    )
                    position_open = None
                # Exit if RSI goes overbought
                elif rsi > self.rsi_upper:
                    signals.append(
                        Signal(
                            symbol=bar.symbol,
                            action=SignalAction.EXIT,
                            timestamp=bar.timestamp,
                            price=bar.close,
                            confidence=0.80,
                            strategy_name=self.name,
                            indicators={"rsi": rsi},
                            reason=f"Overbought exit: RSI ({rsi:.1f}) exceeded upper threshold ({self.rsi_upper})",
                        )
                    )
                    position_open = None

            # EXIT SHORT: Trend breaks or RSI becomes oversold
            elif position_open == "SHORT":
                if ema_f > ema_s:
                    signals.append(
                        Signal(
                            symbol=bar.symbol,
                            action=SignalAction.EXIT,
                            timestamp=bar.timestamp,
                            price=bar.close,
                            confidence=0.85,
                            strategy_name=self.name,
                            indicators={"ema_fast": ema_f, "ema_slow": ema_s},
                            reason=f"Trend reversal: EMA{self.fast_ema_period} ({ema_f:.2f}) crossed above EMA{self.slow_ema_period} ({ema_s:.2f})",
                        )
                    )
                    position_open = None
                elif rsi < (100.0 - self.rsi_upper):
                    signals.append(
                        Signal(
                            symbol=bar.symbol,
                            action=SignalAction.EXIT,
                            timestamp=bar.timestamp,
                            price=bar.close,
                            confidence=0.80,
                            strategy_name=self.name,
                            indicators={"rsi": rsi},
                            reason=f"Oversold cover exit: RSI ({rsi:.1f}) reached lower threshold ({100.0 - self.rsi_upper:.1f})",
                        )
                    )
                    position_open = None

        return signals