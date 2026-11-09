import argparse
import logging
import sys
from typing import List, Dict, Optional

from src.data.models import TimeFrame
from src.data.feed_manager import FeedManager
from src.storage.db import Database
from src.storage.repository import MarketDataRepository

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("DataPipeline")


class DataPipeline:
    """Coordinates fetching market data from feeds and syncing into local storage."""

    def __init__(self, feed: Optional[FeedManager] = None, repo: Optional[MarketDataRepository] = None):
        self.feed = feed or FeedManager()
        self.repo = repo or MarketDataRepository()

    def sync_symbol(self, symbol: str, timeframe: TimeFrame, limit: int = 100) -> int:
        """Fetch and store bars for a single symbol and timeframe."""
        symbol = symbol.upper().strip()
        try:
            bars = self.feed.get_bars(symbol, timeframe=timeframe, limit=limit)
            if not bars:
                logger.warning("No bars returned for %s (%s)", symbol, timeframe.value)
                return 0
            saved = self.repo.save_bars(bars, timeframe=timeframe)
            logger.info("Synced %d bars for %s (%s)", saved, symbol, timeframe.value)
            return saved
        except Exception as e:
            logger.error("Failed to sync %s (%s): %s", symbol, timeframe.value, e)
            return 0

    def sync_symbols(self, symbols: List[str], timeframes: List[TimeFrame], limit: int = 100) -> Dict[str, int]:
        """Sync a batch of symbols across multiple timeframes."""
        results: Dict[str, int] = {}
        for sym in symbols:
            total_for_sym = 0
            for tf in timeframes:
                saved = self.sync_symbol(sym, tf, limit=limit)
                total_for_sym += saved
            results[sym] = total_for_sym
        return results

    def sync_watchlist(self, timeframes: Optional[List[TimeFrame]] = None, limit: int = 100) -> Dict[str, int]:
        """Sync all active symbols in the watchlist."""
        if timeframes is None:
            timeframes = [TimeFrame.M5, TimeFrame.M15, TimeFrame.D1]
        symbols = self.repo.get_watchlist()
        if not symbols:
            logger.info("Watchlist is currently empty.")
            return {}
        return self.sync_symbols(symbols, timeframes, limit=limit)


def main():
    parser = argparse.ArgumentParser(description="Market Data Ingestion Pipeline")
    parser.add_argument("--symbols", type=str, help="Comma-separated list of symbols (e.g., SPY,AAPL,NVDA)")
    parser.add_argument("--timeframe", type=str, default="15m", choices=["1m", "5m", "15m", "1h", "1d"], help="Bar timeframe")
    parser.add_argument("--limit", type=int, default=100, help="Number of bars to fetch")
    parser.add_argument("--add-watchlist", type=str, help="Add comma-separated symbols to watchlist")
    parser.add_argument("--sync-watchlist", action="store_true", help="Sync all symbols in watchlist")

    args = parser.parse_args()
    pipeline = DataPipeline()

    if args.add_watchlist:
        for s in args.add_watchlist.split(","):
            s = s.strip().upper()
            if s:
                pipeline.repo.add_to_watchlist(s)
                print(f"Added {s} to watchlist.")

    if args.sync_watchlist:
        tf = TimeFrame(args.timeframe)
        print(f"Syncing watchlist at {tf.value}...")
        results = pipeline.sync_watchlist(timeframes=[tf], limit=args.limit)
        print("Sync results:", results)
        return

    if args.symbols:
        symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
        tf = TimeFrame(args.timeframe)
        print(f"Syncing symbols {symbols} at {tf.value} (limit={args.limit})...")
        results = pipeline.sync_symbols(symbols, [tf], limit=args.limit)
        print("Sync results:", results)
    else:
        print("No operation specified. Use --symbols or --sync-watchlist. See --help.")


if __name__ == "__main__":
    main()
