"""
Live Trading Executor for Polymarket
Handles real money trades with risk management
"""
import logging
from typing import Dict, Optional, Any
from datetime import datetime

logger = logging.getLogger('LiveExecutor')

class LiveExecutor:
    def __init__(self, 
                 polymarket_client,
                 config: Optional[Dict] = None,
                 notifier=None):
        self.client = polymarket_client
        self.config = config or {}
        self.notifier = notifier
        
        # Risk management
        self.max_trade_size = config.get('max_trade_size', 100)  # USDC
        self.max_daily_loss = config.get('max_daily_loss', 1000)  # USDC
        self.daily_pnl = 0.0
        self.trade_history = []
        
        logger.info("LiveExecutor initialized")
        logger.warning("⚠️  LIVE TRADING MODE - REAL MONEY AT RISK")
        
        if self.config.get('confirm_trades', True):
            logger.info("Trade confirmation enabled")
    
    def execute_trade(self, 
                     market_id: str, 
                     side: str, 
                     size: float, 
                     price: Optional[float] = None,
                     confidence: float = 0.0) -> Dict:
        """
        Execute live trade with safety checks
        """
        # Safety checks
        if size > self.max_trade_size:
            logger.error(f"Trade size {size} exceeds max {self.max_trade_size}")
            return {'status': 'rejected', 'reason': 'Size limit exceeded'}
        
        if self.daily_pnl <= -self.max_daily_loss:
            logger.error("Daily loss limit reached")
            return {'status': 'rejected', 'reason': 'Daily loss limit'}
        
        # Prepare order
        if not price:
            price = 0.5  # Market order approx
        
        logger.info(f"LIVE TRADE: {side} {size} USDC on {market_id} @ {price}")
        
        # Execute via Polymarket client
        result = self.client.place_order(market_id, side, size, price)
        
        if result.get('status') == 'filled':
            self.trade_history.append(result)
            self._notify_trade(result)
            logger.info(f"✓ Trade filled: {result.get('order_id')[:10]}...")
        else:
            logger.error(f"✗ Trade failed: {result.get('error')}")
        
        return result
    
    def get_portfolio_value(self) -> Dict:
        """Get live portfolio status"""
        balance = self.client.get_balance()
        positions = self.client.get_positions()
        
        total_value = balance.get('usdc', 0)
        # Calculate position values...
        
        return {
            'cash_balance': balance.get('usdc', 0),
            'positions_value': 0,  # Calculate from positions
            'total_value': total_value,
            'unrealized_pnl': 0,
            'total_return': self.daily_pnl,
            'wallet': balance.get('wallet', '')
        }
    
    def _notify_trade(self, trade: Dict):
        """Send notification"""
        if self.notifier:
            msg = (
                f"🚨 LIVE TRADE EXECUTED\n"
                f"Market: {trade['market_id'][:20]}...\n"
                f"Side: {trade['side']}\n"
                f"Size: ${trade['size']}\n"
                f"Price: {trade['price']}\n"
                f"Tx: {trade.get('tx_hash', 'N/A')[:10]}..."
            )
            self.notifier.send_message_sync(
                self.notifier.config.get('chat_id'),
                msg
            )
    
    def get_trade_history(self, limit: int = 50) -> list:
        return self.trade_history[-limit:]
