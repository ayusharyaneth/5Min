"""
Market Finder - Updated for Polymarket Live Trading Only
Removed: Shimmer/Paper references
"""

import logging
from typing import Dict, List, Optional, Any
from datetime import datetime

logger = logging.getLogger('MarketFinder')

class MarketFinder:
    def __init__(self, 
                 polymarket_client=None,  # Changed from clob
                 config: Optional[Dict] = None,
                 live_executor=None):      # Changed from paper_executor
        """
        Market Finder for Polymarket Live Trading
        """
        self.config = config or {}
        self.client = polymarket_client  # Polymarket client directly
        self.live_executor = live_executor
        self.active_monitors = {}
        
        # Trading parameters
        self.min_confidence = config.get('min_confidence', 0.75)
        self.auto_trade = config.get('live_auto_trade', False)
        
        logger.info("📊 MarketFinder initialized (Polymarket mode)")

    def find_active_btc_5m_markets(self) -> List[Dict]:
        """
        Find active 5-minute BTC prediction markets on Polymarket
        """
        if not self.client:
            logger.error("❌ No Polymarket client available")
            return []
        
        try:
            # Use Polymarket client to fetch markets
            if hasattr(self.client, 'get_active_markets'):
                markets = self.client.get_active_markets()
                
                # Filter for BTC 5m markets
                btc_markets = [
                    m for m in markets 
                    if 'btc' in m.get('symbol', '').lower() 
                    or 'bitcoin' in m.get('question', '').lower()
                    or '5m' in m.get('symbol', '').lower()
                ]
                
                logger.info(f"📊 Found {len(btc_markets)} BTC 5m markets on Polymarket")
                return btc_markets
            else:
                logger.error("❌ Polymarket client missing get_active_markets method")
                return []
                
        except Exception as e:
            logger.error(f"❌ Error fetching markets: {e}")
            return []

    def find_opportunities(self, symbols: List[str]) -> List[Dict]:
        """
        Analyze markets for trading opportunities
        Returns signals with confidence scores
        """
        opportunities = []
        
        for symbol in symbols:
            try:
                # Get market data from Polymarket
                market_data = self._get_market_data(symbol)
                
                if not market_data:
                    continue
                
                # Simple momentum strategy (customize as needed)
                signal = self._analyze_market(market_data)
                
                if signal and signal['confidence'] >= self.min_confidence:
                    opportunities.append(signal)
                    
            except Exception as e:
                logger.error(f"❌ Error analyzing {symbol}: {e}")
        
        return opportunities

    def _get_market_data(self, symbol: str) -> Optional[Dict]:
        """Fetch market data from Polymarket"""
        try:
            if hasattr(self.client, 'get_market_ticker'):
                return self.client.get_market_ticker(symbol)
            return None
        except:
            return None

    def _analyze_market(self, market_data: Dict) -> Optional[Dict]:
        """
        Analyze market for trading signal
        Simple example: Price momentum + volume
        """
        try:
            price = market_data.get('last_price', 0.5)
            volume = market_data.get('volume', 0)
            
            # Example logic: If price > 0.55 and volume spike, BUY
            # If price < 0.45 and volume spike, SELL
            if price > 0.55 and volume > 1000:
                return {
                    'symbol': market_data.get('market_id', 'UNKNOWN'),
                    'signal': 'BUY',
                    'confidence': min(price + 0.3, 0.95),
                    'price': price,
                    'reason': 'momentum_high'
                }
            elif price < 0.45 and volume > 1000:
                return {
                    'symbol': market_data.get('market_id', 'UNKNOWN'),
                    'signal': 'SELL',
                    'confidence': min((1-price) + 0.3, 0.95),
                    'price': price,
                    'reason': 'momentum_low'
                }
            
            return None
            
        except Exception as e:
            logger.error(f"Analysis error: {e}")
            return None
