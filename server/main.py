"""
Binance 总仓位止损 — FastAPI 后端
================================
启动: uvicorn server.main:app --host 0.0.0.0 --port 8080
环境变量: 所有配置以 SL_ 前缀从环境变量读取
"""
import os
import sys
import logging
import threading
import secrets
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

# 确保项目根在 Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server.config import settings
from server.auth import hash_password
from server.routes import routers
from server.services import init_client, state, run_monitor_loop

# ── 日志 ──
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("main")

# ── 启动检查 ──
if not settings.secret_key:
    settings.secret_key = secrets.token_urlsafe(32)
    logger.warning("未设置 SL_SECRET_KEY，已生成随机密钥（重启后 JWT 将失效）")

if not settings.auth_password_hash:
    # 尝试从环境变量 SL_PASSWORD 读取明文密码并哈希
    raw_pw = os.environ.get("SL_PASSWORD", "")
    if raw_pw:
        settings.auth_password_hash = hash_password(raw_pw)
        logger.info("已从 SL_PASSWORD 环境变量加载密码")
    else:
        logger.critical("❌ 未设置登录密码！请设置环境变量 SL_PASSWORD")
        sys.exit(1)

# ── 限流器 ──
limiter = Limiter(key_func=get_remote_address, default_limits=["120/minute"])


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动后台线程"""
    # 初始化币安客户端
    if settings.binance_api_key and settings.binance_api_key != "demo":
        try:
            init_client(
                settings.binance_api_key,
                settings.binance_api_secret,
                settings.binance_testnet,
                settings.binance_proxy,
            )
            state.client.get_positions()
            logger.info("币安 API 连接成功")
        except Exception as e:
            logger.warning(f"币安 API 连接失败: {e}")

    # 启动监控线程
    monitor_thread = threading.Thread(target=run_monitor_loop, daemon=True, name="monitor")
    monitor_thread.start()
    logger.info("监控线程已启动")

    yield
    state.monitoring = False


app = FastAPI(
    title="Binance 总仓位止损",
    version="2.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url=None,
)

# ── CORS ──
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins.split(","),
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

# ── 限流 ──
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# ── 全局错误处理 ──
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """不泄露堆栈给客户端"""
    logger.error(f"未处理异常: {type(exc).__name__}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "服务器内部错误"},
    )


# ── 注册路由 ──
for router in routers:
    app.include_router(router)


# ── 健康检查 ──
@app.get("/health")
async def health():
    return {"status": "ok", "monitoring": state.monitoring}


# ── 静态文件（前端）─
from fastapi.staticfiles import StaticFiles

static_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "client", "dist")
if os.path.isdir(static_dir):
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")


# ── 命令行入口 ──
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=settings.host, port=settings.port)
