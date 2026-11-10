"""REST API and static file web server for Claude Trading Dashboard."""

import json
import logging
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from typing import Optional

from src.data.models import TimeFrame
from src.execution.engine import ExecutionEngine, ExecutionMode
from src.execution.virtual_broker import VirtualBroker
from src.risk.circuit_breaker import CircuitBreaker
from src.risk.post_mortem import PostMortemRepository
from src.storage.repository import MarketDataRepository

logger = logging.getLogger(__name__)


class DashboardAPIHandler(SimpleHTTPRequestHandler):
    """HTTP request handler supporting both REST API endpoints and dashboard static files."""

    # Class-level shared singletons
    engine: Optional[ExecutionEngine] = None
    market_repo: Optional[MarketDataRepository] = None

    @classmethod
    def initialize_services(
        cls,
        engine: Optional[ExecutionEngine] = None,
        market_repo: Optional[MarketDataRepository] = None,
    ):
        """Configure shared service instances."""
        cls.engine = engine or ExecutionEngine()
        cls.market_repo = market_repo or MarketDataRepository()

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
                    "quantity": p.quantity,
                    "entry_price": p.entry_price,
                    "current_price": p.current_price,
                    "unrealized_pnl": p.unrealized_pnl,
                    "unrealized_pnl_pct": p.unrealized_pnl_pct,
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
            limit = int(query.get("limit", [5])[0])
            pms = [pm.to_dict() for pm in engine.post_mortem_repo.get_recent_post_mortems(limit=limit)]
            self._send_json({"post_mortems": pms})

        elif path == "/api/bars":
            symbol = query.get("symbol", ["SPY"])[0].upper()
            timeframe = query.get("timeframe", ["15m"])[0]
            limit = int(query.get("limit", [100])[0])

            bars = []
            if self.market_repo:
                try:
                    tf_enum = TimeFrame(timeframe)
                    db_bars = self.market_repo.get_bars(symbol, tf_enum, limit=limit)
                    bars = [b.to_dict() for b in db_bars]
                except Exception as e:
                    logger.debug(f"Could not load bars from DB: {e}")

            # If no bars in DB, generate synthetic or default test data
            if not bars:
                import random
                price = 150.0
                for i in range(30):
                    change = random.uniform(-1.5, 1.8)
                    high = price + random.uniform(0.2, 1.0)
                    low = price - random.uniform(0.2, 1.0)
                    close = price + change
                    bars.append({
                        "symbol": symbol,
                        "timeframe": timeframe,
                        "timestamp": f"2026-11-10T09:{i*2:02d}:00",
                        "open": round(price, 2),
                        "high": round(high, 2),
                        "low": round(low, 2),
                        "close": round(close, 2),
                        "volume": random.randint(10000, 50000),
                    })
                    price = close

            self._send_json({"symbol": symbol, "timeframe": timeframe, "bars": bars})

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

        if path == "/api/circuit-breaker/override":
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

            # Update market price in virtual broker if in virtual mode
            if isinstance(engine.broker, VirtualBroker):
                engine.broker.set_market_price(symbol, price)

            order = engine.execute_signal(
                symbol=symbol,
                action=action,
                price=price,
                quantity=quantity,
                strategy_name=strategy,
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


def run_server(port: int = 8000, engine: Optional[ExecutionEngine] = None):
    """Start local dashboard HTTP server."""
    DashboardAPIHandler.initialize_services(engine=engine)
    server_address = ("", port)
    httpd = HTTPServer(server_address, DashboardAPIHandler)
    logger.info(f"Dashboard server running at http://localhost:{port}/")
    return httpd