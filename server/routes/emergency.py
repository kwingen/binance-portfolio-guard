"""紧急清仓 + SSE 实时推送"""
import json
import asyncio
import logging
from fastapi import APIRouter, HTTPException, Depends, Request
from jose import JWTError, jwt
from sse_starlette.sse import EventSourceResponse

from server.config import settings
from server.auth import require_auth, is_revoked
from server.models import EmergencyCloseRequest
from server.services import state, on_event, close_all_positions

logger = logging.getLogger("emergency")

router = APIRouter(prefix="/api", tags=["紧急操作"])

# SSE 队列
_sse_queues: list[asyncio.Queue] = []


def _sse_handler(event: str, data: dict):
    msg = json.dumps({"event": event, "data": data}, default=str)
    dead = []
    for q in _sse_queues:
        try:
            q.put_nowait(msg)
        except asyncio.QueueFull:
            dead.append(q)
    for q in dead:
        try:
            _sse_queues.remove(q)
        except ValueError:
            pass


on_event(_sse_handler)


def _verify_sse_token(token: str) -> bool:
    """SSE token 验证 — 接受普通 JWT 或专用 SSE token"""
    if not token:
        return False
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
        if is_revoked(payload.get("jti", "")):
            return False
        return True
    except JWTError:
        return False


@router.get("/events")
async def sse_stream(request: Request, token: str = ""):
    """SSE 实时推送 — 优先从 Cookie 读 token，兼容 query param"""
    cookie_token = request.cookies.get("sl_token", "")
    effective_token = cookie_token or token
    if not _verify_sse_token(effective_token):
        raise HTTPException(status_code=401, detail="无效或过期的令牌")

    queue: asyncio.Queue = asyncio.Queue(maxsize=256)

    async def generate():
        _sse_queues.append(queue)
        try:
            yield {"event": "connected", "data": "{}"}
            while True:
                try:
                    msg = await asyncio.wait_for(queue.get(), timeout=15)
                    yield {"data": msg}
                except asyncio.TimeoutError:
                    yield {"comment": "heartbeat"}
        except asyncio.CancelledError:
            pass
        finally:
            try:
                _sse_queues.remove(queue)
            except ValueError:
                pass

    return EventSourceResponse(generate())


@router.post("/emergency-close", dependencies=[Depends(require_auth)])
async def emergency_close(req: EmergencyCloseRequest):
    """紧急一键清仓（需 confirm=true）"""
    if not req.confirm:
        raise HTTPException(400, detail="请确认操作")

    if not state.client:
        raise HTTPException(500, detail="客户端未初始化")

    try:
        logger.warning("🚨 紧急清仓触发!")
        positions = state.client.get_positions()
        result = close_all_positions(state.client, positions, dry_run=settings.dry_run)

        state.stop_loss_triggered = True
        state.monitoring = False

        _sse_handler("emergency_close", result)
        return result
    except Exception as e:
        logger.error(f"紧急清仓失败: {e}")
        raise HTTPException(500, detail=str(e))
