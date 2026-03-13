"""Paper trading state store with thread-safe operations."""
import threading
import time
from collections import deque
from typing import Dict, List, Optional, Any

from strategy.position import Position
from utils.logger import get_logger

logger = get_logger(__name__)


class PaperStateStore:
    """Thread-safe state store for paper trading."""
    
    def __init__(self, trend_window: int, starting_balance: float):
        self._lock = threading.RLock()
        self._trend_window = trend_window
        
        # Virtual balance
        self._virtual_balance = starting_balance
        self._starting_balance = starting_balance
        
        # Positions: market_id -> Position
        self._positions: Dict[str, Position] = {}
        
        # Price history: market_id -> {"up": deque, "down": deque}
        self._price_history: Dict[str, Dict[str, deque]] = {}
        
        # Market metadata: market_id -> market info dict
        self._market_meta: Dict[str, Dict] = {}
        
        # Paper trading statistics
        self._paper_trade_count = 0
        self._paper_usdc_spent = 0.0
        self._paper_realized_pnl = 0.0
        self._closed_markets: List[Dict] = []
    
    def _ensure_price_history(self, market_id: str):
        """Ensure price history exists for a market."""
        if market_id not in self._price_history:
            self._price_history[market_id] = {
                "up": deque(maxlen=self._trend_window * 2),
                "down": deque(maxlen=self._trend_window * 2)
            }
    
    # Virtual balance methods
    def get_virtual_balance(self) -> float:
        """Get current virtual balance."""
        with self._lock:
            return self._virtual_balance
    
    def deduct_balance(self, amount: float) -> bool:
        """Deduct from virtual balance. Returns True if successful."""
        with self._lock:
            if self._virtual_balance >= amount:
                self._virtual_balance -= amount
                return True
            return False
    
    def credit_balance(self, amount: float):
        """Credit virtual balance."""
        with self._lock:
            self._virtual_balance += amount
    
    # Position methods (same interface as live StateStore)
    def get_position(self, market_id: str) -> Optional[Position]:
        """Get position for a market."""
        with self._lock:
            return self._positions.get(market_id)
    
    def set_position(self, market_id: str, position: Position):
        """Set position for a market."""
        with self._lock:
            self._positions[market_id] = position
    
    def remove_position(self, market_id: str) -> bool:
        """Remove position for a market. Returns True if existed."""
        with self._lock:
            if market_id in self._positions:
                del self._positions[market_id]
                return True
            return False
    
    def list_active_markets(self) -> List[str]:
        """List all active market IDs."""
        with self._lock:
            return list(self._positions.keys())
    
    def has_position(self, market_id: str) -> bool:
        """Check if position exists for a market."""
        with self._lock:
            return market_id in self._positions
    
    # Price history methods
    def append_price(self, market_id: str, side: str, price: float):
        """Append a price point to history."""
        with self._lock:
            self._ensure_price_history(market_id)
            if price > 0:
                self._price_history[market_id][side].append(price)
    
    def get_price_history(self, market_id: str, side: str) -> List[float]:
        """Get price history for a market side."""
        with self._lock:
            self._ensure_price_history(market_id)
            return list(self._price_history[market_id][side])
    
    def clear_price_history(self, market_id: str):
        """Clear price history for a market."""
        with self._lock:
            if market_id in self._price_history:
                del self._price_history[market_id]
    
    # Market metadata methods
    def set_market_meta(self, market_id: str, meta: Dict):
        """Set market metadata."""
        with self._lock:
            self._market_meta[market_id] = meta
    
    def get_market_meta(self, market_id: str) -> Optional[Dict]:
        """Get market metadata."""
        with self._lock:
            return self._market_meta.get(market_id)
    
    def remove_market_meta(self, market_id: str):
        """Remove market metadata."""
        with self._lock:
            if market_id in self._market_meta:
                del self._market_meta[market_id]
    
    # Paper-specific methods
    def record_paper_trade(
        self,
        market_id: str,
        side: str,
        shares: float,
        price: float,
        rule: str,
        reason: str
    ):
        """Record a paper trade."""
        with self._lock:
            self._paper_trade_count += 1
            self._paper_usdc_spent += shares * price
            logger.info(f"Paper trade recorded: {side} {shares} @ {price} (rule: {rule})")
    
    def record_closed_market(self, result: Dict):
        """Record a closed market result."""
        with self._lock:
            self._closed_markets.append(result)
            pnl = result.get("pnl", 0)
            self._paper_realized_pnl += pnl
            # Credit virtual balance with max(0, pnl)
            self._virtual_balance += max(0, pnl)
            logger.info(f"Paper market closed: {result.get('market_id')}, PnL: {pnl:.4f}")
    
    def get_closed_markets(self) -> List[Dict]:
        """Get all closed market results."""
        with self._lock:
            return list(self._closed_markets)
    
    def get_paper_stats(self) -> Dict:
        """Get paper trading statistics."""
        with self._lock:
            winning = sum(1 for m in self._closed_markets if m.get("pnl", 0) > 0)
            losing = sum(1 for m in self._closed_markets if m.get("pnl", 0) < 0)
            breakeven = sum(1 for m in self._closed_markets if m.get("pnl", 0) == 0)
            total = len(self._closed_markets)
            
            return {
                "virtual_balance": self._virtual_balance,
                "starting_balance": self._starting_balance,
                "trade_count": self._paper_trade_count,
                "usdc_spent": self._paper_usdc_spent,
                "realized_pnl": self._paper_realized_pnl,
                "total_markets": total,
                "winning_markets": winning,
                "losing_markets": losing,
                "breakeven_markets": breakeven,
                "win_rate_pct": (winning / total * 100) if total > 0 else 0,
                "roi_pct": ((self._virtual_balance - self._starting_balance) / self._starting_balance * 100) if self._starting_balance > 0 else 0,
                "active_positions": len(self._positions)
            }
    
    def reset(self, starting_balance: float):
        """Reset the paper store to initial state."""
        with self._lock:
            self._virtual_balance = starting_balance
            self._starting_balance = starting_balance
            self._positions.clear()
            self._price_history.clear()
            self._market_meta.clear()
            self._paper_trade_count = 0
            self._paper_usdc_spent = 0.0
            self._paper_realized_pnl = 0.0
            self._closed_markets.clear()
            logger.info(f"Paper store reset with balance {starting_balance}")
    
    # Control flag methods (for compatibility with live store interface)
    def should_trade(self) -> bool:
        """Always returns True for paper trading."""
        return True
    
    def is_panic_mode(self) -> bool:
        """Always returns False for paper trading."""
        return False
    
    def is_trading_halted(self) -> bool:
        """Always returns False for paper trading."""
        return False
