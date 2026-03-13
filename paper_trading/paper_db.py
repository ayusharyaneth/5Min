"""SQLite database for paper trading persistence."""
import sqlite3
import time
from typing import Dict, List, Optional

from utils.logger import get_logger

logger = get_logger(__name__)


class PaperDB:
    """SQLite database manager for paper trading data."""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()
    
    def _get_conn(self) -> sqlite3.Connection:
        """Get a database connection with WAL mode."""
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.row_factory = sqlite3.Row
        return conn
    
    def _init_db(self):
        """Initialize database tables."""
        with self._get_conn() as conn:
            # Sessions table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS paper_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    started_at REAL NOT NULL,
                    ended_at REAL,
                    starting_balance REAL NOT NULL,
                    ending_balance REAL,
                    total_realized_pnl REAL DEFAULT 0,
                    trade_count INTEGER DEFAULT 0,
                    notes TEXT
                )
            """)
            
            # Markets table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS paper_markets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id INTEGER NOT NULL,
                    market_id TEXT NOT NULL,
                    question TEXT,
                    winner TEXT,
                    up_shares REAL DEFAULT 0,
                    down_shares REAL DEFAULT 0,
                    total_cost REAL DEFAULT 0,
                    pnl REAL DEFAULT 0,
                    resolved_at REAL,
                    trade_count INTEGER DEFAULT 0,
                    FOREIGN KEY (session_id) REFERENCES paper_sessions(id)
                )
            """)
            
            # Trades table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS paper_trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id INTEGER NOT NULL,
                    market_id TEXT NOT NULL,
                    side TEXT NOT NULL,
                    shares REAL NOT NULL,
                    price REAL NOT NULL,
                    total_cost REAL NOT NULL,
                    rule TEXT,
                    reason TEXT,
                    placed_at REAL NOT NULL,
                    FOREIGN KEY (session_id) REFERENCES paper_sessions(id)
                )
            """)
            
            conn.commit()
            logger.info(f"Database initialized: {self.db_path}")
    
    def start_session(self, starting_balance: float) -> int:
        """
        Start a new paper trading session.
        
        Args:
            starting_balance: Initial virtual balance
            
        Returns:
            Session ID
        """
        with self._get_conn() as conn:
            cursor = conn.execute(
                "INSERT INTO paper_sessions (started_at, starting_balance) VALUES (?, ?)",
                (time.time(), starting_balance)
            )
            session_id = cursor.lastrowid
            conn.commit()
            logger.info(f"Started paper session {session_id} with balance {starting_balance}")
            return session_id
    
    def end_session(
        self,
        ending_balance: float,
        pnl: float,
        count: int,
        notes: str = ""
    ):
        """
        End the current paper trading session.
        
        Args:
            ending_balance: Final virtual balance
            pnl: Total realized PnL
            count: Total trade count
            notes: Optional notes
        """
        with self._get_conn() as conn:
            # Find the most recent session without an end time
            cursor = conn.execute(
                "SELECT id FROM paper_sessions WHERE ended_at IS NULL ORDER BY started_at DESC LIMIT 1"
            )
            row = cursor.fetchone()
            if row:
                session_id = row["id"]
                conn.execute(
                    """UPDATE paper_sessions 
                       SET ended_at = ?, ending_balance = ?, total_realized_pnl = ?, 
                           trade_count = ?, notes = ?
                       WHERE id = ?""",
                    (time.time(), ending_balance, pnl, count, notes, session_id)
                )
                conn.commit()
                logger.info(f"Ended paper session {session_id}")
    
    def save_market_result(
        self,
        session_id: int,
        market_id: str,
        question: str,
        winner: str,
        up_shares: float,
        down_shares: float,
        total_cost: float,
        pnl: float,
        trade_count: int
    ):
        """Save a closed market result."""
        with self._get_conn() as conn:
            conn.execute(
                """INSERT INTO paper_markets 
                   (session_id, market_id, question, winner, up_shares, down_shares, 
                    total_cost, pnl, resolved_at, trade_count)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (session_id, market_id, question, winner, up_shares, down_shares,
                 total_cost, pnl, time.time(), trade_count)
            )
            conn.commit()
    
    def save_trade(
        self,
        session_id: int,
        market_id: str,
        side: str,
        shares: float,
        price: float,
        total_cost: float,
        rule: str,
        reason: str
    ):
        """Save a paper trade."""
        with self._get_conn() as conn:
            conn.execute(
                """INSERT INTO paper_trades 
                   (session_id, market_id, side, shares, price, total_cost, rule, reason, placed_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (session_id, market_id, side, shares, price, total_cost, rule, reason, time.time())
            )
            conn.commit()
    
    def get_all_market_results(self) -> List[Dict]:
        """Get all market results from all sessions."""
        with self._get_conn() as conn:
            cursor = conn.execute(
                "SELECT * FROM paper_markets ORDER BY resolved_at DESC"
            )
            return [dict(row) for row in cursor.fetchall()]
    
    def get_session_market_results(self, session_id: Optional[int] = None) -> List[Dict]:
        """Get market results for a specific session or the latest session."""
        with self._get_conn() as conn:
            if session_id is None:
                # Get latest session
                cursor = conn.execute(
                    "SELECT id FROM paper_sessions ORDER BY started_at DESC LIMIT 1"
                )
                row = cursor.fetchone()
                if not row:
                    return []
                session_id = row["id"]
            
            cursor = conn.execute(
                "SELECT * FROM paper_markets WHERE session_id = ? ORDER BY resolved_at DESC",
                (session_id,)
            )
            return [dict(row) for row in cursor.fetchall()]
    
    def get_all_trades(self, session_id: Optional[int] = None) -> List[Dict]:
        """Get all trades, optionally filtered by session."""
        with self._get_conn() as conn:
            if session_id:
                cursor = conn.execute(
                    "SELECT * FROM paper_trades WHERE session_id = ? ORDER BY placed_at DESC",
                    (session_id,)
                )
            else:
                cursor = conn.execute(
                    "SELECT * FROM paper_trades ORDER BY placed_at DESC"
                )
            return [dict(row) for row in cursor.fetchall()]
    
    def get_sessions_summary(self) -> List[Dict]:
        """Get summary of all sessions."""
        with self._get_conn() as conn:
            cursor = conn.execute(
                "SELECT * FROM paper_sessions ORDER BY started_at DESC"
            )
            return [dict(row) for row in cursor.fetchall()]
    
    def get_current_session_id(self) -> Optional[int]:
        """Get the current (most recent unended) session ID."""
        with self._get_conn() as conn:
            cursor = conn.execute(
                "SELECT id FROM paper_sessions WHERE ended_at IS NULL ORDER BY started_at DESC LIMIT 1"
            )
            row = cursor.fetchone()
            return row["id"] if row else None
