"""监控控制路由"""
from fastapi import APIRouter, Depends

from server.auth import require_auth
from server.services import state

router = APIRouter(prefix="/api/monitor", tags=["监控"], dependencies=[Depends(require_auth)])


@router.post("/start")
async def start_monitor():
    if state.monitoring:
        return {"ok": True, "message": "监控已在运行"}
    state.set_monitoring(True)
    return {"ok": True, "message": "监控已启动"}


@router.post("/stop")
async def stop_monitor():
    state.set_monitoring(False)
    return {"ok": True, "message": "监控已停止"}
