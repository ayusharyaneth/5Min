#!/usr/bin/env python3
"""
5Min Trading Bot - Strategy Validation + Live Trading Only
Removed: Shimmer (replaced by backtesting)
Kept: Backtesting (validation) + Polymarket (live)
"""

# Load .env
import os
import sys

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    if os.path.exists('.env'):
        with open('.env') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key] = value.strip().strip('"').strip("'")

def validate():
    if not os.getenv('TELEGRAM_TOKEN'):
        print("❌ TELEGRAM_TOKEN not set")
        sys.exit(1)
    if not os.getenv('AUTHORIZED_USER_ID'):
        print("❌ AUTHORIZED_USER_ID not set (security required)")
        sys.exit(1)
    return True

validate()

import logging
import json
import threading
import asyncio
import time
import traceback
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format='%(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger('MAIN')

# Only import Polymarket (removed Shimmer)
try:
    from data.polymarket_client import PolymarketClient
    from live_trading.live_executor import LiveExecutor
    from backtest.engine import StrategyValidator  # New
    from backtest.polymarket_historical import PolymarketHistoricalData  # New
    from telegram_bot.bot import TelegramBotRunner
except ImportError as e:
    logger.error(f"Import failed: {e}")
    sys.exit(1)


class TradingBot:
    def __init__(self):
        self.config = self._load_config()
        self.running = False
        self.threads = []
        self.start_time = time.time()
        
        # Only Live mode (removed Paper/Shimmer)
        self.live_enabled = os.getenv('LIVE_ENABLED', 'false').lower() == 'true'
        self.run_backtest_first = os.getenv('RUN_BACKTEST', 'true').lower() == 'true'
        
        self.polymarket = None
        self.live_exec = None
        self.telegram = None

    def _load_config(self):
        return {
            "telegram_token": os.getenv("TELEGRAM_TOKEN"),
            "authorized_user_id": os.getenv("AUTHORIZED_USER_ID"),
            "trades_channel_id": os.getenv("TRADES_CHANNEL_ID", ""),
            "logs_channel_id": os.getenv("LOGS_CHANNEL_ID", ""),
            
            # Polymarket Live
            "live_enabled": os.getenv("LIVE_ENABLED", "false").lower() == "true",
            "live_auto_trade": os.getenv("LIVE_AUTO_TRADE", "false").lower() == "true",
            "polymarket_pk": os.getenv("POLYMARKET_PK", ""),
            "polymarket_api_key": os.getenv("POLYMARKET_API_KEY", ""),
            "polymarket_secret": os.getenv("POLYMARKET_SECRET", ""),
            "live_trade_size": float(os.getenv("LIVE_TRADE_SIZE", "5")),
            "live_max_size": float(os.getenv("LIVE_MAX_SIZE", "50")),
            
            # Backtest settings
            "backtest_days": int(os.getenv("BACKTEST_DAYS", "30")),
            "min_confidence": float(os.getenv("MIN_CONFIDENCE", "0.75")),
            
            "check_interval": 60
        }

    async def run_strategy_validation(self):
        """Run backtest to validate strategy before live trading"""
        logger.info("🧪 STRATEGY VALIDATION MODE")
        logger.info("Testing strategy on historical data...")
        
        validator = StrategyValidator({
            'initial_balance': 10000,
            'trade_size': self.config['live_trade_size'],
            'min_confidence': self.config['min_confidence'],
            'take_profit': 0.05,
            'stop_loss': 0.03
        })
        
        # Fetch historical Polymarket data
        fetcher = PolymarketHistoricalData()
        historical_data = await fetcher.fetch_historical_markets(self.config['backtest_days'])
        
        if not historical_data:
            logger.warning("Using synthetic data for backtest")
            historical_data = await fetcher.generate_synthetic_data(self.config['backtest_days'])
        
        # Run backtest
        results = await validator.run_backtest(historical_data)
        validator.export_results("backtest_results.json")
        
        # Check if profitable
        if results.get('is_profitable') and results.get('recommendation') == 'PROCEED_TO_LIVE':
            logger.info("✅ STRATEGY VALIDATED - Ready for live trading")
            return True
        else:
            logger.error("❌ STRATEGY FAILED - Do not proceed to live trading")
            logger.info("💡 Check backtest_results.json and optimize your strategy")
            return False

    def _init_live(self):
        """Initialize Polymarket Live Trading"""
        if not self.live_enabled:
            return
            
        logger.info("💰 Initializing Live Trading (Polymarket)...")
        logger.warning("🔥 REAL MONEY MODE")
        
        try:
            self.polymarket = PolymarketClient({
                'private_key': self.config['polymarket_pk'],
                'api_key': self.config['polymarket_api_key'],
                'secret': self.config['polymarket_secret']
            })
            
            if not self.polymarket.connected:
                raise Exception("Connection failed")
            
            self.live_exec = LiveExecutor(
                polymarket_client=self.polymarket,
                config=self.config
            )
            
            wallet = self.polymarket.wallet_address or "Unknown"
            masked = f"{wallet[:6]}...{wallet[-4]}" if len(wallet) > 10 else "***"
            balance = self.polymarket.get_balance()
            
            logger.info(f"💰 Connected: {masked}")
            logger.info(f"💰 Balance: {balance.get('usdc', 0)} USDC")
            
            if self.config['live_auto_trade']:
                logger.warning("🚨 AUTO-TRADE IS ACTIVE!")
                
        except Exception as e:
            logger.error(f"💰 Live Init Failed: {e}")
            self.live_enabled = False

    def _init_telegram(self):
        """Initialize Telegram Bot"""
        if not self.config.get('telegram_token'):
            return
            
        try:
            self.telegram = TelegramBotRunner(
                token=self.config['telegram_token'],
                config={k: v for k, v in self.config.items() if 'key' not in k and 'secret' not in k and 'pk' not in k},
                live_executor=self.live_exec,
                live_enabled=self.live_enabled,
                get_uptime=lambda: f"{int((time.time() - self.start_time) // 3600)}h {int((time.time() - self.start_time) % 3600 // 60)}m"
            )
            
            if self.live_exec:
                self.live_exec._external_notifier = self.telegram
            
            logger.info("📱 Telegram Ready")
        except Exception as e:
            logger.error(f"📱 Telegram Failed: {e}")

    async def start(self):
        """Main start sequence"""
        print("\n╔" + "═" * 50 + "╗")
        print("║" + " " * 10 + "🤖 5MIN TRADING BOT" + " " * 19 + "║")
        print("╚" + "═" * 50 + "╝\n")
        
        # Step 1: Run Backtest Validation (if enabled)
        if self.run_backtest_first:
            validated = await self.run_strategy_validation()
            if not validated:
                logger.error("Exiting due to failed strategy validation")
                return
        
        # Step 2: Initialize Live Trading (if enabled and passed backtest)
        if self.live_enabled:
            self._init_live()
        
        self._init_telegram()
        
        if self.telegram:
            self.telegram.start()
            time.sleep(2)
        
        # Step 3: Start Live Trading Loop
        if self.live_enabled:
            t = threading.Thread(target=self._live_loop, daemon=True)
            t.start()
            self.threads.append(t)
            logger.info("💰 Live trading started")
        
        logger.info("🚀 Bot running (Ctrl+C to stop)")
        
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print()
            logger.info("🛑 Stopping...")
            self.stop()

    def _live_loop(self):
        """Live trading loop"""
        logger.info("💰 Live loop started")
        interval = self.config['check_interval']
        
        while True:
            try:
                if self.live_exec:
                    # Your live trading logic here
                    logger.info("💰 Scanning markets...")
                time.sleep(interval)
            except Exception as e:
                logger.error(f"❌ Live error: {e}")
                time.sleep(5)

    def stop(self):
        self.running = False
        if self.telegram:
            self.telegram.stop()
        logger.info("👋 Stopped")


def main():
    bot = TradingBot()
    asyncio.run(bot.start())

if __name__ == "__main__":
    main()
