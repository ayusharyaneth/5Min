"""Paper trading CLOB client shim."""
import time
import uuid
from typing import Dict, List, Optional

from api.clob_client import CLOBClient
from paper_trading.paper_store import PaperStateStore
from utils.logger import get_logger

logger = get_logger(__name__)


class PaperCLOBClient:
    """
    Paper trading CLOB client.
    
    Price methods delegate to real CLOB client.
    Order methods are fully simulated.
    """
    
    def __init__(self, real_clob: CLOBClient, paper_store: PaperStateStore):
        self.real_clob = real_clob
        self.paper_store = paper_store
        self._open_orders: Dict[str, Dict] = {}
    
    # === Price methods - delegate to real CLOB ===
    def get_best_ask(self, token_id: str) -> float:
        """Get best ask from real CLOB."""
        return self.real_clob.get_best_ask(token_id)
    
    def get_order_book(self, token_id: str) -> Dict:
        """Get order book from real CLOB."""
        return self.real_clob.get_order_book(token_id)
    
    def get_market(self, market_id: str) -> Dict:
        """Get market from real CLOB."""
        return self.real_clob.get_market(market_id)
    
    def get_markets(self, params: Optional[Dict] = None) -> List[Dict]:
        """Get markets from real CLOB."""
        return self.real_clob.get_markets(params)
    
    # === Order methods - simulated ===
    def place_order(
        self,
        token_id: str,
        side: str,
        size: float,
        price: float
    ) -> Dict:
        """
        Simulate placing an order.
        
        Args:
            token_id: Token ID
            side: "BUY" or "SELL"
            size: Number of shares
            price: Price per share
            
        Returns:
            Simulated order response
        """
        cost = size * price
        
        # Check virtual balance
        if not self.paper_store.deduct_balance(cost):
            raise Exception("Paper: Insufficient virtual balance")
        
        # Generate paper order ID
        order_id = f"PAPER-{uuid.uuid4().hex[:12].upper()}"
        
        # Store order
        self._open_orders[order_id] = {
            "orderID": order_id,
            "token_id": token_id,
            "side": side,
            "size": size,
            "price": price,
            "placed_at": time.time()
        }
        
        logger.info(f"Paper order placed: {order_id} {side} {size} @ {price}")
        
        return {
            "orderID": order_id,
            "status": "MATCHED",
            "transactedAt": str(int(time.time())),
            "paper": True
        }
    
    def cancel_order(self, order_id: str) -> bool:
        """
        Cancel a paper order.
        
        Args:
            order_id: Order ID to cancel
            
        Returns:
            True if cancelled
        """
        if order_id in self._open_orders:
            order = self._open_orders.pop(order_id)
            # Refund the balance
            refund = order["size"] * order["price"]
            self.paper_store.credit_balance(refund)
            logger.info(f"Paper order cancelled: {order_id}, refunded {refund:.4f}")
            return True
        return False
    
    def cancel_all_orders(self) -> Dict:
        """
        Cancel all paper orders.
        
        Returns:
            Cancellation result
        """
        count = len(self._open_orders)
        for order in list(self._open_orders.values()):
            refund = order["size"] * order["price"]
            self.paper_store.credit_balance(refund)
        
        self._open_orders.clear()
        logger.info(f"All paper orders cancelled: {count} orders")
        return {"cancelled": count}
    
    def get_open_orders(self) -> List[Dict]:
        """
        Get all open paper orders.
        
        Returns:
            List of open orders
        """
        return list(self._open_orders.values())
    
    def get_wallet_balance(self) -> Dict:
        """
        Get virtual wallet balance.
        
        Returns:
            Balance dictionary
        """
        return {"balance": self.paper_store.get_virtual_balance()}
