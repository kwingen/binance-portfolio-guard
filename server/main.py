"""
Binance 总仓位止损 — FastAPI 后端
================================
启动: uvicorn server.main:app --host 0.0.0.0 --port 8080
环境变量: 所有配置以 SL_ 前缀从环境变量读取
"""
import os
import sys
import time
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
from server.auth import hash_password, validate_password_strength, is_setup_needed
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
        ok, err = validate_password_strength(raw_pw)
        if not ok:
            logger.critical(f"❌ SL_PASSWORD 不符合复杂度要求: {err}")
            sys.exit(1)
        settings.auth_password_hash = hash_password(raw_pw)
        logger.info("已加载环境变量中的密码")
    else:
        # 生成一次性 setup token，仅在控制台显示
        setup_token = secrets.token_urlsafe(16)
        settings._setup_token = setup_token
        settings._setup_mode = True
        logger.warning("=" * 60)
        logger.warning("⚠️  首次运行 — 需要设置管理员密码")
        logger.warning(f"    Setup Token: {setup_token}")
        logger.warning("    此 token 仅在服务器控制台显示，切勿泄露")
        logger.warning("    打开浏览器访问页面，输入此 token 完成初始化")
        logger.warning("=" * 60)
else:
    settings._setup_mode = False

# ── 限流器 ──
limiter = Limiter(key_func=get_remote_address, default_limits=["240/minute"])


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
    logger.info("正在关闭...")
    state.monitoring = False
    time.sleep(8)  # 等待当前轮询完成
    logger.info("已关闭")


app = FastAPI(
    title="Binance 总仓位止损",
    version="2.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url=None,
)

# ── CORS ── 严格限制，相同源访问（前后端同端口不需要跨域）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8080", "http://127.0.0.1:8080"],
    allow_credentials=False,  # 纯 JWT Bearer，不需要 cookie
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


@app.get("/ready")
async def ready():
    """就绪探测 — 用于 Docker/K8s readinessProbe"""
    api_ok = False
    if state.client and state.client.api_key != "demo":
        try:
            state.client.get_positions()
            api_ok = True
        except Exception:
            pass
    return {
        "ready": True,
        "api_connected": api_ok,
        "setup_complete": not is_setup_needed(),
    }


# ── 静态文件（前端）── SPA fallback: 非 API 路径返回 index.html
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

static_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "client", "dist")
index_html = os.path.join(static_dir, "index.html")

if os.path.isdir(static_dir):
    app.mount("/static", StaticFiles(directory=os.path.join(static_dir, "static")), name="static_assets")

    @app.get("/{full_path:path}")
    async def spa_fallback(full_path: str):
        """所有非 API 路径回退到 index.html（防路径遍历）"""
        # 禁止路径穿越
        safe = os.path.normpath(full_path)
        if safe.startswith("..") or os.path.isabs(safe):
            return FileResponse(index_html)
        file_path = os.path.join(static_dir, safe)
        # 确保解析后在 static_dir 内
        if not os.path.realpath(file_path).startswith(os.path.realpath(static_dir)):
            return FileResponse(index_html)
        if os.path.isfile(file_path):
            return FileResponse(file_path)
        return FileResponse(index_html)

    @app.get("/")
    async def root():
        return FileResponse(index_html)


# ── 命令行入口 ──
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=settings.host, port=settings.port)
