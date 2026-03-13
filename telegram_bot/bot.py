import logging
import asyncio
import threading
from datetime import datetime
from typing import Optional, Dict, Any
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler
from telegram.error import BadRequest

# Setup IST timezone
try:
    import pytz
    IST = pytz.timezone('Asia/Kolkata')
except ImportError:
    # Fallback if pytz not installed
    from datetime import timezone, timedelta
    IST = timezone(timedelta(hours=5, minutes=30))

logger = logging.getLogger('Telegram')


def get_ist_time() -> datetime:
    """Get current time in IST"""
    return datetime.now(IST)


def format_ist_time(dt: Optional[datetime] = None, fmt: str = "%d-%m-%Y %H:%M:%S") -> str:
    """Format datetime to IST string"""
    if dt is None:
        dt = get_ist_time()
    elif dt.tzinfo is None:
        # If naive datetime, assume UTC and convert
        dt = dt.replace(tzinfo=timezone.utc).astimezone(IST)
    else:
        dt = dt.astimezone(IST)
    return dt.strftime(fmt) + " IST"


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
        """Minimal command set"""
        handlers = [
            CommandHandler("start", self.cmd_start),
            CommandHandler("status", self.cmd_status),
            CommandHandler("balance", self.cmd_balance),
            CommandHandler("positions", self.cmd_positions),
            CommandHandler("history", self.cmd_history),
            CommandHandler("pnl", self.cmd_pnl),
            CommandHandler("trade", self.cmd_trade),
            CommandHandler("markets", self.cmd_markets),
            CommandHandler("settings", self.cmd_settings),
            CommandHandler("help", self.cmd_help),
            # /stop and /restart removed as requested
        ]
        
        for handler in handlers:
            self.application.add_handler(handler)
        
        # Callbacks
        self.application.add_handler(CallbackQueryHandler(self.refresh_callback, pattern="^refresh_"))
        self.application.add_handler(CallbackQueryHandler(self.toggle_callback, pattern="^toggle_"))
        
        logger.info("UI Loaded")

    def _get_refresh_btn(self, cmd: str) -> InlineKeyboardMarkup:
        """Single refresh button"""
        return InlineKeyboardMarkup([[InlineKeyboardButton("↻ Refresh", callback_data=f"refresh_{cmd}")]])

    def _safe_edit(self, update: Update, text: str, markup=None):
        """Safe message edit"""
        try:
            if update.callback_query:
                update.callback_query.edit_message_text(text, parse_mode='MarkdownV2', reply_markup=markup, disable_web_page_preview=True)
            else:
                update.message.reply_text(text, parse_mode='MarkdownV2', reply_markup=markup, disable_web_page_preview=True)
        except BadRequest as e:
            if "not modified" in str(e).lower():
                if update.callback_query:
                    update.callback_query.answer("Updated")
            else:
                # Escape markdown errors
                try:
                    if update.callback_query:
                        update.callback_query.edit_message_text(text, reply_markup=markup)
                    else:
                        update.message.reply_text(text, reply_markup=markup)
                except:
                    pass

    def _escape_md(self, text: str) -> str:
        """Escape markdown special chars"""
        chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
        for char in chars:
            text = text.replace(char, f'\\{char}')
        return text

    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Clean welcome"""
        time_str = format_ist_time()
        text = (
            f"*5Min Trading Bot*\n"
            f"`{time_str}`\n\n"
            f"Mode: `{self.trading_mode.upper() if hasattr(self, 'trading_mode') else 'PAPER'}`\n"
            f"Auto\\-Trade: `{'ON' if self.config.get('auto_trade') else 'OFF'}`\n\n"
            f"Use /help for commands"
        )
        await update.message.reply_text(text, parse_mode='MarkdownV2')

    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE, edit=False):
        """Minimal status view"""
        lines = ["*Status*"]
        
        # Trading status
        if self.paper_executor:
            try:
                pf = self.paper_executor.get_portfolio_value()
                total = pf.get('total_value', 0)
                ret = pf.get('total_return', 0)
                ret_icon = "+" if ret >= 0 else ""
                lines.append(f"Balance: `${total:,.2f}` ({ret_icon}{ret:,.2f})")
            except:
                lines.append("Balance: `--`")
        else:
            lines.append("Status: Offline")
        
        # Components
        comp = []
        if self.market_finder: comp.append("Markets")
        if self.closure_checker: comp.append("Monitor")
        if comp:
            lines.append(f"Active: {', '.join(comp)}")
        
        # Time
        lines.append(f"`{format_ist_time()}`")
        
        text = '\n'.join(lines)
        markup = self._get_refresh_btn("status")
        
        self._safe_edit(update if edit else None, text, markup)

    async def cmd_balance(self, update: Update, context: ContextTypes.DEFAULT_TYPE, edit=False):
        """Clean balance view"""
        if not self.paper_executor:
            text = "Trading offline"
            if edit:
                self._safe_edit(update, text)
            else:
                await update.message.reply_text(text)
            return
        
        try:
            pf = self.paper_executor.get_portfolio_value()
            
            text = (
                f"*Portfolio*\n\n"
                f"Cash: `${pf['cash_balance']:,.2f}`\n"
                f"Positions: `${pf['positions_value']:,.2f}`\n"
                f"Total: `${pf['total_value']:,.2f}`\n\n"
                f"P&L: `${pf['total_return']:+,.2f}` \\({pf['return_pct']:+.2f}%\\)\n"
                f"`{format_ist_time()}`"
            )
            
            markup = self._get_refresh_btn("balance")
            self._safe_edit(update if edit else None, text, markup)
            
        except Exception as e:
            text = f"Error: {str(e)}"
            self._safe_edit(update if edit else None, text)

    async def cmd_positions(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """List positions cleanly"""
        if not self.paper_executor:
            await update.message.reply_text("Offline")
            return
        
        positions = getattr(self.paper_executor, 'positions', {})
        if not positions:
            await update.message.reply_text("No open positions")
            return
        
        lines = ["*Positions*"]
        for sym, pos in positions.items():
            qty = pos.get('quantity', 0)
            price = pos.get('avg_entry_price', 0)
            lines.append(f"{sym}: `{qty}` @ `${price:,.2f}`")
        
        lines.append(f"\n`{format_ist_time()}`")
        await update.message.reply_text('\n'.join(lines), parse_mode='MarkdownV2')

    async def cmd_history(self, update: Update, context: ContextTypes.DEFAULT_TYPE, edit=False):
        """Recent trades"""
        if not self.paper_executor:
            text = "Offline"
            self._safe_edit(update if edit else None, text)
            return
        
        history = []
        if hasattr(self.paper_executor, 'get_trade_history'):
            history = self.paper_executor.get_trade_history(limit=5)
        elif hasattr(self.paper_executor, 'trade_history'):
            history = self.paper_executor.trade_history[-5:]
        
        if not history:
            text = f"*History*\n\nNo trades yet\n\n`{format_ist_time()}`"
            markup = self._get_refresh_btn("history")
            self._safe_edit(update if edit else None, text, markup)
            return
        
        lines = [f"*Last {len(history)} Trades*"]
        
        for trade in history:
            side = trade.get('side', '?')
            symbol = trade.get('symbol', '?')
            size = trade.get('size', 0)
            price = trade.get('price', 0)
            ts = trade.get('timestamp')
            
            # Format time if available
            time_str = ""
            if ts:
                if isinstance(ts, str):
                    try:
                        from dateutil import parser
                        dt = parser.parse(ts)
                        time_str = format_ist_time(dt, "%H:%M")
                    except:
                        time_str = str(ts)[:5]
                else:
                    time_str = format_ist_time(ts, "%H:%M")
            
            icon = "▲" if side == "BUY" else "▼"
            lines.append(f"{icon} {symbol} `{side}` {size} @ ${price:,.2f} {time_str}")
        
        lines.append(f"\n`{format_ist_time()}`")
        text = '\n'.join(lines)
        markup = self._get_refresh_btn("history")
        
        self._safe_edit(update if edit else None, text, markup)

    async def cmd_pnl(self, update: Update, context: ContextTypes.DEFAULT_TYPE, edit=False):
        """P&L summary"""
        if not self.paper_executor:
            text = "Offline"
            self._safe_edit(update if edit else None, text)
            return
        
        try:
            pf = self.paper_executor.get_portfolio_value()
            trades = len(getattr(self.paper_executor, 'trade_history', []))
            
            text = (
                f"*P&L Summary*\n\n"
                f"Total Return: `${pf['total_return']:+,.2f}`\n"
                f"Return %: `{pf['return_pct']:+.2f}%`\n"
                f"Unrealized: `${pf['unrealized_pnl']:,.2f}`\n\n"
                f"Total Trades: `{trades}`\n"
                f"`{format_ist_time()}`"
            )
            
            markup = self._get_refresh_btn("pnl")
            self._safe_edit(update if edit else None, text, markup)
            
        except Exception as e:
            self._safe_edit(update if edit else None, f"Error: {str(e)}")

    async def cmd_trade(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Trade panel"""
        if not self.paper_executor:
            await update.message.reply_text("Offline")
            return
        
        try:
            pf = self.paper_executor.get_portfolio_value()
            bal = pf.get('cash_balance', 0)
            
            text = (
                f"*New Trade*\n\n"
                f"Available: `${bal:,.2f}`\n\n"
                f"Format:\n"
                f"`/buy BTC 0.5`\n"
                f"`/sell ETH 1.0`"
            )
            await update.message.reply_text(text, parse_mode='MarkdownV2')
        except:
            await update.message.reply_text("Error loading balance")

    async def cmd_markets(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Active markets"""
        lines = ["*Markets*"]
        
        if self.market_finder and hasattr(self.market_finder, 'find_active_btc_5m_markets'):
            try:
                markets = self.market_finder.find_active_btc_5m_markets()
                if markets:
                    lines.append(f"Found {len(markets)} active:\\n")
                    for m in markets[:5]:
                        sym = m.get('symbol', '?')
                        lines.append(f"• {sym}")
                else:
                    lines.append("No active markets")
            except Exception as e:
                lines.append(f"Error: {str(e)}")
        else:
            lines.append("Market finder offline")
        
        lines.append(f"\n`{format_ist_time()}`")
        await update.message.reply_text('\n'.join(lines), parse_mode='MarkdownV2')

    async def cmd_settings(self, update: Update, context: ContextTypes.DEFAULT_TYPE, edit=False):
        """Settings with toggle"""
        is_auto = self.config.get('auto_trade', False)
        mode = self.config.get('trading_mode', 'paper').upper()
        
        text = (
            f"*Settings*\n\n"
            f"Mode: `{mode}`\n"
            f"Auto\\-Trade: `{'ON' if is_auto else 'OFF'}`\n"
            f"Trade Size: `{self.config.get('default_trade_size', '1.0')}`\n\n"
            f"Components:\n"
            f"Trading: `{'Yes' if self.paper_executor else 'No'}`\n"
            f"Markets: `{'Yes' if self.market_finder else 'No'}`\n\n"
            f"`{format_ist_time()}`"
        )
        
        # Toggle button
        btn_text = "Disable Auto" if is_auto else "Enable Auto"
        keyboard = [
            [InlineKeyboardButton(btn_text, callback_data="toggle_auto")],
            [InlineKeyboardButton("↻ Refresh", callback_data="refresh_settings")]
        ]
        markup = InlineKeyboardMarkup(keyboard)
        
        if edit and update.callback_query:
            try:
                await update.callback_query.edit_message_text(
                    text, parse_mode='MarkdownV2', reply_markup=markup
                )
            except BadRequest:
                await update.callback_query.edit_message_text(text, reply_markup=markup)
        else:
            try:
                await update.message.reply_text(text, parse_mode='MarkdownV2', reply_markup=markup)
            except:
                await update.message.reply_text(text, reply_markup=markup)

    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Minimal help"""
        text = (
            f"*Commands*\n\n"
            f"/balance \\- Portfolio\n"
            f"/positions \\- Holdings\n"
            f"/history \\- Trades\n"
            f"/pnl \\- P&L\n"
            f"/markets \\- Markets\n"
            f"/trade \\- Trade\n"
            f"/status \\- Status\n"
            f"/settings \\- Config\n\n"
            f"`{format_ist_time()}`\n"
            f"_IST \\(UTC\\+5:30\\)_"
        )
        await update.message.reply_text(text, parse_mode='MarkdownV2')

    # Callback handlers
    async def refresh_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle all refresh buttons"""
        query = update.callback_query
        data = query.data.replace("refresh_", "")
        
        await query.answer("Updating...")
        
        if data == "status":
            await self.cmd_status(update, context, edit=True)
        elif data == "balance":
            await self.cmd_balance(update, context, edit=True)
        elif data == "history":
            await self.cmd_history(update, context, edit=True)
        elif data == "pnl":
            await self.cmd_pnl(update, context, edit=True)
        elif data == "settings":
            await self.cmd_settings(update, context, edit=True)

    async def toggle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle toggle buttons"""
        query = update.callback_query
        
        if query.data == "toggle_auto":
            current = self.config.get('auto_trade', False)
            self.config['auto_trade'] = not current
            
            await query.answer(f"Auto: {'ON' if self.config['auto_trade'] else 'OFF'}")
            
            # Update market_finder if exists
            if self.market_finder:
                self.market_finder.config['auto_trade'] = self.config['auto_trade']
            
            await self.cmd_settings(update, context, edit=True)

    def start(self):
        if self.running:
            return
        
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        try:
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            
            self.application = Application.builder().token(self.token).build()
            self.register_handlers()
            
            self.running = True
            
            self.application.run_polling(
                drop_pending_updates=True,
                close_loop=False,
                stop_signals=None
            )
        except Exception as e:
            logger.error(f"Error: {e}")
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
            except:
                pass
        self.running = False

    # Notification methods
    async def send_message(self, chat_id: int, message: str):
        if self.application:
            try:
                await self.application.bot.send_message(
                    chat_id=chat_id, 
                    text=message,
                    parse_mode='MarkdownV2'
                )
            except:
                await self.application.bot.send_message(chat_id=chat_id, text=message)

    async def send_trade_notification(self, trade: Dict):
        if not self.config.get('notifications_enabled', True):
            return
        chat_id = self.config.get('chat_id')
        if not chat_id:
            return
        
        text = (
            f"*Trade Executed*\n\n"
            f"{trade.get('symbol')} {trade.get('side')}\n"
            f"Size: `{trade.get('size')}`\n"
            f"Price: `${trade.get('price', 0):,.2f}`\n\n"
            f"`{format_ist_time()}`"
        )
        
        try:
            await self.application.bot.send_message(
                chat_id=chat_id, 
                text=text,
                parse_mode='MarkdownV2'
            )
        except:
            pass

    async def send_opportunity_alert(self, opportunity: Dict):
        chat_id = self.config.get('chat_id')
        if not chat_id:
            return
        
        text = (
            f"*Signal*\n\n"
            f"{opportunity.get('symbol')}\n"
            f"Direction: `{opportunity.get('signal')}`\n"
            f"Confidence: `{opportunity.get('confidence', 0):.0%}`\n\n"
            f"`{format_ist_time()}`"
        )
        
        try:
            await self.application.bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode='MarkdownV2'
            )
        except:
            pass

    async def send_closure_notification(self, market_id: str, winner: str, pnl: float, details: Dict = None):
        chat_id = self.config.get('chat_id')
        if not chat_id:
            return
        
        icon = "✓" if pnl >= 0 else "✗"
        text = (
            f"*Market Closed* {icon}\n\n"
            f"ID: `{market_id[:15]}...`\n"
            f"Result: `{winner}`\n"
            f"P&L: `${pnl:,.2f}`\n\n"
            f"`{format_ist_time()}`"
        )
        
        try:
            await self.application.bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode='MarkdownV2'
            )
        except:
            pass
