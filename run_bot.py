"""
Autonomous Trading Bot — Claude Trading Platform

Scans a universal multi-asset market universe continuously, evaluates all strategies,
modulates with AI sentiment, ranks setups by confidence, and executes the best trades
while feeding live updates to the OLED dashboard server.
"""

import argparse
import logging
import sys
import threading
import time
from datetime import datetime
from typing import List, Dict, Any, Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("TradingBot")

# Core services
from src.data.feed_manager import FeedManager
from src.data.models import TimeFrame
from src.storage.db import Database
from src.storage.repository import MarketDataRepository

from src.strategy.engine import StrategyEngine
from src.strategy.ma_crossover import MACrossoverStrategy
from src.strategy.rsi_reversion import RSIMeanReversionStrategy
from src.strategy.orb import OpeningRangeBreakoutStrategy
from src.strategy.trend_following import TrendFollowingStrategy
from src.strategy.base import SignalAction, Signal

from src.ai.integration import AIMarketIntelligence
from src.ai.agent_manager import SubAgentManager
from src.ai.agents.base import AgentAction

from src.risk.circuit_breaker import CircuitBreaker
from src.risk.post_mortem import PostMortemRepository
from src.risk.market_hours import MarketHoursManager, MarketType
from src.execution.engine import ExecutionEngine, ExecutionMode
from src.execution.virtual_broker import VirtualBroker
from src.execution.alpaca_broker import AlpacaBroker

from src.api.server import DashboardAPIHandler, run_server

# Constants & Multi-Agent Hierarchy Settings
CONFIDENCE_THRESHOLD = 0.45        # Lowered to 0.45 for more responsive, aggressive setups
CRYPTO_CONFIDENCE_THRESHOLD = 0.75 # Lowered to 0.75 to enable high-conviction crypto fills
MAX_CONCURRENT_POSITIONS = 10      # Maximum simultaneous open live positions in portfolio
MAX_EXECUTES_PER_CYCLE = 10        # Top best setups to execute per scan cycle

# Precious Metals Pairs (Gold & Silver spot futures) - CME Globex 23h/day
METALS_SYMBOLS = [
    "XAU/USD", "XAG/USD"
]

# 24/7 Global Crypto Pairs (Comprehensive liquid crypto universe)
CRYPTO_SYMBOLS = [
    "BTC-USD", "ETH-USD", "SOL-USD", "BNB-USD", "XRP-USD",
    "DOGE-USD", "ADA-USD", "AVAX-USD", "LINK-USD", "SUI-USD",
    "NEAR-USD", "APT-USD", "DOT-USD", "LTC-USD", "PEPE-USD",
    "SHIB-USD", "UNI-USD", "ICP-USD", "FET-USD", "RENDER-USD",
    "TAO-USD", "ARB-USD", "OP-USD", "TIA-USD", "INJ-USD",
    "MATIC-USD", "STX-USD", "FTM-USD", "KAS-USD", "BCH-USD",
    "XLM-USD", "AAVE-USD", "FIL-USD", "HBAR-USD", "ATOM-USD"
]

# Top Indian Bluechip Equities (NIFTY 50 Universe) - Traded 09:15 - 15:30 IST
INDIAN_SYMBOLS = [
    "RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", "ICICIBANK.NS",
    "BHARTIARTL.NS", "SBIN.NS", "ITC.NS", "LT.NS", "TATAMOTORS.NS",
    "BAJFINANCE.NS", "MARUTI.NS", "HINDUNILVR.NS", "AXISBANK.NS", "KOTAKBANK.NS",
    "SUNPHARMA.NS", "TITAN.NS", "TATASTEEL.NS", "WIPRO.NS", "NTPC.NS",
    "POWERGRID.NS", "M&M.NS", "ASIANPAINT.NS", "ULTRACEMCO.NS", "COALINDIA.NS",
    "BAJAJFINSV.NS", "ONGC.NS", "ADANIENT.NS", "ADANIPORTS.NS", "NESTLEIND.NS",
    "JSWSTEEL.NS", "HCLTECH.NS", "GRASIM.NS", "TECHM.NS", "CIPLA.NS",
    "DRREDDY.NS", "BPCL.NS", "BRITANNIA.NS", "EICHERMOT.NS", "TATACONSUM.NS",
    "DIVISLAB.NS", "APOLLOHOSP.NS", "HEROMOTOCO.NS", "SBILIFE.NS", "HDFCLIFE.NS",
    "INDUSINDBK.NS", "SHREECEM.NS", "UPL.NS", "HINDALCO.NS", "LTIM.NS"
]


