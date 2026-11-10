"""Alpaca broker client supporting paper and live trading execution."""

import os
import json
import logging
import urllib.request
from typing import List, Optional
from datetime import datetime

from src.execution.broker_base import BaseBroker
from src.execution.models import Order, OrderSide, OrderStatus, OrderType, Position, AccountInfo

logger = logging.getLogger(__name__)


class AlpacaBroker(BaseBroker):
    """Real Alpaca Trading API execution broker."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        base_url: Optional[str] = None,
    ):
        """Initialize Alpaca trading client."""
        self.api_key = api_key or os.getenv("APCA_API_KEY_ID")
        self.secret_key = secret_key or os.getenv("APCA_API_SECRET_KEY")
        self.base_url = (base_url or os.getenv("APCA_API_BASE_URL", "https://paper-api.alpaca.markets")).rstrip("/")

    def _headers(self) -> dict:
        return {
            "APCA-API-KEY-ID": self.api_key or "",
            "APCA-API-SECRET-KEY": self.secret_key or "",
            "Content-Type": "application/json",
            "User-Agent": "ClaudeTrading/1.0",
        }

    def _request(self, endpoint: str, method: str = "GET", data: Optional[dict] = None) -> dict:
        url = f"{self.base_url}{endpoint}"
        body = json.dumps(data).encode("utf-8") if data else None
        req = urllib.request.Request(url, data=body, headers=self._headers(), method=method)

        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def get_account(self) -> AccountInfo:
        """Fetch real Alpaca account balances."""
        try:
            data = self._request("/v2/account")
            positions = self.get_positions()
            return AccountInfo(
                cash=float(data.get("cash", 0.0)),
                portfolio_value=float(data.get("portfolio_value", 0.0)),
                buying_power=float(data.get("buying_power", 0.0)),
                currency=data.get("currency", "USD"),
                day_trades_remaining=int(data.get("daytrade_count", 0)),
                is_pattern_day_trader=bool(data.get("pattern_day_trader", False)),
                open_positions=positions,
            )
        except Exception as e:
            logger.error(f"Failed to fetch Alpaca account: {e}")
            return AccountInfo(cash=0.0, portfolio_value=0.0, buying_power=0.0)

    def get_positions(self) -> List[Position]:
        """Fetch open positions from Alpaca."""
        try:
            items = self._request("/v2/positions")
            res = []
            for item in items:
                pos = Position(
                    symbol=item["symbol"],
                    quantity=int(item["qty"]),
                    entry_price=float(item["avg_entry_price"]),
                    current_price=float(item["current_price"]),
                    unrealized_pnl=float(item.get("unrealized_pl", 0.0)),
                    unrealized_pnl_pct=float(item.get("unrealized_plpc", 0.0)),
                )
                res.append(pos)
            return res
        except Exception as e:
            logger.error(f"Failed to fetch Alpaca positions: {e}")
            return []

    def get_position(self, symbol: str) -> Optional[Position]:
        """Fetch single position."""
        try:
            item = self._request(f"/v2/positions/{symbol.upper()}")
            return Position(
                symbol=item["symbol"],
                quantity=int(item["qty"]),
                entry_price=float(item["avg_entry_price"]),
                current_price=float(item["current_price"]),
                unrealized_pnl=float(item.get("unrealized_pl", 0.0)),
                unrealized_pnl_pct=float(item.get("unrealized_plpc", 0.0)),
            )
        except Exception:
            return None

    def submit_order(self, order: Order) -> Order:
        """Submit order to Alpaca."""
        payload = {
            "symbol": order.symbol.upper(),
            "qty": str(order.quantity),
            "side": order.side.value.lower(),
            "type": order.order_type.value.lower(),
            "time_in_force": "day",
        }
        if order.limit_price:
            payload["limit_price"] = str(order.limit_price)
        if order.stop_price:
            payload["stop_price"] = str(order.stop_price)

        try:
            data = self._request("/v2/orders", method="POST", data=payload)
            order.order_id = data["id"]
            status_map = {
                "new": OrderStatus.PENDING,
                "filled": OrderStatus.FILLED,
                "partially_filled": OrderStatus.PARTIALLY_FILLED,
                "canceled": OrderStatus.CANCELLED,
                "rejected": OrderStatus.REJECTED,
            }
            order.status = status_map.get(data.get("status", ""), OrderStatus.PENDING)
            return order
        except Exception as e:
            order.status = OrderStatus.REJECTED
            order.rejection_reason = str(e)
            return order

    def cancel_order(self, order_id: str) -> bool:
        """Cancel an order via Alpaca API."""
        try:
            self._request(f"/v2/orders/{order_id}", method="DELETE")
            return True
        except Exception as e:
            logger.error(f"Failed to cancel Alpaca order {order_id}: {e}")
            return False

    def get_order(self, order_id: str) -> Optional[Order]:
        """Fetch order details from Alpaca."""
        try:
            data = self._request(f"/v2/orders/{order_id}")
            return Order(
                order_id=data["id"],
                symbol=data["symbol"],
                side=OrderSide(data["side"].upper()),
                order_type=OrderType(data["type"].upper()),
                quantity=int(data["qty"]),
                status=OrderStatus.FILLED if data.get("status") == "filled" else OrderStatus.PENDING,
                filled_quantity=int(data.get("filled_qty", 0)),
                average_fill_price=float(data.get("filled_avg_price") or 0.0),
            )
        except Exception:
            return None

    def close_position(self, symbol: str) -> Optional[Order]:
        """Close position via Alpaca DELETE position endpoint."""
        try:
            data = self._request(f"/v2/positions/{symbol.upper()}", method="DELETE")
            return Order(
                order_id=data.get("id", "close"),
                symbol=symbol.upper(),
                side=OrderSide.SELL,
                order_type=OrderType.MARKET,
                quantity=int(data.get("qty", 1)),
                status=OrderStatus.PENDING,
            )
        except Exception as e:
            logger.error(f"Failed to close Alpaca position {symbol}: {e}")
            return None