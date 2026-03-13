#!/usr/bin/env python3
"""
5Min Trading Bot - Main Entry Point
"""

import os
import sys
import time
import json
import logging
import threading
import asyncio
from typing import Dict, Any

# ═══════════════════════════════════════════════════════════
# LOGGING SETUP
# ═══════════════════════════════════════════════════════════

class AlignFormatter(logging.Formatter):
    def format(self, record):
        icons = {'INFO': '✓', 'WARNING': '⚠', 'ERROR': '✗', 'CRITICAL': '🔥', 'DEBUG': '·'}
        icon = icons.get(record.levelname, '•')
        name = record.name.split('.')[-1].upper()[:10].ljust(10)
        return f"{icon}  {name} | {record.getMessage()}"

handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(AlignFormatter())
root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)
root_logger.handlers = []
root_logger.addHandler(handler)

logging.getLogger('httpx').setLevel(logging.ERROR)
logging.getLogger('telegram').setLevel(logging.ERROR)

logger = logging.getLogger('MAIN')

# ═══════════════════════════════════════════════════════════
# IMPORTS
# ═══════════════════════════════════════════════════════════

try:
    from paper_trading.paper_executor import PaperExecutor
    from paper_trading.paper_db import PaperDB
except ImportError as e:
    logger.error(f"Paper trading import failed: {e}")
    PaperExecutor = None
    PaperDB = None

try:
    from monitor.market_finder import MarketFinder
    from monitor.closure_checker import ClosureChecker
except ImportError as e:
    logger.error(f"Monitor import failed: {e}")
    MarketFinder = None
    ClosureChecker = None

try:
    from telegram_bot.bot import TelegramBotRunner
except ImportError as e:
    TelegramBotRunner = None

try:
    from telegram_bot.dashboard import Dashboard
except ImportError:
    Dashboard = None

# CRITICAL: Import CLOB and Store
try:
    from data.clob_client import CLOBClient
    logger.info("CLOB Client imported successfully")
except ImportError as e:
    logger.error(f"CLOB Client not found: {e}")
    CLOBClient = None

try:
    from data.store import DataStore
    logger.info("DataStore imported successfully")
except ImportError as e:
    logger.error(f"DataStore not found: {e}")
    DataStore = None

# ═══════════════════════════════════════════════════════════
# BOT CLASS
# ═══════════════════════════════════════════════════════════

