"""Batch re-diagnose historical post-mortems using TradeDiagnostician and build CUMULATIVE_LEARNINGS.md."""

import json
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.risk.models import TradeRecord
from src.risk.post_mortem import TradePostMortem
from src.risk.trade_diagnostician import TradeDiagnostician


def main():
    trades_file = Path("data/trades/trades_history.json")
    trade_map = {}
    if trades_file.exists():
        for t in json.loads(trades_file.read_text(encoding="utf-8")):
            trade_map[t["symbol"]] = t

    pm_dir = Path("data/post_mortems")
    learnings_file = Path("data/CUMULATIVE_LEARNINGS.md")

    all_pms = []
    for f in sorted(pm_dir.glob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            pm = TradePostMortem.from_dict(data)

            matched_trade = trade_map.get(pm.symbol)
            side = "BUY"
            reason = "STOP_LOSS" if pm.outcome == "LOSS" else "TAKE_PROFIT"
            if matched_trade:
                side = matched_trade.get("side", side)
                matched_reason = matched_trade.get("reason")
                if matched_reason and matched_reason not in ("LOSS", "WIN"):
                    reason = matched_reason

            tr = TradeRecord(
                trade_id=pm.post_mortem_id.replace("pm_", "tr_"),
                symbol=pm.symbol,
                side=side,
                quantity=10,
                entry_price=pm.entry_price,
                exit_price=pm.exit_price,
                pnl=-pm.loss_amount if pm.outcome == "LOSS" else pm.loss_amount,
                pnl_pct=-pm.loss_pct if pm.outcome == "LOSS" else pm.loss_pct,
                entry_time=pm.entry_time,
                exit_time=pm.exit_time,
                strategy_name=pm.strategy_name,
                reason=reason,
            )

            root, cond, rule, tags = TradeDiagnostician.diagnose_trade(tr)
            pm.root_cause = root
            pm.market_condition = cond
            pm.preventative_rule = rule
            pm.tags = tags

            # Re-save updated json and markdown
            f.write_text(json.dumps(pm.to_dict(), indent=2), encoding="utf-8")
            md_file = f.with_suffix(".md")
            md_file.write_text(pm.to_markdown(), encoding="utf-8")
            all_pms.append((pm, tr))
        except Exception as e:
            print(f"Error processing {f.name}: {e}")

    # Sort all post-mortems chronologically for CUMULATIVE_LEARNINGS.md
    all_pms.sort(key=lambda x: x[0].exit_time)

    lines = [
        "# Cumulative Continuous Learning Log & Preventative Rules\n",
        "This ledger tracks every trade closed by the autonomous trading engine, "
        "recording multi-dimensional diagnostic root causes, market regimes, "
        "and actionable preventative rules enforced via pre-trade memory filters.\n",
        f"**Total Debriefs Logged:** {len(all_pms)}\n",
        "---\n",
    ]

    for pm, tr in all_pms:
        dur_min = max(1.0, (tr.exit_time - tr.entry_time).total_seconds()) / 60.0
        pnl_sign = "+" if tr.pnl >= 0 else ""
        date_str = pm.exit_time.strftime("%Y-%m-%d %H:%M:%S")
        entry = (
            f"\n### [{date_str}] {pm.outcome}: {tr.symbol} ({tr.strategy_name} {tr.side})\n"
            f"- **P&L:** {pnl_sign}${tr.pnl:.2f} ({tr.pnl_pct:.2%})\n"
            f"- **Duration:** {dur_min:.1f} min\n"
            f"- **Entry / Exit:** ${tr.entry_price:.2f} ➔ ${tr.exit_price:.2f} (Reason: {tr.reason or 'SIGNAL_EXIT'})\n"
            f"- **Root Cause:** {pm.root_cause}\n"
            f"- **Preventative Rule:** {pm.preventative_rule}\n"
            f"- **Tags:** {', '.join(pm.tags)}\n"
            f"---\n"
        )
        lines.append(entry)

    learnings_file.write_text("".join(lines), encoding="utf-8")
    print(f"Successfully re-diagnosed {len(all_pms)} post-mortems and generated {learnings_file}!")


if __name__ == "__main__":
    main()
