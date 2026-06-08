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


# ── 仓位分组 ─────────────────────────────────────────

def match_positions_to_groups(positions: list, groups: list):
    """
    将活跃仓位匹配到分组。
    返回: {
        "grouped": {group_index: [positions]},
        "ungrouped": [positions],       # 未归属任何组的仓位
        "groups": [group_dicts],        # 分组信息（含计算结果）
    }
    一个仓位只归属到第一个匹配的组。
    """
    grouped = {}
    assigned = set()

    for gi, group in enumerate(groups):
        if not group.get("enabled", True):
            continue
        matched = []
        for pos in positions:
            symbol = pos.get("symbol", "")
            amt = float(pos.get("positionAmt", 0))
            direction = "long" if amt > 0 else "short"
            pos_key = f"{symbol}_{direction}"

            if pos_key in assigned:
                continue

            for gp in group.get("positions", []):
                if gp["symbol"].upper() == symbol.upper() and gp["direction"] == direction:
                    matched.append(pos)
                    assigned.add(pos_key)
                    break

        if matched:
            # 计算该组的汇总数据
            entry_val = calculate_total_entry_value(matched)
            pnl = calculate_total_pnl(matched)
            notional = calculate_total_notional(matched)
            th = get_effective_threshold(
                group.get("stop_loss_threshold", 5),
                group.get("threshold_type", "percent"),
                entry_val,
            )
            grouped[gi] = {
                "positions": matched,
                "name": group.get("name", f"Group {gi+1}"),
                "entry_value": entry_val,
                "notional": notional,
                "pnl": pnl,
                "pnl_formatted": f"{pnl:+.2f}",
                "threshold": th,
                "threshold_formatted": f"{th:+.2f}",
                "threshold_type": group.get("threshold_type", "percent"),
                "threshold_pct": group.get("stop_loss_threshold", 5),
                "triggered": pnl <= th if entry_val > 0 else False,
            }

    # 未分组仓位
    ungrouped = [p for p in positions
                 if f"{p.get('symbol','')}_{'long' if float(p.get('positionAmt',0))>0 else 'short'}"
                 not in assigned]

    return grouped, ungrouped, assigned


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
        self.last_groups: list = []  # 分组快照
        self.consecutive_failures: int = 0  # 连续失败次数（熔断用）

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
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # 全局阈值（用于未分组仓位）
            global_threshold = get_effective_threshold(
                settings.stop_loss_threshold, settings.threshold_type, total_entry,
            )

            # 仓位分组
            portfolios = getattr(settings, 'portfolios', []) or []
            group_results, ungrouped, _ = match_positions_to_groups(active, portfolios)
            group_list = list(group_results.values())

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
                state.last_groups = group_list

            _emit("position_update", {
                "time": now,
                "positions": [dict(p) if hasattr(p, '__iter__') and not isinstance(p, dict) else p for p in active],
                "total_pnl": round(total_pnl, 4),
                "total_pnl_formatted": f"{total_pnl:+.2f}",
                "total_notional": round(total_notional, 2),
                "total_entry_value": round(total_entry, 2),
                "threshold_type": settings.threshold_type,
                "effective_threshold": round(global_threshold, 2),
                "effective_threshold_formatted": f"{global_threshold:+.2f}",
                "groups": group_list,
                "ungrouped_count": len(ungrouped),
            })

            # ── 分组止损检查 ──
            triggered_group = None
            for gi, ginfo in group_results.items():
                if ginfo["triggered"]:
                    triggered_group = (gi, ginfo)
                    break

            if triggered_group:
                gi, ginfo = triggered_group
                dry = settings.dry_run
                logger.warning("=" * 60)
                logger.warning(f"⚠️ 分组 [{ginfo['name']}] 触发止损!")
                logger.warning(f"   盈亏 {ginfo['pnl_formatted']} ≤ 阈值 {ginfo['threshold_formatted']}")
                logger.warning("=" * 60)

                # 只平该组的仓位
                group_positions = ginfo["positions"]
                result = close_all_positions(client, group_positions, dry_run=dry)
                with state._lock:
                    state.stop_loss_triggered = True
                    state.monitoring = False

                _emit("stop_loss_triggered", {
                    "group_name": ginfo["name"],
                    "total_pnl": round(ginfo["pnl"], 4),
                    "total_pnl_formatted": ginfo["pnl_formatted"],
                    "threshold": ginfo["threshold"],
                    "threshold_formatted": ginfo["threshold_formatted"],
                    "threshold_type": ginfo["threshold_type"],
                    "close_result": result,
                })
                logger.info(f"分组 [{ginfo['name']}] 止损完成，监控停止")

            # ── 全局止损（仅检查未分组仓位）──
            elif ungrouped and calculate_total_pnl(ungrouped) <= global_threshold:
                # 用未分组仓位的 entry value 重算阈值
                ug_entry = calculate_total_entry_value(ungrouped)
                ug_threshold = get_effective_threshold(
                    settings.stop_loss_threshold, settings.threshold_type, ug_entry,
                )
                ug_pnl = calculate_total_pnl(ungrouped)
                if ug_pnl <= ug_threshold:
                    dry = settings.dry_run
                    logger.warning("=" * 60)
                    logger.warning(f"⚠️ 全局止损! 未分组仓位盈亏 {ug_pnl:+.2f} ≤ {ug_threshold:+.2f}")
                    logger.warning("=" * 60)
                    result = close_all_positions(client, ungrouped, dry_run=dry)
                    with state._lock:
                        state.stop_loss_triggered = True
                        state.monitoring = False
                    _emit("stop_loss_triggered", {
                        "group_name": "未分组",
                        "total_pnl": round(ug_pnl, 4),
                        "total_pnl_formatted": f"{ug_pnl:+.2f}",
                        "threshold": ug_threshold,
                        "threshold_formatted": f"{ug_threshold:+.2f}",
                        "threshold_type": settings.threshold_type,
                        "close_result": result,
                    })

            time.sleep(settings.check_interval_seconds - 1)

        except Exception as e:
            # ── 重试（短退避，不超过轮询间隔）──
            last_error = e
            for retry in range(1, 4):
                wait = retry  # 1s, 2s, 3s — 总计 6s，比 5s 轮询略长一个窗口
                logger.warning(f"监控异常，{wait}s 后第 {retry}/3 次重试: {type(e).__name__}")
                time.sleep(wait)
                try:
                    client = state.client
                    positions = client.get_positions()
                    active = get_active_positions(positions)
                    total_pnl = calculate_total_pnl(positions)
                    total_notional = calculate_total_notional(positions)
                    total_entry = calculate_total_entry_value(positions)
                    account_info = client.get_account()
                    with state._lock:
                        state.consecutive_failures = 0
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
                        state.last_check_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        state.last_error = None
                        state.total_checks += 1
                    _emit("position_update", {
                        "time": state.last_check_time,
                        "positions": active,
                        "total_pnl": round(total_pnl, 4),
                        "total_pnl_formatted": f"{total_pnl:+.2f}",
                        "total_notional": round(total_notional, 2),
                        "total_entry_value": round(total_entry, 2),
                        "threshold_type": settings.threshold_type,
                        "groups": [],
                        "ungrouped_count": 0,
                    })
                    logger.info(f"第 {retry} 次重试成功")
                    break
                except Exception as retry_err:
                    last_error = retry_err
            else:
                # 所有重试均失败 → 记录并检查熔断
                err_msg = f"{type(last_error).__name__}: {last_error}"
                logger.error(f"监控异常（重试 3 次后仍失败）: {err_msg}")
                with state._lock:
                    state.consecutive_failures += 1
                    state.last_error = err_msg
                _emit("error", {"message": err_msg})

                # ── 熔断保护 ──
                if state.consecutive_failures >= 10:
                    logger.critical("🔌 熔断触发: 连续 10 次失败，监控已暂停")
                    with state._lock:
                        state.monitoring = False
                    _emit("circuit_breaker", {
                        "reason": f"连续 {state.consecutive_failures} 次失败",
                        "last_error": err_msg,
                    })
                    break
                elif state.consecutive_failures >= 5:
                    cooldown = 30
                    logger.warning(f"⚠️ 连续 {state.consecutive_failures} 次失败，冷却 {cooldown}s")
                    time.sleep(cooldown)
                else:
                    time.sleep(max(settings.check_interval_seconds // 2, 5))
