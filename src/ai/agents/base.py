"""
Base classes and interfaces for the Multi-Agent Trading Swarm.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, Any, Optional, List

from src.data.models import Bar


class AgentAction(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    EXIT = "EXIT"
    HOLD = "HOLD"
    NEUTRAL = "NEUTRAL"


class AgentStatus(str, Enum):
    ACTIVE = "ACTIVE"
    ANALYZING = "ANALYZING"
    IDLE = "IDLE"
    ALERT = "ALERT"
    ERROR = "ERROR"


@dataclass
class AgentSignal:
    agent_id: str
    symbol: str
    action: AgentAction
    confidence: float
    reason: str
    metrics: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    latency_ms: float = 0.0
    status: AgentStatus = AgentStatus.ACTIVE

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "symbol": self.symbol,
            "action": self.action.value,
            "confidence": round(self.confidence, 4),
            "reason": self.reason,
            "metrics": self.metrics,
            "timestamp": self.timestamp.isoformat(),
            "latency_ms": round(self.latency_ms, 2),
            "status": self.status.value,
        }


class BaseSubAgent(ABC):
    """Abstract base class for all specialized trading sub-agents in the swarm."""

    def __init__(self, agent_id: str, name: str, role: str, weight: float = 1.0):
        self.agent_id = agent_id
        self.name = name
        self.role = role
        self.weight = weight
        self.status = AgentStatus.IDLE
        self.last_signal: Optional[AgentSignal] = None
        self.total_analyses = 0
        self.successful_analyses = 0
        self.activity_log: List[Dict[str, Any]] = []

    def record_signal(self, sig: AgentSignal) -> AgentSignal:
        """Record evaluation signal, update last_signal, and append to rolling activity log."""
        self.last_signal = sig
        self.activity_log.append(sig.to_dict())
        if len(self.activity_log) > 30:
            self.activity_log.pop(0)
        return sig

    @abstractmethod
    def analyze(
        self,
        symbol: str,
        bars: List[Bar],
        current_position: Optional[Any] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> AgentSignal:
        """Execute domain-specific analysis for the given symbol and return AgentSignal."""
        pass

    def get_status_summary(self) -> Dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "role": self.role,
            "weight": self.weight,
            "status": self.status.value,
            "total_analyses": self.total_analyses,
            "successful_analyses": self.successful_analyses,
            "last_signal": self.last_signal.to_dict() if self.last_signal else None,
            "activity_log": list(reversed(self.activity_log)),
        }
