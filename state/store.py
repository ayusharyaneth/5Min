"""Live trading state store with thread-safe operations."""
import threading
import time
from collections import deque
from typing import Dict, List, Optional, Any

from utils.logger import get_logger

logger = get_logger(__name__)


class StateStore:
    """Thread-safe state store for live trading."""
    
    def __init__(self, trend_window: int):
        self._lock = threading.RLock()
        self._trend_window = trend_window
        
        # Positions: market_id -> Position
        self._positions: Dict[str, Any] = {}
        
        # Price history: market_id -> {"up": deque, "down": deque}
        self._price_history: Dict[str, Dict[str, deque]] = {}
        
        # Market metadata: market_id -> market info dict
        self._market_meta: Dict[str, Dict] = {}
        
        # Trading statistics
        self._trade_count = 0
        self._usdc_spent_today = 0.0
        self._daily_realized_pnl = 0.0
        self._start_time = time.time()
        
        # Control flags
        self._panic_mode = False
        self._trading_halted = False
    
    def _ensure_price_history(self, market_id: str):
        """Ensure price history exists for a market."""
        if market_id not in self._price_history:
            self._price_history[market_id] = {
                "up": deque(maxlen=self._trend_window * 2),
                "down": deque(maxlen=self._trend_window * 2)
            }
    
    # Position methods
    def get_position(self, market_id: str) -> Optional[Any]:
        """Get position for a market."""
        with self._lock:
            return self._positions.get(market_id)
    
    def set_position(self, market_id: str, position: Any):
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
    
    # Trading statistics methods
    def increment_trade_count(self):
        """Increment trade counter."""
        with self._lock:
            self._trade_count += 1
    
    def add_usdc_spent(self, amount: float):
        """Add to USDC spent today."""
        with self._lock:
            self._usdc_spent_today += amount
    
    def add_realized_pnl(self, pnl: float):
        """Add to daily realized PnL."""
        with self._lock:
            self._daily_realized_pnl += pnl
    
    def get_trade_count(self) -> int:
        """Get total trade count."""
        with self._lock:
            return self._trade_count
    
    def get_usdc_spent(self) -> float:
        """Get total USDC spent today."""
        with self._lock:
            return self._usdc_spent_today
    
    def get_daily_realized_pnl(self) -> float:
        """Get daily realized PnL."""
        with self._lock:
            return self._daily_realized_pnl
    
    def get_stats(self) -> Dict:
        """Get trading statistics."""
        with self._lock:
            return {
                "trade_count": self._trade_count,
                "usdc_spent_today": self._usdc_spent_today,
                "daily_realized_pnl": self._daily_realized_pnl,
                "uptime_seconds": time.time() - self._start_time,
                "panic_mode": self._panic_mode,
                "trading_halted": self._trading_halted,
                "active_positions": len(self._positions)
            }
    
    # Control flag methods
    def set_panic_mode(self, panic: bool):
        """Set panic mode flag."""
        with self._lock:
            self._panic_mode = panic
            logger.warning(f"Panic mode set to: {panic}")
    
    def is_panic_mode(self) -> bool:
        """Check if in panic mode."""
        with self._lock:
            return self._panic_mode
    
    def set_trading_halted(self, halted: bool):
        """Set trading halted flag."""
        with self._lock:
            self._trading_halted = halted
            logger.warning(f"Trading halted set to: {halted}")
    
    def is_trading_halted(self) -> bool:
        """Check if trading is halted."""
        with self._lock:
            return self._trading_halted
    
    def should_trade(self) -> bool:
        """Check if trading should proceed (not panic and not halted)."""
        with self._lock:
            return not self._panic_mode and not self._trading_halted
    
    def reset_daily_stats(self):
        """Reset daily statistics."""
        with self._lock:
            self._usdc_spent_today = 0.0
            self._daily_realized_pnl = 0.0
            self._trade_count = 0
            self._start_time = time.time()
            logger.info("Daily stats reset")
