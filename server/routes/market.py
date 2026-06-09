"""行情代理 — 转发 Binance 公共 API（绕过 CORS/GFW）"""
import requests
from fastapi import APIRouter, Depends, Query

from server.auth import require_auth

router = APIRouter(prefix="/api/market", tags=["行情"], dependencies=[Depends(require_auth)])

BINANCE_FAPI = "https://fapi.binance.com"


@router.get("/klines")
async def klines(symbol: str = Query(...), interval: str = Query("1m"), limit: int = Query(200)):
    """K 线数据代理"""
    try:
        resp = requests.get(
            f"{BINANCE_FAPI}/fapi/v1/klines",
            params={"symbol": symbol.upper(), "interval": interval, "limit": limit},
            timeout=5,
        )
        return resp.json()
    except Exception:
        return []
