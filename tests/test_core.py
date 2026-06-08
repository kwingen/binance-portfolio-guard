"""核心函数测试"""
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from binance_portfolio_sl import calculate_total_pnl, get_active_positions
from server.services.binance_client import (
    calculate_total_entry_value, calculate_total_notional, get_effective_threshold,
)


def make_position(symbol, amt, entry, mark, pnl):
    return {
        "symbol": symbol,
        "positionAmt": str(amt),
        "entryPrice": str(entry),
        "markPrice": str(mark),
        "unRealizedProfit": str(pnl),
        "leverage": "10",
    }


class TestBasicCalculations:
    def test_total_pnl_long_profit(self):
        pos = [make_position("BTCUSDT", 0.1, 60000, 61000, 100)]
        assert calculate_total_pnl(pos) == 100

    def test_total_pnl_short_profit(self):
        pos = [make_position("BTCUSDT", -0.1, 60000, 59000, 100)]
        assert calculate_total_pnl(pos) == 100

    def test_total_pnl_mixed(self):
        pos = [
            make_position("BTCUSDT", 0.1, 60000, 59500, -50),
            make_position("ETHUSDT", -1.0, 3000, 3100, -100),
        ]
        assert calculate_total_pnl(pos) == -150

    def test_entry_value_long(self):
        pos = [make_position("BTCUSDT", 0.1, 60000, 61000, 0)]
        assert calculate_total_entry_value(pos) == 6000

    def test_entry_value_short(self):
        pos = [make_position("BTCUSDT", -0.1, 60000, 59000, 0)]
        assert calculate_total_entry_value(pos) == 6000

    def test_entry_value_mixed(self):
        pos = [
            make_position("BTCUSDT", 0.1, 60000, 0, 0),
            make_position("ETHUSDT", -1.0, 3000, 0, 0),
        ]
        assert calculate_total_entry_value(pos) == 9000

    def test_notional(self):
        pos = [
            make_position("BTCUSDT", 0.1, 0, 65000, 0),
            make_position("ETHUSDT", -1.0, 0, 3200, 0),
        ]
        assert calculate_total_notional(pos) == 6500 + 3200

    def test_active_positions_filter(self):
        pos = [
            make_position("BTCUSDT", 0.1, 60000, 60000, 0),
            make_position("ETHUSDT", 0, 3000, 3000, 0),
        ]
        active = get_active_positions(pos)
        assert len(active) == 1
        assert active[0]["symbol"] == "BTCUSDT"


class TestThresholdCalculation:
    def test_usd_threshold(self):
        assert get_effective_threshold(-100, "usd", 5000) == -100

    def test_percent_threshold(self):
        assert get_effective_threshold(5, "percent", 10000) == -500

    def test_percent_zero_entry(self):
        assert get_effective_threshold(5, "percent", 0) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
