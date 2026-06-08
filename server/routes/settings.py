"""设置路由"""
import json
import os
import logging
from fastapi import APIRouter, HTTPException, Depends

from server.config import settings
from server.auth import require_auth, hash_password
from server.models import SettingsUpdate, SettingsInfo
from server.services import init_client, state

logger = logging.getLogger("settings")
router = APIRouter(prefix="/api/settings", tags=["设置"], dependencies=[Depends(require_auth)])


def _save_config_to_file():
    """将当前 settings 写回配置文件"""
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
        logger.info(f"配置已保存到 {path}")
    except Exception as e:
        logger.error(f"保存配置失败: {e}")


@router.get("", response_model=SettingsInfo)
async def get_settings():
    masked = ""
    if settings.binance_api_key and settings.binance_api_key != "demo":
        masked = settings.binance_api_key[:6] + "****"
    return SettingsInfo(
        api_key_masked=masked,
        testnet=settings.binance_testnet,
        proxy=settings.binance_proxy or "",
        dry_run=settings.dry_run,
        check_interval_seconds=settings.check_interval_seconds,
        threshold_type=settings.threshold_type,
        stop_loss_threshold=settings.stop_loss_threshold,
        has_auth_password=bool(settings.auth_password_hash),
    )


@router.post("")
async def update_settings(data: SettingsUpdate):
    """更新设置，可选地重连 API"""
    changed_api = False

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

    # API 密钥（masked 时不更新）
    if data.api_key and "****" not in data.api_key:
        changed_api = True
        settings.binance_api_key = data.api_key.strip()
    if data.api_secret and "****" not in data.api_secret:
        changed_api = True
        settings.binance_api_secret = data.api_secret.strip()

    # 密码
    if data.auth_password:
        settings.auth_password_hash = hash_password(data.auth_password)

    # API 变更时重连
    if changed_api and settings.binance_api_key and settings.binance_api_key != "demo":
        try:
            init_client(
                settings.binance_api_key,
                settings.binance_api_secret,
                settings.binance_testnet,
                settings.binance_proxy,
            )
            positions = state.client.get_positions()
            logger.info(f"API 重连成功，持仓数: {len(positions)}")
        except Exception as e:
            raise HTTPException(400, f"API 连接失败: {e}")

    _save_config_to_file()
    return {"ok": True}
