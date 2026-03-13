import logging
import asyncio
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
from dataclasses import dataclass

logger = logging.getLogger(__name__)


class ClosureChecker:
    def __init__(self,
                 clob: Any = None,
                 store: Any = None,
                 db: Any = None,
                 notifier: Any = None,
                 config: Optional[Dict] = None,
                 paper_executor: Any = None,
                 **kwargs):
        """
        Initialize ClosureChecker with dependency injection.
        
        Args:
            clob: Central Limit Order Book for real-time market data
            store: Persistence layer for state management
            db: Database connection for recording settlements
            notifier: Notification service (Telegram, etc.)
            config: Configuration dictionary
            paper_executor: Paper trading executor reference
            **kwargs: Additional arguments for future extensibility
        """
        self.config = config or {}
        self.clob = clob
        self.store = store
        self.db = db
        self._external_notifier = notifier
        self.paper_executor = paper_executor
        
        # Handle legacy db_connection kwarg if passed via kwargs
        if 'db_connection' in kwargs and not self.db:
            self.db = kwargs.pop('db_connection')
        
        # Store any additional kwargs as attributes
        for key, value in kwargs.items():
            setattr(self, key, value)
            
        self.active_markets: Dict[str, Dict] = {}
        self.check_interval = self.config.get('check_interval', 60)
        self.is_running = False
        
        # Lazy import for notifier to prevent circular imports
        self._telegram_notifier = None
        
        logger.info(f"ClosureChecker initialized | CLOB: {clob is not None} | "
                   f"Store: {store is not None} | DB: {db is not None}")

    @property
    def notifier(self):
        """Lazy load notifier to prevent circular imports"""
        if self._telegram_notifier is None and self._external_notifier is None:
            try:
                from telegram_bot.notifier import TelegramNotifier
                self._telegram_notifier = TelegramNotifier()
            except Exception as e:
                logger.error(f"Failed to load TelegramNotifier: {e}")
                self._telegram_notifier = None
        return self._external_notifier or self._telegram_notifier

    def check_closure(self, market_id: str) -> bool:
        """
        Check if a specific market has closed.
        Uses CLOB data if available, falls back to store or internal state.
        """
        try:
            # Try CLOB first for real-time status
            if self.clob and hasattr(self.clob, 'get_market_status'):
                try:
                    status = self.clob.get_market_status(market_id)
                    return status.get('status') == 'closed' or status.get('closed', False)
                except Exception as e:
                    logger.debug(f"CLOB status check failed: {e}")
                
                # Alternative CLOB method names
                if hasattr(self.clob, 'is_market_closed'):
                    return self.clob.is_market_closed(market_id)
            
            # Try Store next
            if self.store and hasattr(self.store, 'get_market_status'):
                try:
                    status = self.store.get_market_status(market_id)
                    return status.get('status') == 'closed'
                except Exception as e:
                    logger.debug(f"Store status check failed: {e}")
            
            # Fallback to internal tracking
            market = self.active_markets.get(market_id, {})
            return market.get('status') == 'closed'
            
        except Exception as e:
            logger.error(f"Error checking closure for {market_id}: {e}")
            return False

    def _settle_live_position(self, market_id: str, market: Dict, winner: str):
        """
        Settle a live position based on market outcome.
        
        Args:
            market_id: Unique identifier for the market
            market: Market data dictionary containing position details
            winner: The winning outcome/result
        """
        try:
            logger.info(f"Settling position for {market_id}, winner: {winner}")
            
            # Extract position details
            position_size = market.get('position_size', 0)
            entry_price = market.get('entry_price', 0)
            
            # Calculate PnL
            pnl = self._calculate_pnl(market, winner)
            
            # Create settlement record
            settlement_record = {
                "market_id": market_id,
                "winner": winner,
                "pnl": pnl,
                "settled_at": datetime.now().isoformat(),
                "position_size": position_size,
                "entry_price": entry_price,
                "market_data": market
            }
            
            # Save to database if available
            if self.db and hasattr(self.db, 'record_settlement'):
                try:
                    self.db.record_settlement(settlement_record)
                    logger.debug(f"Recorded settlement to DB for {market_id}")
                except Exception as e:
                    logger.error(f"Failed to record settlement to DB: {e}")
            
            # Save to store if available
            if self.store and hasattr(self.store, 'save_settlement'):
                try:
                    self.store.save_settlement(settlement_record)
                    logger.debug(f"Saved settlement to store for {market_id}")
                except Exception as e:
                    logger.error(f"Failed to save settlement to store: {e}")
            
            # Send notification
            if self.notifier:
                try:
                    if hasattr(self.notifier, 'send_closure_notification'):
                        self.notifier.send_closure_notification(
                            market_id=market_id,
                            winner=winner,
                            pnl=pnl,
                            details=market
                        )
                    elif hasattr(self.notifier, 'send_message'):
                        message = (
                            f"🔒 Market Closed: {market_id}\n"
                            f"Winner: {winner}\n"
                            f"PnL: ${pnl:,.2f}\n"
                            f"Settled at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                        )
                        self.notifier.send_message(message)
                except Exception as e:
                    logger.error(f"Failed to send closure notification: {e}")
            
            # Update paper executor if linked
            if self.paper_executor and hasattr(self.paper_executor, 'settle_position'):
                try:
                    self.paper_executor.settle_position(market_id, pnl, winner)
                except Exception as e:
                    logger.error(f"Failed to update paper executor: {e}")
            
            logger.info(f"Position settled for {market_id}. PnL: ${pnl:,.2f}")
            
        except Exception as e:
            logger.error(f"Critical error settling position {market_id}: {e}")
            raise

    def _calculate_pnl(self, market: Dict, winner: str) -> float:
        """Calculate profit/loss for a settled market"""
        try:
            position = market.get('position', {})
            if not position:
                position = market  # Assume market dict contains position directly
            
            entry_price = float(position.get('entry_price', 0))
            size = float(position.get('size', position.get('quantity', 0)))
            side = position.get('side', '').upper()
            
            # Get exit/settlement price
            exit_price = market.get('settlement_price', 0)
            if not exit_price and market.get('final_price'):
                exit_price = float(market['final_price'])
            
            # Try to get from CLOB if not in market data
            if not exit_price and self.clob and hasattr(self.clob, 'get_last_price'):
                try:
                    symbol = market.get('symbol', market.get('market_id'))
                    exit_price = float(self.clob.get_last_price(symbol))
                except Exception as e:
                    logger.debug(f"Could not get exit price from CLOB: {e}")
            
            if entry_price <= 0 or size <= 0 or exit_price <= 0:
                logger.warning(f"Invalid prices for PnL calc: entry={entry_price}, exit={exit_price}, size={size}")
                return 0.0
            
            if side == 'BUY':
                return (exit_price - entry_price) * size
            elif side == 'SELL':
                return (entry_price - exit_price) * size
            else:
                logger.warning(f"Unknown side for PnL calc: {side}")
                return 0.0
                
        except Exception as e:
            logger.error(f"Error calculating PnL: {e}")
            return 0.0

    def get_market_status(self, market_id: str) -> Dict:
        """Get comprehensive status of a market from all available sources"""
        status = {
            "market_id": market_id,
            "status": "unknown",
            "timestamp": datetime.now().isoformat(),
            "sources": []
        }
        
        # Try CLOB
        if self.clob:
            try:
                if hasattr(self.clob, 'get_market_info'):
                    clob_data = self.clob.get_market_info(market_id)
                    status.update(clob_data)
                    status['sources'].append('clob')
                elif hasattr(self.clob, 'get_market_status'):
                    clob_data = self.clob.get_market_status(market_id)
                    status.update(clob_data)
                    status['sources'].append('clob')
            except Exception as e:
                logger.debug(f"Could not get CLOB data: {e}")
        
        # Try Store
        if self.store:
            try:
                if hasattr(self.store, 'get_market_data'):
                    store_data = self.store.get_market_data(market_id)
                    status.update(store_data)
                    status['sources'].append('store')
            except Exception as e:
                logger.debug(f"Could not get store data: {e}")
        
        # Merge with internal state
        if market_id in self.active_markets:
            status.update(self.active_markets[market_id])
            status['sources'].append('internal')
        
        return status

    def _determine_winner(self, market: Dict) -> str:
        """Determine the winning outcome of a market"""
        # Check explicit outcome first
        if 'outcome' in market:
            return market['outcome']
        if 'winner' in market:
            return market['winner']
        if 'result' in market:
            return market['result']
        
        # Try to determine from CLOB settlement data
        if self.clob and hasattr(self.clob, 'get_settlement_result'):
            try:
                return self.clob.get_settlement_result(market.get('market_id'))
            except Exception as e:
                logger.debug(f"Could not get settlement from CLOB: {e}")
        
        return 'unknown'

    def add_market(self, market_id: str, market_data: Dict):
        """Add a market to active monitoring"""
        self.active_markets[market_id] = {
            **market_data,
            'market_id': market_id,
            'added_at': datetime.now(),
            'status': 'active',
            'check_count': 0
        }
        logger.info(f"Added market {market_id} to closure monitoring")

    def remove_market(self, market_id: str):
        """Remove a market from monitoring"""
        if market_id in self.active_markets:
            del self.active_markets[market_id]
            logger.info(f"Removed market {market_id} from monitoring")

    async def run(self):
        """Main loop to check for market closures"""
        self.is_running = True
        logger.info(f"ClosureChecker monitoring started (interval: {self.check_interval}s)")
        
        while self.is_running:
            try:
                # Check all active markets
                markets_to_remove = []
                
                for market_id, market in list(self.active_markets.items()):
                    market['check_count'] = market.get('check_count', 0) + 1
                    
                    if self.check_closure(market_id):
                        winner = self._determine_winner(market)
                        self._settle_live_position(market_id, market, winner)
                        markets_to_remove.append(market_id)
                
                # Remove settled markets
                for mid in markets_to_remove:
                    self.active_markets.pop(mid, None)
                
                await asyncio.sleep(self.check_interval)
                
            except Exception as e:
                logger.error(f"Error in closure check loop: {e}")
                await asyncio.sleep(5)  # Shorter sleep on error
        
        logger.info("ClosureChecker monitoring stopped")

    def stop(self):
        """Stop the monitoring loop"""
        self.is_running = False

    def get_active_markets(self) -> List[str]:
        """Return list of actively monitored market IDs"""
        return list(self.active_markets.keys())

    def get_settlement_history(self, limit: int = 100) -> List[Dict]:
        """Get history of settled markets from store/db"""
        history = []
        
        if self.store and hasattr(self.store, 'get_settlements'):
            try:
                history = self.store.get_settlements(limit)
            except Exception as e:
                logger.error(f"Failed to get settlements from store: {e}")
        
        if not history and self.db and hasattr(self.db, 'get_settlements'):
            try:
                history = self.db.get_settlements(limit)
            except Exception as e:
                logger.error(f"Failed to get settlements from DB: {e}")
        
        return history
