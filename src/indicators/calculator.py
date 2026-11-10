import math
import numpy as np
from datetime import datetime
from typing import List, Optional, Tuple

from src.data.models import Bar
from src.indicators.models import (
    MACDResult,
    BollingerBandsResult,
    IndicatorSnapshot,
)


class IndicatorCalculator:
    """High-performance, deterministic technical indicator calculation engine."""

    @staticmethod
    def extract_closes(bars: List[Bar]) -> List[float]:
        return [b.close for b in bars]

    @staticmethod
    def extract_highs(bars: List[Bar]) -> List[float]:
        return [b.high for b in bars]

    @staticmethod
    def extract_lows(bars: List[Bar]) -> List[float]:
        return [b.low for b in bars]

    @staticmethod
    def extract_volumes(bars: List[Bar]) -> List[float]:
        return [b.volume for b in bars]

    @staticmethod
    def sma(data: List[float], period: int) -> List[Optional[float]]:
        """Calculate Simple Moving Average (SMA)."""
        if period <= 0:
            raise ValueError("Period must be positive.")
        n = len(data)
        result: List[Optional[float]] = [None] * n
        if n < period:
            return result

        current_sum = sum(data[:period])
        result[period - 1] = round(current_sum / period, 6)

        for i in range(period, n):
            current_sum += data[i] - data[i - period]
            result[i] = round(current_sum / period, 6)

        return result

    @staticmethod
    def ema(data: List[float], period: int) -> List[Optional[float]]:
        """Calculate Exponential Moving Average (EMA)."""
        if period <= 0:
            raise ValueError("Period must be positive.")
        n = len(data)
        result: List[Optional[float]] = [None] * n
        if n < period:
            return result

        multiplier = 2.0 / (period + 1.0)
        # Seed with initial SMA
        current_ema = sum(data[:period]) / period
        result[period - 1] = round(current_ema, 6)

        for i in range(period, n):
            current_ema = (data[i] - current_ema) * multiplier + current_ema
            result[i] = round(current_ema, 6)

        return result

    @staticmethod
    def rsi(data: List[float], period: int = 14) -> List[Optional[float]]:
        """Calculate Relative Strength Index (RSI) using Wilder's smoothing."""
        if period <= 0:
            raise ValueError("Period must be positive.")
        n = len(data)
        result: List[Optional[float]] = [None] * n
        if n <= period:
            return result

        # Calculate price changes
        gains: List[float] = []
        losses: List[float] = []
        for i in range(1, n):
            change = data[i] - data[i - 1]
            if change > 0:
                gains.append(change)
                losses.append(0.0)
            else:
                gains.append(0.0)
                losses.append(abs(change))

        # Initial average gain & loss over first 'period' deltas
        avg_gain = sum(gains[:period]) / period
        avg_loss = sum(losses[:period]) / period

        if avg_loss == 0.0:
            result[period] = 100.0 if avg_gain > 0 else 50.0
        else:
            rs = avg_gain / avg_loss
            result[period] = round(100.0 - (100.0 / (1.0 + rs)), 4)

        # Subsequent values using Wilder's smoothed average
        for i in range(period + 1, n):
            gain = gains[i - 1]
            loss = losses[i - 1]
            avg_gain = (avg_gain * (period - 1) + gain) / period
            avg_loss = (avg_loss * (period - 1) + loss) / period

            if avg_loss == 0.0:
                result[i] = 100.0 if avg_gain > 0 else 50.0
            else:
                rs = avg_gain / avg_loss
                result[i] = round(100.0 - (100.0 / (1.0 + rs)), 4)

        return result

    @classmethod
    def macd(
        cls,
        data: List[float],
        fast_period: int = 12,
        slow_period: int = 26,
        signal_period: int = 9,
    ) -> MACDResult:
        """Calculate MACD line, signal line, and MACD histogram."""
        if fast_period >= slow_period:
            raise ValueError("fast_period must be less than slow_period.")

        n = len(data)
        fast_ema = cls.ema(data, fast_period)
        slow_ema = cls.ema(data, slow_period)

        macd_line: List[Optional[float]] = [None] * n
        valid_indices: List[int] = []
        valid_macd_values: List[float] = []

        for i in range(n):
            if fast_ema[i] is not None and slow_ema[i] is not None:
                val = round(fast_ema[i] - slow_ema[i], 6)
                macd_line[i] = val
                valid_indices.append(i)
                valid_macd_values.append(val)

        signal_line: List[Optional[float]] = [None] * n
        histogram: List[Optional[float]] = [None] * n

        if len(valid_macd_values) >= signal_period:
            valid_signal = cls.ema(valid_macd_values, signal_period)
            for idx, orig_i in enumerate(valid_indices):
                sig_val = valid_signal[idx]
                signal_line[orig_i] = sig_val
                if sig_val is not None and macd_line[orig_i] is not None:
                    histogram[orig_i] = round(macd_line[orig_i] - sig_val, 6)

        return MACDResult(macd=macd_line, signal=signal_line, histogram=histogram)

    @classmethod
    def bollinger_bands(
        cls,
        data: List[float],
        period: int = 20,
        num_std: float = 2.0,
    ) -> BollingerBandsResult:
        """Calculate Bollinger Bands: Middle, Upper, Lower, Bandwidth, and %B."""
        n = len(data)
        middle = cls.sma(data, period)
        upper: List[Optional[float]] = [None] * n
        lower: List[Optional[float]] = [None] * n
        bandwidth: List[Optional[float]] = [None] * n
        percent_b: List[Optional[float]] = [None] * n

        if n < period:
            return BollingerBandsResult(upper, middle, lower, bandwidth, percent_b)

        arr = np.array(data, dtype=np.float64)
        for i in range(period - 1, n):
            window = arr[i - period + 1 : i + 1]
            std = float(np.std(window, ddof=0))
            mid = middle[i]
            if mid is not None:
                up = round(mid + num_std * std, 4)
                low = round(mid - num_std * std, 4)
                upper[i] = up
                lower[i] = low

                # Bandwidth = (Upper - Lower) / Middle * 100
                if mid > 0:
                    bandwidth[i] = round(((up - low) / mid) * 100.0, 4)
                else:
                    bandwidth[i] = 0.0

                # %B = (Price - Lower) / (Upper - Lower)
                band_range = up - low
                if band_range > 0:
                    percent_b[i] = round((data[i] - low) / band_range, 4)
                else:
                    percent_b[i] = 0.5

        return BollingerBandsResult(upper, middle, lower, bandwidth, percent_b)

    @classmethod
    def atr(cls, bars: List[Bar], period: int = 14) -> List[Optional[float]]:
        """Calculate Average True Range (ATR) using Wilder's smoothing."""
        if period <= 0:
            raise ValueError("Period must be positive.")
        n = len(bars)
        result: List[Optional[float]] = [None] * n
        if n < period:
            return result

        # Compute True Range (TR) for each bar
        tr: List[float] = [bars[0].high - bars[0].low]
        for i in range(1, n):
            h = bars[i].high
            l = bars[i].low
            prev_close = bars[i - 1].close
            true_range = max(h - l, abs(h - prev_close), abs(l - prev_close))
            tr.append(true_range)

        # Initial ATR is average of first 'period' TRs
        current_atr = sum(tr[:period]) / period
        result[period - 1] = round(current_atr, 4)

        # Wilder's smoothing for subsequent periods
        for i in range(period, n):
            current_atr = (current_atr * (period - 1) + tr[i]) / period
            result[i] = round(current_atr, 4)

        return result

    @classmethod
    def vwap(cls, bars: List[Bar]) -> List[Optional[float]]:
        """Calculate Volume Weighted Average Price (VWAP) with intraday day reset."""
        n = len(bars)
        result: List[Optional[float]] = [None] * n
        if n == 0:
            return result

        cum_tp_vol = 0.0
        cum_vol = 0.0
        current_date = None

        for i, bar in enumerate(bars):
            bar_date = bar.timestamp.date() if hasattr(bar.timestamp, "date") else None

            # Reset cumulative tallies on day transition
            if current_date is not None and bar_date != current_date:
                cum_tp_vol = 0.0
                cum_vol = 0.0
            current_date = bar_date

            typical_price = (bar.high + bar.low + bar.close) / 3.0
            volume = max(0.0, bar.volume)

            cum_tp_vol += typical_price * volume
            cum_vol += volume

            if cum_vol > 0:
                result[i] = round(cum_tp_vol / cum_vol, 4)
            else:
                result[i] = round(typical_price, 4)

        return result

    @classmethod
    def snapshot(cls, bars: List[Bar]) -> Optional[IndicatorSnapshot]:
        """Compute all indicators and return a single snapshot for the latest bar."""
        if not bars:
            return None

        closes = cls.extract_closes(bars)
        latest_bar = bars[-1]

        sma_20 = cls.sma(closes, 20)[-1]
        sma_50 = cls.sma(closes, 50)[-1] if len(closes) >= 50 else None

        ema_9 = cls.ema(closes, 9)[-1]
        ema_21 = cls.ema(closes, 21)[-1] if len(closes) >= 21 else None
        ema_50 = cls.ema(closes, 50)[-1] if len(closes) >= 50 else None

        rsi_14 = cls.rsi(closes, 14)[-1]
        macd_res = cls.macd(closes, 12, 26, 9)
        bb_res = cls.bollinger_bands(closes, 20, 2.0)
        atr_14 = cls.atr(bars, 14)[-1]
        vwap_val = cls.vwap(bars)[-1]

        return IndicatorSnapshot(
            symbol=latest_bar.symbol,
            timestamp=latest_bar.timestamp,
            close=latest_bar.close,
            sma_20=sma_20,
            sma_50=sma_50,
            ema_9=ema_9,
            ema_21=ema_21,
            ema_50=ema_50,
            rsi_14=rsi_14,
            macd=macd_res.latest_macd,
            macd_signal=macd_res.latest_signal,
            macd_histogram=macd_res.latest_histogram,
            bb_upper=bb_res.latest_upper,
            bb_middle=bb_res.latest_middle,
            bb_lower=bb_res.latest_lower,
            atr_14=atr_14,
            vwap=vwap_val,
        )
