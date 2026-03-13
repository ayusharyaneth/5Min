"""Telegram bot command handlers."""
import asyncio
import time
from typing import Optional

from telegram import Update
from telegram.ext import ContextTypes

from api.clob_client import CLOBClient
from paper_trading.paper_clob import PaperCLOBClient
from paper_trading.paper_store import PaperStateStore
from paper_trading.paper_db import PaperDB
from paper_trading.paper_analytics import PaperAnalytics
from state.store import StateStore
from trader.executor import Executor
from paper_trading.paper_executor import PaperExecutor
from monitor.market_finder import MarketFinder
from telegram_bot.notifier import TelegramNotifier
from utils.logger import get_logger

logger = get_logger(__name__)


class Dashboard:
    """Telegram bot dashboard with all command handlers."""
    
    def __init__(
        self,
        live_store: StateStore,
        paper_store: Optional[PaperStateStore],
        clob: Optional[CLOBClient],
        paper_clob: Optional[PaperCLOBClient],
        live_exec: Optional[Executor],
        paper_exec: Optional[PaperExecutor],
        paper_db: PaperDB,
        notifier: TelegramNotifier,
        stop_event,
        allowed_user_id: int,
        paper_starting_balance: float
    ):
        self.live_store = live_store
        self.paper_store = paper_store
        self.clob = clob
        self.paper_clob = paper_clob
        self.live_exec = live_exec
        self.paper_exec = paper_exec
        self.paper_db = paper_db
        self.notifier = notifier
        self.stop_event = stop_event
        self.allowed_user_id = allowed_user_id
        self.paper_starting_balance = paper_starting_balance
    
    def _auth_check(self, update: Update) -> bool:
        """Check if user is authorized."""
        user_id = update.effective_user.id
        if user_id != self.allowed_user_id:
            logger.warning(f"Unauthorized access attempt from user {user_id}")
            return False
        return True
    
    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /status command."""
        if not self._auth_check(update):
            await update.message.reply_text("❌ Unauthorized")
            return
        
        stats = self.live_store.get_stats()
        uptime = stats.get("uptime_seconds", 0)
        hours = int(uptime // 3600)
        minutes = int((uptime % 3600) // 60)
        
        text = (
            f"<b>═══════════════════════════════════════</b>\n"
            f"<b>📊 BOT STATUS</b>\n"
            f"<b>═══════════════════════════════════════</b>\n"
            f"\n"
            f"<b>Status:</b> <code>{'🟢 Running' if not stats.get('trading_halted') else '🔴 Halted'}</code>\n"
            f"<b>Panic Mode:</b> <code>{'🚨 ON' if stats.get('panic_mode') else '✅ Off'}</code>\n"
            f"<b>Uptime:</b> <code>{hours}h {minutes}m</code>\n"
            f"\n"
            f"<b>Active Markets:</b> <code>{stats.get('active_positions', 0)}</code>\n"
            f"<b>Trade Count:</b> <code>{stats.get('trade_count', 0)}</code>\n"
            f"<b>USDC Spent:</b> <code>${stats.get('usdc_spent_today', 0):.4f}</code>\n"
            f"<b>Realized PnL:</b> <code>${stats.get('daily_realized_pnl', 0):.4f}</code>\n"
            f"<b>───────────────────────────────────────</b>"
        )
        
        await update.message.reply_text(text, parse_mode="HTML")
    
    async def cmd_positions(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /positions command."""
        if not self._auth_check(update):
            await update.message.reply_text("❌ Unauthorized")
            return
        
        markets = self.live_store.list_active_markets()
        if not markets:
            await update.message.reply_text("📭 No active positions")
            return
        
        lines = ["<b>═══════════════════════════════════════</b>", "<b>📈 LIVE POSITIONS</b>", "<b>═══════════════════════════════════════</b>", ""]
        
        # Fetch prices concurrently
        async def fetch_position_data(market_id):
            position = self.live_store.get_position(market_id)
            meta = self.live_store.get_market_meta(market_id)
            if not position or not meta:
                return None
            
            up_token = meta.get("up_token_id")
            dn_token = meta.get("down_token_id")
            
            up_ask = self.clob.get_best_ask(up_token) if self.clob and up_token else 0.5
            dn_ask = self.clob.get_best_ask(dn_token) if self.clob and dn_token else 0.5
            
            time_rem = MarketFinder.get_time_remaining(meta)
            unrealized = position.unrealized_pnl(up_ask, dn_ask)
            
            return {
                "market_id": market_id,
                "question": position.question[:50],
                "up_shares": position.up_shares,
                "down_shares": position.down_shares,
                "total_cost": position.total_cost,
                "unrealized": unrealized,
                "time_rem": time_rem
            }
        
        tasks = [fetch_position_data(mid) for mid in markets]
        results = await asyncio.gather(*tasks)
        
        for data in results:
            if data:
                lines.extend([
                    f"<b>Market:</b> <code>{data['question']}...</code>",
                    f"<code>  UP:    {data['up_shares']:.2f} shares</code>",
                    f"<code>  DOWN:  {data['down_shares']:.2f} shares</code>",
                    f"<code>  Cost:  ${data['total_cost']:.4f}</code>",
                    f"<code>  Unrealized: ${data['unrealized']:+.4f}</code>",
                    f"<code>  Time left: {int(data['time_rem'])}s</code>",
                    "<b>───────────────────────────────────────</b>"
                ])
        
        text = "\n".join(lines)
        if len(text) > 4096:
            text = text[:4093] + "..."
        
        await update.message.reply_text(text, parse_mode="HTML")
    
    async def cmd_pnl(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /pnl command."""
        if not self._auth_check(update):
            await update.message.reply_text("❌ Unauthorized")
            return
        
        markets = self.live_store.list_active_markets()
        total_pnl_up = 0
        total_pnl_down = 0
        
        for market_id in markets:
            position = self.live_store.get_position(market_id)
            if position:
                total_pnl_up += position.pnl_if_up_wins()
                total_pnl_down += position.pnl_if_down_wins()
        
        realized = self.live_store.get_daily_realized_pnl()
        
        text = (
            f"<b>═══════════════════════════════════════</b>\n"
            f"<b>💰 PnL SUMMARY</b>\n"
            f"<b>═══════════════════════════════════════</b>\n"
            f"\n"
            f"<b>Open Positions ({len(markets)}):</b>\n"
            f"<code>  If UP wins:   ${total_pnl_up:+.4f}</code>\n"
            f"<code>  If DOWN wins: ${total_pnl_down:+.4f}</code>\n"
            f"\n"
            f"<b>Realized Today:</b> <code>${realized:+.4f}</code>\n"
            f"<b>───────────────────────────────────────</b>"
        )
        
        await update.message.reply_text(text, parse_mode="HTML")
    
    async def cmd_wallet(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /wallet command."""
        if not self._auth_check(update):
            await update.message.reply_text("❌ Unauthorized")
            return
        
        balance = 0.0
        if self.clob:
            try:
                bal_data = self.clob.get_wallet_balance()
                balance = bal_data.get("balance", 0.0)
            except Exception as e:
                logger.error(f"Error getting wallet balance: {e}")
        
        stats = self.live_store.get_stats()
        allocated = stats.get("usdc_spent_today", 0)
        daily_pnl = stats.get("daily_realized_pnl", 0)
        loss_room = max(0, 100 - abs(daily_pnl)) if daily_pnl < 0 else 100
        
        text = (
            f"<b>═══════════════════════════════════════</b>\n"
            f"<b>💼 WALLET</b>\n"
            f"<b>═══════════════════════════════════════</b>\n"
            f"\n"
            f"<b>CLOB Balance:</b> <code>${balance:.4f}</code>\n"
            f"<b>Allocated:</b> <code>${allocated:.4f}</code>\n"
            f"<b>Available:</b> <code>${max(0, balance - allocated):.4f}</code>\n"
            f"\n"
            f"<b>Daily PnL:</b> <code>${daily_pnl:+.4f}</code>\n"
            f"<b>Loss Room:</b> <code>${loss_room:.2f}</code>\n"
            f"<b>Panic Mode:</b> <code>{'🚨 ON' if stats.get('panic_mode') else '✅ Off'}</code>\n"
            f"<b>Halted:</b> <code>{'🔴 Yes' if stats.get('trading_halted') else '🟢 No'}</code>\n"
            f"<b>───────────────────────────────────────</b>"
        )
        
        await update.message.reply_text(text, parse_mode="HTML")
    
    async def cmd_panic(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /panic command."""
        if not self._auth_check(update):
            await update.message.reply_text("❌ Unauthorized")
            return
        
        self.live_store.set_panic_mode(True)
        
        cancelled = 0
        if self.live_exec:
            cancelled = self.live_exec.cancel_all_open_orders()
        
        self.notifier.send_panic_alert(cancelled, "Manual panic triggered via Telegram")
        
        await update.message.reply_text(
            f"🚨 <b>PANIC MODE ACTIVATED</b>\n"
            f"Cancelled <code>{cancelled}</code> orders\n"
            f"Use /resume to re-enable trading",
            parse_mode="HTML"
        )
    
    async def cmd_resume(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /resume command."""
        if not self._auth_check(update):
            await update.message.reply_text("❌ Unauthorized")
            return
        
        self.live_store.set_panic_mode(False)
        self.live_store.set_trading_halted(False)
        
        self.notifier.send_log("✅ Trading resumed", "INFO")
        
        await update.message.reply_text(
            "✅ <b>Trading Resumed</b>\n"
            "Panic mode cleared. Trading enabled.",
            parse_mode="HTML"
        )
    
    async def cmd_stop(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /stop command."""
        if not self._auth_check(update):
            await update.message.reply_text("❌ Unauthorized")
            return
        
        self.stop_event.set()
        self.notifier.send_log("🛑 Stop signal received from Telegram", "INFO")
        
        await update.message.reply_text(
            "🛑 <b>Bot Stopping</b>\n"
            "Shutdown signal sent. Bot will stop after current tick.",
            parse_mode="HTML"
        )
    
    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command."""
        if not self._auth_check(update):
            await update.message.reply_text("❌ Unauthorized")
            return
        
        text = (
            "<b>═══════════════════════════════════════</b>\n"
            "<b>📖 AVAILABLE COMMANDS</b>\n"
            "<b>═══════════════════════════════════════</b>\n"
            "\n"
            "<b>Live Trading:</b>\n"
            "<code>/status</code> - Bot status and stats\n"
            "<code>/positions</code> - Active positions with prices\n"
            "<code>/pnl</code> - PnL summary\n"
            "<code>/wallet</code> - Wallet and balance info\n"
            "<code>/panic</code> - Activate panic mode\n"
            "<code>/resume</code> - Resume trading\n"
            "<code>/stop</code> - Stop the bot\n"
            "\n"
            "<b>Paper Trading:</b>\n"
            "<code>/paper_status</code> - Paper trading status\n"
            "<code>/paper_positions</code> - Paper positions\n"
            "<code>/paper_report</code> - Full analytics report\n"
            "<code>/paper_history</code> - Last 10 closed markets\n"
            "<code>/paper_reset</code> - Reset paper session\n"
            "\n"
            "<code>/help</code> - Show this help message\n"
            "<b>───────────────────────────────────────</b>"
        )
        
        await update.message.reply_text(text, parse_mode="HTML")
    
    # === Paper trading commands ===
    async def cmd_paper_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /paper_status command."""
        if not self._auth_check(update):
            await update.message.reply_text("❌ Unauthorized")
            return
        
        if not self.paper_store:
            await update.message.reply_text("🧪 Paper trading not enabled")
            return
        
        stats = self.paper_store.get_paper_stats()
        
        text = (
            f"<b>═══════════════════════════════════════</b>\n"
            f"<b>🧪 PAPER TRADING STATUS</b>\n"
            f"<b>═══════════════════════════════════════</b>\n"
            f"\n"
            f"<b>Virtual Balance:</b> <code>${stats.get('virtual_balance', 0):.2f}</code>\n"
            f"<b>Starting:</b> <code>${stats.get('starting_balance', 0):.2f}</code>\n"
            f"<b>Change:</b> <code>${stats.get('virtual_balance', 0) - stats.get('starting_balance', 0):+.2f}</code>\n"
            f"<b>ROI:</b> <code>{stats.get('roi_pct', 0):.2f}%</code>\n"
            f"\n"
            f"<b>Markets:</b> <code>{stats.get('total_markets', 0)}</code>\n"
            f"<b>Win Rate:</b> <code>{stats.get('win_rate_pct', 0):.2f}%</code>\n"
            f"<b>Realized PnL:</b> <code>${stats.get('realized_pnl', 0):.4f}</code>\n"
            f"<b>Trade Count:</b> <code>{stats.get('trade_count', 0)}</code>\n"
            f"<b>Active Pos:</b> <code>{stats.get('active_positions', 0)}</code>\n"
            f"<b>───────────────────────────────────────</b>"
        )
        
        await update.message.reply_text(text, parse_mode="HTML")
    
    async def cmd_paper_positions(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /paper_positions command."""
        if not self._auth_check(update):
            await update.message.reply_text("❌ Unauthorized")
            return
        
        if not self.paper_store:
            await update.message.reply_text("🧪 Paper trading not enabled")
            return
        
        markets = self.paper_store.list_active_markets()
        if not markets:
            await update.message.reply_text("🧪 📭 No active paper positions")
            return
        
        lines = ["<b>═══════════════════════════════════════</b>", "<b>🧪 PAPER POSITIONS</b>", "<b>═══════════════════════════════════════</b>", ""]
        
        for market_id in markets:
            position = self.paper_store.get_position(market_id)
            meta = self.paper_store.get_market_meta(market_id)
            if not position or not meta:
                continue
            
            up_ask = self.paper_clob.get_best_ask(meta.get("up_token_id")) if self.paper_clob else 0.5
            dn_ask = self.paper_clob.get_best_ask(meta.get("down_token_id")) if self.paper_clob else 0.5
            
            time_rem = MarketFinder.get_time_remaining(meta)
            unrealized = position.unrealized_pnl(up_ask, dn_ask)
            
            lines.extend([
                f"<b>Market:</b> <code>{position.question[:50]}...</code>",
                f"<code>  UP:    {position.up_shares:.2f} shares</code>",
                f"<code>  DOWN:  {position.down_shares:.2f} shares</code>",
                f"<code>  Cost:  ${position.total_cost:.4f}</code>",
                f"<code>  Unrealized: ${unrealized:+.4f}</code>",
                f"<code>  Time left: {int(time_rem)}s</code>",
                "<b>───────────────────────────────────────</b>"
            ])
        
        text = "\n".join(lines)
        if len(text) > 4096:
            text = text[:4093] + "..."
        
        await update.message.reply_text(text, parse_mode="HTML")
    
    async def cmd_paper_report(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /paper_report command."""
        if not self._auth_check(update):
            await update.message.reply_text("❌ Unauthorized")
            return
        
        if not self.paper_store:
            await update.message.reply_text("🧪 Paper trading not enabled")
            return
        
        # Merge in-memory and DB results
        db_results = self.paper_db.get_session_market_results()
        memory_results = self.paper_store.get_closed_markets()
        
        # Deduplicate by market_id
        seen = set()
        all_results = []
        for r in db_results + memory_results:
            mid = r.get("market_id")
            if mid and mid not in seen:
                seen.add(mid)
                all_results.append(r)
        
        analytics = PaperAnalytics.compute(all_results)
        report = PaperAnalytics.format_report(
            analytics,
            self.paper_store.get_virtual_balance(),
            self.paper_starting_balance
        )
        
        self.notifier.send_paper_report(report)
        await update.message.reply_text("📊 Paper report sent to #logs channel")
    
    async def cmd_paper_history(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /paper_history command."""
        if not self._auth_check(update):
            await update.message.reply_text("❌ Unauthorized")
            return
        
        if not self.paper_store:
            await update.message.reply_text("🧪 Paper trading not enabled")
            return
        
        results = self.paper_db.get_session_market_results()
        
        if not results:
            await update.message.reply_text("🧪 📭 No closed paper markets yet")
            return
        
        lines = ["<b>═══════════════════════════════════════</b>", "<b>🧪 PAPER HISTORY (Last 10)</b>", "<b>═══════════════════════════════════════</b>", ""]
        
        total_pnl = 0
        for r in results[:10]:
            pnl = r.get("pnl", 0)
            total_pnl += pnl
            winner = r.get("winner", "?")
            color = "🟢" if pnl > 0 else "🔴" if pnl < 0 else "⚪"
            
            lines.extend([
                f"<b>{r.get('question', 'Unknown')[:50]}...</b>",
                f"<code>  Winner: {winner}</code>",
                f"<code>  PnL: {color} ${pnl:+.4f}</code>",
                "<b>───────────────────────────────────────</b>"
            ])
        
        lines.extend([
            "",
            f"<b>Session Total:</b> <code>${total_pnl:+.4f}</code>",
            "<b>═══════════════════════════════════════</b>"
        ])
        
        text = "\n".join(lines)
        if len(text) > 4096:
            text = text[:4093] + "..."
        
        await update.message.reply_text(text, parse_mode="HTML")
    
    async def cmd_paper_reset(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /paper_reset command."""
        if not self._auth_check(update):
            await update.message.reply_text("❌ Unauthorized")
            return
        
        if not self.paper_store:
            await update.message.reply_text("🧪 Paper trading not enabled")
            return
        
        # End current session
        stats = self.paper_store.get_paper_stats()
        self.paper_db.end_session(
            ending_balance=self.paper_store.get_virtual_balance(),
            pnl=stats.get("realized_pnl", 0),
            count=stats.get("trade_count", 0),
            notes="Reset via Telegram command"
        )
        
        # Start new session
        new_session_id = self.paper_db.start_session(self.paper_starting_balance)
        
        # Reset store
        self.paper_store.reset(self.paper_starting_balance)
        
        self.notifier.send_paper_log(f"Session reset. New session ID: {new_session_id}", "INFO")
        
        await update.message.reply_text(
            f"🧪 <b>Paper Session Reset</b>\n"
            f"New session ID: <code>{new_session_id}</code>\n"
            f"Balance reset to: <code>${self.paper_starting_balance:.2f}</code>",
            parse_mode="HTML"
        )
