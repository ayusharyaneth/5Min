#!/usr/bin/env python3
"""
5Min Trading Bot - Independent Dual Systems
Auto-loads .env file
"""

# ═══════════════════════════════════════════════════════════
# STEP 1: AUTO-LOAD .ENV FILE (MUST BE FIRST)
# ═══════════════════════════════════════════════════════════

import os
import sys

print("🔧 Loading environment...")

try:
    from dotenv import load_dotenv
    load_dotenv()
    print("✅ Loaded .env file")
except ImportError:
    print("⚠️  python-dotenv not installed, using manual loader")
    if os.path.exists('.env'):
        with open('.env') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    value = value.strip().strip('"').strip("'")
                    os.environ[key] = value
        print("✅ Loaded .env manually")
    else:
        print("❌ .env file not found!")
        sys.exit(1)

# Debug output
print(f"   PAPER_ENABLED: {os.getenv('PAPER_ENABLED', 'NOT SET')}")
print(f"   LIVE_ENABLED: {os.getenv('LIVE_ENABLED', 'NOT SET')}")

# ═══════════════════════════════════════════════════════════
# STEP 2: VALIDATION
# ═══════════════════════════════════════════════════════════

def validate_environment():
    paper = os.getenv('PAPER_ENABLED', '').lower() == 'true'
    live = os.getenv('LIVE_ENABLED', '').lower() == 'true'
    
    if not paper and not live:
        print("\n❌ ERROR: No trading mode enabled!")
        print("   Set PAPER_ENABLED=true or LIVE_ENABLED=true in .env")
        sys.exit(1)
    
    if not os.getenv('TELEGRAM_TOKEN'):
        print("\n❌ ERROR: TELEGRAM_TOKEN not set!")
        sys.exit(1)
    
    print("✅ Validation passed")
    return paper, live

paper_enabled, live_enabled = validate_environment()

# ═══════════════════════════════════════════════════════════
# STEP 3: LOGGING & IMPORTS
# ═══════════════════════════════════════════════════════════

import logging
import json
import threading
import asyncio
import time
from typing import Dict, Any

