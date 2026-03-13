"""Paper trading executor."""
import time
from typing import Optional

from strategy.decision import TradeDecision
from strategy.position import Position
from paper_trading.paper_clob import PaperCLOBClient
from paper_trading.paper_store import PaperStateStore
from paper_trading.paper_db import PaperDB
from telegram_bot.notifier import TelegramNotifier
from utils.logger import get_logger

logger = get_logger(__name__)


class PaperExecutor:
    """Executor for paper trading with same interface as live Executor."""
    
    def __init__(
        self,
        paper_clob: PaperCLOBClient,
        paper_store: PaperStateStore,
        paper_db: PaperDB,
        notifier: TelegramNotifier
    ):
        self.paper_clob = paper_clob
        self.paper_store = paper_store
        self.paper_db = paper_db
        self.notifier = notifier
    
    def execute(
        self,
        market: Dict,
        decision: TradeDecision,
        position: Position
    ) -> bool:
        """
        Execute a paper trade decision.
        
        Args:
            market: Market dictionary
            decision: Trade decision
            position: Current position
            
        Returns:
            True if executed successfully
        """
        if decision.action == "HOLD":
            return True
        
        market_id = market.get("market_id")
        token_id = market.get("up_token_id") if decision.action == "BUY_UP" else market.get("down_token_id")
        side = "BUY"
        
        try:
            # Check virtual balance
            cost = decision.shares * decision.price
            if self.paper_store.get_virtual_balance() < cost:
                logger.warning(f"Paper: Insufficient balance for {decision.action}")
                return False
            
            # Place paper order
            result = self.paper_clob.place_order(
                token_id=token_id,
                side=side,
                size=decision.shares,
                price=decision.price
            )
            
            order_id = result.get("orderID", "")
            
            # Update position
            if decision.action == "BUY_UP":
                position.apply_buy_up(decision.shares, decision.price, order_id)
            else:
                position.apply_buy_down(decision.shares, decision.price, order_id)
            
            # Record trade in store
            self.paper_store.record_paper_trade(
                market_id=market_id,
                side=decision.action,
                shares=decision.shares,
                price=decision.price,
                rule=decision.rule,
                reason=decision.reason
            )
            
            # Save trade to database
            session_id = self.paper_db.get_current_session_id()
            if session_id:
                self.paper_db.save_trade(
                    session_id=session_id,
                    market_id=market_id,
                    side=decision.action,
                    shares=decision.shares,
                    price=decision.price,
                    total_cost=cost,
                    rule=decision.rule,
                    reason=decision.reason
                )
            
            # Send notification
            trade_data = {
                "market_id": market_id,
                "question": market.get("question", ""),
                "side": decision.action,
                "shares": decision.shares,
                "price": decision.price,
                "cost": cost,
                "order_id": order_id,
                "rule": decision.rule,
                "virtual_balance_after": self.paper_store.get_virtual_balance(),
                "pnl_if_up": position.pnl_if_up_wins(),
                "pnl_if_down": position.pnl_if_down_wins()
            }
            self.notifier.send_paper_trade(trade_data)
            
            logger.info(f"Paper trade executed: {decision.action} {decision.shares} @ {decision.price}")
            return True
            
        except Exception as e:
            logger.error(f"Paper trade execution failed: {e}")
            return False
    
    def cancel_all_open_orders(self) -> int:
        """
        Cancel all open paper orders.
        
        Returns:
            Number of orders cancelled
        """
        result = self.paper_clob.cancel_all_orders()
        count = result.get("cancelled", 0)
        logger.info(f"Cancelled {count} paper orders")
        return count
