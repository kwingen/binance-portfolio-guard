"""仓位分组匹配测试"""
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from server.services.monitor import match_positions_to_groups


def make_position(symbol, amt, entry=60000, mark=60000, pnl=0):
    return {
        "symbol": symbol, "positionAmt": str(amt),
        "entryPrice": str(entry), "markPrice": str(mark),
        "unRealizedProfit": str(pnl), "leverage": "10",
    }


class TestGroupMatching:
    def test_single_group_match(self):
        positions = [make_position("BTCUSDT", 0.1)]
        groups = [{
            "name": "BTC组", "enabled": True,
            "positions": [{"symbol": "BTCUSDT", "direction": "long"}],
            "stop_loss_threshold": 5, "threshold_type": "percent",
        }]
        grouped, ungrouped, _ = match_positions_to_groups(positions, groups)
        assert len(grouped) == 1
        assert len(ungrouped) == 0
        assert grouped[0]["name"] == "BTC组"

    def test_no_match(self):
        positions = [make_position("BTCUSDT", 0.1)]
        groups = [{
            "name": "ETH组", "enabled": True,
            "positions": [{"symbol": "ETHUSDT", "direction": "long"}],
            "stop_loss_threshold": 5, "threshold_type": "percent",
        }]
        grouped, ungrouped, _ = match_positions_to_groups(positions, groups)
        assert len(grouped) == 0
        assert len(ungrouped) == 1

    def test_direction_mismatch(self):
        positions = [make_position("BTCUSDT", 0.1)]  # long
        groups = [{
            "name": "BTC空组", "enabled": True,
            "positions": [{"symbol": "BTCUSDT", "direction": "short"}],
            "stop_loss_threshold": 5, "threshold_type": "percent",
        }]
        grouped, ungrouped, _ = match_positions_to_groups(positions, groups)
        assert len(grouped) == 0

    def test_no_duplicate(self):
        positions = [make_position("BTCUSDT", 0.1)]
        groups = [
            {"name": "组1", "enabled": True,
             "positions": [{"symbol": "BTCUSDT", "direction": "long"}],
             "stop_loss_threshold": 5, "threshold_type": "percent"},
            {"name": "组2", "enabled": True,
             "positions": [{"symbol": "BTCUSDT", "direction": "long"}],
             "stop_loss_threshold": 3, "threshold_type": "percent"},
        ]
        grouped, _, assigned = match_positions_to_groups(positions, groups)
        assert len(grouped) == 1  # 只匹配第一个组
        assert "BTCUSDT_long" in assigned

    def test_mixed_long_short(self):
        positions = [
            make_position("BTCUSDT", 0.1),   # long
            make_position("ETHUSDT", -1.0),   # short
        ]
        groups = [{
            "name": "混合组", "enabled": True,
            "positions": [
                {"symbol": "BTCUSDT", "direction": "long"},
                {"symbol": "ETHUSDT", "direction": "short"},
            ],
            "stop_loss_threshold": 5, "threshold_type": "percent",
        }]
        grouped, ungrouped, _ = match_positions_to_groups(positions, groups)
        assert len(grouped) == 1
        assert len(ungrouped) == 0
        assert len(grouped[0]["positions"]) == 2

    def test_disabled_group(self):
        positions = [make_position("BTCUSDT", 0.1)]
        groups = [{
            "name": "禁用组", "enabled": False,
            "positions": [{"symbol": "BTCUSDT", "direction": "long"}],
            "stop_loss_threshold": 5, "threshold_type": "percent",
        }]
        grouped, ungrouped, _ = match_positions_to_groups(positions, groups)
        assert len(grouped) == 0
        assert len(ungrouped) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
