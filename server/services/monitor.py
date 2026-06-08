"""
后台监控服务 —— 线程安全的状态管理
仅暴露函数，不依赖 FastAPI（方便测试）
"""
import time
import json
import threading
import logging
from datetime import datetime
from typing import Optional, Callable

from server.config import settings
from server.services.binance_client import (
    BinanceFuturesClient,
    get_active_positions,
    calculate_total_pnl,
    calculate_total_entry_value,
    calculate_total_notional,
    get_effective_threshold,
    close_all_positions,
)

logger = logging.getLogger("monitor")


class MonitorState:
    """线程安全的监控状态"""

    def __init__(self):
        self._lock = threading.RLock()
        self.monitoring = False
        self.stop_loss_triggered = False
        self.last_positions: list = []
        self.last_pnl = 0.0
        self.last_notional = 0.0
        self.last_entry_value = 0.0
        self.last_account: dict = {}
        self.last_check_time: Optional[str] = None
        self.last_error: Optional[str] = None
        self.total_checks = 0
        self.client: Optional[BinanceFuturesClient] = None

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "monitoring": self.monitoring,
                "stop_loss_triggered": self.stop_loss_triggered,
                "positions": list(self.last_positions),
                "total_pnl": self.last_pnl,
                "total_notional": self.last_notional,
                "total_entry_value": self.last_entry_value,
                "account": dict(self.last_account),
                "last_check_time": self.last_check_time,
                "last_error": self.last_error,
                "total_checks": self.total_checks,
            }

    def set_monitoring(self, val: bool):
        with self._lock:
            self.monitoring = val
            if val:
                self.stop_loss_triggered = False


# 全局单例
state = MonitorState()

# SSE 回调列表
_event_callbacks: list[Callable] = []
_event_lock = threading.Lock()


def on_event(callback: Callable):
    """注册事件回调 callback(event_name, data)"""
    with _event_lock:
        _event_callbacks.append(callback)


def _emit(event: str, data: dict):
    with _event_lock:
        for cb in _event_callbacks:
            try:
                cb(event, data)
            except Exception:
                pass


def init_client(api_key: str, api_secret: str, testnet: bool = False, proxy: str = None):
    state.client = BinanceFuturesClient(
        api_key=api_key, api_secret=api_secret,
        testnet=testnet, proxy=proxy, timeout=8,
    )


def run_monitor_loop():
    """后台监控循环（在独立线程中运行）"""
    logger.info("监控线程启动")
    while True:
        time.sleep(1)
        if not state.monitoring or state.stop_loss_triggered:
            continue
        if not state.client:
            time.sleep(5)
            continue

        try:
            client = state.client
            positions = client.get_positions()
            active = get_active_positions(positions)
            total_pnl = calculate_total_pnl(positions)
            total_notional = calculate_total_notional(positions)
            total_entry = calculate_total_entry_value(positions)
            account_info = client.get_account()
            effective = get_effective_threshold(
                settings.stop_loss_threshold,
                settings.threshold_type,
                total_entry,
            )
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            with state._lock:
                state.last_positions = active
                state.last_pnl = total_pnl
                state.last_notional = total_notional
                state.last_entry_value = total_entry
                state.last_account = {
                    "totalWalletBalance": account_info.get("totalWalletBalance", "?"),
                    "totalUnrealizedProfit": account_info.get("totalUnrealizedProfit", "?"),
                    "totalMarginBalance": account_info.get("totalMarginBalance", "?"),
                    "availableBalance": account_info.get("availableBalance", "?"),
                }
                state.last_check_time = now
                state.last_error = None
                state.total_checks += 1

            _emit("position_update", {
                "time": now,
                "positions": [dict(p) if hasattr(p, '__iter__') and not isinstance(p, dict) else p for p in active],
                "total_pnl": round(total_pnl, 4),
                "total_pnl_formatted": f"{total_pnl:+.2f}",
                "total_notional": round(total_notional, 2),
                "total_entry_value": round(total_entry, 2),
                "threshold_type": settings.threshold_type,
                "effective_threshold": round(effective, 2),
                "effective_threshold_formatted": f"{effective:+.2f}",
            })

            # 止损判断
            if active and total_pnl <= effective:
                dry = settings.dry_run
                desc = f"总盈亏 {total_pnl:+.2f} ≤ {effective:+.2f}"
                if settings.threshold_type == "percent":
                    desc += f" (开仓成本 {total_entry:.2f} × {settings.stop_loss_threshold}%)"
                logger.warning("=" * 60)
                logger.warning(f"⚠️ 触发止损! {desc}")
                logger.warning("=" * 60)

                result = close_all_positions(client, positions, dry_run=dry)
                with state._lock:
                    state.stop_loss_triggered = True
                    state.monitoring = False

                _emit("stop_loss_triggered", {
                    "total_pnl": round(total_pnl, 4),
                    "total_pnl_formatted": f"{total_pnl:+.2f}",
                    "threshold": effective,
                    "threshold_formatted": f"{effective:+.2f}",
                    "threshold_type": settings.threshold_type,
                    "close_result": result,
                })

            time.sleep(settings.check_interval_seconds - 1)

        except Exception as e:
            err_msg = f"{type(e).__name__}: {e}"
            logger.error(f"监控异常: {err_msg}")
            with state._lock:
                state.last_error = err_msg
            _emit("error", {"message": err_msg})
            time.sleep(max(settings.check_interval_seconds // 2, 15))
