"""REST API and static file web server for Claude Trading Dashboard."""

import time
import json
import logging
from http.server import HTTPServer, ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from typing import Optional

from src.data.models import TimeFrame
from src.data.feed_manager import FeedManager
from src.execution.engine import ExecutionEngine, ExecutionMode
from src.execution.virtual_broker import VirtualBroker
from src.risk.circuit_breaker import CircuitBreaker
from src.risk.post_mortem import PostMortemRepository
from src.risk.market_hours import MarketHoursManager
from src.storage.repository import MarketDataRepository
from src.ai.agent_manager import SubAgentManager

logger = logging.getLogger(__name__)


class DashboardAPIHandler(SimpleHTTPRequestHandler):
    """HTTP request handler supporting both REST API endpoints and dashboard static files."""

    # Class-level shared singletons
    engine: Optional[ExecutionEngine] = None
    market_repo: Optional[MarketDataRepository] = None
    feed_manager: Optional[FeedManager] = None
    sub_agent_manager: Optional[SubAgentManager] = None
    scanner_logs: list = []

    @classmethod
    def log_event(cls, message: str, level: str = "INFO", symbol: str = "", action: str = ""):
        """Record a live bot / scanner event."""
        import datetime
        now = datetime.datetime.now().strftime("%H:%M:%S")
        cls.scanner_logs.append({
            "time": now,
            "message": message,
            "level": level,
            "symbol": symbol,
            "action": action
        })
        # Keep recent 200 logs
        if len(cls.scanner_logs) > 200:
            cls.scanner_logs.pop(0)

    @classmethod
    def initialize_services(
        cls,
        engine: Optional[ExecutionEngine] = None,
        market_repo: Optional[MarketDataRepository] = None,
        feed_manager: Optional[FeedManager] = None,
        sub_agent_manager: Optional[SubAgentManager] = None,
    ):
        """Configure shared service instances without clobbering existing instances."""
        if engine is not None or cls.engine is None:
            cls.engine = engine or ExecutionEngine()
        if market_repo is not None or cls.market_repo is None:
            cls.market_repo = market_repo or MarketDataRepository()
        if feed_manager is not None or cls.feed_manager is None:
            cls.feed_manager = feed_manager or FeedManager()
        if sub_agent_manager is not None or cls.sub_agent_manager is None:
            cls.sub_agent_manager = sub_agent_manager or SubAgentManager()

    def end_headers(self):
        """Inject CORS headers."""
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        super().end_headers()

    def do_OPTIONS(self):
        """Handle pre-flight CORS requests."""
        self.send_response(200)
        self.end_headers()

    def _send_json(self, data: dict, status: int = 200):
        """Send a JSON formatted response."""
        content = json.dumps(data, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def do_GET(self):
        """Route GET requests to API endpoints or static dashboard files."""
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        if path.startswith("/api/"):
            return self._handle_api_get(path, query)

        # Serve static dashboard files
        dashboard_dir = Path(__file__).resolve().parent.parent.parent / "dashboard"
        if path == "/" or path == "/index.html":
            file_path = dashboard_dir / "index.html"
            content_type = "text/html; charset=utf-8"
        elif path.endswith(".js"):
            file_path = dashboard_dir / path.lstrip("/")
            content_type = "application/javascript"
        elif path.endswith(".css"):
            file_path = dashboard_dir / path.lstrip("/")
            content_type = "text/css"
        else:
            file_path = dashboard_dir / path.lstrip("/")
            content_type = "text/plain"

        if file_path.exists() and file_path.is_file():
            content = file_path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        else:
            self._send_json({"error": "Not Found"}, status=404)

    def _handle_api_get(self, path: str, query: dict):
        """Handle REST API GET endpoints."""
        engine = self.engine or ExecutionEngine()

        if path == "/api/account":
            acc = engine.broker.get_account()
            self._send_json({
                "mode": engine.mode.value,
                "cash": acc.cash,
                "portfolio_value": acc.portfolio_value,
                "buying_power": acc.buying_power,
                "currency": acc.currency,
                "day_trades_remaining": acc.day_trades_remaining,
            })

        elif path == "/api/positions":
            positions = [
                {
                    "symbol": p.symbol,
                    "side": getattr(p, "side", "LONG"),
                    "quantity": p.quantity,
                    "entry_price": p.entry_price,
                    "current_price": p.current_price,
                    "unrealized_pnl": p.unrealized_pnl,
                    "unrealized_pnl_pct": p.unrealized_pnl_pct,
                    "opened_at": p.opened_at.isoformat() if hasattr(p, "opened_at") and p.opened_at else None,
                    "stop_loss": getattr(p, "stop_loss", None),
                    "take_profit": getattr(p, "take_profit", None),
                    "strategy": getattr(p, "strategy", "MANUAL"),
                }
                for p in engine.broker.get_positions()
            ]
            self._send_json({"positions": positions})

        elif path == "/api/circuit-breaker":
            cb = engine.circuit_breaker
            drawdown_pct = (cb.daily_starting_equity - cb.current_equity) / cb.daily_starting_equity if cb.daily_starting_equity > 0 else 0.0
            self._send_json({
                "is_cooldown_active": cb.is_cooldown_active(),
                "cooldown_reason": cb.cooldown_reason,
                "cooldown_until": cb.cooldown_until.isoformat() if cb.cooldown_until else None,
                "consecutive_losses": cb.consecutive_losses,
                "consecutive_loss_limit": cb.config.consecutive_loss_limit,
                "current_drawdown_pct": round(drawdown_pct, 4),
                "max_daily_drawdown_pct": cb.config.max_daily_drawdown_pct,
                "manual_override": cb.manual_override,
            })

        elif path == "/api/trades":
            trades = [t.to_dict() for t in engine.trade_history]
            self._send_json({"trades": trades})

        elif path == "/api/post-mortems":
            limit = int(query.get("limit", [50])[0])
            pms = [pm.to_dict() for pm in engine.post_mortem_repo.get_recent_post_mortems(limit=limit)]
            total_count = len(engine.post_mortem_repo._cache)
            self._send_json({"post_mortems": pms, "total_count": total_count})

        elif path == "/api/scanner-logs":
            limit = int(query.get("limit", [50])[0])
            self._send_json({"logs": self.scanner_logs[-limit:]})

        elif path in ("/api/market-hours", "/api/market-summary"):
            summary = MarketHoursManager.get_open_markets_summary()
            self._send_json(summary)

        elif path == "/api/agents":
            if not self.sub_agent_manager:
                self.sub_agent_manager = SubAgentManager()
            telemetry = self.sub_agent_manager.get_swarm_telemetry()
            self._send_json(telemetry)

        elif path == "/api/bars":
            raw_symbol = query.get("symbol", ["SPY"])[0].upper().strip()
            timeframe_str = query.get("timeframe", ["15m"])[0]
            limit = int(query.get("limit", [100])[0])

            # Normalize crypto tickers so "BTC" maps directly to liquid "BTC-USD"
            if raw_symbol in ("BTC", "BITCOIN"):
                symbol = "BTC-USD"
            elif raw_symbol in ("ETH", "ETHEREUM"):
                symbol = "ETH-USD"
            elif raw_symbol in ("SOL", "SOLANA"):
                symbol = "SOL-USD"
            elif raw_symbol in ("DOGE", "DOGECOIN"):
                symbol = "DOGE-USD"
            elif raw_symbol in ("AVAX", "AVALANCHE"):
                symbol = "AVAX-USD"
            else:
                symbol = raw_symbol

            try:
                tf_enum = TimeFrame(timeframe_str)
            except Exception:
                tf_enum = TimeFrame.M15

            bars = []
            # 1. Try FeedManager for real live market data
            try:
                if not self.feed_manager:
                    self.feed_manager = FeedManager()
                live_bars = self.feed_manager.get_bars(symbol, timeframe=tf_enum, limit=limit)
                if live_bars:
                    bars = [b.to_dict() for b in live_bars]
            except Exception as e:
                logger.warning(f"FeedManager fetch failed for {symbol}: {e}")

            # 2. Try database repository
            if not bars and self.market_repo:
                try:
                    db_bars = self.market_repo.get_bars(symbol, tf_enum, limit=limit)
                    bars = [b.to_dict() for b in db_bars]
                except Exception as e:
                    logger.debug(f"Could not load bars from DB: {e}")

            # 3. Fallback: only if live feed and DB are both unavailable
            if not bars:
                # Realistic price baseline by asset class to prevent misleading $150 defaults
                anchor_price = 150.0
                if "BTC" in symbol:
                    anchor_price = 74500.0
                elif "ETH" in symbol:
                    anchor_price = 2100.0
                elif "SOL" in symbol:
                    anchor_price = 85.0
                elif "DOGE" in symbol:
                    anchor_price = 0.07
                elif "AVAX" in symbol:
                    anchor_price = 8.60
                elif "SPY" in symbol:
                    anchor_price = 758.0
                elif "QQQ" in symbol:
                    anchor_price = 688.0
                elif "AAPL" in symbol:
                    anchor_price = 225.0
                elif "MSFT" in symbol:
                    anchor_price = 420.0
                elif "NVDA" in symbol:
                    anchor_price = 145.0
                elif "TSLA" in symbol:
                    anchor_price = 215.0
                elif "AMZN" in symbol:
                    anchor_price = 205.0
                elif "GOOGL" in symbol:
                    anchor_price = 180.0
                elif "META" in symbol:
                    anchor_price = 580.0
                elif "NFLX" in symbol:
                    anchor_price = 810.0
                elif "AMD" in symbol:
                    anchor_price = 140.0
                elif "COIN" in symbol:
                    anchor_price = 290.0
                elif "MSTR" in symbol:
                    anchor_price = 330.0
                elif ".NS" in symbol or ".BO" in symbol:
                    anchor_price = 1350.0

                import random
                from datetime import datetime, timezone, timedelta
                now = datetime.now(timezone.utc)
                price = anchor_price
                step_minutes = tf_enum.minutes
                for i in range(30):
                    bar_time = now - timedelta(minutes=(30 - i) * step_minutes)
                    change = random.uniform(-price * 0.004, price * 0.005)
                    high = price + random.uniform(0.001 * price, 0.003 * price)
                    low = price - random.uniform(0.001 * price, 0.003 * price)
                    close = price + change
                    bars.append({
                        "symbol": symbol,
                        "timeframe": timeframe_str,
                        "timestamp": bar_time.isoformat(),
                        "open": round(price, 2),
                        "high": round(high, 2),
                        "low": round(low, 2),
                        "close": round(close, 2),
                        "volume": random.randint(10000, 50000),
                    })
                    price = close

            self._send_json({"symbol": symbol, "timeframe": timeframe_str, "bars": bars})

        else:
            self._send_json({"error": f"Endpoint not found: {path}"}, status=404)

    def do_POST(self):
        """Handle REST API POST requests."""
        parsed = urlparse(self.path)
        path = parsed.path

        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length) if content_length > 0 else b"{}"

        try:
            payload = json.loads(body.decode("utf-8")) if body else {}
        except json.JSONDecodeError:
            return self._send_json({"error": "Invalid JSON"}, status=400)

        engine = self.engine or ExecutionEngine()

        if path == "/api/scanner-logs":
            msg = payload.get("message", "")
            level = payload.get("level", "INFO")
            symbol = payload.get("symbol", "")
            action = payload.get("action", "")
            self.log_event(message=msg, level=level, symbol=symbol, action=action)
            return self._send_json({"success": True})

        elif path == "/api/circuit-breaker/override":
            override = payload.get("override", True)
            engine.circuit_breaker.set_manual_override(override)
            self._send_json({"success": True, "manual_override": engine.circuit_breaker.manual_override})

        elif path == "/api/mode":
            mode_str = payload.get("mode", "VIRTUAL").upper()
            if mode_str in ("VIRTUAL", "LIVE"):
                engine.set_mode(ExecutionMode(mode_str))
                self._send_json({"success": True, "mode": engine.mode.value})
            else:
                self._send_json({"error": "Invalid mode. Use VIRTUAL or LIVE"}, status=400)

        elif path == "/api/execute":
            symbol = payload.get("symbol", "").upper()
            action = payload.get("action", "").upper()
            price = float(payload.get("price", 100.0))
            quantity = int(payload.get("quantity", 10))
            strategy = payload.get("strategy", "MANUAL")

            if not symbol or action not in ("BUY", "SELL", "EXIT"):
                return self._send_json({"error": "symbol and valid action (BUY/SELL/EXIT) required"}, status=400)

            stop_loss = float(payload["stop_loss"]) if payload.get("stop_loss") is not None else None
            take_profit = float(payload["take_profit"]) if payload.get("take_profit") is not None else None

            # Update market price in virtual broker if in virtual mode
            if isinstance(engine.broker, VirtualBroker):
                engine.broker.set_market_price(symbol, price)

            order = engine.execute_signal(
                symbol=symbol,
                action=action,
                price=price,
                quantity=quantity,
                strategy_name=strategy,
                stop_loss=stop_loss,
                take_profit=take_profit,
            )

            if order:
                self._send_json({"success": True, "order": order.to_dict()})
            else:
                reason = "Blocked by risk management or circuit breaker"
                if engine.circuit_breaker.is_cooldown_active():
                    reason = f"Circuit breaker active: {engine.circuit_breaker.cooldown_reason}"
                self._send_json({"success": False, "reason": reason}, status=400)

        else:
            self._send_json({"error": f"POST endpoint not found: {path}"}, status=404)


def run_server(
    port: int = 8000,
    engine: Optional[ExecutionEngine] = None,
    market_repo: Optional[MarketDataRepository] = None,
    feed_manager: Optional[FeedManager] = None,
    sub_agent_manager: Optional[SubAgentManager] = None,
):
    """Start local dashboard HTTP server."""
    DashboardAPIHandler.initialize_services(
        engine=engine,
        market_repo=market_repo,
        feed_manager=feed_manager,
        sub_agent_manager=sub_agent_manager,
    )
    ThreadingHTTPServer.allow_reuse_address = True
    server_address = ("", port)
    httpd = ThreadingHTTPServer(server_address, DashboardAPIHandler)
    logger.info(f"Dashboard server running at http://localhost:{port}/")
    return httpd