logging.basicConfig(
    level=logging.INFO,
    format='%(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger('MAIN')

try:
    from data.shimmer_client import ShimmerClient
    from data.polymarket_client import PolymarketClient
    from paper_trading.paper_executor import PaperExecutor
    from live_trading.live_executor import LiveExecutor
    from monitor.market_finder import MarketFinder
    from telegram_bot.bot import TelegramBotRunner
except ImportError as e:
    logger.error(f"Import failed: {e}")
    sys.exit(1)

# ═══════════════════════════════════════════════════════════
# BOT CLASS
# ═══════════════════════════════════════════════════════════

class TradingBot:
    def __init__(self):
        self.config = self._load_config()
        self.running = False
        self.threads = []
        
        self.paper_enabled = paper_enabled
        self.live_enabled = live_enabled
        
        # Components
        self.shimmer = None
        self.paper_exec = None
        self.polymarket = None
        self.live_exec = None
        self.market_finder = None
        self.telegram = None

    def _load_config(self) -> Dict:
        config = {
            "telegram_token": os.getenv("TELEGRAM_TOKEN"),
            "telegram_chat_id": os.getenv("TELEGRAM_CHAT_ID", ""),
            
            "paper_enabled": paper_enabled,
            "live_enabled": live_enabled,
            
            # Paper settings
            "shimmer_api_key": os.getenv("SHIMMER_API_KEY", ""),
            "shimmer_mock_mode": os.getenv("SHIMMER_MOCK_MODE", "true").lower() == "true",
            "auto_trade": os.getenv("PAPER_AUTO_TRADE", "false").lower() == "true",
            "default_trade_size": float(os.getenv("PAPER_TRADE_SIZE", "10")),
            "initial_balance": 10000.0,
            
            # Live settings
            "polymarket_pk": os.getenv("POLYMARKET_PK", ""),
            "polymarket_api_key": os.getenv("POLYMARKET_API_KEY", ""),
            "polymarket_secret": os.getenv("POLYMARKET_SECRET", ""),
            "live_auto_trade": os.getenv("LIVE_AUTO_TRADE", "false").lower() == "true",
            "live_trade_size": float(os.getenv("LIVE_TRADE_SIZE", "5")),
            "live_max_size": float(os.getenv("LIVE_MAX_SIZE", "50")),
            
            "check_interval": 60
        }
        
        if os.path.exists("config.json"):
            try:
                with open("config.json") as f:
                    config.update(json.load(f))
            except:
                pass
        return config

    def _init_systems(self):
        """Initialize independent trading systems"""
        logger.info("═" * 60)
        logger.info("INITIALIZING SYSTEMS")
        logger.info("═" * 60)
        
        # ═══════════════════════════════════════════════════════
        # SYSTEM A: PAPER TRADING (Shimmer)
        # ═══════════════════════════════════════════════════════
        if self.paper_enabled:
            logger.info("[PAPER] Initializing Shimmer...")
            try:
                self.shimmer = ShimmerClient({
                    'mock_mode': self.config['shimmer_mock_mode'],
                    'api_key': self.config['shimmer_api_key']
                })
                
                self.paper_exec = PaperExecutor(
                    initial_balance=self.config['initial_balance'],
                    paper_clob=self.shimmer,
                    config=self.config
                )
                
                self.market_finder = MarketFinder(
                    clob=self.shimmer,
                    config=self.config,
                    paper_executor=self.paper_exec
                )
                
                mode = "MOCK" if self.shimmer.mock_mode else "API"
                logger.info(f"[PAPER] ✅ Ready | Mode: {mode} | Balance: ${self.config['initial_balance']:,.0f}")
                
            except Exception as e:
                logger.error(f"[PAPER] ❌ Failed: {e}")
                self.paper_enabled = False
        
        # ═══════════════════════════════════════════════════════
        # SYSTEM B: LIVE TRADING (Polymarket)
        # ═══════════════════════════════════════════════════════
        if self.live_enabled:
            logger.info("[LIVE] Initializing Polymarket...")
            logger.warning("[LIVE] ⚠️  REAL MONEY!")
            
            try:
                self.polymarket = PolymarketClient({
                    'private_key': self.config['polymarket_pk'],
                    'api_key': self.config['polymarket_api_key'],
                    'secret': self.config['polymarket_secret']
                })
                
                if self.polymarket.connected:
                    self.live_exec = LiveExecutor(
                        polymarket_client=self.polymarket,
                        config=self.config
                    )
                    
                    balance = self.polymarket.get_balance()
                    logger.info(f"[LIVE] ✅ CONNECTED | {balance.get('usdc', 0)} USDC")
                else:
                    raise Exception("Connection failed")
                    
            except Exception as e:
                logger.error(f"[LIVE] ❌ Failed: {e}")
                self.live_enabled = False
        
        # ═══════════════════════════════════════════════════════
        # TELEGRAM BOT - Pass all components properly
        # ═══════════════════════════════════════════════════════
        if TelegramBotRunner and self.config.get('telegram_token'):
            logger.info("[TELEGRAM] Initializing...")
            try:
                # CRITICAL: Pass components with correct parameter names
                self.telegram = TelegramBotRunner(
                    token=self.config['telegram_token'],
                    config=self.config,
                    paper_executor=self.paper_exec,      # Paper system
                    live_executor=self.live_exec,        # Live system
                    market_finder=self.market_finder,    # Market data
                    paper_enabled=self.paper_enabled,    # Status flags
                    live_enabled=self.live_enabled
                )
                
                # Link notifiers back
                if self.paper_exec:
                    self.paper_exec._external_notifier = self.telegram
                if self.live_exec:
                    self.live_exec._external_notifier = self.telegram
                
                logger.info("[TELEGRAM] ✅ Ready")
            except Exception as e:
                logger.error(f"[TELEGRAM] ❌ Failed: {e}")

        # Summary
        active = []
        if self.paper_enabled: active.append("PAPER")
        if self.live_enabled: active.append("LIVE")
        logger.info("═" * 60)
        logger.info(f"ACTIVE: {' + '.join(active) if active else 'None'}")
        logger.info("═" * 60)

    def _paper_loop(self):
        """Paper trading loop"""
        logger.info("[PAPER] Loop started")
        interval = self.config.get('check_interval', 60)
        
        while self.running and self.paper_enabled:
            try:
                if self.market_finder:
                    markets = self.market_finder.find_active_btc_5m_markets()
                    
                    if markets:
                        logger.info(f"[PAPER] Found {len(markets)} markets")
                        
                        for market in markets[:2]:
                            symbol = market.get('symbol')
                            opportunities = self.market_finder.find_opportunities([symbol])
                            
                            if opportunities and self.config.get('auto_trade'):
                                for opp in opportunities:
                                    logger.info(f"[PAPER] Signal: {symbol} {opp['signal']}")
                                    result = self.paper_exec.execute_trade(
                                        symbol=symbol,
                                        side=opp['signal'],
                                        size=self.config.get('default_trade_size', 10)
                                    )
                                    if result.get('success'):
                                        logger.info("[PAPER] ✅ Executed")
                    else:
                        logger.debug("[PAPER] No markets")
                
                time.sleep(interval)
                
            except Exception as e:
                logger.error(f"[PAPER] Error: {e}")
                time.sleep(5)

    def _live_loop(self):
        """Live trading loop"""
        logger.info("[LIVE] Loop started - REAL MONEY")
        interval = self.config.get('check_interval', 60)
        
        while self.running and self.live_enabled:
            try:
                if self.live_exec:
                    # Live uses its own market scanning via Polymarket
                    logger.info("[LIVE] Scanning Polymarket...")
                    # Add live-specific logic here
                    pass
                
                time.sleep(interval)
                
            except Exception as e:
                logger.error(f"[LIVE] Error: {e}")
                time.sleep(5)

    def start(self):
        """Start all systems"""
        print("\n" + "═" * 60)
        print("   5MIN TRADING BOT")
        if self.paper_enabled:
            print("   📘 PAPER: ENABLED")
        if self.live_enabled:
            print("   💰 LIVE:  ENABLED")
        print("═" * 60 + "\n")
        
        self.running = True
        self._init_systems()
        
        # Start Telegram
        if self.telegram:
            self.telegram.start()
            time.sleep(2)
            print()
        
        # Start Paper Thread
        if self.paper_enabled:
            t = threading.Thread(target=self._paper_loop, name="Paper", daemon=True)
            t.start()
            self.threads.append(t)
        
        # Start Live Thread
        if self.live_enabled:
            t = threading.Thread(target=self._live_loop, name="Live", daemon=True)
            t.start()
            self.threads.append(t)
        
        logger.info("Bot running - Ctrl+C to stop")
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
        logger.info("Stopping...")
        self.running = False
        
        if self.telegram:
            self.telegram.stop()
        
        for t in self.threads:
            if t.is_alive():
                t.join(timeout=3)
        
        logger.info("Bot stopped")

    def run(self):
        try:
            self.start()
        except Exception as e:
            logger.critical(f"Fatal: {e}")
            import traceback
            traceback.print_exc()
            raise

# ═══════════════════════════════════════════════════════════
# ENTRY
# ═══════════════════════════════════════════════════════════

def main():
    bot = TradingBot()
    bot.run()

if __name__ == "__main__":
    main()
