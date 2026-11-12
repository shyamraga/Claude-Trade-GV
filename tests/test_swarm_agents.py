"""Unit tests for the Multi-Agent Trading Swarm and SubAgentManager."""

import unittest
from datetime import datetime, timezone
from src.data.models import Bar
from src.ai.agents.base import AgentAction, AgentStatus
from src.ai.agents.trader_timemachine import TraderTimeMachine
from src.ai.agents.trader_analyst import TraderAnalyst
from src.ai.agents.trader_entry import TraderEntry
from src.ai.agents.trader_exit import TraderExit
from src.ai.agents.trader_news import TraderNews
from src.ai.agents.trader_pelosi import TraderPelosi
from src.ai.agent_manager import SubAgentManager, SwarmReport


def create_sample_bars(n: int = 30, base_price: float = 100.0, trend: float = 1.0):
    bars = []
    price = base_price
    for i in range(n):
        price += trend * 0.5
        vol = 16000.0 if (trend > 0 and i == n - 1) else (5000.0 + i * 150.0)
        b = Bar(
            symbol="TEST",
            timestamp=datetime.now(timezone.utc),
            open=price - 0.2,
            high=price + 0.8,
            low=price - 0.6,
            close=price,
            volume=vol,
        )
        bars.append(b)
    return bars


class TestSubAgents(unittest.TestCase):
    def setUp(self):
        self.bars_bull = create_sample_bars(35, 100.0, 1.2)
        self.bars_bear = create_sample_bars(35, 100.0, -1.2)

    def test_trader_timemachine_bull(self):
        agent = TraderTimeMachine()
        sig = agent.analyze("TEST", self.bars_bull)
        self.assertEqual(sig.agent_id, "trader-timemachine")
        self.assertIn(sig.action, [AgentAction.BUY, AgentAction.HOLD])
        self.assertGreater(sig.confidence, 0.5)

    def test_trader_analyst_bull(self):
        agent = TraderAnalyst()
        sig = agent.analyze("TEST", self.bars_bull)
        self.assertEqual(sig.agent_id, "trader-analyst")
        self.assertEqual(sig.action, AgentAction.BUY)
        self.assertGreater(sig.confidence, 0.6)

    def test_trader_entry(self):
        agent = TraderEntry()
        sig = agent.analyze("TEST", self.bars_bull)
        self.assertEqual(sig.agent_id, "trader-entry")
        self.assertIn("optimal_entry_price", sig.metrics)

    def test_trader_exit(self):
        agent = TraderExit()
        sig = agent.analyze("TEST", self.bars_bull)
        self.assertEqual(sig.agent_id, "trader-exit")
        self.assertIn("atr", sig.metrics)

    def test_trader_news(self):
        agent = TraderNews()
        sig = agent.analyze("TEST", self.bars_bull, context={"sentiment": "bullish"})
        self.assertEqual(sig.agent_id, "trader-news")
        self.assertEqual(sig.action, AgentAction.BUY)

    def test_trader_pelosi(self):
        agent = TraderPelosi()
        sig = agent.analyze("NVDA", self.bars_bull)
        self.assertEqual(sig.agent_id, "trader-pelosi")
        self.assertEqual(sig.action, AgentAction.BUY)
        self.assertIn("smart_money_bias", sig.metrics)


