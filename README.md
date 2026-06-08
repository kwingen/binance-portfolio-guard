# Binance 合约总仓位止损监控

每 5 秒通过币安合约 API 读取所有仓位，计算总未实现盈亏，触及阈值时一键清仓止损。

## API 限额消耗

每轮检查消耗 10 weight（positionRisk 5 + account 5），5 秒间隔 = 每分钟 120 weight，仅占 2400 限额的 **5%**。

## 快速开始

### 1. 创建配置文件

```bash
cp config.example.json config.json
```

编辑 `config.json`，填入真实的 API Key 和参数：

```json
{
  "api_key": "你的API_KEY",
  "api_secret": "你的API_SECRET",
  "testnet": false,
  "stop_loss_threshold": -100,
  "check_interval_seconds": 5,
  "dry_run": true,
  "proxy": null,
  "log_file": "binance_sl.log",
  "log_level": "INFO"
}
```

### 2. 币安 API 权限

在币安后台创建 API Key 时，**只勾选合约交易权限**：

- ✅ `Enable Futures`（合约交易）
- ❌ 不要勾选提现权限
- 设置 IP 白名单为你的服务器 IP（`curl -s ifconfig.me` 查看）

### 3. 启动仪表盘

```bash
cd /app/binance_portfolio_sl
/app/.venv/bin/python dashboard_server.py config.json --port 8080
```

浏览器访问 `http://<你的服务器IP>:8080`

### 4. 先演习再实盘

面板上默认为 DEMO 模式，先点「启动监控」看几轮日志确认正常，再把 `dry_run` 改 false。

### 5. 设为开机自启（可选）

```bash
sudo cp binance-sl.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now binance-sl
```

## 参数说明

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `stop_loss_threshold` | 止损阈值（负数=亏损，如 -100 = 总亏损 100 USDT） | -100 |
| `check_interval_seconds` | 检查间隔秒数 | 5 |
| `dry_run` | 演习模式 | true |
| `testnet` | 测试网 | false |
| `proxy` | HTTP 代理 | null |

## 止损逻辑

1. 每 5 秒获取所有合约仓位
2. 累加所有仓位的 `unRealizedProfit`
3. 总未实现盈亏 ≤ 阈值 → 触发止损
4. 撤销挂单 → 市价单逐仓平掉（`reduceOnly=true`）
5. 多仓 → 卖出 | 空仓 → 买入

## 面板功能

- 实时总盈亏显示
- 持仓列表 + 账户信息
- 在线修改止损阈值
- 紧急一键清仓（双击确认）
- 实时日志流
