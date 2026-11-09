from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

from src.data.models import Bar, TimeFrame
from src.storage.db import Database


class MarketDataRepository:
    """Repository for querying and storing market data in SQLite."""

    def __init__(self, db: Optional[Database] = None):
        self.db = db or Database()

    def save_bars(self, bars: List[Bar], timeframe: TimeFrame) -> int:
        """Batch saves bars with INSERT OR REPLACE semantics. Returns saved count."""
        if not bars:
            return 0

        rows = []
        for b in bars:
            ts_str = b.timestamp.isoformat()
            rows.append((
                b.symbol.upper(),
                timeframe.value,
                ts_str,
                b.open,
                b.high,
                b.low,
                b.close,
                b.volume,
                b.vwap
            ))

        sql = """
        INSERT OR REPLACE INTO bars (
            symbol, timeframe, timestamp, open, high, low, close, volume, vwap
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        conn = self.db.get_connection()
        try:
            with conn:
                conn.executemany(sql, rows)
            return len(rows)
        finally:
            if self.db._shared_mem_conn is None:
                conn.close()

    def get_bars(
        self,
        symbol: str,
        timeframe: TimeFrame,
        limit: int = 100,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None
    ) -> List[Bar]:
        """Fetch historical bars in chronological order (oldest to newest)."""
        symbol = symbol.upper().strip()
        query = ["SELECT symbol, timeframe, timestamp, open, high, low, close, volume, vwap FROM bars WHERE symbol = ? AND timeframe = ?"]
        params: List[Any] = [symbol, timeframe.value]

        if start:
            query.append("AND timestamp >= ?")
            params.append(start.isoformat())
        if end:
            query.append("AND timestamp <= ?")
            params.append(end.isoformat())

        query.append("ORDER BY timestamp DESC")
        if limit:
            query.append("LIMIT ?")
            params.append(limit)

        sql = " ".join(query)
        conn = self.db.get_connection()
        try:
            cur = conn.cursor()
            cur.execute(sql, params)
            rows = cur.fetchall()

            bars = []
            for r in rows:
                bars.append(Bar(
                    symbol=r["symbol"],
                    timestamp=datetime.fromisoformat(r["timestamp"]),
                    open=r["open"],
                    high=r["high"],
                    low=r["low"],
                    close=r["close"],
                    volume=r["volume"],
                    vwap=r["vwap"]
                ))
            # Reverse so that oldest bar is index 0 and newest is index -1
            bars.reverse()
            return bars
        finally:
            if self.db._shared_mem_conn is None:
                conn.close()

    def get_latest_bar(self, symbol: str, timeframe: TimeFrame) -> Optional[Bar]:
        """Fetch the most recent bar stored for a symbol and timeframe."""
        bars = self.get_bars(symbol, timeframe, limit=1)
        return bars[-1] if bars else None

    def get_bar_count(self, symbol: str, timeframe: TimeFrame) -> int:
        """Returns the number of stored bars for a symbol and timeframe."""
        symbol = symbol.upper().strip()
        sql = "SELECT COUNT(*) FROM bars WHERE symbol = ? AND timeframe = ?"
        conn = self.db.get_connection()
        try:
            cur = conn.cursor()
            cur.execute(sql, (symbol, timeframe.value))
            return cur.fetchone()[0]
        finally:
            if self.db._shared_mem_conn is None:
                conn.close()

    def add_to_watchlist(self, symbol: str) -> None:
        """Add symbol to active watchlist."""
        symbol = symbol.upper().strip()
        now = datetime.now(timezone.utc).isoformat()
        sql = "INSERT OR REPLACE INTO watchlists (symbol, added_at, active) VALUES (?, ?, 1)"
        conn = self.db.get_connection()
        try:
            with conn:
                conn.execute(sql, (symbol, now))
        finally:
            if self.db._shared_mem_conn is None:
                conn.close()

    def get_watchlist(self) -> List[str]:
        """Fetch active watched symbols."""
        sql = "SELECT symbol FROM watchlists WHERE active = 1 ORDER BY symbol ASC"
        conn = self.db.get_connection()
        try:
            cur = conn.cursor()
            cur.execute(sql)
            return [r[0] for r in cur.fetchall()]
        finally:
            if self.db._shared_mem_conn is None:
                conn.close()

    def remove_from_watchlist(self, symbol: str) -> None:
        """Remove or deactivate a symbol from the watchlist."""
        symbol = symbol.upper().strip()
        sql = "UPDATE watchlists SET active = 0 WHERE symbol = ?"
        conn = self.db.get_connection()
        try:
            with conn:
                conn.execute(sql, (symbol,))
        finally:
            if self.db._shared_mem_conn is None:
                conn.close()
