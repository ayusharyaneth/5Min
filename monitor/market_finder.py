import logging
import asyncio
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime

logger = logging.getLogger(__name__)


class MarketFinder:
    def __init__(self, 
                 clob: Any = None,
                 store: Any = None,
                 db: Any = None,
                 notifier: Any = None,
                 config: Optional[Dict] = None,
                 paper_executor: Any = None,
                 **kwargs):
        """
        Initialize MarketFinder with dependency injection
        
        Args:
            clob: Central Limit Order Book instance for market data
            store: Data storage/persistence layer
            db: Database connection
            notifier: Notification service (Telegram, etc.)
            config: Configuration dictionary
            paper_executor: Reference to paper trading executor
            **kwargs: Additional keyword arguments for future extensibility
        """
        self.config = config or {}
        self.opportunities: List[Dict] = []
        self.active_monitors: Dict[str, Any] = {}
        self.is_running = False
        
        # Store injected dependencies
        self.clob = clob
        self.store = store
        self.db = db
        self._external_notifier = notifier
        self.paper_executor = paper_executor
        
        # Handle any extra kwargs
        for key, value in kwargs.items():
            setattr(self, key, value)
            logger.debug(f"MarketFinder stored extra param: {key}")
        
        # Lazy import for notifier to avoid circular imports
        self._telegram_notifier = None
        
        logger.info(f"MarketFinder initialized | CLOB: {clob is not None} | "
                   f"Store: {store is not None} | DB: {db is not None}")

    @property
    def notifier(self):
        """Lazy load Telegram notifier to prevent circular imports"""
        if self._telegram_notifier is None and self._external_notifier is None:
            try:
                from telegram_bot.notifier import TelegramNotifier
                self._telegram_notifier = TelegramNotifier()
            except Exception as e:
                logger.error(f"Failed to load TelegramNotifier: {e}")
                self._telegram_notifier = None
        return self._external_notifier or self._telegram_notifier

    def find_active_btc_5m_markets(self) -> List[Dict]:
        """
        Find active Bitcoin 5-minute prediction markets.
        Returns list of market dictionaries with market_id, symbol, expiry, etc.
        """
        markets = []
        
        try:
            # Try to get from CLOB if available
            if self.clob and hasattr(self.clob, 'get_active_markets'):
                try:
                    all_markets = self.clob.get_active_markets()
                    # Filter for BTC 5m markets
                    markets = [
                        m for m in all_markets 
                        if m.get('base_asset', '').upper() in ['BTC', 'bitcoin', 'XBT']
                        and '5m' in m.get('timeframe', '').lower()
                        or m.get('duration') == 300  # 5 minutes in seconds
                    ]
                    logger.info(f"Found {len(markets)} BTC 5m markets from CLOB")
                    return markets
                except Exception as e:
                    logger.error(f"Error fetching from CLOB: {e}")
            
            # Try store if CLOB failed or unavailable
            if self.store and hasattr(self.store, 'get_markets'):
                try:
                    all_markets = self.store.get_markets(
                        filters={'base_asset': 'BTC', 'timeframe': '5m', 'status': 'active'}
                    )
                    markets = all_markets
                    logger.info(f"Found {len(markets)} BTC 5m markets from store")
                    return markets
                except Exception as e:
                    logger.error(f"Error fetching from store: {e}")
            
            # Fallback: Return empty list or mock data for testing
            logger.warning("No CLOB or store available for market discovery, returning empty list")
            return []
            
        except Exception as e:
            logger.error(f"Error in find_active_btc_5m_markets: {e}")
            return []
    
    def find_active_eth_5m_markets(self) -> List[Dict]:
        """Find active Ethereum 5-minute markets (convenience method)"""
        markets = []
        
        try:
            # Try to get from CLOB if available
            if self.clob and hasattr(self.clob, 'get_active_markets'):
                try:
                    all_markets = self.clob.get_active_markets()
                    # Filter for ETH 5m markets
                    markets = [
                        m for m in all_markets 
                        if m.get('base_asset', '').upper() in ['ETH', 'ethereum', 'ETHER']
                        and ('5m' in m.get('timeframe', '').lower() or m.get('duration') == 300)
                    ]
                    logger.info(f"Found {len(markets)} ETH 5m markets from CLOB")
                    return markets
                except Exception as e:
                    logger.error(f"Error fetching ETH markets from CLOB: {e}")
            
            # Try store if CLOB failed or unavailable
            if self.store and hasattr(self.store, 'get_markets'):
                try:
                    all_markets = self.store.get_markets(
                        filters={'base_asset': 'ETH', 'timeframe': '5m', 'status': 'active'}
                    )
                    markets = all_markets
                    logger.info(f"Found {len(markets)} ETH 5m markets from store")
                    return markets
                except Exception as e:
                    logger.error(f"Error fetching ETH markets from store: {e}")
            
            logger.warning("No CLOB or store available for ETH market discovery, returning empty list")
            return []
            
        except Exception as e:
            logger.error(f"Error in find_active_eth_5m_markets: {e}")
            return []

    def find_opportunities(self, symbols: List[str], 
                          min_confidence: float = 0.7,
                          strategy: str = "default") -> List[Dict]:
        """
        Scan for trading opportunities and notify
        
        Args:
            symbols: List of symbols to analyze
            min_confidence: Minimum confidence threshold (0-1)
            strategy: Trading strategy to use
            
        Returns:
            List of opportunity dictionaries
        """
        opportunities = []
        
        for symbol in symbols:
            try:
                # Analyze symbol using CLOB data if available
                opportunity = self._analyze_symbol(symbol, strategy)
                
                if opportunity and opportunity.get('confidence', 0) >= min_confidence:
                    opportunities.append(opportunity)
                    
                    # Persist opportunity if store available
                    if self.store and hasattr(self.store, 'save_opportunity'):
                        try:
                            self.store.save_opportunity(opportunity)
                        except Exception as e:
                            logger.error(f"Failed to save opportunity to store: {e}")
                    
                    # Notify via Telegram
                    try:
                        if self.notifier:
                            if hasattr(self.notifier, 'send_opportunity_alert'):
                                self.notifier.send_opportunity_alert(opportunity)
                            elif hasattr(self.notifier, 'send_message'):
                                msg = (f"🔍 Opportunity Found\n"
                                      f"Symbol: {opportunity.get('symbol')}\n"
                                      f"Signal: {opportunity.get('signal')}\n"
                                      f"Confidence: {opportunity.get('confidence', 0):.2%}")
                                self.notifier.send_message(msg)
                    except Exception as e:
                        logger.error(f"Failed to send notification: {e}")
                    
                    # Auto-execute if paper_executor available and auto_trade enabled
                    if (self.paper_executor and 
                        self.config.get('auto_trade', False) and
                        opportunity.get('auto_execute')):
                        self._execute_opportunity(opportunity)
                        
            except Exception as e:
                logger.error(f"Error analyzing {symbol}: {e}")
                continue
        
        self.opportunities = opportunities
        return opportunities

    def _analyze_symbol(self, symbol: str, strategy: str = "default") -> Optional[Dict]:
        """
        Analyze a single symbol for opportunities
        
        Uses CLOB data if available, otherwise uses store or external feeds
        """
        timestamp = datetime.now()
        
        try:
            # Get market data from CLOB if available
            market_data = None
            if self.clob and hasattr(self.clob, 'get_orderbook'):
                market_data = self.clob.get_orderbook(symbol)
            elif self.clob and hasattr(self.clob, 'get_ticker'):
                market_data = self.clob.get_ticker(symbol)
            elif self.store and hasattr(self.store, 'get_market_data'):
                market_data = self.store.get_market_data(symbol)
            
            if not market_data:
                logger.debug(f"No market data available for {symbol}")
                return None
            
            # Run analysis based on strategy
            if strategy == "arbitrage":
                signal = self._check_arbitrage(symbol, market_data)
            elif strategy == "momentum":
                signal = self._check_momentum(symbol, market_data)
            else:
                signal = self._check_default_strategy(symbol, market_data)
            
            if signal and signal.get('found'):
                return {
                    'symbol': symbol,
                    'signal': signal.get('side', 'BUY'),
                    'confidence': signal.get('confidence', 0.5),
                    'expected_profit': signal.get('expected_profit', 0),
                    'timestamp': timestamp,
                    'market_data': market_data,
                    'strategy': strategy,
                    'auto_execute': signal.get('auto_execute', False)
                }
            
            return None
            
        except Exception as e:
            logger.error(f"Error in _analyze_symbol for {symbol}: {e}")
            return None

    def _check_arbitrage(self, symbol: str, market_data: Dict) -> Optional[Dict]:
        """Check for arbitrage opportunities"""
        # Your arbitrage logic here
        return None

    def _check_momentum(self, symbol: str, market_data: Dict) -> Optional[Dict]:
        """Check for momentum signals"""
        # Your momentum logic here
        return None

    def _check_default_strategy(self, symbol: str, market_data: Dict) -> Optional[Dict]:
        """Default analysis strategy"""
        # Example implementation - replace with your actual logic
        try:
            # Simple example: check if spread is favorable
            bid = market_data.get('bid', 0)
            ask = market_data.get('ask', 0)
            
            if bid > 0 and ask > 0:
                spread = (ask - bid) / ((ask + bid) / 2)
                if spread < 0.001:  # Tight spread
                    return {
                        'found': True,
                        'side': 'BUY',
                        'confidence': 0.8,
                        'expected_profit': 0.01
                    }
            return {'found': False}
        except Exception as e:
            logger.error(f"Error in default strategy: {e}")
            return {'found': False}

    def _execute_opportunity(self, opportunity: Dict):
        """Execute trade via paper_executor if available"""
        if not self.paper_executor:
            return
            
        try:
            symbol = opportunity['symbol']
            side = opportunity['signal']
            size = self.config.get('default_trade_size', 1.0)
            
            if hasattr(self.paper_executor, 'execute_trade'):
                result = self.paper_executor.execute_trade(
                    symbol=symbol,
                    side=side,
                    size=size,
                    metadata={'source': 'market_finder_auto', 'confidence': opportunity.get('confidence')}
                )
                logger.info(f"Auto-executed trade: {result}")
            else:
                logger.warning("PaperExecutor missing execute_trade method")
                
        except Exception as e:
            logger.error(f"Failed to auto-execute opportunity: {e}")

    def scan_markets(self, market_type: str = "crypto", 
                    symbols: Optional[List[str]] = None) -> List[Dict]:
        """
        Scan specific market type
        
        Args:
            market_type: Type of market (crypto, stocks, forex, etc.)
            symbols: Specific symbols to scan, or None for all available
            
        Returns:
            List of opportunities found
        """
        logger.info(f"Scanning {market_type} markets")
        
        # Get symbols from CLOB if not provided
        if not symbols and self.clob and hasattr(self.clob, 'get_symbols'):
            try:
                symbols = self.clob.get_symbols()
            except Exception as e:
                logger.error(f"Failed to get symbols from CLOB: {e}")
                symbols = []
        
        if not symbols:
            logger.warning(f"No symbols available for {market_type}")
            return []
        
        return self.find_opportunities(symbols)

    def start_monitoring(self, symbols: List[str], interval: int = 60):
        """
        Start continuous monitoring of markets
        
        Args:
            symbols: List of symbols to monitor
            interval: Check interval in seconds
        """
        self.is_running = True
        self.active_monitors['main'] = {
            'symbols': symbols,
            'interval': interval,
            'started_at': datetime.now()
        }
        logger.info(f"Started monitoring {len(symbols)} symbols every {interval}s")

    async def run_async(self, symbols: List[str], interval: int = 60):
        """Async loop for continuous monitoring"""
        self.start_monitoring(symbols, interval)
        
        while self.is_running:
            try:
                self.find_opportunities(symbols)
                await asyncio.sleep(interval)
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
                await asyncio.sleep(5)  # Short sleep on error

    def stop_monitoring(self):
        """Stop the monitoring loop"""
        self.is_running = False
        self.active_monitors.clear()
        logger.info("MarketFinder monitoring stopped")

    def get_opportunities_history(self, limit: int = 100) -> List[Dict]:
        """Get history of found opportunities"""
        if self.store and hasattr(self.store, 'get_opportunities'):
            try:
                return self.store.get_opportunities(limit)
            except Exception as e:
                logger.error(f"Failed to get opportunities from store: {e}")
        
        return self.opportunities[-limit:] if self.opportunities else []

    def update_config(self, new_config: Dict):
        """Update configuration dynamically"""
        self.config.update(new_config)
        logger.info(f"Updated MarketFinder config: {new_config.keys()}")
