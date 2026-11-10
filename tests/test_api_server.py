"""Unit tests for Dashboard REST API server."""

import json
import shutil
import tempfile
import threading
import unittest
import urllib.request
import urllib.error
from http.server import HTTPServer
from pathlib import Path

from src.api.server import DashboardAPIHandler
from src.execution.engine import ExecutionEngine, ExecutionMode
from src.execution.models import OrderSide, OrderStatus
from src.execution.virtual_broker import VirtualBroker
from src.risk.circuit_breaker import CircuitBreaker
from src.risk.post_mortem import PostMortemRepository
from src.storage.repository import MarketDataRepository


class TestDashboardAPIServer(unittest.TestCase):
    """Test suite for REST API endpoints and handlers."""

    @classmethod
    def setUpClass(cls):
        cls.temp_dir = Path(tempfile.mkdtemp())
        cls.broker = VirtualBroker(initial_cash=50000.0)
        cls.circuit_breaker = CircuitBreaker()
        cls.post_mortem_repo = PostMortemRepository(memory_dir=cls.temp_dir)
        cls.engine = ExecutionEngine(
            mode=ExecutionMode.VIRTUAL,
            virtual_broker=cls.broker,
            circuit_breaker=cls.circuit_breaker,
            post_mortem_repo=cls.post_mortem_repo,
        )
        from src.storage.db import Database
        cls.db = Database(str(cls.temp_dir / "test_market.db"))
        cls.market_repo = MarketDataRepository(db=cls.db)

        # Initialize handler singletons
        DashboardAPIHandler.initialize_services(
            engine=cls.engine,
            market_repo=cls.market_repo,
        )

        # Bind to port 0 for an ephemeral free port
        cls.server = HTTPServer(("127.0.0.1", 0), DashboardAPIHandler)
        cls.port = cls.server.server_address[1]
        cls.base_url = f"http://127.0.0.1:{cls.port}"

        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        shutil.rmtree(cls.temp_dir, ignore_errors=True)

    def _get(self, path: str):
        req = urllib.request.Request(f"{self.base_url}{path}")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = resp.read().decode("utf-8")
            return resp.status, json.loads(data)

    def _post(self, path: str, payload: dict):
        data_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}{path}",
            data=data_bytes,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = resp.read().decode("utf-8")
            return resp.status, json.loads(data)

    def test_get_account(self):
        """Test GET /api/account endpoint."""
        status, data = self._get("/api/account")
        self.assertEqual(status, 200)
        self.assertIn("cash", data)
        self.assertIn("portfolio_value", data)
        self.assertIn("mode", data)
        self.assertEqual(data["mode"], "VIRTUAL")

    def test_get_positions(self):
        """Test GET /api/positions endpoint."""
        status, data = self._get("/api/positions")
        self.assertEqual(status, 200)
        self.assertIn("positions", data)
        self.assertIsInstance(data["positions"], list)

    def test_get_circuit_breaker(self):
        """Test GET /api/circuit-breaker endpoint."""
        status, data = self._get("/api/circuit-breaker")
        self.assertEqual(status, 200)
        self.assertIn("is_cooldown_active", data)
        self.assertIn("consecutive_losses", data)
        self.assertIn("manual_override", data)

    def test_circuit_breaker_override(self):
        """Test POST /api/circuit-breaker/override."""
        status, data = self._post("/api/circuit-breaker/override", {"override": True})
        self.assertEqual(status, 200)
        self.assertTrue(data.get("manual_override"))

        # Reset override
        self._post("/api/circuit-breaker/override", {"override": False})

    def test_switch_mode(self):
        """Test POST /api/mode endpoint."""
        status, data = self._post("/api/mode", {"mode": "LIVE"})
        self.assertEqual(status, 200)
        self.assertEqual(data.get("mode"), "LIVE")

        # Switch back to VIRTUAL
        status, data = self._post("/api/mode", {"mode": "VIRTUAL"})
        self.assertEqual(status, 200)
        self.assertEqual(data.get("mode"), "VIRTUAL")

    def test_get_bars(self):
        """Test GET /api/bars endpoint."""
        status, data = self._get("/api/bars?symbol=SPY&timeframe=15m&limit=10")
        self.assertEqual(status, 200)
        self.assertEqual(data["symbol"], "SPY")
        self.assertEqual(data["timeframe"], "15m")
        self.assertGreater(len(data["bars"]), 0)

    def test_execute_order(self):
        """Test POST /api/execute endpoint."""
        payload = {
            "symbol": "AAPL",
            "action": "BUY",
            "price": 150.0,
            "quantity": 10,
            "strategy": "MOMENTUM",
            "stop_loss": 147.0,
            "take_profit": 156.0,
        }
        status, data = self._post("/api/execute", payload)
        self.assertEqual(status, 200)
        self.assertTrue(data.get("success"))
        self.assertEqual(data["order"]["symbol"], "AAPL")
        self.assertEqual(data["order"]["quantity"], 10)

        # Check /api/positions has timestamps and exit targets
        status_pos, pos_data = self._get("/api/positions")
        self.assertEqual(status_pos, 200)
        aapl_pos = next((p for p in pos_data["positions"] if p["symbol"] == "AAPL"), None)
        self.assertIsNotNone(aapl_pos)
        self.assertIsNotNone(aapl_pos.get("opened_at"))
        self.assertEqual(aapl_pos.get("stop_loss"), 147.0)
        self.assertEqual(aapl_pos.get("take_profit"), 156.0)
        self.assertEqual(aapl_pos.get("strategy"), "MOMENTUM")

    def test_get_trades(self):
        """Test GET /api/trades endpoint."""
        status, data = self._get("/api/trades")
        self.assertEqual(status, 200)
        self.assertIn("trades", data)
        self.assertIsInstance(data["trades"], list)

    def test_get_post_mortems(self):
        """Test GET /api/post-mortems endpoint."""
        status, data = self._get("/api/post-mortems?limit=5")
        self.assertEqual(status, 200)
        self.assertIn("post_mortems", data)
        self.assertIsInstance(data["post_mortems"], list)

    def test_serve_static_files(self):
        """Test serving index.html, styles.css, and app.js."""
        # 1. index.html
        req = urllib.request.Request(f"{self.base_url}/")
        with urllib.request.urlopen(req, timeout=5) as resp:
            self.assertEqual(resp.status, 200)
            self.assertIn("text/html", resp.headers.get("Content-Type", ""))
            content = resp.read().decode("utf-8")
            self.assertIn("CLAUDE TRADING", content)

        # 2. styles.css
        req_css = urllib.request.Request(f"{self.base_url}/styles.css")
        with urllib.request.urlopen(req_css, timeout=5) as resp:
            self.assertEqual(resp.status, 200)
            self.assertIn("text/css", resp.headers.get("Content-Type", ""))
            content = resp.read().decode("utf-8")
            self.assertIn("--bg-oled", content)

        # 3. app.js
        req_js = urllib.request.Request(f"{self.base_url}/app.js")
        with urllib.request.urlopen(req_js, timeout=5) as resp:
            self.assertEqual(resp.status, 200)
            self.assertIn("application/javascript", resp.headers.get("Content-Type", ""))
            content = resp.read().decode("utf-8")
            self.assertIn("FinancialChartRenderer", content)


if __name__ == "__main__":
    unittest.main()
