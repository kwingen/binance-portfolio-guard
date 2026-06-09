# Binance Portfolio Guard

币安合约止损面板 — 仓位分组独立止损，一键清仓。

![仪表盘](docs/screenshots/dashboard.png)

## 特性

- **仓位分组独立止损** — 每组独立阈值，触发只平该组，从持仓列表点选添加
- **双止损模式** — USDT 绝对值 / 开仓成本百分比，止损线锚定入场价
- **API Key 加密持久化** — 保存后重启不丢失
- **零配置启动** — `./deploy.sh` 一键部署，Web 引导初始化
- **安全** — httpOnly Cookie + CSRF + bcrypt + JWT(15min) + Setup Token + 密码复杂度强制
- **重试与熔断** — API 失败自动重试，连续 10 次失败暂停监控
- **25 个单元测试** — 覆盖核心计算/密码/分组匹配

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
| 实时盈亏 / 持仓（按分组排列） / 紧急清仓 / 日志 | API Key / 代理 / 密码 / 模式切换 |

![设置面板](docs/screenshots/settings.png)

## 止损逻辑

- 多仓 → SELL | 空仓 → BUY
- 触发前自动撤单，市价 `reduceOnly`
- 分组止损锚定各组开仓成本，不随市价漂移
- 分组管理在持仓卡片右上角，点选持仓加入
- 全局止损仅计算未分组仓位，不影响已分组仓位

## 安全

| 层级 | 措施 |
|------|------|
| 密码 | bcrypt，8 位 + 大小写 + 数字 + 特殊字符 |
| 会话 | httpOnly Secure SameSite Cookie + CSRF 双验证 |
| JWT | 15 分钟过期 + jti 黑名单 |
| API Key | 加密持久化 + 修改需密码验证 |
| 防御 | Setup 5 次/分钟，API 240 次/分钟限流 |
| 运行时 | 非 root，异常不泄露堆栈 |

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
pytest tests/ -v          # 25 个单元测试
cd client && npm run dev   # 前端热重载
```

## 技术栈

FastAPI + Vue 3 + Vite + Pinia + SSE + Docker 多阶段构建

## License

GPL-3.0
