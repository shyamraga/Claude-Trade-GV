"""
SubAgentManager: Supervisor Agent for the Multi-Agent Trading Swarm.

Manages, monitors, and coordinates all specialized sub-agents simultaneously:
  1. trader-timemachine (Historical fractal & regime matching)
  2. trader-analyst (Technical indicator matrix & multi-timeframe consensus)
  3. trader-entry (Precision entry timing, VWAP proximity & slippage control)
  4. trader-exit (Dynamic trailing stops & profit target management)
  5. trader-news (Macroeconomic catalysts & breaking news sentiment)
  6. trader-pelosi (Congressional filings & institutional whale flows)

Synthesizes their simultaneous intelligence into a unified SwarmReport and reports
directly to the TradingBot orchestrator agent.
"""

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List

from src.data.models import Bar
from src.ai.agents.base import BaseSubAgent, AgentSignal, AgentAction, AgentStatus
from src.ai.agents.trader_timemachine import TraderTimeMachine
from src.ai.agents.trader_analyst import TraderAnalyst
from src.ai.agents.trader_entry import TraderEntry
from src.ai.agents.trader_exit import TraderExit
from src.ai.agents.trader_news import TraderNews
from src.ai.agents.trader_pelosi import TraderPelosi

logger = logging.getLogger("SubAgentManager")


@dataclass
class SwarmReport:
    """Executive decision report produced by SubAgentManager for the Orchestrator."""
    symbol: str
    action: AgentAction
    confidence: float
    consensus_strength: float  # Percentage of swarm in agreement (0.0 - 1.0)
    agent_signals: Dict[str, AgentSignal]
    executive_summary: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    latency_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "action": self.action.value,
            "confidence": round(self.confidence, 4),
            "consensus_strength": round(self.consensus_strength, 3),
            "executive_summary": self.executive_summary,
            "timestamp": self.timestamp.isoformat(),
            "latency_ms": round(self.latency_ms, 2),
            "agent_signals": {
                aid: sig.to_dict() for aid, sig in self.agent_signals.items()
            },
        }


@dataclass
class ScanProgress:
    """Tracks real-time batch scan progress across the market universe."""
    is_scanning: bool = False
    cycle_number: int = 0
    evaluated_count: int = 0
    total_symbols: int = 0
    progress_pct: float = 0.0
    current_symbol: str = "IDLE"
    current_action: str = "IDLE"
    cycle_start_time: float = 0.0
    cycle_finish_time: float = 0.0
    next_scan_seconds: int = 0
    top_swarm_setup: Optional[Dict[str, Any]] = None
    top_agent_setups: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        elapsed = 0.0
        remaining_s = 0
        now = time.time()
        if self.is_scanning and self.cycle_start_time > 0:
            elapsed = round(now - self.cycle_start_time, 1)
        elif not self.is_scanning and self.cycle_finish_time > 0:
            past = int(now - self.cycle_finish_time)
            remaining_s = max(0, self.next_scan_seconds - past)

        return {
            "is_scanning": self.is_scanning,
            "cycle_number": self.cycle_number,
            "evaluated_count": self.evaluated_count,
            "total_symbols": self.total_symbols,
            "progress_pct": round(self.progress_pct, 1),
            "current_symbol": self.current_symbol,
            "elapsed_seconds": elapsed,
            "next_scan_seconds": remaining_s,
            "top_swarm_setup": self.top_swarm_setup,
        }


