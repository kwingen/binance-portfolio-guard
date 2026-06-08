# Binance 合约总仓位止损监控

全仓合约止损面板 — 每 5 秒检查未实现盈亏，支持按仓位分组独立止损，触及阈值时一键清仓。

![登录页](docs/screenshots/login.png)

## 架构

```
client/          Vue 3 + Vite + Pinia     前端 SPA
server/          FastAPI                   后端 REST API
binance_portfolio_sl.py                    核心止损库（纯 Python）
```

## 界面

![仪表盘](docs/screenshots/dashboard.png)

![设置面板](docs/screenshots/settings.png)

## 快速开始

### Docker（推荐）

```bash
git clone https://github.com/kwingen/binance-portfolio-guard.git
cd binance-portfolio-guard
./deploy.sh
```

脚本自动检测环境：
- **有 Docker** → `docker compose up -d`，一键启动
- **无 Docker** → 自动创建 venv、安装依赖、构建前端、启动服务

首次启动控制台输出一次性 **Setup Token**，浏览器打开 `http://localhost:8080`，输入 token + 设置密码即可。

### 配置（可选）

```bash
# 环境变量方式
export SL_PASSWORD="你的强密码"
export SL_BINANCE_API_KEY="你的API_Key"
export SL_BINANCE_API_SECRET="你的API_Secret"

# 或创建 .env 文件
cp .env.example .env
# 编辑填入配置
```

所有配置也可在 Web 面板中完成，无需手动编辑文件。

## 止损模式

### 全局止损

适用于未分组的仓位：

| 模式 | 配置值 | 计算方式 |
|------|--------|----------|
| **USDT** | -100 | 总盈亏 ≤ -100 → 止损 |
| **%** | 5 | 总盈亏 ≤ -(开仓成本 × 5%) → 止损 |

止损线锚定**开仓成本**（entryPrice × 数量），不随市价浮动。

### 仓位分组独立止损

在设置面板中创建仓位组，每组独立配置止损：

```
📦 BTC+ETH 大仓位          5% 止损
   仓位: BTCUSDT多, ETHUSDT空

📦 山寨币组                 3% 止损
   仓位: XRPUSDT多, XLMUSDT多, SOLUSDT空
```

触发时**只平该组仓位**，不影响其他组。一个仓位只属于第一个匹配的组。

## 仓位方向

多空双向正确区分：

- **多仓**（positionAmt > 0）→ 卖出平仓
- **空仓**（positionAmt < 0）→ 买入平仓
- 触发前自动撤销所有挂单
- 全部市价单，`reduceOnly=true`

## API 限额

每轮检查消耗 10 weight（positionRisk 5 + account 5），5 秒间隔 = 每分钟 120 weight，仅占 2400 限额的 **5%**。

## 安全特性

| 层级 | 措施 |
|------|------|
| 首次启动 | 随机 Setup Token，仅控制台可见 |
| 密码 | bcrypt 哈希，强制 8 位 + 大小写 + 数字 + 特殊字符 |
| 认证 | JWT + 过期（默认 60 分钟） |
| 防暴力破解 | Setup 端点 5 次/分钟限制，常数时间 token 比较 |
| 输入校验 | Pydantic 模型 |
| API 限流 | 120 req/min (slowapi) |
| 异常处理 | 全局拦截，不泄露堆栈 |
| 紧急操作 | 清仓需双击确认 |

## 环境变量（可选）

所有配置均可通过 Web 面板完成。以下变量作为备选：

| 变量 | 说明 |
|------|------|
| `SL_PASSWORD` | 管理员密码（需符合复杂度） |
| `SL_BINANCE_API_KEY` | 币安 API Key |
| `SL_BINANCE_SECRET` | 币安 API Secret |
| `SL_BINANCE_PROXY` | HTTP 代理 |
| `SL_DRY_RUN` | 演习模式（`true`/`false`） |

## 部署

最低配置：1 vCPU / 256MB 内存 / 1GB 磁盘，需要固定公网 IP（币安白名单）。

## 开发

```bash
# API 文档
open http://localhost:8080/docs

# 前端热重载
cd client && npm run dev

# 生产构建
cd client && npm run build
```
