"""交易/持仓相关路由"""
from fastapi import APIRouter, Depends

from server.config import settings
from server.auth import require_auth
from server.models import DashboardStatus
from server.services import state, get_effective_threshold
from server.services.monitor import match_positions_to_groups
from server.services.binance_client import calculate_total_entry_value, calculate_total_pnl

router = APIRouter(prefix="/api", tags=["交易"], dependencies=[Depends(require_auth)])


@router.get("/status", response_model=DashboardStatus)
async def get_status():
    snap = state.snapshot()
    positions = snap["positions"]
    has_key = bool(settings.binance_api_key and settings.binance_api_key != "demo")

    # 分组计算
    portfolios = getattr(settings, 'portfolios', []) or []
    groups_data = []
    ungrouped = positions
    if portfolios and positions:
        group_results, ungrouped, _ = match_positions_to_groups(positions, portfolios)
        groups_data = list(group_results.values())

    # 全局止损只算未分组仓位的开仓成本
    ug_entry = calculate_total_entry_value(ungrouped)
    effective = get_effective_threshold(
        settings.stop_loss_threshold, settings.threshold_type, ug_entry,
    )

    return DashboardStatus(
        monitoring=snap["monitoring"],
        stop_loss_triggered=snap["stop_loss_triggered"],
        positions=snap["positions"],
        total_pnl=round(snap["total_pnl"], 4),
        total_pnl_formatted=f"{snap['total_pnl']:+.2f}",
        total_notional=round(snap["total_notional"], 2),
        total_entry_value=round(ug_entry, 2),
        account=snap["account"],
        last_check_time=snap["last_check_time"],
        last_error=snap["last_error"],
        total_checks=snap["total_checks"],
        threshold=settings.stop_loss_threshold,
        threshold_type=settings.threshold_type,
        effective_threshold=round(effective, 2),
        effective_threshold_formatted=f"{effective:+.2f}",
        dry_run=settings.dry_run,
        testnet=settings.binance_testnet,
        has_api_key=has_key,
        groups=groups_data,
    )
