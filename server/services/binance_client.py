"""
币安 API 客户端 —— 从 binance_portfolio_sl.py 提取核心能力
"""
import sys
import os
from typing import Optional, List, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# 直接使用了原脚本的客户端，向后兼容
from binance_portfolio_sl import (
    BinanceFuturesClient,
    get_active_positions,
    calculate_total_pnl,
    close_all_positions,
)


def calculate_total_entry_value(positions: list) -> float:
    """总开仓成本 = sum(abs(positionAmt) × entryPrice)"""
    total = 0.0
    for pos in positions:
        try:
            amt = abs(float(pos.get("positionAmt", 0)))
            entry = float(pos.get("entryPrice", 0))
            total += amt * entry
        except (ValueError, TypeError):
            pass
    return total


def calculate_total_notional(positions: list) -> float:
    """总仓位实时市值 = sum(abs(positionAmt) × markPrice)"""
    total = 0.0
    for pos in positions:
        try:
            amt = abs(float(pos.get("positionAmt", 0)))
            mark = float(pos.get("markPrice", 0))
            total += amt * mark
        except (ValueError, TypeError):
            pass
    return total


def get_effective_threshold(threshold: float, threshold_type: str, entry_value: float) -> float:
    """计算有效止损线"""
    if threshold_type == "percent":
        if entry_value <= 0:
            return 0.0
        return -(entry_value * threshold / 100.0)
    return threshold
