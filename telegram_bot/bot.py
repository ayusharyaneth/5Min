"""Telegram bot runner."""
import asyncio
import threading

from telegram.ext import Application, CommandHandler

from telegram_bot.dashboard import Dashboard
from utils.logger import get_logger

logger = get_logger(__name__)


class TelegramBotRunner:
    """Runs the Telegram bot in a background thread."""
    
    def __init__(self, token: str, dashboard: Dashboard):
        self.token = token
        self.dashboard = dashboard
        self._thread: threading.Thread = None
        self._app: Application = None
    
    def start(self):
        """Start the bot in a daemon thread."""
        if not self.token:
            logger.warning("No Telegram token provided, bot not started")
            return
        
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        logger.info("Telegram bot started")
    
    def _run(self):
        """Run the bot event loop."""
        try:
            # Create application
            self._app = Application.builder().token(self.token).build()
            
            # Register command handlers
            self._register_handlers()
            
            # Run polling
            self._app.run_polling(drop_pending_updates=True)
            
        except Exception as e:
            logger.error(f"Telegram bot error: {e}")
    
    def _register_handlers(self):
        """Register all command handlers."""
        handlers = [
            ("status", self.dashboard.cmd_status),
            ("positions", self.dashboard.cmd_positions),
            ("pnl", self.dashboard.cmd_pnl),
            ("wallet", self.dashboard.cmd_wallet),
            ("panic", self.dashboard.cmd_panic),
            ("resume", self.dashboard.cmd_resume),
            ("stop", self.dashboard.cmd_stop),
            ("help", self.dashboard.cmd_help),
            ("paper_status", self.dashboard.cmd_paper_status),
            ("paper_positions", self.dashboard.cmd_paper_positions),
            ("paper_report", self.dashboard.cmd_paper_report),
            ("paper_history", self.dashboard.cmd_paper_history),
            ("paper_reset", self.dashboard.cmd_paper_reset),
        ]
        
        for command, handler in handlers:
            self._app.add_handler(CommandHandler(command, handler))
        
        logger.info(f"Registered {len(handlers)} command handlers")
