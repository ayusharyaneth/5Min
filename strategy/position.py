"""Position and OpenOrder dataclasses."""
from dataclasses import dataclass, field
from typing import List, Optional
import time


@dataclass
class OpenOrder:
    """Represents an open order."""
    order_id: str
    side: str
    shares: float
    price: float
    placed_at: float


@dataclass
class Position:
    """Represents a trading position in a binary market."""
    market_id: str
    question: str = ""
    up_shares: float = 0.0
    up_total_cost: float = 0.0
    down_shares: float = 0.0
    down_total_cost: float = 0.0
    trades: List[dict] = field(default_factory=list)
    open_orders: List[OpenOrder] = field(default_factory=list)
    
    @property
    def up_avg_price(self) -> float:
        """Average price of UP shares."""
        if self.up_shares > 0:
            return self.up_total_cost / self.up_shares
        return 0.0
    
    @property
    def down_avg_price(self) -> float:
        """Average price of DOWN shares."""
        if self.down_shares > 0:
            return self.down_total_cost / self.down_shares
        return 0.0
    
    @property
    def total_cost(self) -> float:
        """Total cost of position."""
        return self.up_total_cost + self.down_total_cost
    
    def pnl_if_up_wins(self) -> float:
        """PnL if UP side wins."""
        return self.up_shares - self.total_cost
    
    def pnl_if_down_wins(self) -> float:
        """PnL if DOWN side wins."""
        return self.down_shares - self.total_cost
    
    def unrealized_pnl(self, up_px: float, dn_px: float) -> float:
        """Unrealized PnL given current prices."""
        return self.up_shares * up_px + self.down_shares * dn_px - self.total_cost
    
    def cost_per_pair_if_add_up(self, n: float, up_ask: float) -> float:
        """Calculate cost per pair if adding UP shares."""
        new_up_cost = self.up_total_cost + n * up_ask
        new_up_shares = self.up_shares + n
        min_shares = min(new_up_shares, self.down_shares)
        if min_shares > 0:
            return (new_up_cost + self.down_total_cost) / min_shares
        return 0.0
    
    def cost_per_pair_if_add_down(self, n: float, dn_ask: float) -> float:
        """Calculate cost per pair if adding DOWN shares."""
        new_down_cost = self.down_total_cost + n * dn_ask
        new_down_shares = self.down_shares + n
        min_shares = min(self.up_shares, new_down_shares)
        if min_shares > 0:
            return (self.up_total_cost + new_down_cost) / min_shares
        return 0.0
    
    def apply_buy_up(self, n: float, price: float, order_id: str = ""):
        """Apply a BUY_UP trade to the position."""
        self.up_shares += n
        self.up_total_cost += n * price
        self.trades.append({
            "side": "BUY_UP",
            "shares": n,
            "price": price,
            "cost": n * price,
            "order_id": order_id,
            "timestamp": time.time()
        })
    
    def apply_buy_down(self, n: float, price: float, order_id: str = ""):
        """Apply a BUY_DOWN trade to the position."""
        self.down_shares += n
        self.down_total_cost += n * price
        self.trades.append({
            "side": "BUY_DOWN",
            "shares": n,
            "price": price,
            "cost": n * price,
            "order_id": order_id,
            "timestamp": time.time()
        })
    
    def add_open_order(self, order: OpenOrder):
        """Add an open order."""
        self.open_orders.append(order)
    
    def remove_open_order(self, order_id: str) -> bool:
        """Remove an open order by ID. Returns True if found."""
        for i, order in enumerate(self.open_orders):
            if order.order_id == order_id:
                self.open_orders.pop(i)
                return True
        return False
    
    def get_all_order_ids(self) -> List[str]:
        """Get all open order IDs."""
        return [o.order_id for o in self.open_orders]
    
    def has_up_position(self) -> bool:
        """Check if has UP position."""
        return self.up_shares > 0
    
    def has_down_position(self) -> bool:
        """Check if has DOWN position."""
        return self.down_shares > 0
    
    def has_both_sides(self) -> bool:
        """Check if has positions on both sides."""
        return self.up_shares > 0 and self.down_shares > 0
    
    def has_any_position(self) -> bool:
        """Check if has any position."""
        return self.up_shares > 0 or self.down_shares > 0
    
    def get_dominant_side(self) -> Optional[str]:
        """Get the dominant side (more shares)."""
        if self.up_shares > self.down_shares:
            return "up"
        elif self.down_shares > self.up_shares:
            return "down"
        return None
