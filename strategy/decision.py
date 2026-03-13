"""Trading decision logic."""
from dataclasses import dataclass
from typing import Optional

from strategy.position import Position
from strategy.trend import detect_trend
from config import (
    COST_PER_PAIR_MAX,
    MAX_BUYS_PER_TICK,
    SIZE_REDUCE_AFTER_SECS,
    SIZE_MIN_RATIO,
    SIZE_MIN_SHARES
)


@dataclass
class TradeDecision:
    """Represents a trading decision."""
    action: str  # "BUY_UP" | "BUY_DOWN" | "HOLD"
    shares: float
    price: float
    reason: str
    rule: str  # rule1|rule2_lock|rule2_expansion|rule3_lock|rule3_expansion|rule4_lock_down|rule4_lock_up|rule4_expansion|hold


def calculate_size(base_size: float, time_rem: float) -> float:
    """
    Calculate order size based on time remaining.
    
    R0 — Size reduction as market approaches closure.
    """
    if time_rem < SIZE_REDUCE_AFTER_SECS:
        ratio = max(SIZE_MIN_RATIO, time_rem / SIZE_REDUCE_AFTER_SECS)
        return max(SIZE_MIN_SHARES, round(base_size * ratio))
    return base_size


def make_decision(
    pos: Position,
    up_ask: float,
    dn_ask: float,
    up_hist: List[float],
    dn_hist: List[float],
    time_rem: float,
    base_size: float
) -> TradeDecision:
    """
    Make a trading decision based on position state and market conditions.
    
    Args:
        pos: Current position
        up_ask: Current UP ask price
        dn_ask: Current DOWN ask price
        up_hist: UP price history
        dn_hist: DOWN price history
        time_rem: Time remaining in seconds
        base_size: Base order size
        
    Returns:
        TradeDecision with action, shares, price, reason, and rule
    """
    # Calculate dynamic size based on time remaining
    size = calculate_size(base_size, time_rem)
    
    # Detect trends
    up_trend = detect_trend(up_hist) if len(up_hist) >= 3 else "flat"
    dn_trend = detect_trend(dn_hist) if len(dn_hist) >= 3 else "flat"
    
    up_rising = up_trend == "rising"
    dn_rising = dn_trend == "rising"
    
    # Get position state
    has_up = pos.has_up_position()
    has_down = pos.has_down_position()
    has_both = pos.has_both_sides()
    
    # PnL scenarios
    pnl_up = pos.pnl_if_up_wins()
    pnl_down = pos.pnl_if_down_wins()
    
    # === R1 — No position ===
    if not has_up and not has_down:
        if up_rising:
            return TradeDecision(
                action="BUY_UP",
                shares=size,
                price=up_ask,
                reason="No position, UP trending rising",
                rule="rule1"
            )
        if dn_rising:
            return TradeDecision(
                action="BUY_DOWN",
                shares=size,
                price=dn_ask,
                reason="No position, DOWN trending rising",
                rule="rule1"
            )
        return TradeDecision(
            action="HOLD",
            shares=0,
            price=0,
            reason="No position, no clear trend",
            rule="hold"
        )
    
    # === R2 — UP only position ===
    if has_up and not has_down:
        # Lock: check if adding DOWN would create profitable pair
        cost_per_pair = pos.cost_per_pair_if_add_down(size, dn_ask)
        if cost_per_pair < COST_PER_PAIR_MAX and cost_per_pair > 0:
            return TradeDecision(
                action="BUY_DOWN",
                shares=size,
                price=dn_ask,
                reason=f"UP only, locking with DOWN (cost/pair: {cost_per_pair:.4f})",
                rule="rule2_lock"
            )
        
        # Expansion: DOWN rising and DOWN PnL would be better
        if dn_rising and pnl_down < pnl_up:
            # Buy enough to make pnl_down >= 0, capped at size*MAX_BUYS_PER_TICK
            max_shares = size * MAX_BUYS_PER_TICK
            needed_shares = max(0, (pos.total_cost - pos.down_shares) / (1 - dn_ask)) if dn_ask < 1 else size
            shares_to_buy = min(max(size, needed_shares), max_shares)
            return TradeDecision(
                action="BUY_DOWN",
                shares=shares_to_buy,
                price=dn_ask,
                reason=f"UP only, DOWN rising and PnL lagging, expanding",
                rule="rule2_expansion"
            )
        
        return TradeDecision(
            action="HOLD",
            shares=0,
            price=0,
            reason="UP only, no lock or expansion conditions met",
            rule="hold"
        )
    
    # === R3 — DOWN only position ===
    if has_down and not has_up:
        # Lock: check if adding UP would create profitable pair
        cost_per_pair = pos.cost_per_pair_if_add_up(size, up_ask)
        if cost_per_pair < COST_PER_PAIR_MAX and cost_per_pair > 0:
            return TradeDecision(
                action="BUY_UP",
                shares=size,
                price=up_ask,
                reason=f"DOWN only, locking with UP (cost/pair: {cost_per_pair:.4f})",
                rule="rule3_lock"
            )
        
        # Expansion: UP rising and UP PnL would be better
        if up_rising and pnl_up < pnl_down:
            max_shares = size * MAX_BUYS_PER_TICK
            needed_shares = max(0, (pos.total_cost - pos.up_shares) / (1 - up_ask)) if up_ask < 1 else size
            shares_to_buy = min(max(size, needed_shares), max_shares)
            return TradeDecision(
                action="BUY_UP",
                shares=shares_to_buy,
                price=up_ask,
                reason=f"DOWN only, UP rising and PnL lagging, expanding",
                rule="rule3_expansion"
            )
        
        return TradeDecision(
            action="HOLD",
            shares=0,
            price=0,
            reason="DOWN only, no lock or expansion conditions met",
            rule="hold"
        )
    
    # === R4 — Both sides position ===
    if has_both:
        dominant = pos.get_dominant_side()
        
        # Lock: add to smaller side if cost/pair is good
        if dominant == "up":
            cost_per_pair = pos.cost_per_pair_if_add_down(size, dn_ask)
            if cost_per_pair < COST_PER_PAIR_MAX and cost_per_pair > 0:
                return TradeDecision(
                    action="BUY_DOWN",
                    shares=size,
                    price=dn_ask,
                    reason=f"Both sides, UP dominant, locking DOWN (cost/pair: {cost_per_pair:.4f})",
                    rule="rule4_lock_down"
                )
        
        if dominant == "down":
            cost_per_pair = pos.cost_per_pair_if_add_up(size, up_ask)
            if cost_per_pair < COST_PER_PAIR_MAX and cost_per_pair > 0:
                return TradeDecision(
                    action="BUY_UP",
                    shares=size,
                    price=up_ask,
                    reason=f"Both sides, DOWN dominant, locking UP (cost/pair: {cost_per_pair:.4f})",
                    rule="rule4_lock_up"
                )
        
        # Expansion: add to side with rising trend and lagging PnL
        if dn_rising and pnl_down < pnl_up:
            return TradeDecision(
                action="BUY_DOWN",
                shares=size,
                price=dn_ask,
                reason="Both sides, DOWN rising and PnL lagging, expanding",
                rule="rule4_expansion"
            )
        
        if up_rising and pnl_up < pnl_down:
            return TradeDecision(
                action="BUY_UP",
                shares=size,
                price=up_ask,
                reason="Both sides, UP rising and PnL lagging, expanding",
                rule="rule4_expansion"
            )
        
        return TradeDecision(
            action="HOLD",
            shares=0,
            price=0,
            reason="Both sides, no lock or expansion conditions met",
            rule="hold"
        )
    
    # === R5 — Fallback HOLD ===
    return TradeDecision(
        action="HOLD",
        shares=0,
        price=0,
        reason="No conditions met",
        rule="hold"
    )