def calculate_trade_quantity(symbol: str, price: float, confidence: float, is_crypto: bool) -> int:
    """
    Level 4 Sizing: Calculate adaptive, aggressive position size based on asset type, price, and confidence.
    Allocates ~$4,500 - $6,500 notional for US equities, ₹100,000 for Indian equities, and proportional crypto/metals.
    """
    if price <= 0:
        return 10

    # Precious Metals (Gold ~$4000/oz, Silver ~$50/oz)
    if "XAU" in symbol or symbol == "GC=F":
        return max(1, min(3, int(5000.0 / price)))  # 1-2 oz Gold (~$4,000-$8,000)
    elif "XAG" in symbol or symbol == "SI=F":
        return max(25, min(200, int(5000.0 / price)))  # ~100 oz Silver (~$5,000)

    if is_crypto:
        if price > 1000.0:     # BTC, ETH
            return 1
        elif price > 100.0:    # SOL, AVAX
            return 5
        else:                  # DOGE, low priced crypto
            return max(10, min(500, int(3000.0 / price)))

    # Indian Equities (Prices in INR, e.g., ₹1,000 - ₹3,500)
    if symbol.endswith(".NS") or symbol.endswith(".BO"):
        target_inr = 100000.0 * (0.85 + 0.3 * confidence)
        shares = int(target_inr / price)
        return max(5, min(250, shares))

    # US Equities (Prices in USD, e.g., $20 - $500): target ~$5,000 notional
    target_usd = 5000.0 * (0.85 + 0.3 * confidence)
    shares = int(target_usd / price)
    return max(5, min(200, shares))



def get_universe(broker: Optional[AlpacaBroker] = None) -> List[str]:
    """
    Retrieve unified global multi-market universe:
    - Precious Metals (Gold XAU/USD, Silver XAG/USD)
    - 24/7 Comprehensive Crypto pairs (BTC, ETH, SOL, BNB, XRP, AVAX, etc.)
    - NIFTY 50 Bluechip Indian Equities (Reliance, TCS, Infosys, HDFC, etc.)
    - Broad Tradable US Equities & Growth Leaders
    """
    default_us_universe = [
        "SPY", "QQQ", "IWM", "DIA", "AAPL", "MSFT", "NVDA", "TSLA", "AMZN",
        "GOOGL", "META", "NFLX", "AMD", "JPM", "COIN", "MSTR", "INTC", "DIS",
        "BA", "JNJ", "XOM", "V", "WMT", "PYPL", "SQ", "SHOP", "UBER", "ABNB",
        "PLTR", "RIVN", "SNOW", "SMCI", "ARM", "AVGO", "QCOM", "MU", "PANW",
        "CRWD", "CRM", "LLY", "NVO", "COST", "MARA", "RIOT", "CLSK", "SOFI",
        "HOOD", "AFRM", "DKNG", "BABA", "NIO", "BIDU", "PDD", "TSM", "ASML"
    ]
    us_equities = default_us_universe
    try:
        if broker is None:
            broker = AlpacaBroker()
        assets = broker._request("/v2/assets?status=active&asset_class=us_equity")
        if assets:
            tradable = [a["symbol"] for a in assets if a.get("tradable") and "." not in a["symbol"]]
            if tradable:
                logger.info("Loaded %d tradable US equities from Alpaca API.", len(tradable))
                us_equities = tradable[:250]
    except Exception as e:
        logger.warning("Could not fetch dynamic Alpaca universe (%s). Using default broad US universe.", e)

    # Combine Precious Metals + 24/7 Crypto + Indian Equities + US Equities
    return METALS_SYMBOLS + CRYPTO_SYMBOLS + INDIAN_SYMBOLS + us_equities