class SubAgentManager:
    """
    Manager Agent overseeing the 6 specialized sub-agents.
    Reports directly to the TradingBot Orchestrator.
    """

    def __init__(self):
        self.manager_id = "agent-manager"
        self.agents: Dict[str, BaseSubAgent] = {
            "trader-timemachine": TraderTimeMachine(weight=1.0),
            "trader-analyst": TraderAnalyst(weight=1.25),
            "trader-entry": TraderEntry(weight=1.0),
            "trader-exit": TraderExit(weight=1.1),
            "trader-news": TraderNews(weight=1.0),
            "trader-pelosi": TraderPelosi(weight=1.15),
        }
        self.last_reports: Dict[str, SwarmReport] = {}
        self.total_swarm_runs = 0
        self.scan_progress = ScanProgress()

    def start_scan_batch(self, total_symbols: int, cycle_number: int = 0) -> None:
        """Initialize batch scanning telemetry for a new universe scan cycle."""
        self.scan_progress.is_scanning = True
        self.scan_progress.cycle_number = cycle_number
        self.scan_progress.evaluated_count = 0
        self.scan_progress.total_symbols = max(1, total_symbols)
        self.scan_progress.progress_pct = 0.0
        self.scan_progress.cycle_start_time = time.time()
        self.scan_progress.current_symbol = "STARTING BATCH..."
        self.scan_progress.top_swarm_setup = None
        self.scan_progress.top_agent_setups = {}

    def update_scan_progress(
        self,
        symbol: str,
        evaluated_count: int,
        current_report: Optional[SwarmReport] = None,
    ) -> None:
        """Update live scanning cursor, calculate completion percentage, and track top setups."""
        self.scan_progress.is_scanning = True
        self.scan_progress.evaluated_count = evaluated_count
        self.scan_progress.current_symbol = symbol
        if self.scan_progress.total_symbols > 0:
            pct = (evaluated_count / self.scan_progress.total_symbols) * 100.0
            self.scan_progress.progress_pct = min(100.0, pct)

        if current_report:
            # Check overall swarm peak setup
            if current_report.action in (AgentAction.BUY, AgentAction.SELL):
                curr_top = self.scan_progress.top_swarm_setup
                if not curr_top or current_report.confidence > curr_top.get("confidence", 0.0):
                    self.scan_progress.top_swarm_setup = {
                        "symbol": symbol,
                        "action": current_report.action.value,
                        "confidence": current_report.confidence,
                        "consensus_strength": current_report.consensus_strength,
                        "summary": current_report.executive_summary,
                    }

            # Track top setup per sub-agent across the scan
            for aid, sig in current_report.agent_signals.items():
                if sig.action in (AgentAction.BUY, AgentAction.SELL):
                    existing = self.scan_progress.top_agent_setups.get(aid)
                    if not existing or sig.confidence > existing.get("confidence", 0.0):
                        self.scan_progress.top_agent_setups[aid] = sig.to_dict()

    def finish_scan_batch(self, next_cooldown_s: int = 20) -> None:
        """Mark universe scan cycle complete and arm next cycle countdown."""
        self.scan_progress.is_scanning = False
        self.scan_progress.progress_pct = 100.0
        self.scan_progress.evaluated_count = self.scan_progress.total_symbols
        self.scan_progress.cycle_finish_time = time.time()
        self.scan_progress.next_scan_seconds = next_cooldown_s
        self.scan_progress.current_symbol = "AWAITING NEXT CYCLE"

    def evaluate_symbol(
        self,
        symbol: str,
        bars: List[Bar],
        current_position: Optional[Any] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> SwarmReport:
        """
        Execute simultaneous evaluation across all 6 sub-agents in parallel threads,
        reconcile their independent verdicts, and synthesize a single SwarmReport.
        """
        start_t = time.perf_counter()
        self.total_swarm_runs += 1

        agent_signals: Dict[str, AgentSignal] = {}

        # Run all 6 sub-agents simultaneously using ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=len(self.agents)) as executor:
            future_to_agent = {
                executor.submit(agent.analyze, symbol, bars, current_position, context): aid
                for aid, agent in self.agents.items()
            }
            for future in as_completed(future_to_agent):
                aid = future_to_agent[future]
                try:
                    sig = future.result()
                    agent_signals[aid] = sig
                    self.agents[aid].record_signal(sig)
                except Exception as exc:
                    logger.error("Sub-agent %s failed for %s: %s", aid, symbol, exc)
                    err_sig = AgentSignal(
                        agent_id=aid,
                        symbol=symbol,
                        action=AgentAction.HOLD,
                        confidence=0.5,
                        reason=f"Agent encountered error: {exc}",
                        status=AgentStatus.ERROR,
                    )
                    agent_signals[aid] = err_sig
                    self.agents[aid].record_signal(err_sig)

        # Consensus Synthesis
        swarm_report = self._synthesize_consensus(symbol, agent_signals, start_t)
        self.last_reports[symbol] = swarm_report
        return swarm_report

    def _synthesize_consensus(
        self,
        symbol: str,
        signals: Dict[str, AgentSignal],
        start_time: float,
    ) -> SwarmReport:
        """Reconcile signals from all 6 agents using weighted confidence scoring."""
        vote_scores = {
            AgentAction.BUY: 0.0,
            AgentAction.SELL: 0.0,
            AgentAction.EXIT: 0.0,
            AgentAction.HOLD: 0.0,
        }
        total_weight = 0.0

        for aid, sig in signals.items():
            agent = self.agents.get(aid)
            w = agent.weight if agent else 1.0
            act = sig.action
            if act in (AgentAction.NEUTRAL, AgentAction.HOLD):
                vote_scores[AgentAction.HOLD] += w * 0.5
            elif act == AgentAction.BUY:
                vote_scores[AgentAction.BUY] += w * sig.confidence
            elif act == AgentAction.SELL:
                vote_scores[AgentAction.SELL] += w * sig.confidence
            elif act == AgentAction.EXIT:
                vote_scores[AgentAction.EXIT] += w * sig.confidence

            total_weight += w

        # Find winning action
        winning_action = max(vote_scores.keys(), key=lambda a: vote_scores[a])
        raw_score = vote_scores[winning_action]

        # Calculate consensus strength (% of active non-hold agents agreeing)
        directional_signals = [
            s for s in signals.values()
            if s.action not in (AgentAction.HOLD, AgentAction.NEUTRAL)
        ]
        agreeing_count = sum(1 for s in signals.values() if s.action == winning_action)
        consensus_strength = agreeing_count / len(signals) if signals else 0.0

        # Confidence calculation
        if winning_action in (AgentAction.BUY, AgentAction.SELL):
            # Base confidence scaled by agent agreement
            conf_pool = [s.confidence for s in signals.values() if s.action == winning_action]
            avg_winning_conf = (sum(conf_pool) / len(conf_pool)) if conf_pool else 0.5
            # Swarm bonus: If >= 4 agents agree on direction, boost confidence
            swarm_bonus = 0.08 if agreeing_count >= 4 else (0.04 if agreeing_count >= 3 else 0.0)
            final_conf = min(0.96, avg_winning_conf + swarm_bonus)
        elif winning_action == AgentAction.EXIT:
            final_conf = 0.90
        else:
            final_conf = 0.50

        # Synthesize executive summary
        key_reasons = []
        for aid, sig in signals.items():
            if sig.action == winning_action:
                key_reasons.append(f"{aid}: {sig.reason}")

        if not key_reasons:
            summary = f"Swarm in equilibrium for {symbol}: no dominant directional consensus."
        else:
            summary = f"Swarm Consensus [{agreeing_count}/6 Agents agree on {winning_action.value}]: " + " | ".join(key_reasons[:3])

        latency = (time.perf_counter() - start_time) * 1000

        return SwarmReport(
            symbol=symbol,
            action=winning_action,
            confidence=round(final_conf, 4),
            consensus_strength=round(consensus_strength, 3),
            agent_signals=signals,
            executive_summary=summary,
            latency_ms=latency,
        )

    def warmup_telemetry(self) -> None:
        """Bootstrap initial telemetry across all 6 agents if no live runs have occurred yet."""
        if self.total_swarm_runs > 0:
            return

        import random
        from datetime import datetime, timezone, timedelta
        from src.data.models import Bar

        sample_symbols = [
            ("XAU/USD", 3995.0, "bullish"),
            ("BTC-USD", 74500.0, "bullish"),
            ("ETH-USD", 2820.0, "bullish"),
            ("NVDA", 146.50, "bullish"),
            ("SOL-USD", 182.40, "bearish"),
            ("XAG/USD", 51.80, "bullish"),
            ("SPY", 592.00, "neutral"),
        ]

        now = datetime.now(timezone.utc)
        self.start_scan_batch(total_symbols=len(sample_symbols), cycle_number=1)
        for idx, (sym, anchor_px, sent) in enumerate(sample_symbols, start=1):
            bars: List[Bar] = []
            px = anchor_px
            for i in range(35):
                t = now - timedelta(minutes=(35 - i) * 15)
                change = random.uniform(-0.005, 0.006) * px
                h = px + random.uniform(0.001, 0.004) * px
                l = px - random.uniform(0.001, 0.004) * px
                c = px + change
                vol = float(random.randint(25000, 120000))
                bars.append(Bar(
                    symbol=sym,
                    timestamp=t,
                    open=round(px, 2),
                    high=round(h, 2),
                    low=round(l, 2),
                    close=round(c, 2),
                    volume=vol,
                ))
                px = c

            rep = self.evaluate_symbol(sym, bars, context={"sentiment": sent})
            self.update_scan_progress(sym, idx, current_report=rep)
        self.finish_scan_batch(next_cooldown_s=30)

    def get_swarm_telemetry(self) -> Dict[str, Any]:
        """Return real-time operational status for all managed sub-agents."""
        if self.total_swarm_runs == 0:
            self.warmup_telemetry()

        agents_summary = {}
        for aid, agent in self.agents.items():
            summary = agent.get_status_summary()
            summary["is_evaluating"] = self.scan_progress.is_scanning
            top_sig = self.scan_progress.top_agent_setups.get(aid)
            summary["top_signal"] = top_sig or summary.get("last_signal")
            agents_summary[aid] = summary

        return {
            "manager_id": self.manager_id,
            "status": "ACTIVE",
            "total_sub_agents": len(self.agents),
            "total_swarm_runs": self.total_swarm_runs,
            "scan_progress": self.scan_progress.to_dict(),
            "agents": agents_summary,
            "recent_symbols_evaluated": list(self.last_reports.keys())[-10:],
            "recent_reports": [rep.to_dict() for rep in list(self.last_reports.values())[-6:]],
        }
