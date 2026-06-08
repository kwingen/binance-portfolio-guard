# Binance 合约总仓位止损监控

全仓合约止损面板 — 每 5 秒检查未实现盈亏，触及阈值时一键清仓。

支持 **USDT 绝对值** 和 **开仓成本百分比** 两种止损模式，多空双向仓位正确区分。

## 架构

```
client/          Vue 3 + Vite + Pinia     前端 SPA
server/          FastAPI                   后端 REST API
binance_portfolio_sl.py                    核心止损库（纯 Python）
```

## 快速开始

### 前置条件

- Python 3.12+
- Node.js 18+（仅构建前端时需要）
- 币安合约 API Key（Enable Futures，**不勾选提现**，IP 白名单设为你服务器的公网 IP）

### 1. 构建前端

```bash
cd client
npm install
npm run build
cd ..
```

### 2. 启动服务器

```bash
python -m uvicorn server.main:app --host 0.0.0.0 --port 8080
```

首次启动会在控制台打印一个 **Setup Token**：

```
============================================================
⚠️  首次运行 — 需要设置管理员密码
    Setup Token: xxxxxxxxxxxxxxxxxxxxxx
    此 token 仅在服务器控制台显示，切勿泄露
============================================================
```

### 3. 浏览器访问

打开 `http://<服务器IP>:8080`，自动跳转到设置页面：

1. 输入控制台的 Setup Token
2. 设置管理员密码（8 位 + 大小写 + 数字 + 特殊字符）
3. 进入仪表盘，点 ⚙️ 齿轮填入币安 API Key
4. 确认 DEMO 模式正常后，关闭 dry_run，启动监控

**全程不需要编辑任何配置文件。**

### 4. 环境变量（可选）

所有配置都可在 Web 面板完成。以下环境变量作为备选：

| 变量 | 说明 |
|------|------|
| `SL_PASSWORD` | 管理员密码（需符合复杂度要求） |
| `SL_BINANCE_API_KEY` | 币安 API Key |
| `SL_BINANCE_API_SECRET` | 币安 API Secret |
| `SL_BINANCE_PROXY` | HTTP 代理 |
| `SL_DRY_RUN` | 演习模式（`true`/`false`） |
| `SL_SECRET_KEY` | JWT 签名密钥（留空自动生成） |

## 止损模式

| 模式 | 配置值 | 计算方式 | 场景 |
|------|--------|----------|------|
| **USDT** | -100 | 总盈亏 ≤ -100 → 止损 | 固定金额止损 |
| **%** | 5 | 总盈亏 ≤ -(开仓成本 × 5%) → 止损 | 按仓位比例止损 |

止损线锚定**开仓成本**（entryPrice × 数量），不随市价浮动。

多仓 → 卖出平仓 | 空仓 → 买入平仓 | 触发前自动撤销所有挂单

## API 限额

每轮检查消耗 10 weight（positionRisk 5 + account 5），
5 秒间隔 = 每分钟 120 weight，占 2400 限额的 **5%**。

## 安全特性

- 首次启动生成一次性 Setup Token，仅控制台可见
- 管理员密码 bcrypt 哈希，强制复杂度（8 位 + 大小写 + 数字 + 特殊字符）
- JWT 认证 + 过期机制
- Setup 端点防暴力破解（每 IP 5 次/分钟）
- Pydantic 输入校验，全局异常拦截不泄露堆栈
- API 限流 120 req/min
- 紧急清仓需双击确认

## 面板功能

- 实时总盈亏 + 开仓成本/市值显示
- 持仓明细表（交易对/方向/数量/开仓价/标记价/杠杆/盈亏）
- 在线切换 USDT / % 止损模式
- 设置面板（API Key、代理、间隔、密码，全部 Web 操作）
- 紧急一键清仓（双击确认防误触）
- SSE 实时推送，无需手动刷新
- Swagger API 文档（`/docs`）

## 开发

```bash
# 后端 API 文档
open http://localhost:8080/docs

# 前端热重载开发
cd client && npm run dev

# 生产构建
cd client && npm run build
```
