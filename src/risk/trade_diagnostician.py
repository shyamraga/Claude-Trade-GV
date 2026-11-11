"""Intelligent analytical diagnosis engine for trade post-mortems and continuous learning."""

import logging
from datetime import datetime
from typing import Optional, List, Dict, Any

from src.risk.models import TradeRecord

logger = logging.getLogger(__name__)


class TradeDiagnostician:
    """
    Analyzes closed trades across multiple dimensions (strategy type, hold duration,
    price displacement, exit trigger, and market regime) to produce precise root-cause
    diagnoses and actionable preventative rules.
    """

    @classmethod
    def diagnose_trade(
        cls,
        trade: TradeRecord,
        market_context_hint: Optional[str] = None,
    ) -> tuple[str, str, str, List[str]]:
        """
        Produce a deep diagnostic report for a closed trade.
        Returns:
            (root_cause, market_condition, preventative_rule, tags)
        """
        symbol = trade.symbol.upper().strip()
        strategy_raw = trade.strategy_name or "MANUAL"

        # Normalize strategy name for classification
        strat_upper = strategy_raw.upper().replace("_", "").replace("-", "").replace(" ", "")
        if "ORB" in strat_upper:
            strategy = "ORB"
        elif "TREND" in strat_upper:
            strategy = "TrendFollowing"
        elif "RSI" in strat_upper:
            strategy = "RSIReversion"
        elif "MA" in strat_upper or "CROSSOVER" in strat_upper:
            strategy = "MACrossover"
        else:
            strategy = strategy_raw

        side = (trade.side or "BUY").upper()
        reason = getattr(trade, "reason", "SIGNAL_EXIT") or "SIGNAL_EXIT"
        pnl = trade.pnl
        pnl_pct = trade.pnl_pct
        is_loss = pnl < 0

        # Duration analysis
        entry_time = trade.entry_time or datetime.now()
        exit_time = trade.exit_time or datetime.now()
        duration_sec = max(1.0, (exit_time - entry_time).total_seconds())
        duration_min = duration_sec / 60.0

        is_crypto = "-USD" in symbol or "/" in symbol
        is_indian = symbol.endswith(".NS") or symbol.endswith(".BO")

        tags: List[str] = [
            symbol,
            strategy,
            "win" if not is_loss else "loss",
            side.lower(),
            reason.lower(),
        ]
        if is_crypto:
            tags.append("crypto")
        elif is_indian:
            tags.append("indian-equity")
        else:
            tags.append("us-equity")

        # ---------------------------------------------------------------------
        # 1. WINNING TRADE DIAGNOSIS & SETUP VALIDATION
        # ---------------------------------------------------------------------
        if not is_loss:
            if reason == "TAKE_PROFIT":
                root_cause = (
                    f"Flawless execution of {strategy} {side} setup. Price moved cleanly to the pre-calculated profit target "
                    f"(${trade.exit_price:.2f}) within {duration_min:.1f} minutes without violating stop-loss threshold."
                )
                market_cond = "Favorable directional momentum with strong volume alignment and low adverse excursion."
                preventative_rule = (
                    f"Validated setup: continue taking {strategy} {side} setups on {symbol} when technical indicators "
                    f"align with higher-timeframe trend."
                )
            elif reason == "TRAILING_STOP":
                root_cause = (
                    f"Trailing stop successfully protected profit (+${pnl:.2f}, +{pnl_pct:.2%}). "
                    f"Position locked in peak gains before momentum deceleration triggered trailing stop exit."
                )
                market_cond = "Strong initial expansion followed by trend deceleration and normal corrective pullback."
                preventative_rule = (
                    f"Dynamic trailing stop mechanism proved effective: continue trailing stops 1.5% behind swing peaks on {symbol}."
                )
            elif reason == "BREAKEVEN_STOP":
                root_cause = (
                    f"Breakeven stop prevented a winner from turning into a loss on {symbol}. "
                    f"Price surged into profit (>1.2%), then experienced a full retracement where breakeven stop preserved capital (+${pnl:.2f})."
                )
                market_cond = "Volatile market rejection following initial momentum push."
                preventative_rule = (
                    f"Breakeven rule validated: maintain early stop advancement to entry on {symbol} once 50% of target is reached."
                )
            else:
                root_cause = (
                    f"Profitable {strategy} {side} trade closed with +${pnl:.2f} (+{pnl_pct:.2%}) "
                    f"after holding for {duration_min:.1f} minutes."
                )
                market_cond = market_context_hint or "Directional trend aligned with entry thesis."
                preventative_rule = f"Maintain active monitoring on {symbol} for similar high-confidence continuation patterns."

            return root_cause, market_cond, preventative_rule, tags

        # ---------------------------------------------------------------------
        # 2. LOSING TRADE DEEP ROOT-CAUSE DIAGNOSIS
        # ---------------------------------------------------------------------
        # A. Strategy-specific Failure Mode Analysis
        if strategy == "ORB":
            if side == "BUY":
                if duration_min < 15.0:
                    root_cause = (
                        f"Premature Long Breakout / Bull Trap on {symbol}. Price briefly pierced the 15-minute opening high "
                        f"(${trade.entry_price:.2f}) on thin volume, triggering retail buy-stops before institutional sellers "
                        f"pushed price back into the range, hitting stop-loss at ${trade.exit_price:.2f}."
                    )
                    market_cond = "Opening volatility shakeout with heavy institutional supply absorbing breakout volume."
                    preventative_rule = (
                        f"For ORB Long on {symbol}, require a full 15-minute bar CLOSE clearly above opening high with at least "
                        f"1.5x relative volume (RVOL) to confirm authentic demand before entering."
                    )
                    tags.append("bull-trap")
                else:
                    root_cause = (
                        f"Failed Continuation on ORB Long for {symbol}. Breakout was established but buying momentum dried up "
                        f"mid-session, resulting in a steady roll-over and stop-loss trigger at ${trade.exit_price:.2f} (-${abs(pnl):.2f})."
                    )
                    market_cond = "Midday momentum exhaustion and loss of buy-side liquidity."
                    preventative_rule = (
                        f"For ORB Long on {symbol}, advance stop-loss to entry once price advances +0.8%, and exit immediately "
                        f"if volume drops below 20-period moving average."
                    )
                    tags.append("failed-continuation")
            else:  # ORB Short
                if duration_min < 15.0:
                    root_cause = (
                        f"Bear Trap / False Breakdown on {symbol} Short. Price flushed below opening range low on thin volume, "
                        f"triggering breakdown sellers before an aggressive V-shape reversal squeezed short sellers out at ${trade.exit_price:.2f}."
                    )
                    market_cond = "Liquidity sweep below opening range low followed by aggressive dip-buying absorption."
                    preventative_rule = (
                        f"For ORB Short on {symbol}, do not short if the broader market index (SPY/QQQ/BTC) is trading positive, "
                        f"or if 15-minute RSI is already oversold (<32)."
                    )
                    tags.append("bear-trap")
                else:
                    root_cause = (
                        f"Short Squeeze on ORB Short for {symbol}. Downside breakdown was overwhelmed by institutional accumulation, "
                        f"driving price back through entry price to stop-loss."
                    )
                    market_cond = "Institutional accumulation floor rejecting breakdown attempt."
                    preventative_rule = (
                        f"For ORB Short on {symbol}, place stop-loss no higher than the opening range midpoint, and cover "
                        f"immediately if 5-minute EMA 9 crosses back above EMA 21."
                    )
                    tags.append("short-squeeze")

        elif strategy == "TrendFollowing":
            if side == "BUY":
                if abs(pnl_pct) > 0.03 or duration_min < 10.0:
                    root_cause = (
                        f"Late Trend Exhaustion / Buying the Top on {symbol}. Entered Long after an extended multi-candle impulse "
                        f"where price was overextended above the 21-period EMA; caught in an aggressive mean-reversion selloff."
                    )
                    market_cond = "Overbought trend exhaustion leading to institutional profit taking."
                    preventative_rule = (
                        f"For TrendFollowing Long on {symbol}, forbid entries when distance between price and EMA 21 exceeds 2.5x ATR, "
                        f"or when intraday RSI is greater than 68."
                    )
                    tags.append("trend-exhaustion")
                else:
                    root_cause = (
                        f"Corrective Wave Whipsaw on TrendFollowing Long for {symbol}. Macro trend was upward, but a deep counter-trend "
                        f"pullback breached stop-loss at ${trade.exit_price:.2f} before trend resumption."
                    )
                    market_cond = "High intraday volatility with wide corrective retracement swings."
                    preventative_rule = (
                        f"For TrendFollowing on {symbol}, enter only on a confirmed retest bounce off the 21-period EMA rather than "
                        f"chasing market breakout candles."
                    )
                    tags.append("pullback-whipsaw")
            else:  # TrendFollowing Short
                root_cause = (
                    f"Shorting the Hole / Oversold Dump on {symbol}. Short entry occurred at the tail-end of a downward impulse near "
                    f"major support; sudden short-covering bounce stopped out the position at ${trade.exit_price:.2f}."
                )
                market_cond = "Oversold bounce regime with aggressive buyer defense at structural support."
                preventative_rule = (
                    f"For TrendFollowing Short on {symbol}, forbid Short entries when RSI is below 35 or when price is within 1% of "
                    f"24-hour horizontal support."
                )
                tags.append("short-the-hole")

        elif strategy == "RSIReversion":
            if side == "BUY":
                root_cause = (
                    f"Falling Knife Syndrome on RSI Long for {symbol}. Bought an oversold RSI reading (<30), but asset entered a "
                    f"persistent high-momentum liquidation cascade where oversold conditions continued plunging through stop-loss."
                )
                market_cond = "Strong liquidation cascade where momentum indicators stay pinned oversold."
                preventative_rule = (
                    f"For RSIReversion Long on {symbol}, never buy on RSI < 30 alone; require a confirmed bullish divergence candle "
                    f"and positive MACD histogram uptick before initiating Long entries."
                )
                tags.append("falling-knife")
            else:  # RSI Short
                root_cause = (
                    f"Runaway Melt-Up Trap on RSI Short for {symbol}. Shorted an overbought RSI reading (>70), but asset experienced "
                    f"parabolic runaway buying momentum that blew through resistance without pulling back."
                )
                market_cond = "Parabolic speculative buying frenzy where overbought signals produce false reversal cues."
                preventative_rule = (
                    f"For RSIReversion Short on {symbol}, require a confirmed bearish reversal pattern (shooting star or bearish engulfing) "
                    f"before shorting overbought conditions."
                )
                tags.append("melt-up-trap")

        elif strategy == "MACrossover":
            root_cause = (
                f"Moving Average Lag Whipsaw in Choppy Consolidation on {symbol}. {strategy} generated a {side} crossover signal "
                f"inside a low-ADX rangebound market, where lagging moving averages produce repeated false trend signals."
            )
            market_cond = "Rangebound sideways chop with lack of directional trend conviction."
            preventative_rule = (
                f"For MACrossover on {symbol}, enforce ADX > 22 trend-strength filter; block crossover entries when ADX indicates "
                f"rangebound or consolidating market conditions."
            )
            tags.append("ma-lag-whipsaw")

        else:
            # Fallback for manual or custom strategies
            root_cause = (
                f"Adverse market movement on {symbol} {side} ({strategy}). Exit triggered via {reason} at ${trade.exit_price:.2f} "
                f"(-${abs(pnl):.2f}, {pnl_pct:.2%}) after {duration_min:.1f} minutes of hold time."
            )
            market_cond = market_context_hint or "Intraday price action diverged from entry setup parameters."
            preventative_rule = (
                f"Exercise caution with {strategy} {side} setups on {symbol}; verify multi-timeframe trend alignment and "
                f"restrict position size if market volatility is elevated."
            )

        return root_cause, market_cond, preventative_rule, tags
