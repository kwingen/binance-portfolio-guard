"""
服务器配置 —— 所有敏感信息从环境变量读取，无硬编码
"""
import os
from pathlib import Path
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # ── 安全 ──
    secret_key: str = ""  # JWT 签名密钥
    access_token_expire_minutes: int = 15  # 15 分钟，降低被窃窗口
    auth_password_hash: str = ""  # bcrypt hash，启动时从明文密码生成

    # ── 币安 API ──
    binance_api_key: str = ""
    binance_api_secret: str = ""
    binance_testnet: bool = False
    binance_proxy: Optional[str] = None

    # ── 止损 ──
    stop_loss_threshold: float = 5.0
    threshold_type: str = "percent"  # "usd" | "percent"
    check_interval_seconds: int = 5
    dry_run: bool = True
    portfolios: list = []  # List[PortfolioGroup]  — 仓位分组

    # ── 服务器 ──
    host: str = "0.0.0.0"
    port: int = 8080

    # ── 文件路径 ──
    config_path: Optional[str] = None  # 配置文件路径，用于持久化设置
    audit_log_path: str = "audit.log"
    database_url: str = "sqlite:///./audit.db"

    model_config = {"env_prefix": "SL_", "env_file": ".env", "extra": "allow"}


settings = Settings()
