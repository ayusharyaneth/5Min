import logging
from datetime import datetime
from typing import Dict, List, Optional
# ... other imports ...

# REMOVE THIS LINE (or comment out):
# from telegram_bot.notifier import TelegramNotifier

logger = logging.getLogger(__name__)


class PaperExecutor:
    def __init__(self, initial_balance: float = 10000.0):
        self.balance = initial_balance
        self.positions = {}
        self.trade_history = []
        
        # LAZY IMPORT: Import moved inside __init__ to break circular dependency
        from telegram_bot.notifier import TelegramNotifier
        self.notifier = TelegramNotifier()
        
        logger.info(f"PaperExecutor initialized with balance: ${initial_balance}")

    def execute_trade(self, symbol: str, action: str, quantity: float, price: float):
        """Execute a paper trade and notify via Telegram"""
        trade_value = quantity * price
        
        if action == "BUY":
            if trade_value > self.balance:
                logger.error(f"Insufficient balance: {self.balance} < {trade_value}")
                return False
            self.balance -= trade_value
            self.positions[symbol] = self.positions.get(symbol, 0) + quantity
            
        elif action == "SELL":
            if symbol not in self.positions or self.positions[symbol] < quantity:
                logger.error(f"Insufficient position for {symbol}")
                return False
            self.balance += trade_value
            self.positions[symbol] -= quantity
            
        # Record trade
        trade = {
            "timestamp": datetime.now(),
            "symbol": symbol,
            "action": action,
            "quantity": quantity,
            "price": price,
            "value": trade_value
        }
        self.trade_history.append(trade)
        
        # Notify via Telegram (self.notifier already initialized)
        try:
            self.notifier.send_trade_notification(trade)
        except Exception as e:
            logger.error(f"Failed to send Telegram notification: {e}")
            
        logger.info(f"Executed {action} {quantity} {symbol} @ ${price}")
        return True

    def get_portfolio_value(self, current_prices: Dict[str, float]) -> float:
        """Calculate total portfolio value"""
        position_value = sum(
            qty * current_prices.get(sym, 0) 
            for sym, qty in self.positions.items()
        )
        return self.balance + position_value
