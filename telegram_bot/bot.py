import logging
import asyncio
import threading
from typing import Optional, Dict, Any
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

logger = logging.getLogger(__name__)


class TelegramBotRunner:
    def __init__(self, 
                 token: str, 
                 config: Optional[Dict] = None,
                 dashboard: Any = None,
                 db: Any = None,
                 store: Any = None,
                 paper_executor: Any = None,
                 **kwargs):
        """
        Initialize Telegram Bot Runner with dependency injection
        
        Args:
            token: Telegram bot API token
            config: Configuration dictionary
            dashboard: Dashboard instance for UI updates
            db: Database connection
            store: Data persistence layer
            paper_executor: Paper trading executor reference
            **kwargs: Additional arguments for extensibility
        """
        self.token = token
        self.config = config or {}
        self.dashboard = dashboard
        self.db = db
        self.store = store
        self.paper_executor = paper_executor
        
        # Handle any extra kwargs
        for key, value in kwargs.items():
            setattr(self, key, value)
            
        self.application = None
        self.running = False
        self._loop = None
        self._thread = None
        
    def register_handlers(self):
        """Register command handlers"""
        handlers = [
            CommandHandler("start", self.cmd_start),
            CommandHandler("status", self.cmd_status),
            CommandHandler("balance", self.cmd_balance),
            CommandHandler("positions", self.cmd_positions),
            CommandHandler("history", self.cmd_history),
            CommandHandler("help", self.cmd_help),
            CommandHandler("stop", self.cmd_stop),
            CommandHandler("pnl", self.cmd_pnl),
            CommandHandler("trade", self.cmd_trade),
            CommandHandler("markets", self.cmd_markets),
            CommandHandler("alert", self.cmd_alert),
            CommandHandler("settings", self.cmd_settings),
            CommandHandler("restart", self.cmd_restart),
        ]
        
        for handler in handlers:
            self.application.add_handler(handler)
            
        logger.info(f"Registered {len(handlers)} command handlers")

    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("🤖 Bot started! Use /help for commands.")

    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show system status including dashboard if available"""
        status_text = "✅ System operational"
        
        if self.dashboard and hasattr(self.dashboard, 'get_status'):
            try:
                dash_status = self.dashboard.get_status()
                status_text += f"\nDashboard: {dash_status}"
            except Exception as e:
                logger.error(f"Error getting dashboard status: {e}")
                
        await update.message.reply_text(status_text)

    async def cmd_balance(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show balance from paper executor if available"""
        if self.paper_executor and hasattr(self.paper_executor, 'get_portfolio_value'):
            try:
                portfolio = self.paper_executor.get_portfolio_value()
                balance_text = (
                    f"💰 Portfolio Status:\n"
                    f"Cash: ${portfolio.get('cash_balance', 0):,.2f}\n"
                    f"Positions: ${portfolio.get('positions_value', 0):,.2f}\n"
                    f"Total: ${portfolio.get('total_value', 0):,.2f}\n"
                    f"PnL: ${portfolio.get('total_return', 0):,.2f}"
                )
                await update.message.reply_text(balance_text)
                return
            except Exception as e:
                logger.error(f"Error getting balance: {e}")
                
        await update.message.reply_text("💰 Balance check...")

    async def cmd_positions(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show open positions"""
        if self.paper_executor and hasattr(self.paper_executor, 'positions'):
            try:
                positions = self.paper_executor.positions
                if not positions:
                    await update.message.reply_text("📊 No open positions")
                    return
                    
                pos_text = "📊 Open Positions:\n"
                for symbol, pos in positions.items():
                    pos_text += f"{symbol}: {pos.get('quantity', 0)} @ ${pos.get('avg_entry_price', 0):.2f}\n"
                await update.message.reply_text(pos_text)
                return
            except Exception as e:
                logger.error(f"Error getting positions: {e}")
                
        await update.message.reply_text("📊 Positions check...")

    async def cmd_history(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show trade history"""
        if self.paper_executor and hasattr(self.paper_executor, 'get_trade_history'):
            try:
                history = self.paper_executor.get_trade_history(limit=5)
                if not history:
                    await update.message.reply_text("📜 No recent trades")
                    return
                    
                hist_text = "📜 Recent Trades:\n"
                for trade in history:
                    hist_text += f"{trade.get('symbol')} {trade.get('side')} @ ${trade.get('price', 0):.2f}\n"
                await update.message.reply_text(hist_text)
                return
            except Exception as e:
                logger.error(f"Error getting history: {e}")
                
        await update.message.reply_text("📜 History check...")

    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        help_text = """
Available commands:
/start - Start the bot
/status - Check system status
/balance - Check balance
/positions - View open positions
/history - View trade history
/pnl - View P&L summary
/trade - Execute manual trade
/markets - List active markets
/alert - Set price alert
/settings - Bot settings
/stop - Stop the bot
/restart - Restart bot
/help - Show this help
        """
        await update.message.reply_text(help_text)

    async def cmd_stop(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("🛑 Stopping bot...")
        self.stop()

    async def cmd_pnl(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show P&L summary"""
        if self.paper_executor and hasattr(self.paper_executor, 'get_portfolio_value'):
            try:
                portfolio = self.paper_executor.get_portfolio_value()
                pnl_text = (
                    f"📈 P&L Summary:\n"
                    f"Total Return: ${portfolio.get('total_return', 0):,.2f}\n"
                    f"Return %: {portfolio.get('return_pct', 0):.2f}%\n"
                    f"Unrealized PnL: ${portfolio.get('unrealized_pnl', 0):,.2f}"
                )
                await update.message.reply_text(pnl_text)
                return
            except Exception as e:
                logger.error(f"Error getting PnL: {e}")
                
        await update.message.reply_text("📈 P&L Summary...")

    async def cmd_trade(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("💱 Trade execution panel...")

    async def cmd_markets(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("📊 Active markets...")

    async def cmd_alert(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("🔔 Alert settings...")

    async def cmd_settings(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("⚙️ Current settings...")

    async def cmd_restart(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("🔄 Restarting...")

    def start(self):
        """Start the bot in a separate thread with its own event loop"""
        if self.running:
            logger.warning("Bot already running")
            return
            
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        logger.info("Telegram bot thread started")

    def _run(self):
        """Internal run method that creates event loop and runs bot"""
        try:
            # Create new event loop for this thread
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            
            # Build application
            self.application = Application.builder().token(self.token).build()
            self.register_handlers()
            
            self.running = True
            logger.info("Telegram bot initialized in thread")
            
            # CRITICAL FIX: Disable signal handlers to avoid "main thread" error
            # stop_signals=None prevents signal registration which only works in main thread
            self.application.run_polling(
                drop_pending_updates=True,
                close_loop=False,
                stop_signals=None  # This fixes: set_wakeup_fd only works in main thread
            )
            
        except Exception as e:
            logger.error(f"Telegram bot error: {e}")
        finally:
            self.running = False
            if self._loop:
                try:
                    self._loop.close()
                except Exception:
                    pass

    def stop(self):
        """Stop the bot gracefully"""
        if self.application and self._loop:
            try:
                asyncio.run_coroutine_threadsafe(
                    self.application.stop(), 
                    self._loop
                )
            except Exception as e:
                logger.error(f"Error stopping bot: {e}")
        self.running = False
        logger.info("Telegram bot stopped")

    def send_message_sync(self, chat_id: int, message: str):
        """Send message synchronously from other threads"""
        if not self.running or not self._loop:
            logger.error("Bot not running, cannot send message")
            return
            
        try:
            # Create coroutine and run it in the bot's event loop
            async def _send():
                await self.application.bot.send_message(
                    chat_id=chat_id, 
                    text=message,
                    parse_mode='HTML'
                )
            
            future = asyncio.run_coroutine_threadsafe(_send(), self._loop)
            future.result(timeout=10)  # Wait for result
            
        except Exception as e:
            logger.error(f"Failed to send message: {e}")

    # Async methods for internal use
    async def send_message(self, chat_id: int, message: str):
        """Async method to send message"""
        if self.application:
            await self.application.bot.send_message(
                chat_id=chat_id, 
                text=message,
                parse_mode='HTML'
            )

    async def send_trade_notification(self, trade: Dict):
        """Send trade notification to configured chat"""
        if not self.config.get('notifications_enabled', True):
            return
            
        chat_id = self.config.get('chat_id')
        if not chat_id:
            logger.warning("No chat_id configured for notifications")
            return
            
        message = (
            f"📝 <b>Trade Executed</b>\n"
            f"Symbol: {trade.get('symbol')}\n"
            f"Side: {trade.get('side')}\n"
            f"Size: {trade.get('size')}\n"
            f"Price: ${trade.get('price', 0):.2f}"
        )
        
        await self.send_message(chat_id, message)

    async def send_opportunity_alert(self, opportunity: Dict):
        """Send opportunity alert"""
        chat_id = self.config.get('chat_id')
        if not chat_id:
            return
            
        message = (
            f"🔍 <b>Opportunity Detected</b>\n"
            f"Symbol: {opportunity.get('symbol')}\n"
            f"Signal: {opportunity.get('signal')}\n"
            f"Confidence: {opportunity.get('confidence', 0):.1%}"
        )
        
        await self.send_message(chat_id, message)

    async def send_closure_notification(self, market_id: str, winner: str, pnl: float, details: Dict = None):
        """Send market closure notification"""
        chat_id = self.config.get('chat_id')
        if not chat_id:
            return
            
        emoji = "🟢" if pnl >= 0 else "🔴"
        message = (
            f"{emoji} <b>Market Closed</b>\n"
            f"ID: {market_id}\n"
            f"Winner: {winner}\n"
            f"PnL: ${pnl:,.2f}"
        )
        
        await self.send_message(chat_id, message)
