import logging
import asyncio
import threading
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler
from telegram.error import BadRequest

# IST Timezone
try:
    import pytz
    IST = pytz.timezone('Asia/Kolkata')
except ImportError:
    IST = timezone(timedelta(hours=5, minutes=30))

logger = logging.getLogger('Telegram')


def get_ist_now() -> datetime:
    return datetime.now(IST)


def fmt_ist(dt: Optional[datetime] = None, fmt: str = "%d %b %Y, %I:%M %p") -> str:
    if dt is None:
        dt = get_ist_now()
    elif dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(IST).strftime(fmt)


class TelegramBotRunner:
    def __init__(self, token: str, config: Optional[Dict] = None, **kwargs):
        self.token = token
        self.config = config or {}
        
        # Store components properly
        self.paper_executor = kwargs.get('paper_executor')
        self.live_executor = kwargs.get('live_executor')
        self.market_finder = kwargs.get('market_finder')
        self.paper_enabled = kwargs.get('paper_enabled', False)
        self.live_enabled = kwargs.get('live_enabled', False)
        
        self.app = None
        self.running = False
        self._loop = None
        self._thread = None
        
        # Log what we received
        logger.info(f"Bot initialized: Paper={self.paper_executor is not None}, Live={self.live_executor is not None}")

    def register_handlers(self):
        handlers = [
            CommandHandler("start", self.cmd_start),
            CommandHandler("menu", self.cmd_menu),
            CommandHandler("balance", self.cmd_balance),
            CommandHandler("positions", self.cmd_positions),
            CommandHandler("history", self.cmd_history),
            CommandHandler("pnl", self.cmd_pnl),
            CommandHandler("markets", self.cmd_markets),
            CommandHandler("settings", self.cmd_settings),
            CommandHandler("help", self.cmd_help),
        ]
        
        for h in handlers:
            self.app.add_handler(h)
        
        self.app.add_handler(CallbackQueryHandler(self.handle_callback))
        logger.info("Handlers registered")

    def _back_btn(self) -> InlineKeyboardButton:
        """Back to menu button"""
        return InlineKeyboardButton("⬅️ Back to Menu", callback_data="nav_menu")

    def _nav_row(self, current: str) -> List[InlineKeyboardButton]:
        """Navigation row with refresh"""
        return [
            InlineKeyboardButton("↻ Refresh", callback_data=f"refresh_{current}"),
            self._back_btn()
        ]

    async def _send_or_edit(self, update: Update, text: str, keyboard=None, edit=False):
        """Safe send/edit with fallback"""
        try:
            if edit and update.callback_query:
                await update.callback_query.edit_message_text(
                    text=text,
                    reply_markup=keyboard,
                    parse_mode='Markdown',
                    disable_web_page_preview=True
                )
            else:
                await update.message.reply_text(
                    text=text,
                    reply_markup=keyboard,
                    parse_mode='Markdown',
                    disable_web_page_preview=True
                )
        except Exception as e:
            logger.error(f"Send/edit error: {e}")
            # Fallback without markdown
            plain = text.replace('*', '').replace('_', '').replace('`', '')
            try:
                if edit and update.callback_query:
                    await update.callback_query.edit_message_text(text=plain, reply_markup=keyboard)
                else:
                    await update.message.reply_text(text=plain, reply_markup=keyboard)
            except:
                pass

    def _get_system_status(self) -> str:
        """Get current system status text"""
        status = []
        if self.paper_executor:
            status.append("📘 Paper: Online")
        else:
            status.append("📘 Paper: Offline")
            
        if self.live_executor:
            status.append("💰 Live: Online")
        else:
            status.append("💰 Live: Offline")
            
        return "\n".join(status)

    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Welcome with system status"""
        status = self._get_system_status()
        
        text = (
            f"*5Min Trading Bot* 🤖\n\n"
            f"{status}\n\n"
            f"⏰ {fmt_ist()}\n\n"
            f"Select an option below:"
        )
        
        keyboard = [[InlineKeyboardButton("📱 Open Menu", callback_data="nav_menu")]]
        await self._send_or_edit(update, text, InlineKeyboardMarkup(keyboard))

    async def cmd_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE, edit=False):
        """Main menu dashboard"""
        # Get quick stats
        paper_bal = "Offline"
        live_bal = "Offline"
        
        if self.paper_executor:
            try:
                pf = self.paper_executor.get_portfolio_value()
                paper_bal = f"${pf.get('total_value', 0):,.2f}"
            except:
                paper_bal = "Error"
        
        if self.live_executor:
            try:
                pf = self.live_executor.get_portfolio_value()
                live_bal = f"${pf.get('total_value', 0):,.2f} USDC"
            except:
                live_bal = "Error"
        
        text = (
            f"*📱 Dashboard*\n\n"
            f"📘 Paper Balance: `{paper_bal}`\n"
            f"💰 Live Balance: `{live_bal}`\n"
            f"⏰ {fmt_ist()}\n\n"
            f"Select option:"
        )
        
        keyboard = [
            [InlineKeyboardButton("💰 Balance", callback_data="nav_balance"),
             InlineKeyboardButton("📊 Markets", callback_data="nav_markets")],
            [InlineKeyboardButton("📜 History", callback_data="nav_history"),
             InlineKeyboardButton("📈 P&L", callback_data="nav_pnl")],
            [InlineKeyboardButton("⚙️ Settings", callback_data="nav_settings"),
             InlineKeyboardButton("❓ Help", callback_data="nav_help")],
        ]
        
        await self._send_or_edit(update, text, InlineKeyboardMarkup(keyboard), edit)

    async def cmd_balance(self, update: Update, context: ContextTypes.DEFAULT_TYPE, edit=False):
        """Show both balances with back button"""
        lines = ["*💰 Account Balances*\n"]
        
        # Paper balance
        if self.paper_executor:
            try:
                pf = self.paper_executor.get_portfolio_value()
                lines.append(
                    f"*Paper Account*\n"
                    f"Cash: `${pf['cash_balance']:,.2f}`\n"
                    f"Positions: `${pf['positions_value']:,.2f}`\n"
                    f"Total: `{pf['total_value']:,.2f}`\n"
                    f"PnL: `{pf['total_return']:+,.2f}` ({pf['return_pct']:+.2f}%)\n"
                )
            except Exception as e:
                lines.append(f"*Paper Account*\nError: {str(e)[:50]}\n")
        else:
            lines.append("*Paper Account*\n_Status: Offline_\n")
        
        # Live balance
        if self.live_executor:
            try:
                pf = self.live_executor.get_portfolio_value()
                lines.append(
                    f"\n*Live Account*\n"
                    f"USDC: `{pf.get('cash_balance', 0):,.2f}`\n"
                    f"Wallet: `{pf.get('wallet', 'N/A')[:10]}...`\n"
                )
            except Exception as e:
                lines.append(f"\n*Live Account*\nError: {str(e)[:50]}\n")
        else:
            lines.append(f"\n*Live Account*\n_Status: Offline_")
        
        lines.append(f"\n⏰ {fmt_ist()}")
        
        keyboard = InlineKeyboardMarkup([self._nav_row("balance")])
        await self._send_or_edit(update, "\n".join(lines), keyboard, edit)

    async def cmd_positions(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show positions with back button"""
        lines = ["*📊 Open Positions*\n"]
        
        if not self.paper_executor and not self.live_executor:
            lines.append("❌ Trading systems offline")
            lines.append(f"\n⏰ {fmt_ist()}")
            keyboard = InlineKeyboardMarkup([[self._back_btn()]])
            await self._send_or_edit(update, "\n".join(lines), keyboard)
            return
        
        # Paper positions
        if self.paper_executor:
            try:
                positions = getattr(self.paper_executor, 'positions', {})
                if positions:
                    lines.append("*Paper Positions:*")
                    for sym, pos in positions.items():
                        lines.append(f"• {sym}: `{pos.get('quantity', 0)}` @ `${pos.get('avg_entry_price', 0):,.2f}`")
                else:
                    lines.append("*Paper:* No open positions")
            except Exception as e:
                lines.append(f"*Paper:* Error loading")
        
        lines.append(f"\n⏰ {fmt_ist()}")
        keyboard = InlineKeyboardMarkup([[self._back_btn()]])
        await self._send_or_edit(update, "\n".join(lines), keyboard)

    async def cmd_history(self, update: Update, context: ContextTypes.DEFAULT_TYPE, edit=False):
        """Trade history with back button"""
        if not self.paper_executor:
            text = (
                "*📜 Trade History*\n\n"
                "❌ Paper trading offline\n\n"
                f"⏰ {fmt_ist()}"
            )
            keyboard = InlineKeyboardMarkup([self._nav_row("history")])
            await self._send_or_edit(update, text, keyboard, edit)
            return
        
        try:
            history = []
            if hasattr(self.paper_executor, 'get_trade_history'):
                history = self.paper_executor.get_trade_history(limit=5)
            elif hasattr(self.paper_executor, 'trade_history'):
                history = self.paper_executor.trade_history[-5:]
            
            if not history:
                text = (
                    "*📜 Trade History*\n\n"
                    "No trades yet\n\n"
                    f"⏰ {fmt_ist()}"
                )
            else:
                lines = [f"*📜 Last {len(history)} Trades*\n"]
                for trade in history:
                    side = trade.get('side', '?')
                    symbol = trade.get('symbol', '?')
                    size = trade.get('size', 0)
                    price = trade.get('price', 0)
                    icon = "🟢" if side == "BUY" else "🔴"
                    lines.append(f"{icon} {symbol} `{side}` {size} @ ${price:,.2f}")
                
                lines.append(f"\n⏰ {fmt_ist()}")
                text = "\n".join(lines)
            
            keyboard = InlineKeyboardMarkup([self._nav_row("history")])
            await self._send_or_edit(update, text, keyboard, edit)
            
        except Exception as e:
            text = f"*📜 Trade History*\n\n❌ Error: {str(e)[:100]}\n\n⏰ {fmt_ist()}"
            keyboard = InlineKeyboardMarkup([[self._back_btn()]])
            await self._send_or_edit(update, text, keyboard, edit)

    async def cmd_pnl(self, update: Update, context: ContextTypes.DEFAULT_TYPE, edit=False):
        """P&L with back button"""
        if not self.paper_executor:
            text = (
                "*📈 Performance Summary*\n\n"
                "❌ Trading offline\n\n"
                f"⏰ {fmt_ist()}"
            )
            keyboard = InlineKeyboardMarkup([self._nav_row("pnl")])
            await self._send_or_edit(update, text, keyboard, edit)
            return
        
        try:
            pf = self.paper_executor.get_portfolio_value()
            trades = len(getattr(self.paper_executor, 'trade_history', []))
            icon = "🟢" if pf['total_return'] >= 0 else "🔴"
            
            text = (
                f"*📈 Performance Summary*\n\n"
                f"{icon} Total Return: `${pf['total_return']:+,.2f}`\n"
                f"📊 Return %: `{pf['return_pct']:+.2f}%`\n"
                f"💵 Unrealized: `${pf['unrealized_pnl']:,.2f}`\n"
                f"📝 Total Trades: `{trades}`\n\n"
                f"⏰ {fmt_ist()}"
            )
            
            keyboard = InlineKeyboardMarkup([self._nav_row("pnl")])
            await self._send_or_edit(update, text, keyboard, edit)
            
        except Exception as e:
            text = f"*📈 Performance*\n\n❌ Error loading data\n\n⏰ {fmt_ist()}"
            keyboard = InlineKeyboardMarkup([[self._back_btn()]])
            await self._send_or_edit(update, text, keyboard, edit)

    async def cmd_markets(self, update: Update, context: ContextTypes.DEFAULT_TYPE, edit=False):
        """Markets with back button"""
        if not self.market_finder:
            text = (
                "*📊 Markets*\n\n"
                "❌ Market finder offline\n\n"
                f"⏰ {fmt_ist()}"
            )
            keyboard = InlineKeyboardMarkup([self._nav_row("markets")])
            await self._send_or_edit(update, text, keyboard, edit)
            return
        
        try:
            markets = self.market_finder.find_active_btc_5m_markets()
            
            if not markets:
                text = (
                    "*📊 Markets*\n\n"
                    "No active markets found\n"
                    "_Check configuration or wait for markets to open_\n\n"
                    f"⏰ {fmt_ist()}"
                )
            else:
                lines = [f"*📊 Active Markets* ({len(markets)} found)\n"]
                for m in markets[:5]:
                    sym = m.get('symbol', 'Unknown')
                    lines.append(f"• {sym}")
                lines.append(f"\n⏰ {fmt_ist()}")
                text = "\n".join(lines)
            
            keyboard = InlineKeyboardMarkup([self._nav_row("markets")])
            await self._send_or_edit(update, text, keyboard, edit)
            
        except Exception as e:
            text = f"*📊 Markets*\n\n❌ Error: {str(e)[:100]}\n\n⏰ {fmt_ist()}"
            keyboard = InlineKeyboardMarkup([[self._back_btn()]])
            await self._send_or_edit(update, text, keyboard, edit)

    async def cmd_settings(self, update: Update, context: ContextTypes.DEFAULT_TYPE, edit=False):
        """Settings with toggle and back button"""
        is_auto = self.config.get('auto_trade', False)
        
        text = (
            f"*⚙️ Settings*\n\n"
            f"🤖 Auto-Trade: `{'ON ✅' if is_auto else 'OFF ❌'}`\n"
            f"💵 Trade Size: `{self.config.get('default_trade_size', 1.0)}`\n\n"
            f"System Status:\n"
            f"📘 Paper: `{'Online' if self.paper_executor else 'Offline'}`\n"
            f"💰 Live: `{'Online' if self.live_executor else 'Offline'}`\n\n"
            f"⏰ {fmt_ist()}"
        )
        
        toggle_text = "🔴 Disable Auto" if is_auto else "🟢 Enable Auto"
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(toggle_text, callback_data="toggle_auto")],
            [InlineKeyboardButton("↻ Refresh", callback_data="refresh_settings"),
             self._back_btn()]
        ])
        
        await self._send_or_edit(update, text, keyboard, edit)

    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE, edit=False):
        """Help with back button"""
        text = (
            f"*📖 Help Guide*\n\n"
            f"*Commands:*\n"
            f"/menu - Main dashboard\n"
            f"/balance - View balances\n"
            f"/positions - Open positions\n"
            f"/markets - Active markets\n"
            f"/history - Trade history\n"
            f"/pnl - Performance stats\n"
            f"/settings - Configuration\n\n"
            f"⏰ All times in IST (UTC+5:30)\n"
            f"{fmt_ist()}"
        )
        
        keyboard = InlineKeyboardMarkup([[self._back_btn()]])
        await self._send_or_edit(update, text, keyboard, edit)

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle all callbacks"""
        query = update.callback_query
        data = query.data
        
        try:
            if data.startswith("nav_"):
                page = data.replace("nav_", "")
                await query.answer(f"Loading {page}...")
                
                if page == "menu":
                    await self.cmd_menu(update, context, edit=True)
                elif page == "balance":
                    await self.cmd_balance(update, context, edit=True)
                elif page == "markets":
                    await self.cmd_markets(update, context, edit=True)
                elif page == "history":
                    await self.cmd_history(update, context, edit=True)
                elif page == "pnl":
                    await self.cmd_pnl(update, context, edit=True)
                elif page == "settings":
                    await self.cmd_settings(update, context, edit=True)
                elif page == "help":
                    await self.cmd_help(update, context, edit=True)
                    
            elif data.startswith("refresh_"):
                page = data.replace("refresh_", "")
                await query.answer("Refreshing...")
                
                if page == "balance":
                    await self.cmd_balance(update, context, edit=True)
                elif page == "markets":
                    await self.cmd_markets(update, context, edit=True)
                elif page == "history":
                    await self.cmd_history(update, context, edit=True)
                elif page == "pnl":
                    await self.cmd_pnl(update, context, edit=True)
                elif page == "settings":
                    await self.cmd_settings(update, context, edit=True)
                    
            elif data == "toggle_auto":
                current = self.config.get('auto_trade', False)
                self.config['auto_trade'] = not current
                
                status = "ON ✅" if self.config['auto_trade'] else "OFF ❌"
                await query.answer(f"Auto-Trade: {status}")
                
                logger.info(f"Auto-Trade toggled to: {status}")
                await self.cmd_settings(update, context, edit=True)
                
        except Exception as e:
            logger.error(f"Callback error: {e}")
            await query.answer("Error occurred")

    def start(self):
        if self.running:
            return
        
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        try:
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            
            self.app = Application.builder().token(self.token).build()
            self.register_handlers()
            
            self.running = True
            logger.info("Bot polling started")
            
            self.app.run_polling(
                drop_pending_updates=True,
                close_loop=False,
                stop_signals=None
            )
        except Exception as e:
            logger.error(f"Bot error: {e}")
        finally:
            self.running = False

    def stop(self):
        if self.app and self._loop:
            try:
                asyncio.run_coroutine_threadsafe(self.app.stop(), self._loop)
            except:
                pass
        self.running = False

    # Notification methods
    async def send_trade_notification(self, trade: Dict):
        if not self.config.get('notifications_enabled', True):
            return
        chat_id = self.config.get('chat_id')
        if not chat_id:
            return
        
        text = (
            f"📝 *Trade Executed*\n\n"
            f"{trade.get('symbol')} {trade.get('side')}\n"
            f"Size: `{trade.get('size')}` @ `${trade.get('price', 0):,.2f}`\n\n"
            f"⏰ {fmt_ist()}"
        )
        
        try:
            await self.app.bot.send_message(chat_id=chat_id, text=text, parse_mode='Markdown')
        except:
            pass

    async def send_opportunity_alert(self, opportunity: Dict):
        chat_id = self.config.get('chat_id')
        if not chat_id:
            return
        
        text = (
            f"🔍 *Signal*\n\n"
            f"{opportunity.get('symbol')} `{opportunity.get('signal')}`\n"
            f"Confidence: `{opportunity.get('confidence', 0):.0%}`\n\n"
            f"⏰ {fmt_ist()}"
        )
        
        try:
            await self.app.bot.send_message(chat_id=chat_id, text=text, parse_mode='Markdown')
        except:
            pass

    async def send_closure_notification(self, market_id: str, winner: str, pnl: float, details: Dict = None):
        chat_id = self.config.get('chat_id')
        if not chat_id:
            return
        
        emoji = "✅" if pnl >= 0 else "❌"
        text = (
            f"{emoji} *Market Closed*\n\n"
            f"ID: `{market_id[:15]}...`\n"
            f"Result: {winner}\n"
            f"PnL: `${pnl:+,.2f}`\n\n"
            f"⏰ {fmt_ist()}"
        )
        
        try:
            await self.app.bot.send_message(chat_id=chat_id, text=text, parse_mode='Markdown')
        except:
            pass
