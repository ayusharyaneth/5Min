# telegram_bot/__init__.py
from telegram_bot.notifier import TelegramNotifier

def get_dashboard():
    """Lazy import to avoid circular dependency"""
    from telegram_bot.dashboard import Dashboard
    return Dashboard
