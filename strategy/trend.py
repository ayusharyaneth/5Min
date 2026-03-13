"""Trend detection functions."""
from typing import List


def detect_trend(history: List[float]) -> str:
    """
    Detect trend from price history.
    
    Args:
        history: List of price points (oldest first)
        
    Returns:
        "rising" if prices are trending up
        "falling" if prices are trending down
        "flat" otherwise
    """
    if len(history) < 3:
        return "flat"
    
    oldest = history[0]
    most_recent = history[-1]
    
    # Count up and down moves
    up_moves = 0
    down_moves = 0
    
    for i in range(1, len(history)):
        if history[i] > history[i-1]:
            up_moves += 1
        elif history[i] < history[i-1]:
            down_moves += 1
    
    # Rising: most recent > oldest AND more up moves than down
    if most_recent > oldest and up_moves > down_moves:
        return "rising"
    
    # Falling: most recent < oldest AND more down moves than up
    if most_recent < oldest and down_moves > up_moves:
        return "falling"
    
    return "flat"


def detect_up_trend(history: List[float]) -> str:
    """Alias for detect_trend - detect trend in UP token history."""
    return detect_trend(history)


def detect_down_trend(history: List[float]) -> str:
    """Alias for detect_trend - detect trend in DOWN token history."""
    return detect_trend(history)
