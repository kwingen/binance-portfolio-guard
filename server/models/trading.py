# ── 交易 ──
from typing import Optional, List, Any
from pydantic import BaseModel, Field


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


class EmergencyCloseRequest(BaseModel):
    confirm: bool = False
