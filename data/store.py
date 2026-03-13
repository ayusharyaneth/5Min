"""Simple data store for persistence"""
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime

logger = logging.getLogger('Store')

class DataStore:
    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self.data = {
            'markets': {},
            'trades': [],
            'positions': {}
        }
        logger.info("Store initialized (memory only)")
    
    def save_trade(self, trade: Dict):
        """Save trade to store"""
        self.data['trades'].append(trade)
        logger.debug(f"Stored trade: {trade.get('symbol')}")
    
    def update_position(self, symbol: str, position: Dict):
        """Update position"""
        self.data['positions'][symbol] = position
    
    def get_position(self, symbol: str) -> Optional[Dict]:
        """Get position"""
        return self.data['positions'].get(symbol)
    
    def save_opportunity(self, opportunity: Dict):
        """Save found opportunity"""
        if 'opportunities' not in self.data:
            self.data['opportunities'] = []
        self.data['opportunities'].append(opportunity)
    
    def get_market_data(self, symbol: str) -> Optional[Dict]:
        """Get stored market data"""
        return self.data['markets'].get(symbol)
    
    def save_state(self, state: Dict):
        """Save bot state"""
        self.data['state'] = state
    
    def load_state(self) -> Optional[Dict]:
        """Load bot state"""
        return self.data.get('state')
