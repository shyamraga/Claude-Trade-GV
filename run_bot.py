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

from src.risk.circuit_breaker import CircuitBreaker
from src.risk.post_mortem import PostMortemRepository
from src.execution.engine import ExecutionEngine, ExecutionMode
from src.execution.virtual_broker import VirtualBroker
from src.execution.alpaca_broker import AlpacaBroker

from src.api.server import DashboardAPIHandler, run_server

# Constants
CONFIDENCE_THRESHOLD = 0.50   # Minimum confidence to consider a general setup
CRYPTO_CONFIDENCE_THRESHOLD = 0.90 # Minimum confidence required for crypto pairs
SHARES_PER_TRADE     = 10     # Fixed lot size per trade execution
MAX_CONCURRENT_POSITIONS = 10 # Maximum simultaneous open live positions in portfolio
MAX_EXECUTES_PER_CYCLE = 10   # Top best setups to execute per scan cycle

CRYPTO_SYMBOLS = ["BTC-USD", "ETH-USD", "SOL-USD", "AVAX-USD", "DOGE-USD"]



def get_universe(broker: Optional[AlpacaBroker] = None) -> List[str]:
    """Retrieve all tradable active US equities from Alpaca and prepend mandatory crypto pairs."""
    default_universe = [
        "BTC-USD", "ETH-USD", "SOL-USD", "AVAX-USD", "DOGE-USD",
        "SPY", "QQQ", "AAPL", "MSFT", "NVDA", "TSLA", "AMZN", "GOOGL", "META",
        "NFLX", "AMD", "JPM", "COIN", "MSTR", "INTC", "DIS", "BA", "JNJ", "XOM",
        "V", "WMT", "PYPL", "SQ", "SHOP", "UBER", "ABNB", "PLTR", "RIVN", "SNOW"
    ]
    try:
        if broker is None:
            broker = AlpacaBroker()
        assets = broker._request("/v2/assets?status=active&asset_class=us_equity")
        if assets:
            tradable = [a["symbol"] for a in assets if a.get("tradable") and "." not in a["symbol"]]
            if tradable:
                logger.info("Loaded %d tradable US equities from Alpaca API.", len(tradable))
                # Combine crypto pairs + top equities
                return CRYPTO_SYMBOLS + tradable[:200]
    except Exception as e:
        logger.warning("Could not fetch dynamic Alpaca universe (%s). Using default crypto & equity universe.", e)

    return CRYPTO_SYMBOLS + default_universe


def build_services(initial_cash: float = 100_000.0):
    """Instantiate and wire all platform services."""
    db               = Database()
    market_repo      = MarketDataRepository(db=db)
    post_mortem_repo = PostMortemRepository()
    circuit_breaker  = CircuitBreaker()
    virtual_broker   = VirtualBroker(initial_cash=initial_cash)
    alpaca_broker    = AlpacaBroker()

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

    return engine, strategy_engine, feed, ai, market_repo, alpaca_broker


