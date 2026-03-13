import logging
import asyncio
import threading
from typing import Optional, Dict, Any, List
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler

logger = logging.getLogger(__name__)


class TelegramBotRunner:
    def __init__(self, 
                 token: str, 
                 config: Optional[Dict] = None,
                 dashboard: Any = None,
                 db: Any = None,
                 store: Any = None,
                 paper_executor: Any = None,
                 market_finder: Any = None,
                 closure_checker: Any = None,
                 **kwargs):
        """
        Initialize Telegram Bot Runner with full dependency injection
        """
        self.token = token
        self.config = config or {}
        self.dashboard = dashboard
        self.db = db
        self.store = store
        self.paper_executor = paper_executor
        self.market_finder = market_finder
        self.closure_checker = closure_checker
        
        for key, value in kwargs.items():
            setattr(self, key, value)
            
        self.application = None
        self.running = False
        self._loop = None
        self._thread = None
        
        logger.info(f"Bot initialized with: "
                   f"paper_executor={paper_executor is not None}, "
                   f"market_finder={market_finder is not None}, "
                   f"dashboard={dashboard is not None}")

    def register_handlers(self):
        """Register all command handlers and callback handlers"""
        # Command handlers
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
        
        # CRITICAL: Add callback query handlers for refresh buttons
        self.application.add_handler(CallbackQueryHandler(self.refresh_balance_callback, pattern="^refresh_balance$"))
        self.application.add_handler(CallbackQueryHandler(self.refresh_history_callback, pattern="^refresh_history$"))
        self.application.add_handler(CallbackQueryHandler(self.refresh_pnl_callback, pattern="^refresh_pnl$"))
        self.application.add_handler(CallbackQueryHandler(self.refresh_status_callback, pattern="^refresh_status$"))
        
        logger.info(f"Registered {len(handlers)} command handlers and 4 refresh callbacks")

    def get_refresh_markup(self, callback_data: str) -> InlineKeyboardMarkup:
        """Create refresh button markup"""
        keyboard = [[InlineKeyboardButton("🔄 Refresh", callback_data=callback_data)]]
        return InlineKeyboardMarkup(keyboard)

    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Welcome message with system status"""
        welcome_text = (
            "🤖 <b>5Min Trading Bot Started</b>\n\n"
            f"Paper Trading: {'✅ Active' if self.paper_executor else '❌ Not Connected'}\n"
            f"Market Finder: {'✅ Active' if self.market_finder else '❌ Not Connected'}\n"
            f"Closure Monitor: {'✅ Active' if self.closure_checker else '❌ Not Connected'}\n\n"
            "Use /help for available commands"
        )
        await update.message.reply_text(welcome_text, parse_mode='HTML')

    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE, edit: bool = False):
        """Show detailed system status with refresh button"""
        status_lines = ["📊 <b>System Status</b>"]
        
        # Check Paper Executor
        if self.paper_executor:
            try:
                portfolio = self.paper_executor.get_portfolio_value() if hasattr(self.paper_executor, 'get_portfolio_value') else None
                if portfolio:
                    status_lines.append(
                        f"💰 Balance: ${portfolio.get('total_value', 0):,.2f} "
                        f"({'🟢' if portfolio.get('total_return', 0) >= 0 else '🔴'} "
                        f"${portfolio.get('total_return', 0):,.2f})"
                    )
                else:
                    status_lines.append("💰 Paper Trading: Connected (no data yet)")
            except Exception as e:
                status_lines.append(f"💰 Paper Trading: Error ({str(e)})")
        else:
            status_lines.append("❌ Paper Trading: Not initialized")
        
        # Check Market Finder
        if self.market_finder:
            active_markets = len(self.market_finder.active_monitors) if hasattr(self.market_finder, 'active_monitors') else 0
            status_lines.append(f"🔍 Market Finder: Connected ({active_markets} monitors)")
        else:
            status_lines.append("❌ Market Finder: Not initialized")
            
        # Check Closure Checker
        if self.closure_checker:
            active = len(self.closure_checker.active_markets) if hasattr(self.closure_checker, 'active_markets') else 0
            status_lines.append(f"🔒 Closure Checker: Connected ({active} markets watching)")
        else:
            status_lines.append("❌ Closure Checker: Not initialized")
        
        # Check DB
        status_lines.append(f"🗄 Database: {'✅ Connected' if self.db else '❌ Not connected'}")
        
        text = "\n".join(status_lines)
        markup = self.get_refresh_markup("refresh_status")
        
        if edit and update.callback_query:
            await update.callback_query.edit_message_text(text, parse_mode='HTML', reply_markup=markup)
        else:
            await update.message.reply_text(text, parse_mode='HTML', reply_markup=markup)

    async def refresh_status_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle refresh button click for status"""
        query = update.callback_query
        await query.answer("Refreshing status...")  # Show loading popup
        await self.cmd_status(update, context, edit=True)

    async def cmd_balance(self, update: Update, context: ContextTypes.DEFAULT_TYPE, edit: bool = False):
        """Show actual balance from paper executor with refresh button"""
        if not self.paper_executor:
            text = (
                "❌ <b>Paper Trading not connected</b>\n"
                "The trading engine is not initialized. Check logs."
            )
            if edit and update.callback_query:
                await update.callback_query.edit_message_text(text, parse_mode='HTML')
            else:
                await update.message.reply_text(text, parse_mode='HTML')
            return
            
        try:
            if not hasattr(self.paper_executor, 'get_portfolio_value'):
                text = "❌ Paper executor missing get_portfolio_value method"
                if edit and update.callback_query:
                    await update.callback_query.edit_message_text(text, parse_mode='HTML')
                else:
                    await update.message.reply_text(text, parse_mode='HTML')
                return
                
            portfolio = self.paper_executor.get_portfolio_value()
            
            balance_text = (
                f"💰 <b>Portfolio Balance</b>\n\n"
                f"Cash: <code>${portfolio.get('cash_balance', 0):,.2f}</code>\n"
                f"Positions Value: <code>${portfolio.get('positions_value', 0):,.2f}</code>\n"
                f"Total Value: <code>${portfolio.get('total_value', 0):,.2f}</code>\n"
                f"Initial Balance: <code>${self.paper_executor.initial_balance:,.2f}</code>\n\n"
                f"Unrealized PnL: {'🟢' if portfolio.get('unrealized_pnl', 0) >= 0 else '🔴'} "
                f"<code>${portfolio.get('unrealized_pnl', 0):,.2f}</code>\n"
                f"Total Return: {'🟢' if portfolio.get('total_return', 0) >= 0 else '🔴'} "
                f"<code>${portfolio.get('total_return', 0):,.2f} ({portfolio.get('return_pct', 0):.2f}%)</code>"
            )
            
            markup = self.get_refresh_markup("refresh_balance")
            
            if edit and update.callback_query:
                await update.callback_query.edit_message_text(balance_text, parse_mode='HTML', reply_markup=markup)
            else:
                await update.message.reply_text(balance_text, parse_mode='HTML', reply_markup=markup)
            
        except Exception as e:
            logger.error(f"Balance error: {e}")
            text = f"❌ Error fetching balance: {str(e)}"
            if edit and update.callback_query:
                await update.callback_query.edit_message_text(text, parse_mode='HTML')
            else:
                await update.message.reply_text(text, parse_mode='HTML')

    async def refresh_balance_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle refresh button click for balance"""
        query = update.callback_query
        await query.answer("Refreshing balance...")  # Show loading popup
        await self.cmd_balance(update, context, edit=True)

    async def cmd_positions(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show open positions"""
        if not self.paper_executor:
            await update.message.reply_text("❌ Paper Trading not connected")
            return
            
        try:
            positions = getattr(self.paper_executor, 'positions', {})
            
            if not positions:
                await update.message.reply_text("📭 <b>No open positions</b>\nAll markets settled or no trades yet.", parse_mode='HTML')
                return
            
            pos_lines = ["📊 <b>Open Positions</b>\n"]
            
            for symbol, pos in positions.items():
                qty = pos.get('quantity', 0)
                avg_price = pos.get('avg_entry_price', 0)
                current_price = 0
                
                if hasattr(self.paper_executor, '_get_market_price'):
                    try:
                        current_price = self.paper_executor._get_market_price(symbol)
                    except:
                        pass
                
                if qty > 0 and current_price > 0:
                    pnl = (current_price - avg_price) * qty
                    pnl_emoji = '🟢' if pnl >= 0 else '🔴'
                    pos_lines.append(
                        f"<b>{symbol}</b>\n"
                        f"  Size: {qty}\n"
                        f"  Avg Entry: ${avg_price:,.2f}\n"
                        f"  Current: ${current_price:,.2f}\n"
                        f"  {pnl_emoji} PnL: ${pnl:,.2f}\n"
                    )
                else:
                    pos_lines.append(
                        f"<b>{symbol}</b>\n"
                        f"  Size: {qty}\n"
                        f"  Avg Entry: ${avg_price:,.2f}\n"
                    )
            
            await update.message.reply_text("\n".join(pos_lines), parse_mode='HTML')
            
        except Exception as e:
            logger.error(f"Positions error: {e}")
            await update.message.reply_text(f"❌ Error fetching positions: {str(e)}")

    async def cmd_history(self, update: Update, context: ContextTypes.DEFAULT_TYPE, edit: bool = False):
        """Show trade history with refresh button"""
        if not self.paper_executor:
            text = "❌ Paper Trading not connected"
            if edit and update.callback_query:
                await update.callback_query.edit_message_text(text, parse_mode='HTML')
            else:
                await update.message.reply_text(text, parse_mode='HTML')
            return
            
        try:
            history = []
            if hasattr(self.paper_executor, 'get_trade_history'):
                history = self.paper_executor.get_trade_history(limit=5)
            elif hasattr(self.paper_executor, 'trade_history'):
                history = self.paper_executor.trade_history[-5:]
            
            if not history:
                text = "📜 <b>No trade history yet</b>\nTrades will appear here once executed."
                markup = self.get_refresh_markup("refresh_history")
                if edit and update.callback_query:
                    await update.callback_query.edit_message_text(text, parse_mode='HTML', reply_markup=markup)
                else:
                    await update.message.reply_text(text, parse_mode='HTML', reply_markup=markup)
                return
            
            hist_lines = ["📜 <b>Recent Trades</b>\n"]
            
            for trade in history:
                side = trade.get('side', 'UNKNOWN')
                emoji = '🟢' if side == 'BUY' else '🔴' if side == 'SELL' else '⚪'
                
                hist_lines.append(
                    f"{emoji} <b>{trade.get('symbol', 'Unknown')}</b> {side}\n"
                    f"   Size: {trade.get('size', 0)}\n"
                    f"   Price: ${trade.get('price', 0):,.2f}\n"
                    f"   Total: ${trade.get('total_value', 0):,.2f}\n"
                    f"   Time: {trade.get('timestamp', 'Unknown')}\n"
                )
            
            markup = self.get_refresh_markup("refresh_history")
            text = "\n".join(hist_lines)
            
            if edit and update.callback_query:
                await update.callback_query.edit_message_text(text, parse_mode='HTML', reply_markup=markup)
            else:
                await update.message.reply_text(text, parse_mode='HTML', reply_markup=markup)
            
        except Exception as e:
            logger.error(f"History error: {e}")
            text = f"❌ Error fetching history: {str(e)}"
            if edit and update.callback_query:
                await update.callback_query.edit_message_text(text, parse_mode='HTML')
            else:
                await update.message.reply_text(text, parse_mode='HTML')

    async def refresh_history_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle refresh button click for history"""
        query = update.callback_query
        await query.answer("Refreshing history...")  # Show loading popup
        await self.cmd_history(update, context, edit=True)

    async def cmd_pnl(self, update: Update, context: ContextTypes.DEFAULT_TYPE, edit: bool = False):
        """Show P&L summary with refresh button"""
        if not self.paper_executor:
            text = "❌ Paper Trading not connected"
            if edit and update.callback_query:
                await update.callback_query.edit_message_text(text, parse_mode='HTML')
            else:
                await update.message.reply_text(text, parse_mode='HTML')
            return
            
        try:
            if not hasattr(self.paper_executor, 'get_portfolio_value'):
                text = "❌ Method not available"
                if edit and update.callback_query:
                    await update.callback_query.edit_message_text(text, parse_mode='HTML')
                else:
                    await update.message.reply_text(text, parse_mode='HTML')
                return
                
            portfolio = self.paper_executor.get_portfolio_value()
            total_return = portfolio.get('total_return', 0)
            return_pct = portfolio.get('return_pct', 0)
            
            pnl_text = (
                f"📈 <b>P&L Summary</b>\n\n"
                f"Total Return: {'🟢' if total_return >= 0 else '🔴'} ${total_return:,.2f}\n"
                f"Return %: {'🟢' if return_pct >= 0 else '🔴'} {return_pct:.2f}%\n\n"
                f"Unrealized PnL: ${portfolio.get('unrealized_pnl', 0):,.2f}\n"
                f"Realized PnL: ${portfolio.get('realized_pnl', 0):,.2f}\n"
                f"Total Trades: {len(getattr(self.paper_executor, 'trade_history', []))}"
            )
            
            markup = self.get_refresh_markup("refresh_pnl")
            
            if edit and update.callback_query:
                await update.callback_query.edit_message_text(pnl_text, parse_mode='HTML', reply_markup=markup)
            else:
                await update.message.reply_text(pnl_text, parse_mode='HTML', reply_markup=markup)
            
        except Exception as e:
            logger.error(f"PnL error: {e}")
            text = f"❌ Error calculating PnL: {str(e)}"
            if edit and update.callback_query:
                await update.callback_query.edit_message_text(text, parse_mode='HTML')
            else:
                await update.message.reply_text(text, parse_mode='HTML')

    async def refresh_pnl_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle refresh button click for PnL"""
        query = update.callback_query
        await query.answer("Refreshing P&L...")  # Show loading popup
        await self.cmd_pnl(update, context, edit=True)

    async def cmd_trade(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show trade execution panel with current market info"""
        if not self.paper_executor:
            await update.message.reply_text("❌ Paper Trading not connected")
            return
            
        try:
            portfolio = self.paper_executor.get_portfolio_value() if hasattr(self.paper_executor, 'get_portfolio_value') else {}
            balance = portfolio.get('cash_balance', 0)
            
            trade_text = (
                f"💱 <b>Trade Execution</b>\n\n"
                f"Available Balance: <code>${balance:,.2f}</code>\n\n"
                f"To place a trade, use format:\n"
                f"<code>/buy SYMBOL SIZE</code> or <code>/sell SYMBOL SIZE</code>\n\n"
                f"Example: <code>/buy BTC-USD 0.5</code>\n\n"
                f"Active Markets: Use /markets to see available symbols"
            )
            await update.message.reply_text(trade_text, parse_mode='HTML')
            
        except Exception as e:
            await update.message.reply_text(f"💱 Trade panel error: {str(e)}")

    async def cmd_markets(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show active markets from market_finder"""
        markets_text = ["📊 <b>Active Markets</b>\n"]
        
        if self.market_finder and hasattr(self.market_finder, 'find_active_btc_5m_markets'):
            try:
                btc_markets = self.market_finder.find_active_btc_5m_markets()
                if btc_markets:
                    markets_text.append(f"\n<b>BTC 5m Markets ({len(btc_markets)} found):</b>")
                    for m in btc_markets[:5]:
                        markets_text.append(f"• {m.get('symbol', m.get('market_id', 'Unknown'))}")
                else:
                    markets_text.append("\n<i>No BTC 5m markets currently active</i>")
            except Exception as e:
                markets_text.append(f"\n<i>Error loading markets: {str(e)}</i>")
        else:
            markets_text.append("\n<i>Market finder not connected</i>")
        
        if self.closure_checker and hasattr(self.closure_checker, 'get_active_markets'):
            try:
                active = self.closure_checker.get_active_markets()
                markets_text.append(f"\n<b>Markets Being Monitored:</b> {len(active)}")
                if active:
                    for m in active[:3]:
                        markets_text.append(f"• {m}")
            except:
                pass
        
        await update.message.reply_text("\n".join(markets_text), parse_mode='HTML')

    async def cmd_alert(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show and set price alerts"""
        alert_text = (
            "🔔 <b>Alert Settings</b>\n\n"
            f"Notification Status: {'✅ Enabled' if self.config.get('notifications_enabled', True) else '❌ Disabled'}\n"
            f"Chat ID: <code>{self.config.get('chat_id', 'Not set')}</code>\n\n"
            "Commands:\n"
            "/alert on - Enable notifications\n"
            "/alert off - Disable notifications"
        )
        await update.message.reply_text(alert_text, parse_mode='HTML')

    async def cmd_settings(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show bot settings"""
        settings_text = (
            "⚙️ <b>Bot Configuration</b>\n\n"
            f"Auto-Trade: {'✅ ON' if self.config.get('auto_trade', False) else '❌ OFF'}\n"
            f"Default Trade Size: {self.config.get('default_trade_size', 'Not set')}\n"
            f"Check Interval: {self.config.get('check_interval', '60')}s\n"
            f"Notifications: {'✅ ON' if self.config.get('notifications_enabled', True) else '❌ OFF'}\n\n"
            f"Connected Components:\n"
            f"  Paper Executor: {'✅' if self.paper_executor else '❌'}\n"
            f"  Market Finder: {'✅' if self.market_finder else '❌'}\n"
            f"  Closure Checker: {'✅' if self.closure_checker else '❌'}\n"
            f"  Database: {'✅' if self.db else '❌'}"
        )
        await update.message.reply_text(settings_text, parse_mode='HTML')

    async def cmd_stop(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Stop the bot"""
        await update.message.reply_text("🛑 <b>Stopping bot...</b>\nGoodbye!", parse_mode='HTML')
        self.stop()

    async def cmd_restart(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Restart command"""
        await update.message.reply_text("🔄 <b>Restarting...</b>\nPlease wait.", parse_mode='HTML')

    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show help"""
        help_text = """
<b>📱 Available Commands</b>

<b>Account Info:</b>
/balance - Show cash balance & portfolio value ↻
/positions - View open positions
/history - Recent trade history ↻
/pnl - Profit & Loss summary ↻

<b>Trading:</b>
/markets - List active markets
/trade - Trade execution panel
/alert - Alert settings

<b>System:</b>
/status - System health check ↻
/settings - Bot configuration
/start - Start message
/stop - Stop the bot
/restart - Restart bot
/help - Show this help

<i>↻ = Has refresh button</i>
        """
        await update.message.reply_text(help_text, parse_mode='HTML')

    def get_refresh_markup(self, callback_data: str) -> InlineKeyboardMarkup:
        """Helper method to create refresh button"""
        keyboard = [[InlineKeyboardButton("🔄 Refresh", callback_data=callback_data)]]
        return InlineKeyboardMarkup(keyboard)

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
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            
            self.application = Application.builder().token(self.token).build()
            self.register_handlers()
            
            self.running = True
            logger.info("Telegram bot initialized and polling...")
            
            self.application.run_polling(
                drop_pending_updates=True,
                close_loop=False,
                stop_signals=None
            )
            
        except Exception as e:
            logger.error(f"Telegram bot fatal error: {e}")
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

    def send_message_sync(self, chat_id: int, message: str):
        """Send message synchronously from other threads"""
        if not self.running or not self._loop:
            logger.error("Bot not running, cannot send message")
            return
            
        try:
            async def _send():
                await self.application.bot.send_message(
                    chat_id=chat_id, 
                    text=message,
                    parse_mode='HTML'
                )
            
            future = asyncio.run_coroutine_threadsafe(_send(), self._loop)
            future.result(timeout=10)
            
        except Exception as e:
            logger.error(f"Failed to send message: {e}")

    async def send_message(self, chat_id: int, message: str):
        """Async method to send message"""
        if self.application:
            await self.application.bot.send_message(
                chat_id=chat_id, 
                text=message,
                parse_mode='HTML'
            )

    async def send_trade_notification(self, trade: Dict):
        """Send trade notification"""
        if not self.config.get('notifications_enabled', True):
            return
            
        chat_id = self.config.get('chat_id')
        if not chat_id:
            return
            
        message = (
            f"📝 <b>Trade Executed</b>\n"
            f"Symbol: {trade.get('symbol')}\n"
            f"Side: {trade.get('side')}\n"
            f"Size: {trade.get('size')}\n"
            f"Price: ${trade.get('price', 0):,.2f}"
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
