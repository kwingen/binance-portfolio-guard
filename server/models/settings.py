# ── 设置 ──
from typing import Optional, List
from pydantic import BaseModel, Field, model_validator


class PortfolioPosition(BaseModel):
    """仓位组中的一个仓位定义"""
    symbol: str = Field(..., min_length=1, max_length=20, description="交易对，如 BTCUSDT")
    direction: str = Field(..., pattern="^(long|short)$", description="多或空")


class PortfolioGroup(BaseModel):
    """一个仓位分组，独立止损"""
    name: str = Field(..., min_length=1, max_length=32, description="分组名称")
    positions: List[PortfolioPosition] = Field(..., min_length=1, max_length=20)
    stop_loss_threshold: float = Field(default=5.0, gt=0)
    threshold_type: str = Field(default="percent", pattern="^(usd|percent)$")
    enabled: bool = True


class SettingsUpdate(BaseModel):
    """部分更新设置"""
    api_key: Optional[str] = None
    api_secret: Optional[str] = None
    testnet: Optional[bool] = None
    proxy: Optional[str] = None
    stop_loss_threshold: Optional[float] = None
    threshold_type: Optional[str] = None
    check_interval_seconds: Optional[int] = None
    dry_run: Optional[bool] = None
    auth_password: Optional[str] = None
    portfolios: Optional[List[PortfolioGroup]] = None
    current_password: Optional[str] = None  # 修改 API Key 时需要

    @model_validator(mode="after")
    def validate_threshold(self):
        if self.threshold_type and self.threshold_type not in ("usd", "percent"):
            raise ValueError("threshold_type 必须是 'usd' 或 'percent'")
        if self.check_interval_seconds is not None and self.check_interval_seconds < 2:
            raise ValueError("间隔不能小于 2 秒")
        return self


class SettingsInfo(BaseModel):
    api_key_masked: str = ""     # 废弃，永远空字符串（安全）
    has_api_configured: bool = False  # 是否已配置 API
    testnet: bool = False
    proxy: str = ""              # 废弃，永远空字符串
    dry_run: bool = True
    check_interval_seconds: int = 5
    threshold_type: str = "percent"
    stop_loss_threshold: float = 5.0
    has_auth_password: bool = False
    portfolios: List[PortfolioGroup] = []


class MonitorControl(BaseModel):
    action: str  # "start" | "stop"