class TestSubAgentManager(unittest.TestCase):
    def setUp(self):
        self.manager = SubAgentManager()
        self.bars_bull = create_sample_bars(35, 100.0, 1.5)

    def test_manager_simultaneous_evaluation(self):
        report = self.manager.evaluate_symbol("NVDA", self.bars_bull)
        self.assertIsInstance(report, SwarmReport)
        self.assertEqual(report.symbol, "NVDA")
        self.assertEqual(len(report.agent_signals), 6)
        self.assertIn("trader-timemachine", report.agent_signals)
        self.assertIn("trader-analyst", report.agent_signals)
        self.assertIn("trader-entry", report.agent_signals)
        self.assertIn("trader-exit", report.agent_signals)
        self.assertIn("trader-news", report.agent_signals)
        self.assertIn("trader-pelosi", report.agent_signals)
        self.assertEqual(report.action, AgentAction.BUY)
        self.assertGreaterEqual(report.confidence, 0.6)

    def test_manager_telemetry(self):
        self.manager.evaluate_symbol("AAPL", self.bars_bull)
        telemetry = self.manager.get_swarm_telemetry()
        self.assertEqual(telemetry["manager_id"], "agent-manager")
        self.assertEqual(telemetry["total_sub_agents"], 6)
        self.assertIn("trader-analyst", telemetry["agents"])
        self.assertIn("scan_progress", telemetry)

    def test_batch_scan_progress_lifecycle(self):
        """Verify dynamic batch scan telemetry accurately calculates completion percentage and state."""
        # 1. Initialize batch
        self.manager.start_scan_batch(total_symbols=10, cycle_number=5)
        prog = self.manager.scan_progress
        self.assertTrue(prog.is_scanning)
        self.assertEqual(prog.cycle_number, 5)
        self.assertEqual(prog.total_symbols, 10)
        self.assertEqual(prog.progress_pct, 0.0)

        # 2. Update progress mid-scan
        rep = self.manager.evaluate_symbol("NVDA", self.bars_bull)
        self.manager.update_scan_progress(symbol="NVDA", evaluated_count=5, current_report=rep)
        self.assertEqual(prog.evaluated_count, 5)
        self.assertEqual(prog.current_symbol, "NVDA")
        self.assertEqual(prog.progress_pct, 50.0)
        self.assertIsNotNone(prog.top_swarm_setup)
        self.assertEqual(prog.top_swarm_setup["symbol"], "NVDA")

        # 3. Finish scan
        self.manager.finish_scan_batch(next_cooldown_s=45)
        self.assertFalse(prog.is_scanning)
        self.assertEqual(prog.progress_pct, 100.0)
        self.assertEqual(prog.next_scan_seconds, 45)

    def test_peak_conviction_setup_retention(self):
        """Ensure top conviction signal is preserved and not erased by subsequent neutral symbols."""
        self.manager.start_scan_batch(total_symbols=2, cycle_number=1)

        # High conviction symbol
        rep_high = self.manager.evaluate_symbol("NVDA", self.bars_bull, context={"sentiment": "bullish"})
        self.manager.update_scan_progress("NVDA", evaluated_count=1, current_report=rep_high)

        # Neutral symbol
        bars_neutral = create_sample_bars(35, 100.0, 0.0)
        rep_neutral = self.manager.evaluate_symbol("FLAT", bars_neutral, context={"sentiment": "neutral"})
        self.manager.update_scan_progress("FLAT", evaluated_count=2, current_report=rep_neutral)

        self.manager.finish_scan_batch()

        # Telemetry should retain NVDA as peak conviction setup
        tele = self.manager.get_swarm_telemetry()
        self.assertEqual(tele["scan_progress"]["top_swarm_setup"]["symbol"], "NVDA")
        self.assertIn("top_signal", tele["agents"]["trader-analyst"])

    def test_metals_evaluation(self):
        """Verify precious metals (XAU/USD & XAG/USD) evaluate cleanly with valid metrics."""
        rep_gold = self.manager.evaluate_symbol("XAU/USD", self.bars_bull)
        self.assertEqual(rep_gold.symbol, "XAU/USD")
        self.assertIn(rep_gold.action, [AgentAction.BUY, AgentAction.HOLD, AgentAction.SELL])

        rep_silver = self.manager.evaluate_symbol("XAG/USD", self.bars_bull)
        self.assertEqual(rep_silver.symbol, "XAG/USD")
        self.assertIn(rep_silver.action, [AgentAction.BUY, AgentAction.HOLD, AgentAction.SELL])


if __name__ == "__main__":
    unittest.main()
