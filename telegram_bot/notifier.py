"""Telegram notification handler."""
import asyncio
import threading
import time
from typing import Dict, Optional

from telegram import Bot
from telegram.constants import ParseMode

from utils.logger import get_logger

logger = get_logger(__name__)


class TelegramNotifier:
    """Handles all Telegram notifications."""
    
    def __init__(
        self,
        token: str,
        logs_channel_id: str,
        trades_channel_id: str
    ):
        self.token = token
        self.logs_channel_id = logs_channel_id
        self.trades_channel_id = trades_channel_id
        self.bot: Optional[Bot] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._loop_thread: Optional[threading.Thread] = None
        
        if token:
            self._start_loop()
    
    def _start_loop(self):
        """Start the asyncio event loop in a daemon thread."""
        self._loop = asyncio.new_event_loop()
        self._loop_thread = threading.Thread(target=self._run_loop, daemon=True)
        self._loop_thread.start()
        
        # Initialize bot in the loop
        future = asyncio.run_coroutine_threadsafe(self._init_bot(), self._loop)
        try:
            future.result(timeout=10)
        except Exception as e:
            logger.error(f"Failed to initialize Telegram bot: {e}")
    
    def _run_loop(self):
        """Run the asyncio event loop."""
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()
    
    async def _init_bot(self):
        """Initialize the Telegram bot."""
        self.bot = Bot(token=self.token)
        me = await self.bot.get_me()
        logger.info(f"Telegram bot initialized: @{me.username}")
    
    def _send_message(self, chat_id: str, text: str, parse_mode: str = ParseMode.HTML):
        """Send a message to a chat."""
        if not self.bot or not self._loop:
            return
        
        try:
            future = asyncio.run_coroutine_threadsafe(
                self.bot.send_message(chat_id=chat_id, text=text, parse_mode=parse_mode),
                self._loop
            )
            future.result(timeout=30)
        except Exception as e:
            logger.error(f"Failed to send Telegram message: {e}")
    
    # === Live notifications ===
    def send_log(self, msg: str, level: str = "INFO"):
        """Send a log message to the logs channel."""
        prefix = {
            "INFO": "ℹ️",
            "WARNING": "⚠️",
            "ERROR": "❌",
            "DEBUG": "🔍"
        }.get(level, "ℹ️")
        
        text = f"{prefix} {msg}"
        self._send_message(self.logs_channel_id, text)
    
    def send_trade(self, trade_data: Dict):
        """Send a trade notification to the trades channel."""
        pnl_up = trade_data.get("pnl_if_up", 0)
        pnl_down = trade_data.get("pnl_if_down", 0)
        
        text = (
            f"<b>═══════════════════════════════════════</b>\n"
            f"<b>🎯 LIVE TRADE EXECUTED</b>\n"
            f"<b>═══════════════════════════════════════</b>\n"
            f"\n"
            f"<b>Market:</b> <code>{trade_data.get('question', 'Unknown')[:60]}...</code>\n"
            f"<b>Side:</b> <code>{trade_data.get('side', 'Unknown')}</code>\n"
            f"<b>Shares:</b> <code>{trade_data.get('shares', 0):.2f}</code>\n"
            f"<b>Price:</b> <code>${trade_data.get('price', 0):.4f}</code>\n"
            f"<b>Cost:</b> <code>${trade_data.get('cost', 0):.4f}</code>\n"
            f"<b>Order ID:</b> <code>{trade_data.get('order_id', 'N/A')[:20]}</code>\n"
            f"<b>Rule:</b> <code>{trade_data.get('rule', 'unknown')}</code>\n"
            f"\n"
            f"<b>PnL Scenarios:</b>\n"
            f"<code>  If UP wins:   ${pnl_up:+.4f}</code>\n"
            f"<code>  If DOWN wins: ${pnl_down:+.4f}</code>\n"
            f"\n"
            f"<b>Time:</b> <code>{time.strftime('%Y-%m-%d %H:%M:%S')}</code>\n"
            f"<b>───────────────────────────────────────</b>"
        )
        
        self._send_message(self.trades_channel_id, text)
    
    def send_market_closed(
        self,
        market_id: str,
        question: str,
        winner: str,
        pnl: float,
        up_shares: float,
        down_shares: float,
        total_cost: float
    ):
        """Send a market closed notification."""
        pnl_color = "🟢" if pnl > 0 else "🔴" if pnl < 0 else "⚪"
        
        text = (
            f"<b>═══════════════════════════════════════</b>\n"
            f"<b>🏁 MARKET CLOSED</b>\n"
            f"<b>═══════════════════════════════════════</b>\n"
            f"\n"
            f"<b>Market:</b> <code>{question[:60]}...</code>\n"
            f"<b>Winner:</b> <code>{winner}</code>\n"
            f"<b>───────────────────────────────────────</b>\n"
            f"<b>Position:</b>\n"
            f"<code>  UP shares:   {up_shares:.2f}</code>\n"
            f"<code>  DOWN shares: {down_shares:.2f}</code>\n"
            f"<code>  Total cost:  ${total_cost:.4f}</code>\n"
            f"\n"
            f"<b>Result:</b> {pnl_color} <code>${pnl:+.4f}</code>\n"
            f"\n"
            f"<b>Time:</b> <code>{time.strftime('%Y-%m-%d %H:%M:%S')}</code>\n"
            f"<b>───────────────────────────────────────</b>"
        )
        
        self._send_message(self.trades_channel_id, text)
    
    def send_panic_alert(self, cancelled: int, details: str = ""):
        """Send a panic mode alert."""
        text = (
            f"<b>═══════════════════════════════════════</b>\n"
            f"<b>🚨 PANIC MODE ACTIVATED</b>\n"
            f"<b>═══════════════════════════════════════</b>\n"
            f"\n"
            f"<b>Cancelled Orders:</b> <code>{cancelled}</code>\n"
            f"<b>Details:</b> <code>{details}</code>\n"
            f"\n"
            f"<b>Time:</b> <code>{time.strftime('%Y-%m-%d %H:%M:%S')}</code>\n"
            f"<b>───────────────────────────────────────</b>"
        )
        
        self._send_message(self.logs_channel_id, text)
    
    def send_loss_limit_alert(self, daily_pnl: float, limit: float):
        """Send a daily loss limit alert."""
        text = (
            f"<b>═══════════════════════════════════════</b>\n"
            f"<b>⛔ DAILY LOSS LIMIT REACHED</b>\n"
            f"<b>═══════════════════════════════════════</b>\n"
            f"\n"
            f"<b>Daily PnL:</b> <code>${daily_pnl:.4f}</code>\n"
            f"<b>Limit:</b> <code>-${limit:.2f}</code>\n"
            f"\n"
            f"<b>Trading has been halted!</b>\n"
            f"Use /resume to re-enable trading.\n"
            f"\n"
            f"<b>Time:</b> <code>{time.strftime('%Y-%m-%d %H:%M:%S')}</code>\n"
            f"<b>───────────────────────────────────────</b>"
        )
        
        self._send_message(self.logs_channel_id, text)
    
    def send_error(self, context: str, error: str):
        """Send an error notification."""
        text = (
            f"<b>═══════════════════════════════════════</b>\n"
            f"<b>❌ ERROR</b>\n"
            f"<b>═══════════════════════════════════════</b>\n"
            f"\n"
            f"<b>Context:</b> <code>{context}</code>\n"
            f"<b>Error:</b> <code>{error[:200]}</code>\n"
            f"\n"
            f"<b>Time:</b> <code>{time.strftime('%Y-%m-%d %H:%M:%S')}</code>\n"
            f"<b>───────────────────────────────────────</b>"
        )
        
        self._send_message(self.logs_channel_id, text)
    
    # === Paper trading notifications ===
    def send_paper_log(self, msg: str, level: str = "INFO"):
        """Send a paper trading log message."""
        prefix = {
            "INFO": "ℹ️",
            "WARNING": "⚠️",
            "ERROR": "❌",
            "DEBUG": "🔍"
        }.get(level, "ℹ️")
        
        text = f"🧪 [PAPER] {prefix} {msg}"
        self._send_message(self.logs_channel_id, text)
    
    def send_paper_trade(self, trade_data: Dict):
        """Send a paper trade notification."""
        pnl_up = trade_data.get("pnl_if_up", 0)
        pnl_down = trade_data.get("pnl_if_down", 0)
        
        text = (
            f"<b>═══════════════════════════════════════</b>\n"
            f"<b>🧪 [PAPER] SIMULATED TRADE</b>\n"
            f"<b>═══════════════════════════════════════</b>\n"
            f"\n"
            f"<b>Market:</b> <code>{trade_data.get('question', 'Unknown')[:60]}...</code>\n"
            f"<b>Side:</b> <code>{trade_data.get('side', 'Unknown')}</code>\n"
            f"<b>Shares:</b> <code>{trade_data.get('shares', 0):.2f}</code>\n"
            f"<b>Price:</b> <code>${trade_data.get('price', 0):.4f}</code>\n"
            f"<b>Cost:</b> <code>${trade_data.get('cost', 0):.4f}</code>\n"
            f"<b>Order ID:</b> <code>{trade_data.get('order_id', 'N/A')[:20]}</code>\n"
            f"<b>Rule:</b> <code>{trade_data.get('rule', 'unknown')}</code>\n"
            f"<b>Virtual Balance:</b> <code>${trade_data.get('virtual_balance_after', 0):.2f}</code>\n"
            f"\n"
            f"<b>PnL Scenarios:</b>\n"
            f"<code>  If UP wins:   ${pnl_up:+.4f}</code>\n"
            f"<code>  If DOWN wins: ${pnl_down:+.4f}</code>\n"
            f"\n"
            f"<b>Time:</b> <code>{time.strftime('%Y-%m-%d %H:%M:%S')}</code>\n"
            f"<b>───────────────────────────────────────</b>"
        )
        
        self._send_message(self.trades_channel_id, text)
    
    def send_paper_market_closed(
        self,
        market_id: str,
        question: str,
        winner: str,
        pnl: float,
        up_shares: float,
        down_shares: float,
        total_cost: float
    ):
        """Send a paper market closed notification."""
        pnl_color = "🟢" if pnl > 0 else "🔴" if pnl < 0 else "⚪"
        
        text = (
            f"<b>═══════════════════════════════════════</b>\n"
            f"<b>🧪 [PAPER] MARKET CLOSED</b>\n"
            f"<b>═══════════════════════════════════════</b>\n"
            f"\n"
            f"<b>Market:</b> <code>{question[:60]}...</code>\n"
            f"<b>Winner:</b> <code>{winner}</code>\n"
            f"<b>───────────────────────────────────────</b>\n"
            f"<b>Position:</b>\n"
            f"<code>  UP shares:   {up_shares:.2f}</code>\n"
            f"<code>  DOWN shares: {down_shares:.2f}</code>\n"
            f"<code>  Total cost:  ${total_cost:.4f}</code>\n"
            f"\n"
            f"<b>Result:</b> {pnl_color} <code>${pnl:+.4f}</code>\n"
            f"\n"
            f"<b>Time:</b> <code>{time.strftime('%Y-%m-%d %H:%M:%S')}</code>\n"
            f"<b>───────────────────────────────────────</b>"
        )
        
        self._send_message(self.trades_channel_id, text)
    
    def send_paper_report(self, report_text: str):
        """Send a paper trading report."""
        self._send_message(self.logs_channel_id, report_text)
