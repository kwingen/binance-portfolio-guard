"""交易/持仓相关路由"""
import logging
from fastapi import APIRouter, HTTPException, Depends

from server.config import settings
from server.auth import require_auth
from server.models import DashboardStatus, OrderRequest
from server.services import state, get_effective_threshold

logger = logging.getLogger("trading")
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


@router.post("/order")
async def place_order(req: OrderRequest):
    """开仓下单"""
    if not state.client:
        raise HTTPException(500, "API 未初始化")

    if settings.dry_run:
        return {
            "ok": True, "dry_run": True, "symbol": req.symbol,
            "side": req.side, "type": req.order_type, "quantity": req.quantity,
        }

    try:
        # 先设杠杆
        state.client.set_leverage(req.symbol, req.leverage)

        # 下单
        result = state.client.place_order(
            symbol=req.symbol.upper(),
            side=req.side,
            order_type=req.order_type,
            quantity=req.quantity,
            price=req.price if req.order_type == "LIMIT" else None,
        )

        if isinstance(result, dict) and result.get("code") and result["code"] < 0:
            raise HTTPException(400, f"下单失败: {result.get('msg', '未知错误')}")

        logger.info(f"下单成功: {req.side} {req.quantity} {req.symbol} @ {req.order_type}")
        return {"ok": True, "order": result}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"下单异常: {e}")
        raise HTTPException(500, str(e))
