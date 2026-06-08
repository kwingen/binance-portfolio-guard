#!/usr/bin/env python3
"""
Binance 合约总仓位止损 - Web 仪表盘 v2
=========================================
Flask 后端 + 登录认证 + SSE 实时推送 + API 配置面板

用法:
    python3 dashboard_server.py config.json
    python3 dashboard_server.py config.json --port 8080 --host 0.0.0.0

环境变量 (优先级高于配置文件):
    SL_PASSWORD   登录密码
    SL_SECRET_KEY Flask session 密钥
"""

import sys
import os
import json
import time
import secrets
import threading
import logging
import argparse
import traceback
from datetime import datetime
from functools import wraps
from flask import Flask, render_template_string, request, jsonify, Response, session, redirect, url_for
from flask_cors import CORS

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from binance_portfolio_sl import BinanceFuturesClient, get_active_positions, \
    calculate_total_pnl, close_all_positions, load_config as load_sl_config

app = Flask(__name__)
CORS(app, supports_credentials=True)

# ── 安全配置 ────────────────────────────────────────
SECRET_KEY = os.environ.get("SL_SECRET_KEY", secrets.token_hex(32))
AUTH_PASSWORD = os.environ.get("SL_PASSWORD", None)  # None = 从配置文件读取

app.secret_key = SECRET_KEY
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

# ── 全局状态 ────────────────────────────────────────
state_lock = threading.RLock()

STATE = {
    "monitoring": False,
    "stop_loss_triggered": False,
    "last_positions": [],
    "last_pnl": 0.0,
    "last_notional": 0.0,
    "last_entry_value": 0.0,
    "last_account": {},
    "last_check_time": None,
    "last_error": None,
    "total_checks": 0,
    "client": None,
    "config": {},
    "config_path": None,
}

sse_clients: list = []
sse_lock = threading.Lock()


# ── 认证 ────────────────────────────────────────────

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("authenticated"):
            if request.path.startswith("/api/"):
                return jsonify({"error": "未登录", "redirect": "/login"}), 401
            return redirect(url_for("login_page"))
        return f(*args, **kwargs)
    return decorated


def check_password(pw: str) -> bool:
    pwd = AUTH_PASSWORD
    if not pwd:
        with state_lock:
            pwd = STATE["config"].get("auth_password", "")
    if not pwd:
        return False  # 未设置密码，拒绝登录
    return secrets.compare_digest(pw, pwd)


@app.route("/login", methods=["GET", "POST"])
def login_page():
    if request.method == "POST":
        data = request.get_json(force=True) if request.is_json else request.form
        pw = data.get("password", "")
        if check_password(pw):
            session["authenticated"] = True
            session.permanent = True
            if request.is_json:
                return jsonify({"ok": True, "redirect": "/"})
            return redirect(url_for("index"))
        if request.is_json:
            return jsonify({"error": "密码错误"}), 401
        return render_template_string(LOGIN_HTML, error="密码错误")
    return render_template_string(LOGIN_HTML, error="")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login_page"))


# ── 辅助计算 ────────────────────────────────────────

def calculate_total_entry_value(positions: list[dict]) -> float:
    total = 0.0
    for pos in positions:
        try:
            amt = abs(float(pos.get("positionAmt", 0)))
            entry = float(pos.get("entryPrice", 0))
            total += amt * entry
        except (ValueError, TypeError):
            pass
    return total


def calculate_total_notional(positions: list[dict]) -> float:
    total = 0.0
    for pos in positions:
        try:
            amt = abs(float(pos.get("positionAmt", 0)))
            mark = float(pos.get("markPrice", 0))
            total += amt * mark
        except (ValueError, TypeError):
            pass
    return total


def get_effective_threshold(config: dict, entry_value: float) -> float:
    threshold_type = config.get("threshold_type", "usd")
    raw = float(config.get("stop_loss_threshold", -100))
    if threshold_type == "percent":
        if entry_value <= 0:
            return 0
        return -(entry_value * raw / 100.0)
    return raw


# ── SSE ─────────────────────────────────────────────

def broadcast_sse(event: str, data: dict):
    with sse_lock:
        dead = []
        for q in sse_clients:
            try:
                q.append(json.dumps({"event": event, "data": data}))
            except Exception:
                dead.append(q)
        for q in dead:
            sse_clients.remove(q)


