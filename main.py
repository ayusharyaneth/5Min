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
# ULTRA-CLEAN LOGGING SETUP
# ═══════════════════════════════════════════════════════════

class AlignFormatter(logging.Formatter):
    """
    Formats logs like:
    ✓  DB         | Connected
    ⚠  MARKETS    | No data source
    ✗  ERROR      | Connection failed
    """
    def format(self, record):
        icons = {
            'INFO': '✓',
            'WARNING': '⚠',
            'ERROR': '✗',
            'CRITICAL': '🔥',
            'DEBUG': '·'
        }
        
        # Get icon
        icon = icons.get(record.levelname, '•')
        
        # Get module name (shortened, uppercased, aligned)
        # Example: paper_trading.paper_executor -> PAPER_EXE
        name_parts = record.name.split('.')
        name = name_parts[-1].upper()
        
        # Truncate or pad to 10 characters for alignment
        if len(name) > 10:
            name = name[:10]
        else:
            name = name.ljust(10)
        
        return f"{icon}  {name} | {record.getMessage()}"

# Setup formatter
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(AlignFormatter())

# Configure root logger
root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)
root_logger.handlers = []  # Clear defaults
root_logger.addHandler(handler)

# Silence external noise completely
logging.getLogger('httpx').setLevel(logging.ERROR)  # Only show errors
logging.getLogger('telegram').setLevel(logging.ERROR)
logging.getLogger('telegram.ext').setLevel(logging.ERROR)
logging.getLogger('telegram_bot.bot').setLevel(logging.INFO)

logger = logging.getLogger('MAIN')

# ═══════════════════════════════════════════════════════════
# IMPORTS
# ═══════════════════════════════════════════════════════════

try:
    from paper_trading.paper_executor import PaperExecutor
    from paper_trading.paper_db import PaperDB
except ImportError as e:
    PaperExecutor = None
    PaperDB = None

try:
    from monitor.market_finder import MarketFinder
    from monitor.closure_checker import ClosureChecker
except ImportError as e:
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

CLOBClient = None
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
            "auto_trade": False,
            "default_trade_size": 1.0,
            "db_path": "trades.db"
        }
        
        if os.path.exists(path):
            try:
                with open(path) as f:
                    defaults.update(json.load(f))
            except Exception as e:
                logger.warning(f"Config error: {e}")
        else:
            with open(path, 'w') as f:
                json.dump(defaults, f, indent=2)
        
        return defaults

    def _init_components(self):
        """Initialize with clean status logging"""
        logger.info("Initializing...")
        
        # Database
        if PaperDB:
            try:
                self.db = PaperDB(self.config['db_path'])
                logger.info("Database connected")
            except Exception as e:
                logger.error(f"Database failed: {e}")
        
        # Dashboard (optional, silent fail)
        if Dashboard:
            try:
                self.dashboard = Dashboard()
                logger.info("Dashboard ready")
            except:
                pass
        
        # Paper Trading Engine
        if PaperExecutor:
            try:
                self.paper_exec = PaperExecutor(
                    initial_balance=self.config['initial_balance'],
                    paper_clob=None,
                    paper_store=None,
                    db=self.db,
                    config=self.config
                )
                bal = self.config['initial_balance']
                logger.info(f"Trading ready | Balance ${bal:,.0f}")
            except Exception as e:
                logger.error(f"Trading failed: {e}")
        
        # Market Finder
        if MarketFinder:
            try:
                self.market_finder = MarketFinder(
                    clob=None,
                    store=None,
                    db=self.db,
                    config=self.config,
                    paper_executor=self.paper_exec
                )
                logger.info("Markets ready")
            except Exception as e:
                logger.error(f"Markets failed: {e}")
        
        # Closure Checker
        if ClosureChecker:
            try:
                self.closure_checker = ClosureChecker(
                    clob=None,
                    store=None,
                    db=self.db,
                    config=self.config,
                    paper_executor=self.paper_exec
                )
                logger.info("Monitor ready")
            except Exception as e:
                logger.error(f"Monitor failed: {e}")
        
        # Telegram Bot
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
                
                # Link notifiers
                if self.paper_exec:
                    self.paper_exec._external_notifier = self.telegram_bot
                if self.market_finder:
                    self.market_finder._external_notifier = self.telegram_bot
                if self.closure_checker:
                    self.closure_checker._external_notifier = self.telegram_bot
                
                logger.info("Telegram ready")
            except Exception as e:
                logger.error(f"Telegram failed: {e}")
        
        # Summary line
        count = sum([bool(self.db), bool(self.paper_exec), 
                    bool(self.market_finder), bool(self.closure_checker),
                    bool(self.telegram_bot)])
        logger.info(f"Systems online: {count}/5")

    def _market_discovery_loop(self):
        """Market discovery - clean logging"""
        interval = self.config.get('discovery_interval', 15)
        
        while self.running:
            try:
                if self.market_finder:
                    markets = self.market_finder.find_active_btc_5m_markets()
                    
                    if markets:
                        logger.info(f"Found {len(markets)} markets")
                        symbols = [m.get('symbol') for m in markets if m]
                        if symbols:
                            opportunities = self.market_finder.find_opportunities(symbols)
                            if opportunities:
                                logger.info(f"Found {len(opportunities)} opportunities")
                    else:
                        # Log only once to prevent spam
                        if not self._market_warning_logged:
                            logger.warning("No markets (CLOB not connected)")
                            self._market_warning_logged = True
                
                time.sleep(interval)
                
            except Exception as e:
                logger.error(f"Discovery error: {e}")
                time.sleep(5)

    def _closure_check_loop(self):
        """Closure monitor"""
        if not self.closure_checker:
            return
        
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
        """Start with visual header"""
        # Print clean header
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
            logger.info("Use Ctrl+C to stop")
            print()  # Empty line for breathing room
        
        # Start threads
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
        """Silent main loop"""
        try:
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            print()  # New line after ^C
            logger.info("══════════════════════════════════════")
            logger.info("     SHUTDOWN SIGNAL RECEIVED")
            self.stop()

    def stop(self):
        """Clean shutdown"""
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