def build_services(initial_cash: float = 100_000.0):
    """Instantiate and wire all platform services including the SubAgentManager."""
    db                = Database()
    market_repo       = MarketDataRepository(db=db)
    post_mortem_repo  = PostMortemRepository()
    circuit_breaker   = CircuitBreaker()
    virtual_broker    = VirtualBroker(initial_cash=initial_cash)
    alpaca_broker     = AlpacaBroker()

    engine = ExecutionEngine(
        mode=ExecutionMode.VIRTUAL,
        virtual_broker=virtual_broker,
        live_broker=alpaca_broker,
        circuit_breaker=circuit_breaker,
        post_mortem_repo=post_mortem_repo,
    )

    strategy_engine = StrategyEngine(repo=market_repo)
    strategy_engine.register_strategy(MACrossoverStrategy())
    strategy_engine.register_strategy(RSIMeanReversionStrategy())
    strategy_engine.register_strategy(OpeningRangeBreakoutStrategy())
    strategy_engine.register_strategy(TrendFollowingStrategy())

    feed = FeedManager()
    ai   = AIMarketIntelligence()
    sub_agent_manager = SubAgentManager()

    return engine, strategy_engine, feed, ai, market_repo, alpaca_broker, sub_agent_manager


def trading_cycle(
    symbols: List[str],
    engine: ExecutionEngine,
    strategy_engine: StrategyEngine,
    feed: FeedManager,
    ai: AIMarketIntelligence,
    sub_agent_manager: Optional[SubAgentManager] = None,
    interval: int = 45,
):
    """
    Execute autonomous trading cycle orchestrated through the Multi-Agent Swarm Hierarchy:
      Level 1: Universal Market Scanner Agent (continuous multi-asset parallel data ingestion)
      Level 2: Quantitative Strategy Ensemble Agent (fresh-bar signal gating & multi-strategy consensus)
      Level 3: Claude AI Sentiment & Intelligence Agent (macro & order flow confidence modulation)
      Level 3.5: Specialized Sub-Agent Swarm (timemachine, analyst, entry, exit, news, pelosi)
      Level 4: Risk Guardian & Memory Learning Agent (circuit breaker & adaptive sizing)
      Level 5: Execution Router & Trailing Order Agent (order dispatch & trailing profit locks)
    """
    cycle_num = getattr(engine, "_cycle_count", 0) + 1
    setattr(engine, "_cycle_count", cycle_num)

    time_str = datetime.now().strftime("%H:%M:%S")
    logger.info("=== [SWARM HIERARCHY] Trading Cycle #%d Started === %s", cycle_num, time_str)
    DashboardAPIHandler.log_event(f"=== [SWARM HIERARCHY] Trading Cycle #{cycle_num} Started === {time_str}", level="CYCLE")

    # -------------------------------------------------------------------------
    # LEVEL 1: Market Hours & Time-Zone Session Filter
    # -------------------------------------------------------------------------
    market_summary = MarketHoursManager.get_open_markets_summary()
    us_state = "OPEN" if market_summary["us_market"]["open"] else "CLOSED"
    in_state = "OPEN" if market_summary["indian_market"]["open"] else "CLOSED"
    session_log = (
        f"[L1:SESSIONS] Active Trading Sessions: "
        f"US Market: {us_state} ({market_summary['us_market']['status']}) | "
        f"Indian Market: {in_state} ({market_summary['indian_market']['status']}) | "
        f"Crypto Market: 24/7 CONTINUOUS"
    )
    logger.info(session_log)
    DashboardAPIHandler.log_event(session_log, level="CYCLE")

    # Filter symbols: Pick Indian companies during Indian hours, US during US hours, Crypto 24/7
    active_symbols = MarketHoursManager.filter_open_symbols(symbols)
    filter_log = f"[L1:FILTER] Filtered {len(symbols)} universe symbols down to {len(active_symbols)} symbols in OPEN market sessions."
    logger.info(filter_log)
    DashboardAPIHandler.log_event(filter_log, level="CYCLE")

    # Level 1 Parallel Batch Data Ingestion (optimized worker concurrency to prevent rate-limit contention)
    bars_batch = feed.get_bars_batch(active_symbols, timeframe=TimeFrame.M15, limit=100, max_workers=8)
    batch_log = f"[L1:BATCH] Parallel data ingestion complete: {len(bars_batch)}/{len(active_symbols)} symbols ready for analysis."
    logger.info(batch_log)
    DashboardAPIHandler.log_event(batch_log, level="CYCLE")

    if sub_agent_manager:
        sub_agent_manager.start_scan_batch(total_symbols=len(bars_batch), cycle_number=cycle_num)

    candidate_setups: List[Dict[str, Any]] = []

    # -------------------------------------------------------------------------
    # LEVEL 1 & 2 & 3: Market Scan, Strategy Ensemble, & Multi-Agent Swarm
    # -------------------------------------------------------------------------
    for idx, (symbol, bars) in enumerate(bars_batch.items(), start=1):
        try:
            if len(bars) < 25:
                continue

            bars_sorted = sorted(bars, key=lambda b: b.timestamp)
            latest_price = bars_sorted[-1].close
            is_crypto = symbol in CRYPTO_SYMBOLS

            # Update broker mark-to-market
            engine.virtual_broker.set_market_price(symbol, latest_price)

            # Auto-check Stop-Loss, Breakeven & Trailing stops on open positions
            auto_exit_order = engine.check_position_stops(symbol, latest_price)
            if auto_exit_order:
                exit_log = f"  [L5:EXEC AUTO-EXIT] {auto_exit_order.exit_reason or 'STOP/TARGET'} hit for {symbol}: closed {auto_exit_order.quantity} @ ${auto_exit_order.average_fill_price:.2f}"
                logger.info(exit_log)
                DashboardAPIHandler.log_event(exit_log, level="FILLED", symbol=symbol, action=auto_exit_order.exit_reason or "EXIT")
                continue

            open_pos = engine.virtual_broker.get_position(symbol)

            # Level 2: Quantitative Strategy Ensemble Agent with Fresh Signal Gating
            cutoff_timestamp = bars_sorted[-2].timestamp if len(bars_sorted) >= 2 else bars_sorted[-1].timestamp
            signal_map = strategy_engine.run_all(bars_sorted)

            fresh_entries: List[Signal] = []
            fresh_exits: List[Signal] = []

            for strat_name, sigs in signal_map.items():
                if not sigs:
                    continue
                latest_sig = sigs[-1]
                if latest_sig.action in (SignalAction.BUY, SignalAction.SELL):
                    if latest_sig.timestamp >= cutoff_timestamp:
                        fresh_entries.append(latest_sig)
                elif latest_sig.action == SignalAction.EXIT:
                    if open_pos and open_pos.quantity > 0:
                        fresh_exits.append(latest_sig)

            # Evaluate best technical signal
            best_sig: Optional[Signal] = None
            agreeing_buys = [s for s in fresh_entries if s.action == SignalAction.BUY]
            agreeing_sells = [s for s in fresh_entries if s.action == SignalAction.SELL]

            if len(agreeing_buys) >= 2:
                base = max(agreeing_buys, key=lambda s: s.confidence)
                consensus_conf = min(0.95, base.confidence + 0.12 * (len(agreeing_buys) - 1))
                names = "+".join(s.strategy_name for s in agreeing_buys)
                best_sig = Signal(
                    symbol=symbol,
                    action=SignalAction.BUY,
                    timestamp=base.timestamp,
                    price=latest_price,
                    confidence=round(consensus_conf, 3),
                    strategy_name=f"CONSENSUS({names})",
                    reason=f"Multi-Strategy Consensus: {len(agreeing_buys)} strategies agree on BUY",
                    stop_loss=base.stop_loss,
                    take_profit=base.take_profit,
                )
            elif len(agreeing_sells) >= 2:
                base = max(agreeing_sells, key=lambda s: s.confidence)
                consensus_conf = min(0.95, base.confidence + 0.12 * (len(agreeing_sells) - 1))
                names = "+".join(s.strategy_name for s in agreeing_sells)
                best_sig = Signal(
                    symbol=symbol,
                    action=SignalAction.SELL,
                    timestamp=base.timestamp,
                    price=latest_price,
                    confidence=round(consensus_conf, 3),
                    strategy_name=f"CONSENSUS({names})",
                    reason=f"Multi-Strategy Consensus: {len(agreeing_sells)} strategies agree on SHORT",
                    stop_loss=base.stop_loss,
                    take_profit=base.take_profit,
                )
            elif fresh_entries:
                best_sig = max(fresh_entries, key=lambda s: s.confidence)
            elif fresh_exits:
                best_sig = max(fresh_exits, key=lambda s: s.confidence)

            # Level 3: Claude AI Sentiment Enrichment
            sentiment_label = "neutral"
            final_confidence = best_sig.confidence if best_sig else 0.50
            try:
                action_str = best_sig.action.value if best_sig else "BUY"
                modulated = ai.enrich_signal(
                    symbol=symbol,
                    action=action_str,
                    confidence=final_confidence,
                    bars=bars_sorted,
                )
                if best_sig:
                    final_confidence = modulated.get("modulated_confidence", best_sig.confidence)
                sentiment_label = modulated.get("sentiment", "neutral")
                if is_crypto and best_sig and best_sig.action in (SignalAction.BUY, SignalAction.SELL):
                    if (best_sig.action == SignalAction.BUY and sentiment_label == "bullish") or \
                       (best_sig.action == SignalAction.SELL and sentiment_label == "bearish"):
                        final_confidence = min(0.96, final_confidence + 0.15)
            except Exception as e:
                logger.debug("AI modulation error for %s: %s", symbol, e)

            # Level 3.5: Multi-Agent Swarm Simultaneous Evaluation (6 Specialized Agents)
            if sub_agent_manager:
                swarm_report = sub_agent_manager.evaluate_symbol(
                    symbol=symbol,
                    bars=bars_sorted,
                    current_position=open_pos,
                    context={"sentiment": sentiment_label},
                )
                sub_agent_manager.update_scan_progress(
                    symbol=symbol,
                    evaluated_count=idx,
                    current_report=swarm_report,
                )
                agreeing_count = sum(1 for s in swarm_report.agent_signals.values() if s.action == swarm_report.action)
                swarm_log = (
                    f"  [SWARM-6]  {symbol} Swarm Verdict: {swarm_report.action.value} "
                    f"(conf={int(swarm_report.confidence*100)}%, strength={int(swarm_report.consensus_strength*100)}% "
                    f"[{agreeing_count}/6 agents agree]) // {swarm_report.executive_summary}"
                )
                logger.info(swarm_log)
                DashboardAPIHandler.log_event(swarm_log, level="AI", symbol=symbol)

                # Cross-Verification between Strategies and Swarm
                if best_sig and best_sig.action.value == swarm_report.action.value:
                    # Strategy + Swarm Confluence Boost
                    final_confidence = min(0.96, max(final_confidence, swarm_report.confidence) + 0.10)
                elif not best_sig and swarm_report.action.value in ("BUY", "SELL") and swarm_report.confidence >= 0.72:
                    # Swarm Consensus initiates high-conviction setup
                    atr_approx = latest_price * 0.015
                    best_sig = Signal(
                        symbol=symbol,
                        action=SignalAction(swarm_report.action.value),
                        timestamp=bars_sorted[-1].timestamp,
                        price=latest_price,
                        confidence=swarm_report.confidence,
                        strategy_name="SWARM_CONSENSUS(6_AGENTS)",
                        reason=swarm_report.executive_summary,
                        stop_loss=latest_price - (1.5 * atr_approx) if swarm_report.action.value == "BUY" else latest_price + (1.5 * atr_approx),
                        take_profit=latest_price + (3.0 * atr_approx) if swarm_report.action.value == "BUY" else latest_price - (3.0 * atr_approx),
                    )
                    final_confidence = swarm_report.confidence
                elif swarm_report.action == AgentAction.EXIT and open_pos and open_pos.quantity > 0:
                    best_sig = Signal(
                        symbol=symbol,
                        action=SignalAction.EXIT,
                        timestamp=bars_sorted[-1].timestamp,
                        price=latest_price,
                        confidence=swarm_report.confidence,
                        strategy_name="SWARM_DEFENSIVE_EXIT",
                        reason=swarm_report.executive_summary,
                    )
                    final_confidence = swarm_report.confidence

            if not best_sig:
                continue

            # Signal logging with hierarchy tagging
            sig_log = f"  [L2:STRAT] {symbol} {best_sig.action.value} @ ${latest_price:.2f} (strat={best_sig.strategy_name}, conf={int(best_sig.confidence*100)}%, SL=${best_sig.stop_loss or 0:.2f}, TP=${best_sig.take_profit or 0:.2f})"
            logger.info(sig_log)
            DashboardAPIHandler.log_event(sig_log, level="SIGNAL", symbol=symbol, action=best_sig.action.value)

            post_ai_log = f"  [L3:AI]    {symbol} post-AI confidence={int(final_confidence*100)}% (sentiment={sentiment_label})"
            logger.info(post_ai_log)
            DashboardAPIHandler.log_event(post_ai_log, level="AI", symbol=symbol)

            # Gating against asset thresholds
            required_conf = CRYPTO_CONFIDENCE_THRESHOLD if is_crypto else CONFIDENCE_THRESHOLD
            if final_confidence >= required_conf:
                candidate_setups.append({
                    "symbol": symbol,
                    "action": best_sig.action.value,
                    "price": latest_price,
                    "confidence": final_confidence,
                    "strategy": best_sig.strategy_name,
                    "sentiment": sentiment_label,
                    "reason": best_sig.reason,
                    "stop_loss": best_sig.stop_loss,
                    "take_profit": best_sig.take_profit,
                    "is_crypto": is_crypto,
                })

        except Exception as exc:
            logger.debug("Error scanning %s: %s", symbol, exc)

    # Finalize batch scan telemetry once universe loop finishes
    if sub_agent_manager:
        sub_agent_manager.finish_scan_batch(next_cooldown_s=interval)

    if not candidate_setups:
        logger.info("No fresh high-confidence setups found across market this cycle.")
        DashboardAPIHandler.log_event("=== Trading cycle complete (no fresh setups) ===", level="CYCLE")
        return

    # -------------------------------------------------------------------------
    # LEVEL 4 & 5: Risk Guardian & Execution Router Agent
    # -------------------------------------------------------------------------
    current_positions = engine.virtual_broker.get_positions()
    current_count = len(current_positions)
    available_slots = max(0, MAX_CONCURRENT_POSITIONS - current_count)

    slots_msg = f"[L4:RISK] Active Portfolio: {current_count}/{MAX_CONCURRENT_POSITIONS} positions (available entry slots: {available_slots})"
    logger.info(slots_msg)
    DashboardAPIHandler.log_event(slots_msg, level="CYCLE")

    # Sort all setups by final AI confidence descending (prioritizing the highest-conviction trades)
    candidate_setups.sort(key=lambda x: x["confidence"], reverse=True)

    executed_count = 0
    for setup in candidate_setups:
        if executed_count >= MAX_EXECUTES_PER_CYCLE:
            break

        symbol = setup["symbol"]
        action = setup["action"]
        price = setup["price"]
        conf = setup["confidence"]
        strategy = setup["strategy"]
        stop_loss = setup.get("stop_loss")
        take_profit = setup.get("take_profit")
        is_crypto = setup.get("is_crypto", False)

        # Level 4 Risk Check: Enforce maximum 10 concurrent open trades
        if action in ("BUY", "SELL") and available_slots <= 0:
            held_log = f"  [L4:RISK CAP] Cannot enter {action} {symbol}: max 10 concurrent live positions already filled."
            logger.info(held_log)
            DashboardAPIHandler.log_event(held_log, level="SKIP", symbol=symbol)
            continue

        # Prevent duplicate entries on symbols where a matching position is already open
        existing_pos = engine.virtual_broker.get_position(symbol)
        if action == "BUY" and existing_pos and existing_pos.quantity > 0 and existing_pos.side.upper() == "LONG":
            skip_log = f"  [L4:RISK SKIP] BUY {symbol} skipped: already hold open LONG position ({existing_pos.quantity} shares)"
            logger.info(skip_log)
            DashboardAPIHandler.log_event(skip_log, level="SKIP", symbol=symbol)
            continue
        elif action == "SELL" and existing_pos and existing_pos.quantity > 0 and existing_pos.side.upper() == "SHORT":
            skip_log = f"  [L4:RISK SKIP] SELL (SHORT) {symbol} skipped: already hold open SHORT position ({existing_pos.quantity} shares)"
            logger.info(skip_log)
            DashboardAPIHandler.log_event(skip_log, level="SKIP", symbol=symbol)
            continue

        # Level 4 Dynamic Position Sizing (Adaptive Aggressive Allocation)
        trade_quantity = calculate_trade_quantity(symbol, price, conf, is_crypto)

        # Level 5: Execution Router Agent Dispatch
        order = engine.execute_signal(
            symbol=symbol,
            action=action,
            price=price,
            quantity=trade_quantity,
            strategy_name=strategy,
            stop_loss=stop_loss,
            take_profit=take_profit,
        )

        if order:
            action_desc = "SHORT" if (order.side.value == "SELL" and (not existing_pos or existing_pos.side.upper() == "SHORT")) else order.side.value
            fill_log = f"  [L5:EXEC FILLED] {action_desc} {symbol} {order.quantity} @ ${order.average_fill_price:.2f} (Target TP: ${take_profit or 0:.2f}, SL: ${stop_loss or 0:.2f})"
            logger.info(fill_log)
            DashboardAPIHandler.log_event(fill_log, level="FILLED", symbol=symbol, action=action_desc)
            if action in ("BUY", "SELL"):
                available_slots -= 1
                executed_count += 1
            elif action == "EXIT":
                available_slots = min(MAX_CONCURRENT_POSITIONS, available_slots + 1)
        else:
            block_log = f"  [L4:RISK BLOCKED] Order blocked for {symbol} by circuit breaker or loss-prevention memory."
            logger.info(block_log)
            DashboardAPIHandler.log_event(block_log, level="BLOCKED", symbol=symbol, action=action)

    cycle_end_log = f"=== [SWARM HIERARCHY] Trading Cycle Complete: {executed_count} orders executed ==="
    logger.info(cycle_end_log)
    DashboardAPIHandler.log_event(cycle_end_log, level="CYCLE")


