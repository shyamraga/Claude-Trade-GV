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
            ("BTC-USD", 74250.0, "bullish"),
            ("ETH-USD", 2820.0, "bullish"),
            ("NVDA", 146.50, "bullish"),
            ("SOL-USD", 182.40, "bearish"),
            ("SPY", 592.00, "neutral"),
        ]

        now = datetime.now(timezone.utc)
        for sym, anchor_px, sent in sample_symbols:
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

            self.evaluate_symbol(sym, bars, context={"sentiment": sent})

    def get_swarm_telemetry(self) -> Dict[str, Any]:
        """Return real-time operational status for all managed sub-agents."""
        if self.total_swarm_runs == 0:
            self.warmup_telemetry()

        return {
            "manager_id": self.manager_id,
            "status": "ACTIVE",
            "total_sub_agents": len(self.agents),
            "total_swarm_runs": self.total_swarm_runs,
            "agents": {
                aid: agent.get_status_summary() for aid, agent in self.agents.items()
            },
            "recent_symbols_evaluated": list(self.last_reports.keys())[-10:],
            "recent_reports": [rep.to_dict() for rep in list(self.last_reports.values())[-6:]],
        }
