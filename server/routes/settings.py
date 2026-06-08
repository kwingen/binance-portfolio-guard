"""设置路由 — 安全加固版"""
import json
import os
import logging
from fastapi import APIRouter, HTTPException, Depends, Request

from server.config import settings
from server.auth import require_auth, hash_password, verify_password
from server.models import SettingsUpdate, SettingsInfo
from server.services import init_client, state

logger = logging.getLogger("settings")
router = APIRouter(prefix="/api/settings", tags=["设置"], dependencies=[Depends(require_auth)])


# ── 审计日志 ──
def audit_log(action: str, detail: str = "", request: Request = None):
    ip = request.client.host if request and request.client else "unknown"
    logger.warning(f"[AUDIT] {action} | IP={ip} | {detail}")


def _save_config_to_file():
    path = settings.config_path
    if not path or "example" in os.path.basename(path).lower():
        return
    cfg = {
        "api_key": settings.binance_api_key,
        "api_secret": settings.binance_api_secret,
        "testnet": settings.binance_testnet,
        "proxy": settings.binance_proxy,
        "stop_loss_threshold": settings.stop_loss_threshold,
        "threshold_type": settings.threshold_type,
        "check_interval_seconds": settings.check_interval_seconds,
        "dry_run": settings.dry_run,
    }
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"保存配置失败: {e}")


@router.get("", response_model=SettingsInfo)
async def get_settings():
    """
    获取设置。**绝不返回 API Key 或 Secret 的任何信息。**
    只返回一个布尔值表示是否已配置 API。
    """
    has_key = bool(settings.binance_api_key and settings.binance_api_key != "demo"
                   and settings.binance_api_secret)
    return SettingsInfo(
        api_key_masked="",  # 永不返回 API Key 信息
        has_api_configured=has_key,
        testnet=settings.binance_testnet,
        proxy="",  # 也不返回代理，避免泄露网络拓扑
        dry_run=settings.dry_run,
        check_interval_seconds=settings.check_interval_seconds,
        threshold_type=settings.threshold_type,
        stop_loss_threshold=settings.stop_loss_threshold,
        has_auth_password=bool(settings.auth_password_hash),
        portfolios=getattr(settings, 'portfolios', []),
    )


@router.post("")
async def update_settings(data: SettingsUpdate, request: Request):
    """
    更新设置。修改 API 密钥需要提供当前密码二次验证。
    """
    changed_api = False

    # ── 非敏感设置（无需密码验证）──
    if data.threshold_type:
        if data.threshold_type not in ("usd", "percent"):
            raise HTTPException(400, "threshold_type 无效")
        settings.threshold_type = data.threshold_type
    if data.stop_loss_threshold is not None:
        settings.stop_loss_threshold = data.stop_loss_threshold
    if data.check_interval_seconds is not None:
        if data.check_interval_seconds < 2:
            raise HTTPException(400, "间隔不能小于 2 秒")
        settings.check_interval_seconds = data.check_interval_seconds
    if data.dry_run is not None:
        settings.dry_run = data.dry_run
    if data.testnet is not None:
        if data.testnet != settings.binance_testnet:
            changed_api = True
        settings.binance_testnet = data.testnet
    if data.proxy is not None:
        if data.proxy != (settings.binance_proxy or ""):
            changed_api = True
        settings.binance_proxy = data.proxy or None

    # ── API 密钥变更：必须提供密码 ──
    wants_api_change = (
        (data.api_key and "****" not in data.api_key) or
        (data.api_secret and "****" not in data.api_secret)
    )
    if wants_api_change:
        if not data.current_password:
            raise HTTPException(403, "修改 API 密钥需要提供当前密码")
        if not verify_password(data.current_password, settings.auth_password_hash):
            audit_log("API_KEY_CHANGE_FAILED", "密码验证失败", request)
            raise HTTPException(403, "密码错误")

        if data.api_key and "****" not in data.api_key:
            changed_api = True
            settings.binance_api_key = data.api_key.strip()
            audit_log("API_KEY_CHANGED", "API Key 已更新", request)
        if data.api_secret and "****" not in data.api_secret:
            changed_api = True
            settings.binance_api_secret = data.api_secret.strip()
            audit_log("API_SECRET_CHANGED", "API Secret 已更新", request)

    # ── 密码变更 ──
    if data.auth_password:
        settings.auth_password_hash = hash_password(data.auth_password)
        audit_log("PASSWORD_CHANGED", "", request)

    # ── 仓位分组 ──
    if data.portfolios is not None:
        settings.portfolios = [p.model_dump() if hasattr(p, 'model_dump') else p
                               for p in data.portfolios]

    # API 变更时重连
    if changed_api and settings.binance_api_key and settings.binance_api_key != "demo":
        try:
            init_client(
                settings.binance_api_key, settings.binance_api_secret,
                settings.binance_testnet, settings.binance_proxy,
            )
            positions = state.client.get_positions()
            logger.info(f"API 重连成功，持仓数: {len(positions)}")
        except Exception as e:
            raise HTTPException(400, f"API 连接失败: {e}")

    _save_config_to_file()
    return {"ok": True}
