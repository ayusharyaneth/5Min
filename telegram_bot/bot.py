import logging
import asyncio
import threading
from typing import Optional, Dict, Any
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler
from telegram.error import BadRequest

logger = logging.getLogger('Telegram')


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

    def register_handlers(self):
        """Register command handlers - RESTART REMOVED"""
        handlers = [
            CommandHandler("start", self.cmd_start),
            CommandHandler("status", self.cmd_status),
            CommandHandler("balance", self.cmd_balance),
            CommandHandler("positions", self.cmd_positions),
            CommandHandler("history", self.cmd_history),
            CommandHandler("help", self.cmd_help),
            # STOP REMOVED - use Ctrl+C
            CommandHandler("pnl", self.cmd_pnl),
            CommandHandler("trade", self.cmd_trade),
            CommandHandler("markets", self.cmd_markets),
            CommandHandler("alert", self.cmd_alert),
            CommandHandler("settings", self.cmd_settings),
            # RESTART COMMAND REMOVED
        ]
        
        for handler in handlers:
            self.application.add_handler(handler)
        
        # Callbacks
        self.application.add_handler(CallbackQueryHandler(self.refresh_balance_callback, pattern="^refresh_balance$"))
        self.application.add_handler(CallbackQueryHandler(self.refresh_history_callback, pattern="^refresh_history$"))
        self.application.add_handler(CallbackQueryHandler(self.refresh_pnl_callback, pattern="^refresh_pnl$"))
        self.application.add_handler(CallbackQueryHandler(self.refresh_status_callback, pattern="^refresh_status$"))
        self.application.add_handler(CallbackQueryHandler(self.toggle_auto_trade_callback, pattern="^toggle_auto_trade$"))
        
        logger.info("Commands loaded: 11")

    def get_refresh_markup(self, callback_data: str) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Refresh", callback_data=callback_data)]])

    async def safe_edit_message(self, update: Update, text: str, markup: InlineKeyboardMarkup):
        try:
            if update.callback_query:
                await update.callback_query.edit_message_text(text=text, parse_mode='HTML', reply_markup=markup)
            else:
                await update.message.reply_text(text, parse_mode='HTML', reply_markup=markup)
        except BadRequest as e:
            if "Message is not modified" in str(e):
                if update.callback_query:
                    await update.callback_query.answer("✓ Up to date")
        except Exception as e:
            logger.error(f"Edit failed: {e}")

    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        text = (
            "🤖 <b>5Min Trading Bot</b>\n\n"
            f"Trading: {'✓' if self.paper_executor else '✗'}\n"
            f"Markets: {'✓' if self.market_finder else '✗'}\n"
            f"Auto: {'ON' if self.config.get('auto_trade') else 'OFF'}\n\n"
            "Use /help"
        )
        await update.message.reply_text(text, parse_mode='HTML')

    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE, edit: bool = False):
        from datetime import datetime
        lines = ["📊 <b>Status</b>"]
        
        if self.paper_executor:
            try:
                pf = self.paper_executor.get_portfolio_value()
                ret = pf.get('total_return', 0)
                lines.append(f"💰 ${pf['total_value']:,.0f} ({'+' if ret>=0 else ''}${ret:,.0f})")
            except:
                lines.append("💰 Ready")
        else:
            lines.append("❌ Trading Offline")
        
        lines.append(f"🔍 Finder: {'✓' if self.market_finder else '✗'}")
        lines.append(f"🔒 Monitor: {'✓' if self.closure_checker else '✗'}")
        lines.append(f"⚡ Auto: {'ON' if self.config.get('auto_trade') else 'OFF'}")
        lines.append(f"\n<i>{datetime.now().strftime('%H:%M:%S')}</i>")
        
        text = "\n".join(lines)
        markup = self.get_refresh_markup("refresh_status")
        
        if edit: await self.safe_edit_message(update, text, markup)
        else: await update.message.reply_text(text, parse_mode='HTML', reply_markup=markup)

    async def refresh_status_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.callback_query.answer("Refreshing...")
        await self.cmd_status(update, context, edit=True)

    async def cmd_balance(self, update: Update, context: ContextTypes.DEFAULT_TYPE, edit: bool = False):
        if not self.paper_executor:
            text = "❌ Trading offline"
            if edit: await self.safe_edit_message(update, text, None)
            else: await update.message.reply_text(text)
            return
        
        try:
            pf = self.paper_executor.get_portfolio_value()
            from datetime import datetime
            text = (
                f"💰 <b>Balance</b> <i>{datetime.now().strftime('%H:%M')}</i>\n\n"
                f"Cash: ${pf['cash_balance']:,.2f}\n"
                f"Positions: ${pf['positions_value']:,.2f}\n"
                f"Total: ${pf['total_value']:,.2f}\n\n"
                f"PnL: {'🟢' if pf['total_return']>=0 else '🔴'} ${pf['total_return']:,.2f}"
            )
            markup = self.get_refresh_markup("refresh_balance")
            if edit: await self.safe_edit_message(update, text, markup)
            else: await update.message.reply_text(text, parse_mode='HTML', reply_markup=markup)
        except Exception as e:
            logger.error(f"Balance error: {e}")
            text = "❌ Error"
            if edit: await self.safe_edit_message(update, text, None)
            else: await update.message.reply_text(text)

    async def refresh_balance_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.callback_query.answer("Refreshing...")
        await self.cmd_balance(update, context, edit=True)

    async def cmd_positions(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self.paper_executor:
            await update.message.reply_text("❌ Offline")
            return
        
        positions = getattr(self.paper_executor, 'positions', {})
        if not positions:
            await update.message.reply_text("📭 No positions")
            return
        
        lines = ["📊 Positions"]
        for sym, pos in positions.items():
            lines.append(f"\n<b>{sym}</b>\n  {pos.get('quantity', 0)} @ ${pos.get('avg_entry_price', 0):,.2f}")
        
        await update.message.reply_text("\n".join(lines), parse_mode='HTML')

    async def cmd_history(self, update: Update, context: ContextTypes.DEFAULT_TYPE, edit: bool = False):
        if not self.paper_executor:
            text = "❌ Offline"
            if edit: await self.safe_edit_message(update, text, None)
            else: await update.message.reply_text(text)
            return
        
        history = []
        if hasattr(self.paper_executor, 'get_trade_history'):
            history = self.paper_executor.get_trade_history(limit=5)
        elif hasattr(self.paper_executor, 'trade_history'):
            history = self.paper_executor.trade_history[-5:]
        
        from datetime import datetime
        
        if not history:
            text = "📜 No trades yet"
            markup = self.get_refresh_markup("refresh_history")
            if edit: await self.safe_edit_message(update, text, markup)
            else: await update.message.reply_text(text, parse_mode='HTML', reply_markup=markup)
            return
        
        lines = [f"📜 Trades <i>{datetime.now().strftime('%H:%M')}</i>\n"]
        for t in history:
            emoji = '🟢' if t.get('side') == 'BUY' else '🔴'
            lines.append(f"{emoji} {t.get('symbol')} {t.get('side')} @ ${t.get('price', 0):,.2f}")
        
        text = "\n".join(lines)
        markup = self.get_refresh_markup("refresh_history")
        if edit: await self.safe_edit_message(update, text, markup)
        else: await update.message.reply_text(text, parse_mode='HTML', reply_markup=markup)

    async def refresh_history_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.callback_query.answer("Refreshing...")
        await self.cmd_history(update, context, edit=True)

    async def cmd_pnl(self, update: Update, context: ContextTypes.DEFAULT_TYPE, edit: bool = False):
        if not self.paper_executor:
            text = "❌ Offline"
            if edit: await self.safe_edit_message(update, text, None)
            else: await update.message.reply_text(text)
            return
        
        try:
            pf = self.paper_executor.get_portfolio_value()
            from datetime import datetime
            text = (
                f"📈 P&L <i>{datetime.now().strftime('%H:%M')}</i>\n\n"
                f"Return: ${pf['total_return']:,.2f} ({pf['return_pct']:.2f}%)\n"
                f"Unrealized: ${pf['unrealized_pnl']:,.2f}\n"
                f"Trades: {len(getattr(self.paper_executor, 'trade_history', []))}"
            )
            markup = self.get_refresh_markup("refresh_pnl")
            if edit: await self.safe_edit_message(update, text, markup)
            else: await update.message.reply_text(text, parse_mode='HTML', reply_markup=markup)
        except Exception as e:
            text = "❌ Error"
            if edit: await self.safe_edit_message(update, text, None)
            else: await update.message.reply_text(text)

    async def refresh_pnl_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.callback_query.answer("Refreshing...")
        await self.cmd_pnl(update, context, edit=True)

    async def cmd_trade(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self.paper_executor:
            await update.message.reply_text("❌ Offline")
            return
        
        bal = self.paper_executor.get_portfolio_value().get('cash_balance', 0)
        text = (
            f"💱 Trade\n\n"
            f"Available: ${bal:,.2f}\n\n"
            f"<code>/buy BTC-USD 0.5</code>\n"
            f"<code>/sell BTC-USD 0.5</code>"
        )
        await update.message.reply_text(text, parse_mode='HTML')

    async def cmd_markets(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        lines = ["📊 Markets"]
        
        if self.market_finder and hasattr(self.market_finder, 'find_active_btc_5m_markets'):
            try:
                markets = self.market_finder.find_active_btc_5m_markets()
                if markets:
                    lines.append(f"\nBTC 5m ({len(markets)}):")
                    for m in markets[:5]:
                        lines.append(f"• {m.get('symbol', m.get('market_id', '?'))}")
                else:
                    lines.append("\nNo active markets")
            except Exception as e:
                lines.append(f"\nError: {e}")
        else:
            lines.append("\nFinder offline")
        
        await update.message.reply_text("\n".join(lines), parse_mode='HTML')

    async def cmd_alert(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        text = (
            "🔔 Alerts\n\n"
            f"Status: {'✓ ON' if self.config.get('notifications_enabled', True) else '✗ OFF'}"
        )
        await update.message.reply_text(text, parse_mode='HTML')

    async def cmd_settings(self, update: Update, context: ContextTypes.DEFAULT_TYPE, edit: bool = False):
        from datetime import datetime
        is_auto = self.config.get('auto_trade', False)
        
        text = (
            f"⚙️ Settings <i>{datetime.now().strftime('%H:%M')}</i>\n\n"
            f"Auto-Trade: {'✓ ON' if is_auto else '✗ OFF'}\n"
            f"Size: {self.config.get('default_trade_size', '1.0')}\n"
            f"Interval: {self.config.get('check_interval', '60')}s\n\n"
            f"Trading: {'✓' if self.paper_executor else '✗'}\n"
            f"Finder: {'✓' if self.market_finder else '✗'}\n"
            f"Monitor: {'✓' if self.closure_checker else '✗'}"
        )
        
        toggle_btn = "🔴 Disable" if is_auto else "🟢 Enable"
        keyboard = [
            [InlineKeyboardButton(f"{toggle_btn} Auto", callback_data="toggle_auto_trade")],
            [InlineKeyboardButton("🔄 Refresh", callback_data="refresh_settings")]
        ]
        markup = InlineKeyboardMarkup(keyboard)
        
        if edit and update.callback_query:
            try:
                await update.callback_query.edit_message_text(text, parse_mode='HTML', reply_markup=markup)
            except BadRequest as e:
                if "Message is not modified" not in str(e):
                    raise
        else:
            await update.message.reply_text(text, parse_mode='HTML', reply_markup=markup)

    async def toggle_auto_trade_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        current = self.config.get('auto_trade', False)
        self.config['auto_trade'] = not current
        new_status = "ON" if self.config['auto_trade'] else "OFF"
        
        logger.info(f"Auto-Trade: {new_status}")
        await query.answer(f"Auto {new_status}")
        
        if self.market_finder:
            self.market_finder.config['auto_trade'] = self.config['auto_trade']
        
        await self.cmd_settings(update, context, edit=True)

    # RESTART METHOD COMPLETELY REMOVED

    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Help - RESTART REMOVED"""
        help_text = """
<b>Commands</b>

Account:
/balance - Balance ↻
/positions - Positions
/history - History ↻
/pnl - P&L ↻

Trading:
/markets - Markets
/trade - Trade panel
/settings - Config & Auto-Toggle

System:
/status - Status ↻
/start - Start
/help - Help

<i>↻ = Refresh button</i>

<b>Note:</b> Stop with Ctrl+C
        """
        await update.message.reply_text(help_text, parse_mode='HTML')

    def start(self):
        if self.running:
            return
        
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        logger.info("Polling started")

    def _run(self):
        try:
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            
            self.application = Application.builder().token(self.token).build()
            self.register_handlers()
            
            self.running = True
            logger.info("Bot active")
            
            self.application.run_polling(
                drop_pending_updates=True,
                close_loop=False,
                stop_signals=None
            )
        except Exception as e:
            logger.error(f"Bot error: {e}")
        finally:
            self.running = False
            if self._loop:
                try:
                    self._loop.close()
                except:
                    pass

    def stop(self):
        if self.application and self._loop:
            try:
                asyncio.run_coroutine_threadsafe(self.application.stop(), self._loop)
            except Exception as e:
                logger.error(f"Stop error: {e}")
        self.running = False

    async def send_trade_notification(self, trade: Dict):
        if not self.config.get('notifications_enabled', True):
            return
        chat_id = self.config.get('chat_id')
        if not chat_id:
            return
        msg = f"📝 {trade.get('symbol')} {trade.get('side')} {trade.get('size')} @ ${trade.get('price', 0):,.2f}"
        await self.application.bot.send_message(chat_id=chat_id, text=msg, parse_mode='HTML')

    async def send_opportunity_alert(self, opportunity: Dict):
        chat_id = self.config.get('chat_id')
        if not chat_id:
            return
        msg = f"🔍 {opportunity.get('symbol')} {opportunity.get('signal')} ({opportunity.get('confidence', 0):.0%})"
        await self.application.bot.send_message(chat_id=chat_id, text=msg, parse_mode='HTML')

    async def send_closure_notification(self, market_id: str, winner: str, pnl: float, details: Dict = None):
        chat_id = self.config.get('chat_id')
        if not chat_id:
            return
        emoji = "🟢" if pnl >= 0 else "🔴"
        msg = f"{emoji} Closed: {market_id}\nPnL: ${pnl:,.2f}"
        await self.application.bot.send_message(chat_id=chat_id, text=msg, parse_mode='HTML')
