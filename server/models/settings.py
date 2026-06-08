# ── 设置 ──
from typing import Optional
from pydantic import BaseModel, Field, model_validator


class SettingsUpdate(BaseModel):
    """部分更新设置"""
    api_key: Optional[str] = None
    api_secret: Optional[str] = None
    testnet: Optional[bool] = None
    proxy: Optional[str] = None
    stop_loss_threshold: Optional[float] = None
    threshold_type: Optional[str] = None       # "usd" | "percent"
    check_interval_seconds: Optional[int] = None
    dry_run: Optional[bool] = None
    auth_password: Optional[str] = None

    @model_validator(mode="after")
    def validate_threshold(self):
        if self.threshold_type and self.threshold_type not in ("usd", "percent"):
            raise ValueError("threshold_type 必须是 'usd' 或 'percent'")
        if self.check_interval_seconds is not None and self.check_interval_seconds < 2:
            raise ValueError("间隔不能小于 2 秒")
        return self


class SettingsInfo(BaseModel):
    api_key_masked: str = ""
    testnet: bool = False
    proxy: str = ""
    dry_run: bool = True
    check_interval_seconds: int = 5
    threshold_type: str = "percent"
    stop_loss_threshold: float = 5.0
    has_auth_password: bool = False


class MonitorControl(BaseModel):
    action: str  # "start" | "stop"
