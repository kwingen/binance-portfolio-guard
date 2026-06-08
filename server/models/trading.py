# ── 交易 ──
from typing import Optional, List, Any
from pydantic import BaseModel, Field, model_validator


class PositionItem(BaseModel):
    symbol: str
    positionAmt: str
    entryPrice: str
    markPrice: str
    unRealizedProfit: str
    leverage: str = "1"


class AccountInfo(BaseModel):
    totalWalletBalance: str = "0"
    totalUnrealizedProfit: str = "0"
    totalMarginBalance: str = "0"
    availableBalance: str = "0"


class DashboardStatus(BaseModel):
    monitoring: bool
    stop_loss_triggered: bool
    positions: List[dict] = []
    total_pnl: float = 0.0
    total_pnl_formatted: str = "+0.00"
    total_notional: float = 0.0
    total_entry_value: float = 0.0
    account: dict = {}
    last_check_time: Optional[str] = None
    last_error: Optional[str] = None
    total_checks: int = 0
    threshold: float = 5.0
    threshold_type: str = "percent"
    effective_threshold: float = 0.0
    effective_threshold_formatted: str = "+0.00"
    dry_run: bool = True
    testnet: bool = False
    has_api_key: bool = False
    groups: List[dict] = []


class EmergencyCloseRequest(BaseModel):
    confirm: bool = False


class OrderRequest(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=20)
    side: str = Field(..., pattern="^(BUY|SELL)$")        # BUY=做多, SELL=做空
    order_type: str = Field(default="MARKET", pattern="^(MARKET|LIMIT)$")
    quantity: float = Field(..., gt=0)
    price: Optional[float] = None                           # LIMIT 订单必填
    leverage: int = Field(default=1, ge=1, le=125)

    @model_validator(mode="after")
    def check_limit_price(self):
        if self.order_type == "LIMIT" and self.price is None:
            raise ValueError("限价单必须提供 price")
        return self