def main():
    parser = argparse.ArgumentParser(description="Claude Universal Autonomous Trading Bot")
    parser.add_argument(
        "--symbols", default="ALL",
        help="Comma-separated symbols or 'ALL' to scan all active tradable equities from Alpaca"
    )
    parser.add_argument(
        "--interval", type=int, default=45,
        help="Scan interval in seconds (default: 45)"
    )
    parser.add_argument(
        "--port", type=int, default=8000,
        help="Dashboard HTTP port (default: 8000)"
    )
    parser.add_argument(
        "--cash", type=float, default=100_000.0,
        help="Starting virtual cash balance"
    )
    parser.add_argument(
        "--once", action="store_true",
        help="Run a single trading cycle and exit (useful for automated verification and test runs)"
    )
    args = parser.parse_args()

    engine, strategy_engine, feed, ai, market_repo, alpaca_broker, sub_agent_manager = build_services(args.cash)

    # Determine trading universe
    if args.symbols.upper() == "ALL":
        symbols = get_universe(alpaca_broker)
    else:
        symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]

    logger.info("Claude Universal Autonomous Trading Bot — Multi-Agent Swarm Orchestrator")
    logger.info("  Universe Size : %d symbols", len(symbols))
    logger.info("  Sub-Agents    : 6 Specialized Swarm Agents (timemachine, analyst, entry, exit, news, pelosi)")
    logger.info("  Scan Interval : %ds", args.interval)
    logger.info("  Dashboard     : http://localhost:%d/", args.port)
    logger.info("  Starting Cash : $%.2f", args.cash)

    # Mount services in dashboard API handler
    DashboardAPIHandler.initialize_services(
        engine=engine,
        market_repo=market_repo,
        feed_manager=feed,
        sub_agent_manager=sub_agent_manager,
    )

    # Start dashboard server in background thread
    httpd = run_server(
        port=args.port,
        engine=engine,
        market_repo=market_repo,
        feed_manager=feed,
        sub_agent_manager=sub_agent_manager,
    )
    server_thread = threading.Thread(target=httpd.serve_forever, daemon=True, name="DashboardServer")
    server_thread.start()
    logger.info("Dashboard running at http://localhost:%d/", args.port)

    try:
        while True:
            trading_cycle(symbols, engine, strategy_engine, feed, ai, sub_agent_manager, interval=args.interval)
            if args.once:
                logger.info("Single scan run completed (--once specified).")
                break
            logger.info("Next market scan in %ds...\n", args.interval)
            time.sleep(args.interval)
    except KeyboardInterrupt:
        logger.info("Shutdown requested — stopping bot and server.")
        httpd.shutdown()
        httpd.server_close()


if __name__ == "__main__":
    main()
