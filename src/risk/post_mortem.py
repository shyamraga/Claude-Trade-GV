"""Trade loss post-mortem generation and continuous learning memory loop."""

import json
import logging
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional, List

from src.risk.models import TradeRecord

logger = logging.getLogger(__name__)


@dataclass
class TradePostMortem:
    """Detailed post-mortem analysis of a losing trade."""

    post_mortem_id: str
    symbol: str
    strategy_name: str
    entry_price: float
    exit_price: float
    loss_amount: float
    loss_pct: float
    entry_time: datetime
    exit_time: datetime
    root_cause: str  # e.g., "False breakout above resistance", "Ignored bearish RSI divergence"
    market_condition: str  # e.g., "Choppy high-volatility sideways market"
    preventative_rule: str  # e.g., "Do not enter breakouts when volume is below 20-day SMA"
    tags: List[str]

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        d = asdict(self)
        d["entry_time"] = self.entry_time.isoformat()
        d["exit_time"] = self.exit_time.isoformat()
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "TradePostMortem":
        """Deserialize from dictionary."""
        d = dict(data)
        if isinstance(d.get("entry_time"), str):
            d["entry_time"] = datetime.fromisoformat(d["entry_time"])
        if isinstance(d.get("exit_time"), str):
            d["exit_time"] = datetime.fromisoformat(d["exit_time"])
        return cls(**d)

    def to_markdown(self) -> str:
        """Format post-mortem as readable Markdown for storage in project memory."""
        return f"""# Trade Loss Post-Mortem: {self.symbol} ({self.strategy_name})

- **Date:** {self.exit_time.strftime('%Y-%m-%d %H:%M:%S')}
- **Loss:** -${abs(self.loss_amount):,.2f} ({self.loss_pct:.2%})
- **Entry / Exit:** ${self.entry_price:.2f} / ${self.exit_price:.2f}
- **Market Context:** {self.market_condition}

## Root Cause Analysis
{self.root_cause}

## Preventative Rule
> **Rule:** {self.preventative_rule}

**Tags:** {', '.join(self.tags)}
"""


class PostMortemRepository:
    """Manages trade loss post-mortems and queries memory before trade entry."""

    def __init__(self, memory_dir: Optional[Path] = None):
        """Initialize repository pointing to memory directory."""
        self.memory_dir = memory_dir or (Path(__file__).resolve().parent.parent.parent / "data" / "post_mortems")
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        self._cache: List[TradePostMortem] = []
        self._load_all()

    def _load_all(self) -> None:
        """Load all existing post-mortems from disk."""
        self._cache.clear()
        for file in self.memory_dir.glob("*.json"):
            try:
                data = json.loads(file.read_text(encoding="utf-8"))
                self._cache.append(TradePostMortem.from_dict(data))
            except Exception as e:
                logger.warning(f"Failed to load post-mortem {file.name}: {e}")

    def create_post_mortem(
        self,
        trade: TradeRecord,
        root_cause: str,
        market_condition: str,
        preventative_rule: str,
        tags: Optional[List[str]] = None,
    ) -> TradePostMortem:
        """Create and persist a new post-mortem for a losing trade."""
        pm_id = f"pm_{trade.symbol}_{int(trade.exit_time.timestamp())}"
        post_mortem = TradePostMortem(
            post_mortem_id=pm_id,
            symbol=trade.symbol,
            strategy_name=trade.strategy_name,
            entry_price=trade.entry_price,
            exit_price=trade.exit_price,
            loss_amount=abs(trade.pnl),
            loss_pct=abs(trade.pnl_pct),
            entry_time=trade.entry_time,
            exit_time=trade.exit_time,
            root_cause=root_cause,
            market_condition=market_condition,
            preventative_rule=preventative_rule,
            tags=tags or [trade.symbol, trade.strategy_name, "loss"],
        )

        # Save JSON data and Markdown record
        json_path = self.memory_dir / f"{pm_id}.json"
        md_path = self.memory_dir / f"{pm_id}.md"

        json_path.write_text(json.dumps(post_mortem.to_dict(), indent=2), encoding="utf-8")
        md_path.write_text(post_mortem.to_markdown(), encoding="utf-8")

        self._cache.append(post_mortem)
        logger.info(f"Post-mortem created and saved to {json_path.name}")
        return post_mortem

    def check_pre_trade_filter(
        self,
        symbol: str,
        strategy_name: str,
        proposed_setup_tags: Optional[List[str]] = None,
    ) -> tuple[bool, Optional[str]]:
        """
        Query past loss memory to see if this symbol/strategy setup previously failed.
        Returns: (is_allowed, warning_or_block_reason)
        """
        symbol = symbol.upper()
        similar_losses = [
            pm for pm in self._cache
            if pm.symbol == symbol and pm.strategy_name == strategy_name
        ]

        if not similar_losses:
            return True, None

        # Check the most recent failure
        latest_loss = sorted(similar_losses, key=lambda x: x.exit_time, reverse=True)[0]
        warning_msg = (
            f"Pre-trade memory match: {symbol} had prior loss with {strategy_name} "
            f"(-${latest_loss.loss_amount:,.2f}). Preventative rule: '{latest_loss.preventative_rule}'"
        )

        logger.warning(warning_msg)
        return False, warning_msg

    def get_recent_post_mortems(self, limit: int = 5) -> List[TradePostMortem]:
        """Get the latest post-mortems."""
        return sorted(self._cache, key=lambda x: x.exit_time, reverse=True)[:limit]