def trading_cycle(
    symbols: List[str],
    engine: ExecutionEngine,
    strategy_engine: StrategyEngine,
    feed: FeedManager,
    ai: AIMarketIntelligence,
):
    """Scan all market symbols continuously, evaluate strategies, rank setups by confidence, and execute the best."""
    time_str = datetime.now().strftime("%H:%M:%S")
    logger.info("=== Trading cycle started ===  %s", time_str)
    DashboardAPIHandler.log_event(f"=== Trading cycle started ===  {time_str}", level="CYCLE")

    candidate_setups: List[Dict[str, Any]] = []

    for symbol in symbols:
        try:
            bars = feed.get_bars(symbol, timeframe=TimeFrame.M15, limit=100)
            if len(bars) < 25:
                continue

            bars_sorted = sorted(bars, key=lambda b: b.timestamp)
            latest_price = bars_sorted[-1].close

            # Update broker mark-to-market
            engine.virtual_broker.set_market_price(symbol, latest_price)

            # Auto-check Stop-Loss & Take-Profit targets on open positions
            auto_exit_order = engine.check_position_stops(symbol, latest_price)
            if auto_exit_order:
                exit_log = f"  [AUTO-EXIT] {auto_exit_order.exit_reason or 'STOP/TARGET'} hit for {symbol}: closed {auto_exit_order.quantity} @ ${auto_exit_order.average_fill_price:.2f}"
                logger.info(exit_log)
                DashboardAPIHandler.log_event(exit_log, level="FILLED", symbol=symbol, action=auto_exit_order.exit_reason or "EXIT")
                continue

            # Run all strategies
            signal_map = strategy_engine.run_all(bars_sorted)
            latest_signals = [
                sigs[-1] for sigs in signal_map.values()
                if sigs and sigs[-1].action in (SignalAction.BUY, SignalAction.SELL, SignalAction.EXIT)
            ]

            if not latest_signals:
                continue

            # Best signal for this symbol
            best_sig = max(latest_signals, key=lambda s: s.confidence)

            # If the signal is EXIT, only proceed if we actually hold an open position to close
            if best_sig.action == SignalAction.EXIT:
                open_pos = engine.virtual_broker.get_position(symbol)
                if not open_pos or open_pos.quantity <= 0:
                    continue

            # Filter out weak signals below baseline threshold before AI modulation
            if best_sig.confidence < CONFIDENCE_THRESHOLD:
                continue

            # Multi-Agent Collaboration: AI Sentiment & Momentum Intelligence
            final_confidence = best_sig.confidence
            sentiment_label = "neutral"
            try:
                modulated = ai.enrich_signal(
                    symbol=symbol,
                    action=best_sig.action.value,
                    confidence=best_sig.confidence,
                    bars=bars_sorted,
                )
                final_confidence = modulated.get("modulated_confidence", best_sig.confidence)
                sentiment_label = modulated.get("sentiment", "neutral")
            except Exception as e:
                logger.debug("AI modulation error for %s: %s", symbol, e)

            sig_log = f"  {symbol}  best signal: {best_sig.action.value} @ ${latest_price:.2f}  confidence={int(best_sig.confidence*100)}%  strategy={best_sig.strategy_name}"
            logger.info(sig_log)
            DashboardAPIHandler.log_event(sig_log, level="SIGNAL", symbol=symbol, action=best_sig.action.value)

            post_ai_log = f"  {symbol}  post-AI confidence={int(final_confidence*100)}%  sentiment={sentiment_label}"
            logger.info(post_ai_log)
            DashboardAPIHandler.log_event(post_ai_log, level="AI", symbol=symbol)

            # Enforce 90% threshold for crypto and 50% for equities after AI sentiment modulation
            is_crypto = symbol in CRYPTO_SYMBOLS
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
                })

        except Exception as exc:
            logger.debug("Error scanning %s: %s", symbol, exc)

    if not candidate_setups:
        logger.info("No high-confidence setups found across market this cycle.")
        DashboardAPIHandler.log_event("=== Trading cycle complete ===", level="CYCLE")
        return

    # Check portfolio-level concurrent position limit
    current_positions = engine.virtual_broker.get_positions()
    current_count = len(current_positions)
    available_slots = max(0, MAX_CONCURRENT_POSITIONS - current_count)

    slots_msg = f"Portfolio positions: {current_count}/{MAX_CONCURRENT_POSITIONS} active (available entry slots: {available_slots})"
    logger.info(slots_msg)
    DashboardAPIHandler.log_event(slots_msg, level="CYCLE")

    # Sort all candidate setups globally across the entire market by confidence descending
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

        # Enforce portfolio maximum 10 concurrent open trades: skip new entries if full
        if action in ("BUY", "SELL") and available_slots <= 0:
            held_log = f"  [CAP REACHED] Cannot enter {action} {symbol}: max 10 concurrent live positions already filled."
            logger.info(held_log)
            DashboardAPIHandler.log_event(held_log, level="SKIP", symbol=symbol)
            continue

        # Prevent duplicate entries on symbols where a matching side position is already open
        existing_pos = engine.virtual_broker.get_position(symbol)
        if action == "BUY" and existing_pos and existing_pos.quantity > 0 and existing_pos.side.upper() == "LONG":
            skip_log = f"  [SKIP]  BUY {symbol} skipped: already hold open LONG position ({existing_pos.quantity} shares)"
            logger.info(skip_log)
            DashboardAPIHandler.log_event(skip_log, level="SKIP", symbol=symbol)
            continue
        elif action == "SELL" and existing_pos and existing_pos.quantity > 0 and existing_pos.side.upper() == "SHORT":
            skip_log = f"  [SKIP]  SELL (SHORT) {symbol} skipped: already hold open SHORT position ({existing_pos.quantity} shares)"
            logger.info(skip_log)
            DashboardAPIHandler.log_event(skip_log, level="SKIP", symbol=symbol)
            continue

        order = engine.execute_signal(
            symbol=symbol,
            action=action,
            price=price,
            quantity=SHARES_PER_TRADE,
            strategy_name=strategy,
            stop_loss=stop_loss,
            take_profit=take_profit,
        )

        if order:
            action_desc = "SHORT" if (order.side.value == "SELL" and (not existing_pos or existing_pos.side.upper() == "SHORT")) else order.side.value
            fill_log = f"  [FILLED]  {action_desc} {symbol} {order.quantity} @ ${order.average_fill_price:.2f}"
            logger.info(fill_log)
            DashboardAPIHandler.log_event(fill_log, level="FILLED", symbol=symbol, action=action_desc)
            if action in ("BUY", "SELL"):
                available_slots -= 1
                executed_count += 1
            elif action == "EXIT":
                available_slots = min(MAX_CONCURRENT_POSITIONS, available_slots + 1)
        else:
            block_log = f"  [BLOCKED] ORDER BLOCKED for {symbol} (risk / memory guard)."
            logger.info(block_log)
            DashboardAPIHandler.log_event(block_log, level="BLOCKED", symbol=symbol, action=action)

    cycle_end_log = "=== Trading cycle complete ==="
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
    args = parser.parse_args()

    engine, strategy_engine, feed, ai, market_repo, alpaca_broker = build_services(args.cash)

    # Determine trading universe
    if args.symbols.upper() == "ALL":
        symbols = get_universe(alpaca_broker)
    else:
        symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]

    logger.info("Claude Universal Autonomous Trading Bot")
    logger.info("  Universe Size : %d symbols", len(symbols))
    logger.info("  Scan Interval : %ds", args.interval)
    logger.info("  Dashboard     : http://localhost:%d/", args.port)
    logger.info("  Starting Cash : $%.2f", args.cash)

    # Mount services in dashboard API handler
    DashboardAPIHandler.initialize_services(engine=engine, market_repo=market_repo)

    # Start dashboard server in background thread
    httpd = run_server(port=args.port, engine=engine)
    server_thread = threading.Thread(target=httpd.serve_forever, daemon=True, name="DashboardServer")
    server_thread.start()
    logger.info("Dashboard running at http://localhost:%d/", args.port)

    try:
        while True:
            trading_cycle(symbols, engine, strategy_engine, feed, ai)
            logger.info("Next market scan in %ds...\n", args.interval)
            time.sleep(args.interval)
    except KeyboardInterrupt:
        logger.info("Shutdown requested — stopping bot and server.")
        httpd.shutdown()
        httpd.server_close()


if __name__ == "__main__":
    main()