@app.route("/api/events")
@login_required
def sse_stream():
    def generate():
        q = []
        with sse_lock:
            sse_clients.append(q)
        try:
            yield f"data: {json.dumps({'event': 'connected', 'data': {}})}\n\n"
            while True:
                if q:
                    msg = q.pop(0)
                    yield f"data: {msg}\n\n"
                else:
                    yield f": heartbeat\n\n"
                    time.sleep(2)
        except GeneratorExit:
            pass
        finally:
            with sse_lock:
                if q in sse_clients:
                    sse_clients.remove(q)
    return Response(generate(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ── REST API (全部需登录) ───────────────────────────

@app.route("/api/status")
@login_required
def api_status():
    with state_lock:
        cfg = STATE["config"]
        threshold_type = cfg.get("threshold_type", "usd")
        entry_value = STATE["last_entry_value"]
        effective = get_effective_threshold(cfg, entry_value)

        return jsonify({
            "monitoring": STATE["monitoring"],
            "stop_loss_triggered": STATE["stop_loss_triggered"],
            "positions": STATE["last_positions"],
            "total_pnl": round(STATE["last_pnl"], 4),
            "total_pnl_formatted": f"{STATE['last_pnl']:+.2f}",
            "total_notional": round(STATE["last_notional"], 2),
            "total_entry_value": round(STATE["last_entry_value"], 2),
            "account": STATE["last_account"],
            "last_check_time": STATE["last_check_time"],
            "last_error": STATE["last_error"],
            "total_checks": STATE["total_checks"],
            "threshold": cfg.get("stop_loss_threshold", -100),
            "threshold_type": threshold_type,
            "effective_threshold": round(effective, 2),
            "effective_threshold_formatted": f"{effective:+.2f}",
            "dry_run": cfg.get("dry_run", True),
            "testnet": cfg.get("testnet", False),
            "has_api_key": STATE["config"].get("api_key", "demo") != "demo",
        })


@app.route("/api/config", methods=["GET", "POST"])
@login_required
def api_config():
    if request.method == "GET":
        with state_lock:
            return jsonify({
                "stop_loss_threshold": STATE["config"].get("stop_loss_threshold", 0),
                "threshold_type": STATE["config"].get("threshold_type", "usd"),
                "check_interval_seconds": STATE["config"].get("check_interval_seconds", 5),
                "dry_run": STATE["config"].get("dry_run", True),
            })

    data = request.get_json(force=True)
    with state_lock:
        if "stop_loss_threshold" in data:
            STATE["config"]["stop_loss_threshold"] = float(data["stop_loss_threshold"])
        if "threshold_type" in data:
            STATE["config"]["threshold_type"] = data["threshold_type"]
        if "check_interval_seconds" in data:
            STATE["config"]["check_interval_seconds"] = max(int(data["check_interval_seconds"]), 2)
        if "dry_run" in data:
            STATE["config"]["dry_run"] = bool(data["dry_run"])

        broadcast_sse("config_updated", STATE["config"])
    return jsonify({"ok": True})


@app.route("/api/settings", methods=["GET", "POST"])
@login_required
def api_settings():
    """获取 / 保存完整设置（API Key、密码等）"""
    if request.method == "GET":
        with state_lock:
            cfg = STATE["config"]
            return jsonify({
                "api_key_masked": cfg.get("api_key", "")[:6] + "****" if cfg.get("api_key") else "",
                "testnet": cfg.get("testnet", False),
                "proxy": cfg.get("proxy", ""),
                "dry_run": cfg.get("dry_run", True),
                "check_interval_seconds": cfg.get("check_interval_seconds", 5),
                "threshold_type": cfg.get("threshold_type", "usd"),
                "stop_loss_threshold": cfg.get("stop_loss_threshold", 5),
                "has_auth_password": bool(cfg.get("auth_password")),
            })

    data = request.get_json(force=True)
    config_path = STATE.get("config_path")

    if config_path and "example" in os.path.basename(config_path).lower():
        return jsonify({"error": "不能覆盖示例配置，请先 cp config.example.json config.json"}), 400

    with state_lock:
        cfg = dict(STATE["config"])

    # API 密钥
    if data.get("api_key") and "****" not in data["api_key"]:
        cfg["api_key"] = data["api_key"].strip()
    if data.get("api_secret") and "****" not in data["api_secret"]:
        cfg["api_secret"] = data["api_secret"].strip()
    if "testnet" in data:
        cfg["testnet"] = bool(data["testnet"])
    if "proxy" in data:
        cfg["proxy"] = data["proxy"].strip() or None
    if "dry_run" in data:
        cfg["dry_run"] = bool(data["dry_run"])
    if "stop_loss_threshold" in data:
        cfg["stop_loss_threshold"] = float(data["stop_loss_threshold"])
    if "threshold_type" in data:
        cfg["threshold_type"] = data["threshold_type"]
    if "check_interval_seconds" in data:
        cfg["check_interval_seconds"] = max(int(data["check_interval_seconds"]), 2)
    if "auth_password" in data and data["auth_password"]:
        cfg["auth_password"] = data["auth_password"].strip()
        global AUTH_PASSWORD
        AUTH_PASSWORD = cfg["auth_password"]

    # 保存到文件
    if config_path and os.path.isdir(os.path.dirname(config_path)):
        try:
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2, ensure_ascii=False)
            logging.info(f"设置已保存到 {config_path}")
        except Exception as e:
            return jsonify({"error": f"保存失败: {e}"}), 500

    # 重连 API（如果密钥变了）
    try:
        new_client = BinanceFuturesClient(
            api_key=cfg["api_key"],
            api_secret=cfg["api_secret"],
            testnet=cfg.get("testnet", False),
            proxy=cfg.get("proxy"),
            timeout=8,
        )
        positions = new_client.get_positions()
        logging.info("API 重连成功 ✓")
    except Exception as e:
        logging.error(f"API 重连失败: {e}")
        return jsonify({"error": f"API 连接失败: {e}"}), 400

    with state_lock:
        STATE["client"] = new_client
        STATE["config"] = cfg

    broadcast_sse("config_updated", cfg)
    return jsonify({"ok": True, "positions_count": len(positions)})


@app.route("/api/emergency-close", methods=["POST"])
@login_required
def api_emergency_close():
    data = request.get_json(silent=True) or {}
    if not data.get("confirm"):
        return jsonify({"error": "请确认操作", "need_confirm": True}), 400

    with state_lock:
        client = STATE["client"]
        dry_run = STATE["config"].get("dry_run", True)
    if not client:
        return jsonify({"error": "客户端未初始化"}), 500

    try:
        logging.warning("🚨 紧急清仓触发!")
        positions = client.get_positions()
        result = close_all_positions(client, positions, dry_run=dry_run)
        with state_lock:
            STATE["stop_loss_triggered"] = True
            STATE["monitoring"] = False
        broadcast_sse("emergency_close", result)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/monitor/start", methods=["POST"])
@login_required
def api_monitor_start():
    with state_lock:
        if STATE["monitoring"]:
            return jsonify({"ok": True, "message": "监控已在运行"})
        STATE["monitoring"] = True
        STATE["stop_loss_triggered"] = False
    broadcast_sse("monitor_status", {"monitoring": True})
    return jsonify({"ok": True})


@app.route("/api/monitor/stop", methods=["POST"])
@login_required
def api_monitor_stop():
    with state_lock:
        STATE["monitoring"] = False
    broadcast_sse("monitor_status", {"monitoring": False})
    return jsonify({"ok": True})


# ── 后台监控 ────────────────────────────────────────

def monitor_loop():
    logging.info("监控线程启动")
    while True:
        time.sleep(1)
        with state_lock:
            if not STATE["monitoring"] or STATE["stop_loss_triggered"]:
                continue
            client = STATE["client"]
            config = dict(STATE["config"])
            dry_run = config.get("dry_run", True)
            interval = config.get("check_interval_seconds", 5)

        if not client:
            time.sleep(5)
            continue

        try:
            positions = client.get_positions()
            active = get_active_positions(positions)
            total_pnl = calculate_total_pnl(positions)
            total_notional = calculate_total_notional(positions)
            total_entry = calculate_total_entry_value(positions)
            account_info = client.get_account()
            effective_threshold = get_effective_threshold(config, total_entry)
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            with state_lock:
                STATE["last_positions"] = active
                STATE["last_pnl"] = total_pnl
                STATE["last_notional"] = total_notional
                STATE["last_entry_value"] = total_entry
                STATE["last_account"] = {
                    "totalWalletBalance": account_info.get("totalWalletBalance", "?"),
                    "totalUnrealizedProfit": account_info.get("totalUnrealizedProfit", "?"),
                    "totalMarginBalance": account_info.get("totalMarginBalance", "?"),
                    "availableBalance": account_info.get("availableBalance", "?"),
                }
                STATE["last_check_time"] = now
                STATE["last_error"] = None
                STATE["total_checks"] += 1

            broadcast_sse("position_update", {
                "time": now,
                "positions": active,
                "total_pnl": round(total_pnl, 4),
                "total_pnl_formatted": f"{total_pnl:+.2f}",
                "total_notional": round(total_notional, 2),
                "total_entry_value": round(total_entry, 2),
                "threshold_type": config.get("threshold_type", "usd"),
                "effective_threshold": round(effective_threshold, 2),
                "effective_threshold_formatted": f"{effective_threshold:+.2f}",
            })

            if active and total_pnl <= effective_threshold:
                tt = config.get("threshold_type", "usd")
                if tt == "percent":
                    desc = (f"总盈亏 {total_pnl:+.2f} ≤ {effective_threshold:+.2f} "
                            f"(开仓成本 {total_entry:.2f} × {config.get('stop_loss_threshold',5)}%)")
                else:
                    desc = f"总盈亏 {total_pnl:+.2f} ≤ {effective_threshold:+.2f} USDT"
                logging.warning("=" * 60)
                logging.warning(f"⚠️ 触发止损! {desc}")
                logging.warning("=" * 60)

                result = close_all_positions(client, positions, dry_run=dry_run)
                with state_lock:
                    STATE["stop_loss_triggered"] = True
                    STATE["monitoring"] = False

                broadcast_sse("stop_loss_triggered", {
                    "total_pnl": round(total_pnl, 4),
                    "total_pnl_formatted": f"{total_pnl:+.2f}",
                    "threshold": effective_threshold,
                    "threshold_formatted": f"{effective_threshold:+.2f}",
                    "threshold_type": tt,
                    "close_result": result,
                })

            time.sleep(interval - 1)
        except Exception as e:
            err_msg = f"{type(e).__name__}: {e}"
            logging.error(f"监控异常: {err_msg}")
            traceback.print_exc()
            with state_lock:
                STATE["last_error"] = err_msg
            broadcast_sse("error", {"message": err_msg})
            time.sleep(max(interval // 2, 15))


# ── HTML 模板 ────────────────────────────────────────

LOGIN_HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>登录 - Binance 止损面板</title>
<style>
  :root { --bg:#0f1117; --card-bg:#1a1d27; --border:#2a2d37; --text:#e0e0e0; --text-dim:#888; --red:#ff1744; --blue:#448aff; }
  * { margin:0; padding:0; box-sizing:border-box; }
  body {
    font-family:-apple-system,BlinkMacSystemFont,'PingFang SC','Microsoft YaHei',sans-serif;
    background:var(--bg); color:var(--text); display:flex; align-items:center;
    justify-content:center; min-height:100vh;
  }
  .login-box {
    background:var(--card-bg); border:1px solid var(--border); border-radius:12px;
    padding:40px; width:100%; max-width:380px;
  }
  .login-box h2 { font-size:20px; margin-bottom:24px; text-align:center; }
  .form-group { margin-bottom:16px; }
  .form-group label { display:block; color:var(--text-dim); font-size:12px; margin-bottom:6px; }
  .form-group input {
    width:100%; background:var(--bg); border:1px solid var(--border); color:var(--text);
    padding:12px; border-radius:8px; font-size:15px; font-family:inherit;
  }
  .btn {
    width:100%; padding:12px; border:none; border-radius:8px; font-size:15px;
    font-weight:600; cursor:pointer; background:var(--blue); color:#fff; transition:filter 0.15s;
  }
  .btn:hover { filter:brightness(1.1); }
  .error { color:var(--red); font-size:13px; text-align:center; margin-bottom:12px; }
</style>
</head>
<body>
<div class="login-box">
  <h2>🔐 Binance 止损面板</h2>
  {% if error %}<div class="error">{{ error }}</div>{% endif %}
  <form method="POST" id="loginForm">
    <div class="form-group">
      <label>密码</label>
      <input type="password" name="password" id="password" placeholder="请输入访问密码" autofocus>
    </div>
    <button type="submit" class="btn">登 录</button>
  </form>
</div>
</body>
</html>"""


DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Binance 总仓位止损面板</title>
<style>
  :root { --bg:#0f1117; --card-bg:#1a1d27; --border:#2a2d37; --text:#e0e0e0; --text-dim:#888;
          --green:#00c853; --red:#ff1744; --blue:#448aff; --orange:#ff9100; --yellow:#ffd600; }
  * { margin:0;padding:0;box-sizing:border-box; }
  body { font-family:-apple-system,BlinkMacSystemFont,'PingFang SC','Microsoft YaHei',sans-serif;
    background:var(--bg);color:var(--text);min-height:100vh;padding:16px; }
  .topbar { display:flex;align-items:center;justify-content:space-between;margin-bottom:16px;flex-wrap:wrap;gap:8px; }
  .topbar-left { display:flex;align-items:center;gap:12px; }
  .topbar h1 { font-size:20px;font-weight:600; }
  .btn { padding:8px 16px;border:none;border-radius:6px;font-size:13px;font-weight:600;
    cursor:pointer;transition:all 0.15s;font-family:inherit; }
  .btn:hover { filter:brightness(1.15); }
  .btn:disabled { opacity:0.4;cursor:not-allowed; }
  .btn-green { background:var(--green);color:#000; }
  .btn-red { background:var(--red);color:#fff; }
  .btn-blue { background:var(--blue);color:#fff; }
  .btn-ghost { background:transparent;border:1px solid var(--border);color:var(--text); }

  .grid { display:grid;gap:12px;grid-template-columns:repeat(auto-fit,minmax(280px,1fr)); }
  .card { background:var(--card-bg);border:1px solid var(--border);border-radius:10px;padding:16px; }
  .card h3 { font-size:13px;color:var(--text-dim);text-transform:uppercase;letter-spacing:0.5px;margin-bottom:8px; }
  .pnl-big { font-size:42px;font-weight:700;line-height:1.1; }
  .pnl-big.positive { color:var(--green); }
  .pnl-big.negative { color:var(--red); }
  .metric-row { display:flex;justify-content:space-between;padding:4px 0;font-size:14px;border-bottom:1px solid rgba(255,255,255,0.04); }
  .metric-row:last-child { border-bottom:none; }
  .metric-label { color:var(--text-dim); }
  .metric-value { font-weight:500; }
  table { width:100%;border-collapse:collapse;font-size:13px; }
  th { text-align:left;color:var(--text-dim);font-weight:500;padding:8px 6px;border-bottom:1px solid var(--border);white-space:nowrap; }
  td { padding:6px 6px;border-bottom:1px solid rgba(255,255,255,0.03);white-space:nowrap; }
  td.pnl-pos { color:var(--green); } td.pnl-neg { color:var(--red); }
  .controls { display:flex;gap:6px;flex-wrap:wrap;align-items:center; }
  .threshold-input input,.threshold-input select {
    background:var(--bg);border:1px solid var(--border);color:var(--text);
    padding:6px 10px;border-radius:6px;font-size:13px;font-family:inherit; }
  .threshold-input input { width:75px; }
  .threshold-input label { color:var(--text-dim);font-size:12px;white-space:nowrap; }
  .emergency-btn { width:100%;padding:16px;font-size:18px;background:var(--red);
    color:#fff;border:none;border-radius:10px;cursor:pointer;font-weight:700;margin-top:16px; }
  .emergency-btn:hover { background:#d50000; }
  .emergency-btn.confirming { background:#b71c1c;animation:pulse 0.5s infinite; }
  @keyframes pulse { 0%,100%{opacity:1}50%{opacity:0.4} }
  .log-stream { background:var(--bg);border:1px solid var(--border);border-radius:6px;
    padding:10px;max-height:200px;overflow-y:auto;font-family:monospace;font-size:12px;color:var(--text-dim); }
  .log-stream .error { color:var(--red); }
  .log-stream .warn { color:var(--yellow); }
  .log-stream .info { color:var(--blue); }
  .empty-state { text-align:center;padding:32px;color:var(--text-dim); }
  .badge { display:inline-block;padding:2px 8px;border-radius:10px;font-size:11px;font-weight:600; }
  .badge-live { background:rgba(0,200,83,0.15);color:var(--green); }
  .badge-demo { background:rgba(255,145,0,0.15);color:var(--orange); }
  .badge-red { background:rgba(255,23,68,0.15);color:var(--red); }

  /* 设置面板 - modal overlay */
  .modal-overlay { display:none;position:fixed;top:0;left:0;width:100%;height:100%;
    background:rgba(0,0,0,0.7);z-index:100;align-items:center;justify-content:center; }
  .modal-overlay.show { display:flex; }
  .modal { background:var(--card-bg);border:1px solid var(--border);border-radius:12px;
    padding:24px;width:100%;max-width:520px;max-height:85vh;overflow-y:auto; }
  .modal h2 { font-size:18px;margin-bottom:16px;display:flex;justify-content:space-between;align-items:center; }
  .modal-close { cursor:pointer;color:var(--text-dim);font-size:24px;border:none;background:none; }
  .form-group { margin-bottom:12px; }
  .form-group label { display:block;color:var(--text-dim);font-size:12px;margin-bottom:4px; }
  .form-group input,.form-group select { width:100%;background:var(--bg);border:1px solid var(--border);
    color:var(--text);padding:8px 10px;border-radius:6px;font-size:13px;font-family:inherit; }
  .form-row { display:flex;gap:10px; }
  .form-row .form-group { flex:1; }
  .settings-status { font-size:12px;margin-left:10px; }
</style>
</head>
<body>

<!-- 设置 Modal -->
<div class="modal-overlay" id="settingsModal">
  <div class="modal">
    <h2>⚙️ 设置 <button class="modal-close" onclick="closeSettings()">×</button></h2>
    <div class="form-row">
      <div class="form-group"><label>API Key</label><input type="text" id="apiKeyInput" placeholder="币安 API Key"></div>
      <div class="form-group"><label>API Secret</label><input type="password" id="apiSecretInput" placeholder="留空不修改"></div>
    </div>
    <div class="form-row">
      <div class="form-group"><label>网络</label><select id="testnetSelect"><option value="false">主网</option><option value="true">测试网</option></select></div>
      <div class="form-group"><label>代理 (可选)</label><input type="text" id="proxyInput" placeholder="http://127.0.0.1:7890"></div>
    </div>
    <div class="form-row">
      <div class="form-group"><label>访问密码</label><input type="password" id="authPasswordInput" placeholder="留空不修改"></div>
      <div class="form-group"><label>检查间隔 (秒)</label><input type="number" id="intervalInput" min="2" value="5"></div>
    </div>
    <div class="form-row">
      <div class="form-group"><label>止损阈值</label><input type="number" id="settingsThreshold" step="0.1" value="5"></div>
      <div class="form-group"><label>阈值类型</label><select id="settingsThresholdType"><option value="percent">% (开仓成本百分比)</option><option value="usd">USDT</option></select></div>
    </div>
    <div style="margin-top:12px;display:flex;align-items:center;gap:8px;">
      <button class="btn btn-blue" onclick="saveSettings()">💾 保存设置</button>
      <span class="settings-status" id="settingsStatus"></span>
    </div>
  </div>
</div>

<!-- 顶部栏 -->
<div class="topbar">
  <div class="topbar-left">
    <h1>📊 Binance 总仓位止损</h1>
    <span id="modeBadge" class="badge badge-demo">DEMO</span>
    <span id="apiBadge" class="badge badge-red" style="display:none">⚠ 未配置API</span>
  </div>
  <div class="controls">
    <div class="threshold-input">
      <label>止损:</label>
      <input type="number" id="thresholdInput" step="0.1" value="0">
      <select id="thresholdTypeSelect" onchange="onThresholdTypeChange()">
        <option value="usd">USDT</option><option value="percent">%</option>
      </select>
    </div>
    <button class="btn btn-blue" onclick="applyConfig()">应用</button>
    <button class="btn btn-green" id="btnStart" onclick="startMonitor()">▶ 启动</button>
    <button class="btn btn-ghost" id="btnStop" onclick="stopMonitor()">⏸ 停止</button>
    <button class="btn btn-ghost" onclick="openSettings()" title="设置">⚙️</button>
    <a href="/logout" style="text-decoration:none"><button class="btn btn-ghost" style="font-size:11px">退出</button></a>
  </div>
</div>

<div class="grid">
  <div class="card">
    <h3>总未实现盈亏</h3>
    <div id="pnlDisplay" class="pnl-big" style="color:var(--text-dim)">—</div>
    <div style="margin-top:4px;font-size:12px;color:var(--text-dim)">开仓成本: <span id="entryValueDisplay">—</span> USDT ｜ 市值: <span id="notionalDisplay">—</span> USDT</div>
  </div>
  <div class="card">
    <h3>账户概览</h3>
    <div id="accountInfo">
      <div class="metric-row"><span class="metric-label">钱包余额</span><span class="metric-value">—</span></div>
      <div class="metric-row"><span class="metric-label">保证金余额</span><span class="metric-value">—</span></div>
      <div class="metric-row"><span class="metric-label">可用余额</span><span class="metric-value">—</span></div>
      <div class="metric-row"><span class="metric-label">最近检查</span><span class="metric-value" id="lastCheck">—</span></div>
    </div>
  </div>
  <div class="card">
    <h3>监控状态</h3>
    <div id="monitorStatus">
      <div class="metric-row"><span class="metric-label">状态</span><span class="metric-value" id="monitorState">⏸ 已停止</span></div>
      <div class="metric-row"><span class="metric-label">检查次数</span><span class="metric-value" id="checkCount">0</span></div>
      <div class="metric-row"><span class="metric-label">止损线</span><span class="metric-value" id="thresholdDisplay">—</span></div>
      <div class="metric-row"><span class="metric-label">模式</span><span class="metric-value" id="modeDisplay">—</span></div>
    </div>
  </div>
</div>

<div class="card" style="margin-top:12px">
  <h3 id="positionsTitle">持仓 (0)</h3>
  <div style="overflow-x:auto">
    <table id="positionsTable" style="display:none"><thead><tr><th>交易对</th><th>方向</th><th>数量</th><th>开仓价</th><th>标记价</th><th>杠杆</th><th>价值</th><th>盈亏</th></tr></thead><tbody id="positionsBody"></tbody></table>
  </div>
  <div id="noPositions" class="empty-state">暂无持仓</div>
</div>

<button class="emergency-btn" id="emergencyBtn" onclick="handleEmergencyClose()">🚨 紧急一键清仓</button>
<p style="font-size:11px;color:var(--text-dim);margin-top:4px;text-align:center">需要双击确认 · 市价单平掉所有仓位</p>

<div class="card" style="margin-top:12px"><h3>实时日志</h3><div class="log-stream" id="logStream"></div></div>

<script>
let eventSource=null,emergencyConfirming=false,confirmTimer=null;

function connectSSE(){
  if(eventSource)eventSource.close();
  eventSource=new EventSource('/api/events');
  eventSource.onopen=()=>addLog('info','SSE 已连接');
  eventSource.addEventListener('connected',()=>fetchStatus());
  eventSource.addEventListener('position_update',e=>{
    let d=JSON.parse(e.data);
    updatePositions(d.positions,d.total_pnl,d.total_pnl_formatted,d.total_notional,d.total_entry_value,d.threshold_type,d.effective_threshold_formatted);
    document.getElementById('lastCheck').textContent=d.time;
    document.getElementById('notionalDisplay').textContent=(d.total_notional||0).toFixed(2);
    document.getElementById('entryValueDisplay').textContent=(d.total_entry_value||0).toFixed(2);
  });
  eventSource.addEventListener('stop_loss_triggered',e=>{
    let d=JSON.parse(e.data);
    addLog('error',`🚨 止损触发! 盈亏 ${d.total_pnl_formatted} ≤ ${d.threshold_formatted}`);
    updateMonitorUI(false,true);fetchStatus();
  });
  eventSource.addEventListener('emergency_close',e=>{
    let d=JSON.parse(e.data);
    addLog('warn',`🔥 紧急清仓: 成功 ${d.success}, 失败 ${d.failed}`);fetchStatus();
  });
  eventSource.addEventListener('config_updated',()=>fetchStatus());
  eventSource.addEventListener('monitor_status',e=>updateMonitorUI(JSON.parse(e.data).monitoring,false));
  eventSource.addEventListener('error',e=>{try{addLog('error',JSON.parse(e.data).message)}catch(_){}});
  eventSource.onerror=()=>{addLog('error','SSE 断开，5秒后重连...');setTimeout(connectSSE,5000);};
}

function updatePositions(positions,totalPnl,formatted,notional,entryValue,thresholdType,effThreshold){
  document.getElementById('pnlDisplay').textContent=formatted||'0.00';
  document.getElementById('pnlDisplay').className='pnl-big '+(totalPnl>=0?'positive':'negative');
  let tb=document.getElementById('positionsBody'),table=document.getElementById('positionsTable'),
      no=document.getElementById('noPositions'),t=document.getElementById('positionsTitle');
  if(!positions||positions.length===0){table.style.display='none';no.style.display='block';t.textContent='持仓 (0)';return;}
  table.style.display='';no.style.display='none';t.textContent=`持仓 (${positions.length})`;
  tb.innerHTML=positions.map(p=>{
    let amt=parseFloat(p.positionAmt),pnl=parseFloat(p.unRealizedProfit),mark=parseFloat(p.markPrice);
    return `<tr><td><strong>${p.symbol}</strong></td><td>${amt>0?'📈 多':'📉 空'}</td>
    <td>${Math.abs(amt).toFixed(4)}</td><td>${parseFloat(p.entryPrice).toFixed(4)}</td>
    <td>${mark.toFixed(4)}</td><td>${p.leverage||'?'}x</td>
    <td>${(Math.abs(amt)*mark).toFixed(2)}</td>
    <td class="${pnl>=0?'pnl-pos':'pnl-neg'}">${pnl.toFixed(2)}</td></tr>`;
  }).join('');
}

function updateMonitorUI(mon,trig){
  let el=document.getElementById('monitorState');
  if(trig){el.innerHTML='🚨 已触发止损';el.style.color='var(--red)';}
  else if(mon){el.innerHTML='🟢 监控中';el.style.color='var(--green)';}
  else{el.innerHTML='⏸ 已停止';el.style.color='var(--text-dim)';}
}

function addLog(level,msg){
  let s=document.getElementById('logStream');
  s.innerHTML+=`<div class="${level}">[${new Date().toLocaleTimeString()}] ${msg}</div>`;
  s.scrollTop=s.scrollHeight;while(s.children.length>200)s.removeChild(s.firstChild);
}

function onThresholdTypeChange(){
  let type=document.getElementById('thresholdTypeSelect').value;
  document.getElementById('thresholdInput').step=type==='percent'?'0.1':'1';
}

// ── Ajax ──────────────────────────────────────
function api(method,url,data){return fetch(url,{method,headers:{'Content-Type':'application/json'},body:data?JSON.stringify(data):undefined,credentials:'same-origin'});}

async function fetchStatus(){
  try{
    let r=await fetch('/api/status',{credentials:'same-origin'});
    if(r.status===401){window.location.href='/login';return;}
    let s=await r.json();
    updatePositions(s.positions,s.total_pnl,s.total_pnl_formatted,s.total_notional,s.total_entry_value,s.threshold_type,s.effective_threshold_formatted);
    updateMonitorUI(s.monitoring,s.stop_loss_triggered);
    document.getElementById('checkCount').textContent=s.total_checks;
    document.getElementById('thresholdDisplay').textContent=s.effective_threshold_formatted+' USDT'+(s.threshold_type==='percent'?' (开仓成本×'+s.threshold+'%)':'');
    document.getElementById('thresholdInput').value=s.threshold;
    document.getElementById('thresholdTypeSelect').value=s.threshold_type;
    document.getElementById('modeDisplay').textContent=s.dry_run?'🏗 演习':'⚡ 实盘';
    document.getElementById('notionalDisplay').textContent=(s.total_notional||0).toFixed(2);
    document.getElementById('entryValueDisplay').textContent=(s.total_entry_value||0).toFixed(2);
    document.getElementById('lastCheck').textContent=s.last_check_time||'—';
    let badge=document.getElementById('modeBadge');
    if(s.testnet){badge.textContent='测试网';badge.className='badge badge-demo';}
    else if(s.dry_run){badge.textContent='DEMO';badge.className='badge badge-demo';}
    else{badge.textContent='LIVE';badge.className='badge badge-live';}
    document.getElementById('apiBadge').style.display=s.has_api_key?'none':'inline-block';
  }catch(e){addLog('error','状态获取失败: '+e.message);}
}

async function applyConfig(){
  let t=document.getElementById('thresholdInput').value,ty=document.getElementById('thresholdTypeSelect').value;
  try{await api('POST','/api/config',{stop_loss_threshold:parseFloat(t),threshold_type:ty});addLog('info',`止损: ${t} ${ty==='percent'?'%':'USDT'}`);}
  catch(e){addLog('error','失败: '+e.message);}
}

async function startMonitor(){
  try{await api('POST','/api/monitor/start');addLog('info','监控已启动');}catch(e){addLog('error',e.message);}
}
async function stopMonitor(){
  try{await api('POST','/api/monitor/stop');addLog('info','监控已停止');}catch(e){addLog('error',e.message);}
}

async function handleEmergencyClose(){
  let btn=document.getElementById('emergencyBtn');
  if(!emergencyConfirming){
    emergencyConfirming=true;btn.textContent='⚠️ 再次点击确认清仓!';btn.classList.add('confirming');
    confirmTimer=setTimeout(()=>{emergencyConfirming=false;btn.textContent='🚨 紧急一键清仓';btn.classList.remove('confirming');},5000);
    return;
  }
  clearTimeout(confirmTimer);btn.textContent='执行中...';btn.disabled=true;btn.classList.remove('confirming');emergencyConfirming=false;
  try{
    let r=await api('POST','/api/emergency-close',{confirm:true}),d=await r.json();
    if(d.error)addLog('error','清仓失败: '+d.error);
  }catch(e){addLog('error','请求失败: '+e.message);}
  btn.textContent='🚨 紧急一键清仓';btn.disabled=false;
}

// ── 设置面板 ──────────────────────────────────
function openSettings(){
  fetch('/api/settings',{credentials:'same-origin'}).then(r=>r.json()).then(s=>{
    document.getElementById('apiKeyInput').value=s.api_key_masked||'';
    document.getElementById('apiSecretInput').value=s.api_key_masked?'':'';
    document.getElementById('testnetSelect').value=s.testnet?'true':'false';
    document.getElementById('proxyInput').value=s.proxy||'';
    document.getElementById('intervalInput').value=s.check_interval_seconds;
    document.getElementById('settingsThreshold').value=s.stop_loss_threshold;
    document.getElementById('settingsThresholdType').value=s.threshold_type;
    document.getElementById('authPasswordInput').value=s.has_auth_password?'':'';
    document.getElementById('settingsStatus').textContent='';
  });
  document.getElementById('settingsModal').classList.add('show');
}
function closeSettings(){document.getElementById('settingsModal').classList.remove('show');}
document.getElementById('settingsModal').addEventListener('click',e=>{if(e.target===document.getElementById('settingsModal'))closeSettings();});

async function saveSettings(){
  let apiKey=document.getElementById('apiKeyInput').value.trim();
  let apiSecret=document.getElementById('apiSecretInput').value.trim();
  let data={
    testnet:document.getElementById('testnetSelect').value==='true',
    proxy:document.getElementById('proxyInput').value.trim(),
    check_interval_seconds:parseInt(document.getElementById('intervalInput').value),
    stop_loss_threshold:parseFloat(document.getElementById('settingsThreshold').value),
    threshold_type:document.getElementById('settingsThresholdType').value,
  };
  if(apiKey&&!apiKey.includes('****'))data.api_key=apiKey;
  if(apiSecret&&!apiSecret.includes('****'))data.api_secret=apiSecret;
  let pw=document.getElementById('authPasswordInput').value.trim();
  if(pw)data.auth_password=pw;

  let el=document.getElementById('settingsStatus');
  el.textContent='保存中...';el.style.color='var(--yellow)';
  try{
    let r=await api('POST','/api/settings',data),d=await r.json();
    if(r.ok){el.textContent='✅ 已保存';el.style.color='var(--green)';addLog('info','设置已更新 · 持仓数: '+(d.positions_count||0));closeSettings();fetchStatus();}
    else{el.textContent='❌ '+(d.error||'失败');el.style.color='var(--red)';}
  }catch(e){el.textContent='❌ '+e.message;el.style.color='var(--red)';}
  setTimeout(()=>{el.textContent='';},5000);
}

// ── init ──────────────────────────────────────
connectSSE();fetchStatus();setInterval(fetchStatus,30000);
</script>
</body>
</html>
"""


@app.route("/")
@login_required
def index():
    return render_template_string(DASHBOARD_HTML)


# ── 主入口 ───────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Binance 总仓位止损 - Web 仪表盘 v2")
    parser.add_argument("config", nargs="?", default="config.json", help="配置文件路径")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    config_path = os.path.abspath(args.config)
    config = load_sl_config(args.config)

    if config is None:
        print("⚠️ 未检测到有效 API Key，使用演示模式")
        config = {
            "api_key": "demo", "api_secret": "demo",
            "testnet": False, "stop_loss_threshold": 5,
            "threshold_type": "percent",
            "check_interval_seconds": 5, "dry_run": True,
            "proxy": None, "auth_password": "", "log_level": "INFO",
        }

    # 密码：环境变量 > 配置文件，未设置则退出
    global AUTH_PASSWORD
    if not AUTH_PASSWORD:
        AUTH_PASSWORD = config.get("auth_password", "")
    if not AUTH_PASSWORD:
        print("❌ 未设置登录密码！请设置环境变量 SL_PASSWORD 或在 config.json 中配置 auth_password")
        sys.exit(1)

    log_level = config.get("log_level", "INFO")
    logging.basicConfig(
        level=getattr(logging, log_level.upper(), logging.INFO),
        format="[%(asctime)s] %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    demo_mode = config["api_key"] == "demo"
    client = BinanceFuturesClient(
        api_key=config["api_key"], api_secret=config["api_secret"],
        testnet=config["testnet"], proxy=config.get("proxy"), timeout=8,
    )

    if demo_mode:
        logging.warning("⚠️ 演示模式 — 需在面板设置中填入 API Key")
    else:
        logging.info("验证 API 连接...")
        try:
            client.get_positions()
            logging.info("API 连接成功 ✓")
        except Exception as e:
            logging.error(f"API 连接失败: {e}")

    with state_lock:
        STATE["client"] = client
        STATE["config"] = config
        STATE["config_path"] = config_path

    monitor_thread = threading.Thread(target=monitor_loop, daemon=True, name="monitor")
    monitor_thread.start()

    tt = config.get("threshold_type", "usd")
    logging.info(f"仪表盘 v2 启动: http://{args.host}:{args.port}")
    logging.info(f"模式: {'演习' if config.get('dry_run') else '⚡ 实盘'}")
    logging.info(f"止损: {config['stop_loss_threshold']} {'%' if tt=='percent' else 'USDT'}")

    app.run(host=args.host, port=args.port, debug=args.debug, threaded=True)


if __name__ == "__main__":
    main()
