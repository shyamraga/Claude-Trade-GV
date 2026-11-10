"""Base broker interface for all execution backends."""

from abc import ABC, abstractmethod
from typing import List, Optional

from src.execution.models import Order, Position, AccountInfo


class BaseBroker(ABC):
    """Abstract interface defining required broker operations."""

    @abstractmethod
    def get_account(self) -> AccountInfo:
        """Fetch current account balances, equity, and buying power."""
        pass

    @abstractmethod
    def get_positions(self) -> List[Position]:
        """Fetch all currently open positions."""
        pass

    @abstractmethod
    def get_position(self, symbol: str) -> Optional[Position]:
        """Fetch open position for a specific symbol."""
        pass

    @abstractmethod
    def submit_order(self, order: Order) -> Order:
        """Submit a new order to the broker."""
        pass

    @abstractmethod
    def cancel_order(self, order_id: str) -> bool:
        """Cancel an open order by ID."""
        pass

    @abstractmethod
    def get_order(self, order_id: str) -> Optional[Order]:
        """Fetch order details and fill status by ID."""
        pass

    @abstractmethod
    def close_position(self, symbol: str) -> Optional[Order]:
        """Close an open position completely with a market order."""
        pass