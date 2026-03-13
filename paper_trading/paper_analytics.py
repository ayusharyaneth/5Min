"""Paper trading analytics and reporting."""
import math
from typing import Dict, List

from utils.logger import get_logger

logger = get_logger(__name__)


class PaperAnalytics:
    """Analytics computation for paper trading results."""
    
    @staticmethod
    def compute(results: List[Dict]) -> Dict:
        """
        Compute analytics from market results.
        
        Args:
            results: List of market result dictionaries
            
        Returns:
            Analytics dictionary
        """
        if not results:
            return {
                "total_markets": 0,
                "winning_markets": 0,
                "losing_markets": 0,
                "breakeven_markets": 0,
                "win_rate_pct": 0.0,
                "total_realized_pnl": 0.0,
                "total_usdc_spent": 0.0,
                "avg_pnl_per_market": 0.0,
                "best_market_pnl": 0.0,
                "worst_market_pnl": 0.0,
                "best_market_name": "",
                "worst_market_name": "",
                "roi_pct": 0.0,
                "max_drawdown_pct": 0.0,
                "max_consecutive_wins": 0,
                "max_consecutive_losses": 0,
                "sharpe_ratio": 0.0,
                "avg_trades_per_market": 0.0,
                "rule_breakdown": {},
                "pnl_by_winner": {"UP": 0.0, "DOWN": 0.0},
                "equity_curve": []
            }
        
        total_markets = len(results)
        pnls = [r.get("pnl", 0) for r in results]
        total_pnl = sum(pnls)
        
        winning = [r for r in results if r.get("pnl", 0) > 0]
        losing = [r for r in results if r.get("pnl", 0) < 0]
        breakeven = [r for r in results if r.get("pnl", 0) == 0]
        
        # Best and worst markets
        sorted_by_pnl = sorted(results, key=lambda x: x.get("pnl", 0), reverse=True)
        best = sorted_by_pnl[0] if sorted_by_pnl else None
        worst = sorted_by_pnl[-1] if sorted_by_pnl else None
        
        # Total USDC spent
        total_usdc = sum(r.get("total_cost", 0) for r in results)
        
        # ROI
        roi = (total_pnl / total_usdc * 100) if total_usdc > 0 else 0.0
        
        # Equity curve
        equity_curve = PaperAnalytics._equity_curve(results)
        
        # Max drawdown
        max_dd = PaperAnalytics._max_drawdown(equity_curve)
        
        # Sharpe ratio
        sharpe = PaperAnalytics._sharpe_ratio(pnls)
        
        # Consecutive wins/losses
        max_wins, max_losses = PaperAnalytics._max_consecutive(results)
        
        # Rule breakdown
        rule_breakdown = PaperAnalytics._rule_breakdown(results)
        
        # PnL by winner
        pnl_by_winner = {"UP": 0.0, "DOWN": 0.0}
        for r in results:
            winner = r.get("winner", "")
            if winner in pnl_by_winner:
                pnl_by_winner[winner] += r.get("pnl", 0)
        
        return {
            "total_markets": total_markets,
            "winning_markets": len(winning),
            "losing_markets": len(losing),
            "breakeven_markets": len(breakeven),
            "win_rate_pct": PaperAnalytics._win_rate(results),
            "total_realized_pnl": total_pnl,
            "total_usdc_spent": total_usdc,
            "avg_pnl_per_market": total_pnl / total_markets,
            "best_market_pnl": best.get("pnl", 0) if best else 0.0,
            "worst_market_pnl": worst.get("pnl", 0) if worst else 0.0,
            "best_market_name": best.get("question", "")[:50] if best else "",
            "worst_market_name": worst.get("question", "")[:50] if worst else "",
            "roi_pct": roi,
            "max_drawdown_pct": max_dd,
            "max_consecutive_wins": max_wins,
            "max_consecutive_losses": max_losses,
            "sharpe_ratio": sharpe,
            "avg_trades_per_market": sum(r.get("trade_count", 0) for r in results) / total_markets,
            "rule_breakdown": rule_breakdown,
            "pnl_by_winner": pnl_by_winner,
            "equity_curve": equity_curve
        }
    
    @staticmethod
    def _win_rate(results: List[Dict]) -> float:
        """Calculate win rate percentage."""
        if not results:
            return 0.0
        winning = sum(1 for r in results if r.get("pnl", 0) > 0)
        return winning / len(results) * 100
    
    @staticmethod
    def _max_drawdown(equity: List[float]) -> float:
        """Calculate maximum drawdown percentage."""
        if not equity:
            return 0.0
        
        peak = equity[0]
        max_dd = 0.0
        
        for value in equity:
            if value > peak:
                peak = value
            dd = (peak - value) / peak * 100 if peak > 0 else 0
            max_dd = max(max_dd, dd)
        
        return max_dd
    
    @staticmethod
    def _sharpe_ratio(pnl_list: List[float]) -> float:
        """Calculate Sharpe ratio."""
        if len(pnl_list) < 3:
            return 0.0
        
        mean = sum(pnl_list) / len(pnl_list)
        variance = sum((x - mean) ** 2 for x in pnl_list) / len(pnl_list)
        std = math.sqrt(variance)
        
        if std == 0:
            return 0.0
        
        return mean / std
    
    @staticmethod
    def _max_consecutive(results: List[Dict]) -> tuple:
        """Calculate max consecutive wins and losses."""
        max_wins = 0
        max_losses = 0
        current_wins = 0
        current_losses = 0
        
        for r in results:
            pnl = r.get("pnl", 0)
            if pnl > 0:
                current_wins += 1
                current_losses = 0
                max_wins = max(max_wins, current_wins)
            elif pnl < 0:
                current_losses += 1
                current_wins = 0
                max_losses = max(max_losses, current_losses)
            else:
                current_wins = 0
                current_losses = 0
        
        return max_wins, max_losses
    
    @staticmethod
    def _rule_breakdown(results: List[Dict]) -> Dict:
        """Calculate breakdown by trading rule."""
        breakdown = {}
        
        for r in results:
            # Get trades for this market
            trades = r.get("trades", [])
            for trade in trades:
                rule = trade.get("rule", "unknown")
                pnl = r.get("pnl", 0)
                
                if rule not in breakdown:
                    breakdown[rule] = {"count": 0, "total_pnl": 0.0, "wins": 0, "losses": 0}
                
                breakdown[rule]["count"] += 1
                breakdown[rule]["total_pnl"] += pnl
                if pnl > 0:
                    breakdown[rule]["wins"] += 1
                elif pnl < 0:
                    breakdown[rule]["losses"] += 1
        
        # Calculate win rates
        for rule in breakdown:
            count = breakdown[rule]["count"]
            wins = breakdown[rule]["wins"]
            breakdown[rule]["win_rate"] = wins / count * 100 if count > 0 else 0
        
        return breakdown
    
    @staticmethod
    def _equity_curve(results: List[Dict]) -> List[float]:
        """Generate equity curve (cumulative PnL)."""
        equity = []
        cumulative = 0.0
        
        for r in results:
            cumulative += r.get("pnl", 0)
            equity.append(cumulative)
        
        return equity
    
    @staticmethod
    def format_report(analytics: Dict, virtual_balance: float, starting_balance: float) -> str:
        """
        Format analytics as an HTML report for Telegram.
        
        Args:
            analytics: Analytics dictionary
            virtual_balance: Current virtual balance
            starting_balance: Starting balance
            
        Returns:
            HTML formatted report string
        """
        lines = [
            "<b>═══════════════════════════════════════</b>",
            "<b>📊 PAPER TRADING REPORT</b>",
            "<b>═══════════════════════════════════════</b>",
            "",
            "<b>📈 OVERVIEW</b>",
            f"<code>Total Markets:    {analytics['total_markets']}</code>",
            f"<code>Winning:          {analytics['winning_markets']}</code>",
            f"<code>Losing:           {analytics['losing_markets']}</code>",
            f"<code>Breakeven:        {analytics['breakeven_markets']}</code>",
            f"<code>Win Rate:         {analytics['win_rate_pct']:.2f}%</code>",
            "",
            "<b>💰 PnL SUMMARY</b>",
            f"<code>Total PnL:        ${analytics['total_realized_pnl']:.2f}</code>",
            f"<code>USDC Spent:       ${analytics['total_usdc_spent']:.2f}</code>",
            f"<code>Avg PnL/Market:   ${analytics['avg_pnl_per_market']:.4f}</code>",
            f"<code>ROI:              {analytics['roi_pct']:.2f}%</code>",
            "",
            "<b>🏆 BEST / WORST</b>",
        ]
        
        if analytics['best_market_pnl'] > 0:
            lines.append(f"<code>Best:  +${analytics['best_market_pnl']:.2f}</code>")
            lines.append(f"<code>       {analytics['best_market_name'][:40]}</code>")
        
        if analytics['worst_market_pnl'] < 0:
            lines.append(f"<code>Worst: ${analytics['worst_market_pnl']:.2f}</code>")
            lines.append(f"<code>       {analytics['worst_market_name'][:40]}</code>")
        
        lines.extend([
            "",
            "<b>📉 RISK METRICS</b>",
            f"<code>Max Drawdown:     {analytics['max_drawdown_pct']:.2f}%</code>",
            f"<code>Sharpe Ratio:     {analytics['sharpe_ratio']:.4f}</code>",
            f"<code>Max Consec Wins:  {analytics['max_consecutive_wins']}</code>",
            f"<code>Max Consec Loss:  {analytics['max_consecutive_losses']}</code>",
            "",
            "<b>💼 WALLET</b>",
            f"<code>Starting:         ${starting_balance:.2f}</code>",
            f"<code>Current:          ${virtual_balance:.2f}</code>",
            f"<code>Change:           ${virtual_balance - starting_balance:.2f}</code>",
        ])
        
        # Rule breakdown
        if analytics.get("rule_breakdown"):
            lines.extend([
                "",
                "<b>📋 RULE BREAKDOWN</b>",
            ])
            for rule, stats in analytics["rule_breakdown"].items():
                lines.append(f"<code>{rule:16} {stats['count']:3} trades  ${stats['total_pnl']:+.2f}  {stats['win_rate']:.1f}% WR</code>")
        
        lines.append("<b>═══════════════════════════════════════</b>")
        
        report = "\n".join(lines)
        
        # Truncate to 4096 chars for Telegram
        if len(report) > 4096:
            report = report[:4093] + "..."
        
        return report
