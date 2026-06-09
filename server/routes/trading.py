"""交易/持仓相关路由"""
from fastapi import APIRouter, Depends

from server.config import settings
from server.auth import require_auth
from server.models import DashboardStatus
from server.services import state, get_effective_threshold

router = APIRouter(prefix="/api", tags=["交易"], dependencies=[Depends(require_auth)])


@router.get("/status", response_model=DashboardStatus)
async def get_status():
    snap = state.snapshot()
    effective = get_effective_threshold(
        settings.stop_loss_threshold, settings.threshold_type,
        snap["total_entry_value"],
    )
    has_key = bool(settings.binance_api_key and settings.binance_api_key != "demo")
    return DashboardStatus(
        monitoring=snap["monitoring"],
        stop_loss_triggered=snap["stop_loss_triggered"],
        positions=snap["positions"],
        total_pnl=round(snap["total_pnl"], 4),
        total_pnl_formatted=f"{snap['total_pnl']:+.2f}",
        total_notional=round(snap["total_notional"], 2),
        total_entry_value=round(snap["total_entry_value"], 2),
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
    )
