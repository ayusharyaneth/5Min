"""
Fetch historical data from Polymarket for backtesting
Uses TheGraph or API to get past market data
"""

import logging
import requests
from datetime import datetime, timedelta
from typing import List, Dict
import asyncio

logger = logging.getLogger('Historical')

class PolymarketHistoricalData:
    def __init__(self):
        # TheGraph endpoint for Polymarket
        self.graph_url = "https://api.thegraph.com/subgraphs/name/polymarket/matic-markets"
        
    async def fetch_historical_markets(self, days: int = 30) -> List[Dict]:
        """
        Fetch historical market data from Polymarket
        """
        logger.info(f"📚 Fetching {days} days of historical data...")
        
        # GraphQL query to get closed markets with outcomes
        query = """
        {
          markets(where: {
            createdAt_gt: %d,
            outcomePrices_not: null
          }, orderBy: createdAt, orderDirection: desc, first: 100) {
            id
            question
            outcomes
            outcomePrices
            volume
            createdAt
            resolutionTime
            resolvedOutcome
          }
        }
        """ % int((datetime.now() - timedelta(days=days)).timestamp())
        
        try:
            response = requests.post(
                self.graph_url,
                json={'query': query},
                timeout=30
            )
            data = response.json()
            
            markets = data.get('data', {}).get('markets', [])
            
            # Format for backtesting
            formatted_data = []
            for market in markets:
                formatted_data.append({
                    'timestamp': datetime.fromtimestamp(int(market['createdAt'])),
                    'symbol': f"POLY-{market['id'][:8]}",
                    'price': float(market['outcomePrices'].split(',')[0]),  # Yes price
                    'volume': float(market['volume']),
                    'resolved_outcome': market.get('resolvedOutcome'),
                    'question': market['question']
                })
            
            logger.info(f"✅ Fetched {len(formatted_data)} historical markets")
            return formatted_data
            
        except Exception as e:
            logger.error(f"❌ Failed to fetch historical data: {e}")
            return []

    async def generate_synthetic_data(self, days: int = 30) -> List[Dict]:
        """
        Generate synthetic market data for testing
        Uses random walk with trends to simulate realistic markets
        """
        import random
        import numpy as np
        
        logger.info(f"🎲 Generating {days} days of synthetic market data...")
        
        data = []
        base_price = 0.50
        
        for day in range(days):
            for hour in range(24):
                # Simulate price movement
                trend = np.sin(day * 0.1) * 0.1  # Cyclical trend
                noise = random.gauss(0, 0.02)    # Random noise
                price = base_price + trend + noise
                price = max(0.01, min(0.99, price))  # Keep within bounds
                
                # Simulate volume
                volume = random.uniform(1000, 10000)
                
                # Generate future price path (next 5 minutes)
                future_prices = []
                for i in range(5):
                    future_price = price + random.gauss(0, 0.01) * (i+1)
                    future_price = max(0.01, min(0.99, future_price))
                    future_prices.append(future_price)
                
                data.append({
                    'timestamp': datetime.now() - timedelta(days=days-day, hours=24-hour),
                    'symbol': f'BTC-5M-{day}-{hour}',
                    'price': price,
                    'volume': volume,
                    'price_change_5m': (future_prices[-1] - price) / price,
                    'future_prices': future_prices,
                    'avg_volume': 5000
                })
                
                base_price = price
        
        logger.info(f"✅ Generated {len(data)} synthetic market events")
        return data
