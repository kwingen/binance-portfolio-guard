# Binance Portfolio Guard

币安合约止损面板 — 仓位分组独立止损、内置开仓下单、一键清仓。

![仪表盘](docs/screenshots/dashboard.png)

## 特性

- **仓位分组独立止损** — 每组独立阈值，触发只平该组
- **双止损模式** — USDT 绝对值 / 开仓成本百分比，止损线锚定入场价
- **内置开仓下单** — 市价/限价、做多/做空、杠杆 1~125x，不用切币安
- **零配置启动** — `./deploy.sh` 一键部署，Web 引导初始化
- **安全** — bcrypt + JWT(15min) + jti 黑名单 + Setup Token + API Key 密码二次验证
- **鲁棒** — 指数退避重试 + 熔断保护 + `/ready` 健康探针
- **API 限额** — 每轮 10 weight × 12 轮/分 = 120 weight/分（限额 2400 的 5%）

## 快速开始

```bash
git clone https://github.com/kwingen/binance-portfolio-guard.git
cd binance-portfolio-guard
./deploy.sh
```

首次启动控制台输出 Setup Token，浏览器打开 `http://localhost:8080` 完成初始化。

![登录页](docs/screenshots/login.png)

## 界面

| 仪表盘 | 设置面板 |
|--------|----------|
| 实时盈亏 / 持仓 / 分组卡片 / 开仓下单 / 紧急清仓 / 日志 | API Key / 代理 / 密码 / 仓位分组编辑器 |

![设置面板](docs/screenshots/settings.png)

## 止损逻辑

- 多仓 → SELL | 空仓 → BUY
- 触发前自动撤单，市价 `reduceOnly`
- 分组止损锚定各组开仓成本，不随市价漂移

## 安全

| 层级 | 措施 |
|------|------|
| 初始化 | 一次性 Setup Token，仅控制台可见 |
| 密码 | bcrypt，8 位 + 大小写 + 数字 + 特殊字符 |
| 会话 | JWT 15 分钟过期 + jti 黑名单可吊销 |
| API Key | GET 接口不返回任何 Key 信息，修改需密码验证 |
| CORS | 仅允许 localhost:8080 |
| 防御 | Setup 端点 5 次/分钟，API 240 次/分钟限流 |
| 运行时 | 非 root，异常不泄露堆栈，config 文件 0600 权限 |
| 鲁棒 | 1s/2s/3s 重试 + 连续 10 次失败熔断 + /ready 探针 |

## 部署

```bash
# Docker
docker compose up -d

# 环境变量
export SL_PASSWORD="你的强密码"
export SL_BINANCE_API_KEY="..."

# 手动
pip install -r requirements.txt
cd client && npm ci && npm run build && cd ..
python -m uvicorn server.main:app --host 0.0.0.0 --port 8080
```

最低配置：1 vCPU / 256MB 内存，需固定公网 IP（Binance 白名单）。

## 开发

```bash
# 测试
pytest tests/ -v

# 前端热重载
cd client && npm run dev
```

## 技术栈

FastAPI + Vue 3 + Vite + Pinia + SSE + Docker 多阶段构建

## License

GPL-3.0
