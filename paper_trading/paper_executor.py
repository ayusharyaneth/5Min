import logging
from datetime import datetime
from typing import Dict, List, Optional, Any, Union
from decimal import Decimal

logger = logging.getLogger(__name__)


class PaperExecutor:
    def __init__(self, 
                 initial_balance: float = 10000.0,
                 paper_clob: Any = None,
                 db=None,
                 notifier=None,
                 config: Optional[Dict] = None):
        """
        Initialize Paper Trading Executor
        
        Args:
            initial_balance: Starting balance for paper trading
            paper_clob: Paper Central Limit Order Book instance
            db: Database instance for trade logging
            notifier: Notification service (Telegram, etc.)
            config: Additional configuration dict
        """
        self.balance = float(initial_balance)
        self.initial_balance = float(initial_balance)
        self.positions: Dict[str, Dict] = {}
        self.trade_history: List[Dict] = []
        self.open_orders: List[Dict] = []
        self.db = db
        self.config = config or {}
        
        # Store paper_clob reference
        self.paper_clob = paper_clob
        
        # Lazy import for notifier to avoid circular imports
        self._notifier = notifier
        self._telegram_notifier = None
        
        logger.info(f"PaperExecutor initialized | Balance: ${initial_balance} | CLOB: {paper_clob is not None}")

    @property
    def notifier(self):
        """Lazy load Telegram notifier to prevent circular imports"""
        if self._telegram_notifier is None and self._notifier is None:
            try:
                from telegram_bot.notifier import TelegramNotifier
                self._telegram_notifier = TelegramNotifier()
            except Exception as e:
                logger.error(f"Failed to load TelegramNotifier: {e}")
                self._telegram_notifier = None
        return self._notifier or self._telegram_notifier

    def execute_trade(self, 
                     symbol: str, 
                     side: str, 
                     size: float, 
                     price: Optional[float] = None,
                     order_type: str = "MARKET",
                     metadata: Optional[Dict] = None) -> Dict:
        """
        Execute a paper trade
        
        Args:
            symbol: Trading pair symbol (e.g., 'BTC-USD')
            side: 'BUY' or 'SELL'
            size: Quantity to trade
            price: Limit price (optional for market orders)
            order_type: 'MARKET' or 'LIMIT'
            metadata: Additional trade data
            
        Returns:
            Trade execution result dict
        """
        timestamp = datetime.now()
        execution_price = price or self._get_market_price(symbol)
        total_value = size * execution_price
        
        # Validate funds for BUY
        if side.upper() == "BUY":
            if total_value > self.balance:
                error_msg = f"Insufficient balance: ${self.balance:.2f} < ${total_value:.2f}"
                logger.error(error_msg)
                return {"success": False, "error": error_msg, "symbol": symbol}
            
            self.balance -= total_value
            self._update_position(symbol, size, execution_price, side)
            
        elif side.upper() == "SELL":
            current_pos = self.positions.get(symbol, {}).get('quantity', 0)
            if current_pos < size:
                error_msg = f"Insufficient position: {current_pos} < {size}"
                logger.error(error_msg)
                return {"success": False, "error": error_msg, "symbol": symbol}
            
            self.balance += total_value
            self._update_position(symbol, -size, execution_price, side)
        else:
            return {"success": False, "error": f"Invalid side: {side}"}

        # Record trade
        trade_record = {
            "id": f"{symbol}_{timestamp.timestamp()}",
            "timestamp": timestamp,
            "symbol": symbol,
            "side": side.upper(),
            "size": size,
            "price": execution_price,
            "total_value": total_value,
            "balance_after": self.balance,
            "order_type": order_type,
            "metadata": metadata or {}
        }
        self.trade_history.append(trade_record)
        
        # Save to DB if available
        if self.db:
            try:
                self.db.save_trade(trade_record)
            except Exception as e:
                logger.error(f"Failed to save trade to DB: {e}")
        
        # Notify
        self._notify_trade(trade_record)
        
        logger.info(f"EXECUTED {side} {size} {symbol} @ ${execution_price:.2f} | Balance: ${self.balance:.2f}")
        
        return {"success": True, "trade": trade_record}

    def _update_position(self, symbol: str, quantity_change: float, price: float, side: str):
        """Update internal position tracking"""
        if symbol not in self.positions:
            self.positions[symbol] = {
                "quantity": 0,
                "avg_entry_price": 0,
                "total_cost": 0
            }
        
        pos = self.positions[symbol]
        
        if side.upper() == "BUY":
            # Update average entry price
            total_cost = pos["quantity"] * pos["avg_entry_price"]
            new_total_cost = total_cost + (abs(quantity_change) * price)
            new_quantity = pos["quantity"] + abs(quantity_change)
            
            if new_quantity > 0:
                pos["avg_entry_price"] = new_total_cost / new_quantity
            pos["quantity"] = new_quantity
            
        elif side.upper() == "SELL":
            pos["quantity"] -= abs(quantity_change)
            if pos["quantity"] <= 0:
                pos["avg_entry_price"] = 0
                pos["total_cost"] = 0

    def _get_market_price(self, symbol: str) -> float:
        """Get current market price - uses paper_clob if available"""
        if self.paper_clob and hasattr(self.paper_clob, 'get_price'):
            return float(self.paper_clob.get_price(symbol))
        
        # Fallback - you might want to integrate with your market data feed here
        logger.warning(f"No price source available for {symbol}, using 0")
        return 0.0

    def _notify_trade(self, trade: Dict):
        """Send trade notification"""
        if not self.notifier:
            return
            
        try:
            message = (
                f"📝 Paper Trade Executed\n"
                f"Symbol: {trade['symbol']}\n"
                f"Side: {trade['side']}\n"
                f"Size: {trade['size']}\n"
                f"Price: ${trade['price']:.2f}\n"
                f"Total: ${trade['total_value']:.2f}\n"
                f"Balance: ${trade['balance_after']:.2f}"
            )
            self.notifier.send_message(message)
        except Exception as e:
            logger.error(f"Failed to send trade notification: {e}")

    def get_position(self, symbol: str) -> Dict:
        """Get current position for a symbol"""
        return self.positions.get(symbol, {"quantity": 0, "avg_entry_price": 0})

    def get_portfolio_value(self, market_prices: Optional[Dict[str, float]] = None) -> Dict:
        """
        Calculate total portfolio value
        
        Returns:
            Dict with balance, positions_value, total_value, and unrealized_pnl
        """
        positions_value = 0.0
        unrealized_pnl = 0.0
        
        for symbol, pos in self.positions.items():
            if pos["quantity"] > 0:
                current_price = market_prices.get(symbol, self._get_market_price(symbol)) if market_prices else self._get_market_price(symbol)
                pos_value = pos["quantity"] * current_price
                positions_value += pos_value
                
                # Calculate unrealized PnL
                cost_basis = pos["quantity"] * pos["avg_entry_price"]
                unrealized_pnl += (pos_value - cost_basis)
        
        total_value = self.balance + positions_value
        
        return {
            "cash_balance": self.balance,
            "positions_value": positions_value,
            "total_value": total_value,
            "unrealized_pnl": unrealized_pnl,
            "total_return": total_value - self.initial_balance,
            "return_pct": ((total_value - self.initial_balance) / self.initial_balance * 100) if self.initial_balance else 0
        }

    def get_trade_history(self, limit: int = 100) -> List[Dict]:
        """Get recent trade history"""
        return self.trade_history[-limit:]

    def reset(self):
        """Reset paper trading account"""
        self.balance = self.initial_balance
        self.positions = {}
        self.trade_history = []
        self.open_orders = []
        logger.info("PaperExecutor reset to initial state")