class TradingBot:
    def __init__(self, config_path: str = "config.json"):
        self.config = self._load_config(config_path)
        self.running = False
        self.threads = []
        
        self.db = None
        self.store = None
        self.clob = None
        self.paper_exec = None
        self.market_finder = None
        self.closure_checker = None
        self.dashboard = None
        self.telegram_bot = None
        
        self._market_warning_logged = False

    def _load_config(self, path: str) -> Dict:
        defaults = {
            "telegram_token": os.getenv("TELEGRAM_TOKEN", ""),
            "telegram_chat_id": os.getenv("TELEGRAM_CHAT_ID", ""),
            "initial_balance": 10000.0,
            "check_interval": 60,
            "discovery_interval": 15,
            "auto_trade": False,  # Default OFF for safety
            "default_trade_size": 1.0,
            "db_path": "trades.db",
            "mock_mode": True  # Set to False when using real Shimmer API
        }
        
        if os.path.exists(path):
            try:
                with open(path) as f:
                    loaded = json.load(f)
                    defaults.update(loaded)
            except Exception as e:
                logger.warning(f"Config error: {e}")
        else:
            with open(path, 'w') as f:
                json.dump(defaults, f, indent=2)
                logger.info(f"Created default config: {path}")
        
        return defaults

    def _init_components(self):
        """Initialize all components"""
        logger.info("Initializing...")
        
        # 1. Database
        if PaperDB:
            try:
                self.db = PaperDB(self.config['db_path'])
                logger.info("Database connected")
            except Exception as e:
                logger.error(f"Database failed: {e}")
        
        # 2. Data Store (for persistence)
        if DataStore:
            try:
                self.store = DataStore(config=self.config)
                logger.info("Store connected")
            except Exception as e:
                logger.error(f"Store failed: {e}")
        
        # 3. CLOB Client (CRITICAL - This was missing!)
        if CLOBClient:
            try:
                self.clob = CLOBClient(config=self.config)
                if self.clob.connected:
                    mode = "MOCK" if self.clob.mock_mode else "LIVE"
                    logger.info(f"CLOB connected ({mode} mode)")
                else:
                    logger.error("CLOB failed to connect")
            except Exception as e:
                logger.error(f"CLOB error: {e}")
        else:
            logger.error("CLOB Client not available - markets will be empty!")
        
        # 4. Dashboard (optional)
        if Dashboard:
            try:
                self.dashboard = Dashboard()
                logger.info("Dashboard ready")
            except:
                pass
        
        # 5. Paper Trading Engine (NOW WITH CLOB!)
        if PaperExecutor:
            try:
                self.paper_exec = PaperExecutor(
                    initial_balance=self.config['initial_balance'],
                    paper_clob=self.clob,  # CRITICAL: Pass CLOB for price data
                    paper_store=self.store,
                    db=self.db,
                    config=self.config
                )
                bal = self.config['initial_balance']
                logger.info(f"Trading engine ready | Balance ${bal:,.0f}")
            except Exception as e:
                logger.error(f"Trading engine failed: {e}")
        
        # 6. Market Finder (NOW WITH CLOB!)
        if MarketFinder:
            try:
                self.market_finder = MarketFinder(
                    clob=self.clob,  # CRITICAL: Pass CLOB to find markets
                    store=self.store,
                    db=self.db,
                    config=self.config,
                    paper_executor=self.paper_exec
                )
                logger.info("Market finder ready")
            except Exception as e:
                logger.error(f"Market finder failed: {e}")
        
        # 7. Closure Checker (NOW WITH CLOB!)
        if ClosureChecker:
            try:
                self.closure_checker = ClosureChecker(
                    clob=self.clob,
                    store=self.store,
                    db=self.db,
                    config=self.config,
                    paper_executor=self.paper_exec
                )
                logger.info("Closure checker ready")
            except Exception as e:
                logger.error(f"Closure checker failed: {e}")
        
        # 8. Telegram Bot
        if TelegramBotRunner and self.config.get('telegram_token'):
            try:
                bot_config = self.config.copy()
                bot_config['chat_id'] = self.config.get('telegram_chat_id')
                
                self.telegram_bot = TelegramBotRunner(
                    token=self.config['telegram_token'],
                    config=bot_config,
                    dashboard=self.dashboard,
                    db=self.db,
                    store=self.store,
                    paper_executor=self.paper_exec,
                    market_finder=self.market_finder,
                    closure_checker=self.closure_checker
                )
                
                # Link notifiers back
                if self.paper_exec:
                    self.paper_exec._external_notifier = self.telegram_bot
                if self.market_finder:
                    self.market_finder._external_notifier = self.telegram_bot
                if self.closure_checker:
                    self.closure_checker._external_notifier = self.telegram_bot
                
                logger.info("Telegram bot ready")
            except Exception as e:
                logger.error(f"Telegram bot failed: {e}")
        
        # Summary
        count = sum([bool(self.db), bool(self.store), bool(self.clob), 
                    bool(self.paper_exec), bool(self.market_finder), 
                    bool(self.closure_checker), bool(self.telegram_bot)])
        logger.info(f"Systems online: {count}/7")
        
        # CRITICAL DIAGNOSTIC
        if not self.clob:
            logger.warning("═" * 40)
            logger.warning("NO CLOB CONNECTED - No markets will be found!")
            logger.warning("Bot will run but cannot discover markets.")
            logger.warning("Set 'mock_mode': true in config.json to test.")
            logger.warning("═" * 40)

    def _market_discovery_loop(self):
        """Market discovery with detailed logging"""
        logger.info("Market discovery started")
        interval = self.config.get('discovery_interval', 15)
        
        while self.running:
            try:
                if self.market_finder:
                    # Find markets
                    markets = self.market_finder.find_active_btc_5m_markets()
                    
                    if markets:
                        logger.info(f"Found {len(markets)} active markets")
                        
                        # Log each market found
                        for m in markets[:3]:  # Log first 3
                            logger.info(f"  • {m.get('symbol')} (ID: {m.get('market_id')[:20]}...)")
                        
                        # Extract symbols
                        symbols = [m.get('symbol') for m in markets if m]
                        
                        # Look for opportunities
                        if self.config.get('auto_trade', False):
                            logger.info("Auto-trading enabled, analyzing markets...")
                            opportunities = self.market_finder.find_opportunities(symbols)
                            
                            if opportunities:
                                logger.info(f"FOUND {len(opportunities)} TRADING OPPORTUNITIES!")
                                for opp in opportunities:
                                    logger.info(f"  → {opp.get('symbol')}: {opp.get('signal')} "
                                              f"(confidence: {opp.get('confidence', 0):.0%})")
                                
                                # Execute if auto-trade on
                                if self.paper_exec:
                                    for opp in opportunities:
                                        if opp.get('auto_execute') or self.config.get('auto_trade'):
                                            logger.info(f"Executing trade: {opp.get('symbol')} {opp.get('signal')}")
                                            # Trade execution happens inside market_finder.find_opportunities
                            else:
                                logger.info("No opportunities found this cycle")
                        else:
                            logger.info("Auto-trading disabled (enable in /settings)")
                    else:
                        if not self._market_warning_logged:
                            if self.clob:
                                logger.warning("CLOB connected but no markets found")
                            else:
                                logger.warning("No CLOB - cannot fetch markets")
                            self._market_warning_logged = True
                
                time.sleep(interval)
                
            except Exception as e:
                logger.error(f"Discovery error: {e}")
                time.sleep(5)

    def _closure_check_loop(self):
        """Monitor market closures"""
        if not self.closure_checker:
            return
        
        logger.info("Closure monitoring started")
        loop = None
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self.closure_checker.run())
        except Exception as e:
            logger.error(f"Monitor error: {e}")
        finally:
            if loop:
                try:
                    loop.close()
                except:
                    pass

    def start(self):
        """Start bot"""
        print()
        logger.info("══════════════════════════════════════")
        logger.info("     5MIN TRADING BOT STARTING")
        logger.info("══════════════════════════════════════")
        
        self.running = True
        self._init_components()
        
        # Start Telegram
        if self.telegram_bot:
            self.telegram_bot.start()
            time.sleep(2)
            logger.info("Bot active - Press Ctrl+C to stop")
            print()
        
        # Start background threads
        if self.market_finder:
            t = threading.Thread(target=self._market_discovery_loop, name="Discovery", daemon=True)
            t.start()
            self.threads.append(t)
        
        if self.closure_checker:
            t = threading.Thread(target=self._closure_check_loop, name="Monitor", daemon=True)
            t.start()
            self.threads.append(t)
        
        self._main_loop()

    def _main_loop(self):
        """Main loop"""
        try:
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            print()
            logger.info("══════════════════════════════════════")
            logger.info("     SHUTDOWN SIGNAL RECEIVED")
            self.stop()

    def stop(self):
        """Shutdown"""
        logger.info("Stopping...")
        self.running = False
        
        if self.telegram_bot:
            self.telegram_bot.stop()
        if self.closure_checker and hasattr(self.closure_checker, 'stop'):
            self.closure_checker.stop()
        
        for t in self.threads:
            if t.is_alive():
                t.join(timeout=2)
        
        logger.info("Bot stopped")
        logger.info("══════════════════════════════════════")

    def run(self):
        try:
            self.start()
        except Exception as e:
            logger.critical(f"Fatal: {e}")
            raise


def main():
    bot = TradingBot()
    bot.run()


if __name__ == "__main__":
    main()
