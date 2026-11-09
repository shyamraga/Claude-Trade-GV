import sqlite3
import os
from pathlib import Path
from typing import Optional


class Database:
    """SQLite Database manager with WAL mode and optimized indexing."""

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            project_root = Path(__file__).resolve().parent.parent.parent
            data_dir = project_root / "data"
            data_dir.mkdir(parents=True, exist_ok=True)
            self.db_path = str(data_dir / "market_data.db")
        else:
            self.db_path = db_path
            if db_path != ":memory:":
                Path(db_path).parent.mkdir(parents=True, exist_ok=True)

        self._shared_mem_conn: Optional[sqlite3.Connection] = None
        if self.db_path == ":memory:":
            self._shared_mem_conn = sqlite3.connect(":memory:")
            self._shared_mem_conn.row_factory = sqlite3.Row

        self._init_db()

    def get_connection(self) -> sqlite3.Connection:
        """Returns a configured SQLite connection."""
        if self._shared_mem_conn is not None:
            return self._shared_mem_conn

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        return conn

    def _init_db(self) -> None:
        """Creates tables and indices if they do not exist."""
        conn = self.get_connection()
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS bars (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            timeframe TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            open REAL NOT NULL,
            high REAL NOT NULL,
            low REAL NOT NULL,
            close REAL NOT NULL,
            volume REAL NOT NULL,
            vwap REAL,
            UNIQUE(symbol, timeframe, timestamp)
        );

        CREATE INDEX IF NOT EXISTS idx_bars_query
        ON bars(symbol, timeframe, timestamp DESC);

        CREATE TABLE IF NOT EXISTS watchlists (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT UNIQUE NOT NULL,
            added_at TEXT NOT NULL,
            active INTEGER DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS tick_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            price REAL NOT NULL,
            volume REAL NOT NULL,
            source TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_ticks_query
        ON tick_events(symbol, timestamp DESC);
        """)
        conn.commit()
        if self._shared_mem_conn is None:
            conn.close()

    def close(self) -> None:
        """Closes any open persistent connection."""
        if self._shared_mem_conn is not None:
            self._shared_mem_conn.close()
            self._shared_mem_conn = None
