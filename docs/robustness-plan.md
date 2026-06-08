# 鲁棒性整改方案

## 1. 重试机制 — 优先级：高

**现状**：API 调用失败直接跳过本轮，止损延迟风险。

**方案**：在 `monitor.py` 的轮询循环中加入指数退避重试：

```python
# 单次 check 失败时重试 3 次，间隔 2s/4s/8s
MAX_CHECK_RETRIES = 3
for attempt in range(MAX_CHECK_RETRIES):
    try:
        positions = client.get_positions()
        break
    except Exception:
        if attempt == MAX_CHECK_RETRIES - 1:
            raise
        time.sleep(2 ** attempt)
```

已存在的 `BinanceFuturesClient._request()` 里有单请求重试，加在这里是兜底整个 check 流程（比如 account 查询也失败时）。

**改动范围**：`server/services/monitor.py` 一处，约 15 行。

---

## 2. 熔断保护 — 优先级：高

**方案**：连续失败 N 次 → 暂停监控 M 秒 → 再试一次 → 仍失败则停止并告警。

```python
# 在 MonitorState 中追踪
consecutive_failures = 0
circuit_open_until = 0  # timestamp

# 在 monitor_loop 中
if consecutive_failures >= 10:
    state.monitoring = False
    state.last_error = "熔断: 连续 10 次失败，监控已暂停"
    broadcast_sse("circuit_breaker", {"reason": "10 consecutive failures"})
    break
elif consecutive_failures >= 5:
    # 退避 30 秒
    time.sleep(30)
```

**改动范围**：`server/services/monitor.py`，约 20 行。

---

## 3. 健康检查与就绪探针 — 优先级：中

**现状**：已有 `/health` 但太简单。

**方案**：增强为三个端点：

| 端点 | 返回 | 用途 |
|------|------|------|
| `GET /health` | `{"status":"ok","uptime":123}` | 存活检测 |
| `GET /ready` | `{"ready":true,"api_connected":true}` | 就绪探测（API 是否通） |
| `GET /status` | 已有，包含完整状态 | 业务监控 |

**改动范围**：`server/main.py` 加一个 `/ready` 端点，约 10 行。

---

## 4. 超时控制 — 优先级：低

**现状**：已设置 `timeout=8` 在 BinanceFuturesClient 中。

**分析**：当前实现已足够。币安合约 API 正常响应 <500ms，8 秒是合理余额。无需改动。

---

## 5. 配置边界校验 — 优先级：中

**方案**：在 Pydantic 模型中添加 `field_validator`：

```python
@field_validator("check_interval_seconds")
def check_interval_min(cls, v):
    if v < 2: raise ValueError("最小 2 秒")
    if v > 300: raise ValueError("最大 300 秒")
    return v

@field_validator("leverage")
def leverage_range(cls, v):
    if v < 1 or v > 125: raise ValueError("杠杆范围 1-125")
    return v
```

**改动范围**：`server/models/settings.py`、`server/models/trading.py`，约 8 行。

---

## 6. 资源释放 — 优先级：中

**方案**：

- **文件句柄**：`_save_config_to_file` 已用 `with open()`，没问题
- **SSE 清理**：当前逻辑已通过 `finally` 清理队列，无需改动
- **优雅关闭**：在 `lifespan` 中添加 signal handler：

```python
@asynccontextmanager
async def lifespan(app):
    # ... startup ...
    yield
    # shutdown:
    state.monitoring = False
    # wait for current check to finish (max 10s)
    time.sleep(10)
```

**改动范围**：`server/main.py`，约 5 行。

---

## 7. 日志轮转 — 优先级：低

**方案**：在 `main.py` 的 `logging.basicConfig` 之后添加 `RotatingFileHandler`：

```python
from logging.handlers import RotatingFileHandler
fh = RotatingFileHandler("server.log", maxBytes=10*1024*1024, backupCount=3)
fh.setLevel(logging.WARNING)
logging.getLogger().addHandler(fh)
```

或依靠 Docker 的日志驱动（`json-file` + `max-size`），不改代码也行。

**改动范围**：`server/main.py`，约 5 行（可选，Docker 部署下不必要）。

---

## 8. 状态一致性 — 优先级：中

**问题 1**：停止监控时正在进行的检查不会中断。

**方案**：不用改。当前行为是合理的——等当前轮询完成再停，避免半截操作。5 秒延迟可以接受。

**问题 2**：分组配置更新后下一轮才生效。

**方案**：这是设计取舍。分组配置低频变更，5 秒内生效足够。如果要即时生效，需要加 `threading.Event` 通知，复杂度高，不值得。

**结论**：两条都不改。

---

## 9. 单元测试 — 优先级：高

**方案**：对核心函数添加 pytest：

| 测试目标 | 覆盖内容 |
|---------|---------|
| `calculate_total_entry_value` | 多仓/空仓/混合计算正确性 |
| `calculate_total_pnl` | 盈亏正负号 |
| `match_positions_to_groups` | 分组匹配、去重、未分组 |
| `get_effective_threshold` | USDT 和百分比模式 |
| `validate_password_strength` | 各边界条件 |
| `close_all_positions` (mock) | dry_run / 实盘逻辑 |

```bash
pip install pytest pytest-mock
# tests/test_core.py, tests/test_auth.py, tests/test_monitor.py
```

**改动范围**：新建 `tests/` 目录，3 个文件，约 150 行。

---

## 优先级总结

| 编号 | 问题 | 优先级 | 工作量 | 建议 |
|------|------|--------|--------|------|
| 1 | 重试机制 | 🔴 高 | 15 行 | **改** |
| 2 | 熔断保护 | 🔴 高 | 20 行 | **改** |
| 9 | 单元测试 | 🔴 高 | 150 行 | **改** |
| 3 | /ready 端点 | 🟡 中 | 10 行 | 改 |
| 5 | 配置边界 | 🟡 中 | 8 行 | 改 |
| 6 | 优雅关闭 | 🟡 中 | 5 行 | 改 |
| 4 | 超时控制 | 🟢 低 | 0 | 已满足 |
| 7 | 日志轮转 | 🟢 低 | 5 行 | Docker 部署不需要 |
| 8 | 状态一致性 | 🟢 低 | 0 | 设计合理不改 |
