#!/usr/bin/env python3
"""
5Min Trading Bot - Dual Mode
Shimmer (Simulation) | Polymarket (Live)
"""

import os
import sys
import time
import json
import logging
import threading
import asyncio
from typing import Dict, Any

# Logging setup
class AlignFormatter(logging.Formatter):
    def format(self, record):
        icons = {'INFO': '✓', 'WARNING': '⚠', 'ERROR': '✗', 'CRITICAL': '🔥'}
        icon = icons.get(record.levelname, '•')
        name = record.name.split('.')[-1].upper()[:10].ljust(10)
        return f"{icon}  {name} | {record.getMessage()}"

handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(AlignFormatter())
logging.getLogger().addHandler(handler)
logging.getLogger().setLevel(logging.INFO)
logging.getLogger('httpx').setLevel(logging.ERROR)

logger = logging.getLogger('MAIN')

# Imports
try:
    from data.shimmer_client import ShimmerClient
    from data.polymarket_client import PolymarketClient
    from paper_trading.paper_executor import PaperExecutor
    from live_trading.live_executor import LiveExecutor
    from monitor.market_finder import MarketFinder
    from telegram_bot.bot import TelegramBotRunner
except ImportError as e:
    logger.error(f"Import error: {e}")

class TradingBot:
    def __init__(self, config_path: str = "config.json"):
        self.config = self._load_config(config_path)
        self.running = False
        self.threads = []
        
        # Mode: 'paper' (Shimmer) or 'live' (Polymarket)
        self.trading_mode = self.config.get('trading_mode', 'paper')
        
        self.shimmer = None
        self.polymarket = None
        self.executor = None
        self.market_finder = None
        self.telegram = None
        
    def _load_config(self, path: str) -> Dict:
        defaults = {
            "trading_mode": "paper",  # 'paper' or 'live'
            "telegram_token": os.getenv("TELEGRAM_TOKEN", ""),
            "telegram_chat_id": os.getenv("TELEGRAM_CHAT_ID", ""),
            
            # Shimmer (Paper) Settings
            "shimmer_api_key": os.getenv("SHIMMER_KEY", ""),
            "shimmer_url": "https://api.shimmer.network",
            "mock_mode": True,
            
            # Polymarket (Live) Settings
            "polymarket_private_key": os.getenv("POLYMARKET_PK", ""),
            "polymarket_api_key": os.getenv("POLYMARKET_API_KEY", ""),
            "polymarket_secret": os.getenv("POLYMARKET_SECRET", ""),
            
            # Trading Settings
            "initial_balance": 10000.0,
            "max_trade_size": 100,  # USDC
            "auto_trade": False,
            "confirm_trades": True,  # Require confirmation for live trades
        }
        
        if os.path.exists(path):
            with open(path) as f:
                defaults.update(json.load(f))
        else:
            with open(path, 'w') as f:
                json.dump(defaults, f, indent=2)
        
        return defaults

    def _init_components(self):
        """Initialize based on trading mode"""
        mode = self.trading_mode.upper()
        logger.info(f"{'='*40}")
        logger.info(f"MODE: {mode} TRADING")
        logger.info(f"{'='*40}")
        
        if self.trading_mode == 'paper':
            self._init_paper_mode()
        elif self.trading_mode == 'live':
            self._init_live_mode()
        else:
            logger.error(f"Unknown mode: {self.trading_mode}")
            sys.exit(1)
        
        # Telegram (works with both)
        if TelegramBotRunner and self.config.get('telegram_token'):
            self.telegram = TelegramBotRunner(
                token=self.config['telegram_token'],
                config=self.config,
                executor=self.executor,
                market_finder=self.market_finder
            )
            if self.executor:
                self.executor.notifier = self.telegram
            logger.info("Telegram ready")

    def _init_paper_mode(self):
        """Initialize Shimmer simulation"""
        logger.info("Initializing Paper Trading (Shimmer)...")
        
        # Shimmer Client
        self.shimmer = ShimmerClient(self.config)
        
        # Paper Executor
        if PaperExecutor:
            self.executor = PaperExecutor(
                initial_balance=self.config['initial_balance'],
                paper_clob=self.shimmer,
                config=self.config
            )
        
        # Market Finder using Shimmer data
        self.market_finder = MarketFinder(
            clob=self.shimmer,
            config=self.config,
            paper_executor=self.executor
        )
        
        logger.info("Paper trading ready")
        logger.info(f"Virtual Balance: ${self.config['initial_balance']:,.2f}")

    def _init_live_mode(self):
        """Initialize Polymarket live trading"""
        logger.info("Initializing LIVE Trading (Polymarket)...")
        logger.warning("⚠️  REAL MONEY WILL BE USED")
        
        # Check for wallet key
        if not self.config.get('polymarket_private_key'):
            logger.error("No private key found! Set POLYMARKET_PK env var")
            sys.exit(1)
        
        # Polymarket Client
        self.polymarket = PolymarketClient(self.config)
        
        if not self.polymarket.connected:
            logger.error("Failed to connect to Polymarket")
            sys.exit(1)
        
        # Live Executor
        self.executor = LiveExecutor(
            polymarket_client=self.polymarket,
            config=self.config
        )
        
        # Market Finder using Polymarket data
        self.market_finder = MarketFinder(
            clob=self.polymarket,  # PolymarketClient has same interface
            config=self.config,
            paper_executor=None  # Live executor handles trades
        )
        
        balance = self.polymarket.get_balance()
        logger.info(f"Live trading ready")
        logger.info(f"Real Balance: {balance.get('usdc', 0)} USDC")

    def _trading_loop(self):
        """Main trading loop"""
        logger.info("Trading loop started")
        interval = self.config.get('check_interval', 15)
        
        while self.running:
            try:
                if self.market_finder:
                    # Find markets
                    markets = self.market_finder.find_active_btc_5m_markets()
                    
                    if markets:
                        logger.info(f"Found {len(markets)} markets")
                        
                        for market in markets[:3]:  # Check top 3
                            logger.info(f"  → {market.get('symbol')}")
                            
                            # Analyze
                            opportunities = self.market_finder.find_opportunities([market['symbol']])
                            
                            if opportunities and self.config.get('auto_trade'):
                                for opp in opportunities:
                                    logger.info(f"  💡 Opportunity: {opp.get('signal')} "
                                              f"({opp.get('confidence', 0):.0%})")
                                    
                                    # Execute based on mode
                                    if self.trading_mode == 'paper':
                                        # Auto-execute paper trades
                                        self.executor.execute_trade(
                                            symbol=market['symbol'],
                                            side=opp['signal'],
                                            size=self.config.get('trade_size', 10)
                                        )
                                    else:
                                        # Live mode - require confirmation or strict criteria
                                        if opp.get('confidence', 0) > 0.85:  # High confidence only
                                            logger.warning("High confidence signal - executing LIVE trade")
                                            self.executor.execute_trade(
                                                market_id=market['market_id'],
                                                side=opp['signal'],
                                                size=min(self.config.get('trade_size', 10), 
                                                        self.config.get('max_trade_size', 50)),
                                                price=opp.get('price', 0.5)
                                            )
                    
                    else:
                        logger.warning("No markets found")
                
                time.sleep(interval)
                
            except Exception as e:
                logger.error(f"Loop error: {e}")
                time.sleep(5)

    def start(self):
        """Start bot"""
        print()
        logger.info("══════════════════════════════════════")
        logger.info("   5MIN TRADING BOT")
        logger.info(f"   Mode: {self.trading_mode.upper()}")
        logger.info("══════════════════════════════════════")
        
        self.running = True
        self._init_components()
        
        if self.telegram:
            self.telegram.start()
            time.sleep(2)
        
        # Start trading thread
        t = threading.Thread(target=self._trading_loop, name="Trading", daemon=True)
        t.start()
        self.threads.append(t)
        
        logger.info("Bot running. Press Ctrl+C to stop.")
        self._main_loop()

    def _main_loop(self):
        try:
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            print()
            logger.info("Shutdown...")
            self.stop()

    def stop(self):
        self.running = False
        for t in self.threads:
            t.join(timeout=2)
        logger.info("Stopped")

def main():
    bot = TradingBot()
    bot.run()

if __name__ == "__main__":
    main()
