#!/usr/bin/env python3
"""
Binance 合约总仓位止损监控脚本
=====================================
每分钟检查币安合约账户所有仓位的总未实现盈亏，
超过阈值时一键清仓止损。

用法:
    python3 binance_portfolio_sl.py config.json      # 指定配置文件
    python3 binance_portfolio_sl.py                  # 默认 config.json
    python3 binance_portfolio_sl.py --once config.json  # 只执行一次检查

配置文件示例见 config.example.json

依赖: requests (pip install requests)
"""

import sys
import os
import json
import time
import hmac
import hashlib
import logging
import argparse
import traceback
from datetime import datetime
from urllib.parse import urlencode
from typing import Optional

import requests

# ── 常量 ────────────────────────────────────────────
MAINNET_BASE = "https://fapi.binance.com"
TESTNET_BASE = "https://testnet.binancefuture.com"
USER_AGENT = "BinancePortfolioSL/1.0"

# 重试配置
MAX_RETRIES = 3
RETRY_DELAY = 3  # 秒


class BinanceFuturesClient:
    """币安合约 REST API 客户端（仅实现本脚本所需端点）"""

    def __init__(self, api_key: str, api_secret: str, testnet: bool = False,
                 proxy: Optional[str] = None, timeout: int = 15):
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = TESTNET_BASE if testnet else MAINNET_BASE
        self.timeout = timeout

        self.session = requests.Session()
        self.session.headers.update({
            "X-MBX-APIKEY": api_key,
            "User-Agent": USER_AGENT,
        })
        if proxy:
            self.session.proxies = {"http": proxy, "https": proxy}

    # ── 签名 ───────────────────────────────────────
    def _sign(self, params: dict) -> str:
        query = urlencode(params)
        return hmac.new(
            self.api_secret.encode("utf-8"),
            query.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()

    # ── 请求封装 ──────────────────────────────────
    def _request(self, method: str, path: str, params: dict = None,
                 signed: bool = False, retries: int = MAX_RETRIES) -> dict:
        url = f"{self.base_url}{path}"
        params = params or {}

        if signed:
            params["timestamp"] = int(time.time() * 1000)
            params["signature"] = self._sign(params)

        for attempt in range(1, retries + 1):
            try:
                if method == "GET":
                    resp = self.session.get(url, params=params, timeout=self.timeout)
                elif method == "POST":
                    resp = self.session.post(url, data=params, timeout=self.timeout)
                elif method == "DELETE":
                    resp = self.session.delete(url, params=params, timeout=self.timeout)
                else:
                    raise ValueError(f"Unsupported method: {method}")

                data = resp.json()

                # 检查业务错误
                if isinstance(data, dict) and data.get("code") and data["code"] < 0:
                    logging.error(f"API 错误 [{data['code']}]: {data.get('msg', '')}")
                    if data["code"] == -2015:  # 权限不足
                        raise PermissionError(f"API Key 权限不足: {data.get('msg')}")
                    return data

                return data

            except requests.exceptions.Timeout:
                logging.warning(f"请求超时 (第 {attempt}/{retries} 次): {method} {path}")
            except requests.exceptions.ConnectionError as e:
                logging.warning(f"连接失败 (第 {attempt}/{retries} 次): {e}")
            except PermissionError:
                raise
            except Exception as e:
                logging.warning(f"请求异常 (第 {attempt}/{retries} 次): {e}")

            if attempt < retries:
                time.sleep(RETRY_DELAY * attempt)

        raise ConnectionError(f"请求失败 ({retries} 次重试后): {method} {path}")

    # ── API 端点 ──────────────────────────────────

    def get_positions(self) -> list[dict]:
        """获取所有未平仓仓位 (fapi/v2/positionRisk)"""
        return self._request("GET", "/fapi/v2/positionRisk", signed=True)

    def get_account(self) -> dict:
        """获取账户信息 (fapi/v2/account)"""
        return self._request("GET", "/fapi/v2/account", signed=True)

    def cancel_all_orders(self, symbol: str = None) -> dict:
        """撤销所有挂单"""
        params = {}
        if symbol:
            params["symbol"] = symbol
        return self._request("DELETE", "/fapi/v1/allOpenOrders", params=params, signed=True)

    def close_position(self, symbol: str, quantity: float, side: str) -> dict:
        """
        市价平仓
        symbol: 交易对, 如 BTCUSDT
        quantity: 仓位数量（绝对值）
        side: 平仓方向 - 'SELL' 平多, 'BUY' 平空
        """
        params = {
            "symbol": symbol,
            "side": side,
            "type": "MARKET",
            "quantity": quantity,
            "reduceOnly": "true",
        }
        return self._request("POST", "/fapi/v1/order", params=params, signed=True)


# ── 止损逻辑 ────────────────────────────────────────

def calculate_total_pnl(positions: list[dict]) -> float:
    """计算所有仓位总未实现盈亏 (USDT)"""
    total = 0.0
    for pos in positions:
        try:
            pnl = float(pos.get("unRealizedProfit", 0))
            total += pnl
        except (ValueError, TypeError):
            pass
    return total


def get_active_positions(positions: list[dict]) -> list[dict]:
    """筛选出有实际持仓的仓位（positionAmt != 0）"""
    active = []
    for pos in positions:
        try:
            amt = float(pos.get("positionAmt", 0))
            if abs(amt) > 0:
                active.append(pos)
        except (ValueError, TypeError):
            pass
    return active


def close_all_positions(client: BinanceFuturesClient, positions: list[dict],
                        dry_run: bool = False) -> dict:
    """
    一键平掉所有仓位。
    返回: {"success": int, "failed": int, "details": [...]}
    """
    active = get_active_positions(positions)
    if not active:
        logging.info("没有需要平仓的持仓")
        return {"success": 0, "failed": 0, "details": []}

    result = {"success": 0, "failed": 0, "details": []}

    # 先撤销所有挂单（安全起见）
    if not dry_run:
        try:
            client.cancel_all_orders()
            logging.info("已撤销所有挂单")
        except Exception as e:
            logging.warning(f"撤单失败（继续平仓）: {e}")

    for pos in active:
        symbol = pos["symbol"]
        try:
            position_amt = float(pos["positionAmt"])
        except (ValueError, TypeError, KeyError):
            logging.error(f"无法解析 {symbol} 仓位数量: {pos.get('positionAmt')}")
            result["failed"] += 1
            result["details"].append({"symbol": symbol, "status": "error", "msg": "无法解析仓位数量"})
            continue

        quantity = abs(position_amt)
        # 多仓 -> 卖出平仓；空仓 -> 买入平仓
        side = "SELL" if position_amt > 0 else "BUY"
        side_cn = "平多(卖出)" if position_amt > 0 else "平空(买入)"

        logging.info(f"{'[DRY RUN] ' if dry_run else ''}"
                     f"准备平仓 {symbol}: {side_cn}, 数量={quantity}")

        if dry_run:
            result["success"] += 1
            result["details"].append({
                "symbol": symbol, "side": side, "quantity": quantity,
                "status": "dry_run"
            })
            continue

        try:
            resp = client.close_position(symbol, quantity, side)
            if isinstance(resp, dict) and resp.get("code") and resp["code"] < 0:
                logging.error(f"平仓失败 {symbol}: {resp.get('msg')}")
                result["failed"] += 1
                result["details"].append({
                    "symbol": symbol, "status": "failed", "msg": resp.get("msg")
                })
            else:
                logging.info(f"平仓成功 {symbol}: {side_cn} {quantity}")
                result["success"] += 1
                result["details"].append({
                    "symbol": symbol, "status": "success", "orderId": resp.get("orderId")
                })
        except Exception as e:
            logging.error(f"平仓异常 {symbol}: {e}")
            result["failed"] += 1
            result["details"].append({"symbol": symbol, "status": "error", "msg": str(e)})

    return result


# ── 主循环 ─────────────────────────────────────────

def run_once(client: BinanceFuturesClient, threshold: float, dry_run: bool = False) -> bool:
    """
    执行一次检查 + 止损判断。
    返回: True 如果触发了止损平仓
    """
    # 1. 获取仓位
    logging.debug("获取持仓...")
    positions = client.get_positions()
    active = get_active_positions(positions)

    if not active:
        logging.info("当前无持仓")
        return False

    # 2. 计算总盈亏
    total_pnl = calculate_total_pnl(positions)
    active_count = len(active)
    symbols = ", ".join(p["symbol"] for p in active[:5])
    if len(active) > 5:
        symbols += f" ...等{len(active)}个"

    logging.info(f"持仓 {active_count} 个 [{symbols}] | 总未实现盈亏: {total_pnl:+.2f} USDT")

    # 详细打印每个仓位
    for pos in active:
        try:
            pnl = float(pos["unRealizedProfit"])
            amt = float(pos["positionAmt"])
            entry = float(pos.get("entryPrice", 0))
            mark = float(pos.get("markPrice", 0))
            lev = pos.get("leverage", "?")
            direction = "多" if amt > 0 else "空"
            logging.info(f"  {pos['symbol']:12s} {direction} | "
                         f"数量: {abs(amt):.4f} | "
                         f"开仓: {entry:.4f} | 标记: {mark:.4f} | "
                         f"杠杆: {lev}x | 盈亏: {pnl:+.2f} USDT")
        except Exception:
            pass

    # 3. 判断止损
    if total_pnl <= threshold:
        logging.warning("=" * 60)
        logging.warning(f"⚠️ 触发总仓位止损! 总盈亏 {total_pnl:+.2f} USDT <= 阈值 {threshold:+.2f} USDT")
        logging.warning("=" * 60)

        result = close_all_positions(client, positions, dry_run=dry_run)
        logging.info(f"平仓结果: 成功 {result['success']}, 失败 {result['failed']}")

        if not dry_run and result["failed"] > 0:
            logging.error("⚠️ 部分仓位平仓失败，请手动检查!")
            for d in result["details"]:
                if d["status"] != "success":
                    logging.error(f"  {d['symbol']}: {d.get('msg', d.get('status'))}")

        return True

    return False


def load_config(config_path: str) -> dict:
    """加载并校验配置文件"""
    if not os.path.exists(config_path):
        print(f"配置文件不存在: {config_path}")
        print("请参考 config.example.json 创建配置文件")
        sys.exit(1)

    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    # 必填检查
    required = ["api_key", "api_secret", "stop_loss_threshold"]
    for key in required:
        if key not in config:
            print(f"配置文件缺少必填字段: {key}")
            sys.exit(1)

    if "你的" in config["api_key"]:
        return None  # 返回 None，由调用方决定是否退出

    # 默认值
    config.setdefault("testnet", False)
    config.setdefault("threshold_type", "usd")
    config.setdefault("check_interval_seconds", 5)
    config.setdefault("dry_run", False)
    config.setdefault("proxy", None)
    config.setdefault("log_file", "binance_sl.log")
    config.setdefault("log_level", "INFO")

    return config


def setup_logging(log_file: str, log_level: str):
    """配置双输出日志：控制台 + 文件"""
    level = getattr(logging, log_level.upper(), logging.INFO)
    fmt = logging.Formatter(
        "[%(asctime)s] %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()

    # 文件
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setLevel(level)
    fh.setFormatter(fmt)
    root.addHandler(fh)

    # 控制台
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(level)
    ch.setFormatter(fmt)
    root.addHandler(ch)


def main():
    parser = argparse.ArgumentParser(
        description="Binance 合约总仓位止损监控",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s config.json             持续监控模式（每分钟检查）
  %(prog)s --once config.json      只检查一次
  %(prog)s --dry config.json       无论配置如何，强制 dry-run
        """
    )
    parser.add_argument("config", nargs="?", default="config.json",
                        help="配置文件路径 (默认: config.json)")
    parser.add_argument("--once", action="store_true",
                        help="只执行一次检查后退出")
    parser.add_argument("--dry", action="store_true",
                        help="强制 dry-run 模式（不实际下单）")
    args = parser.parse_args()

    # 加载配置
    config = load_config(args.config)
    if config is None:
        print("请先填写配置文件中真实的 API Key 和 Secret")
        sys.exit(1)

    if args.dry:
        config["dry_run"] = True

    # 日志
    setup_logging(config["log_file"], config["log_level"])

    dry_run = config["dry_run"]
    threshold = config["stop_loss_threshold"]
    interval = max(config["check_interval_seconds"], 10)  # 最少 10 秒

    if dry_run:
        logging.warning("=" * 50)
        logging.warning("DRY RUN 模式 — 不会实际下单")
        logging.warning("=" * 50)

    if config["testnet"]:
        logging.info("使用测试网: testnet.binancefuture.com")
    else:
        logging.info("使用主网: fapi.binance.com ⚠️ 实盘交易")

    logging.info(f"止损阈值: {threshold:+.2f} USDT | 检查间隔: {interval}s | 模式: {'演习' if dry_run else '实盘'}")

    # 创建客户端
    client = BinanceFuturesClient(
        api_key=config["api_key"],
        api_secret=config["api_secret"],
        testnet=config["testnet"],
        proxy=config.get("proxy"),
    )

    # 验证 API 连接
    logging.info("验证 API 连接...")
    try:
        client.get_positions()
        logging.info("API 连接成功 ✓")
    except PermissionError as e:
        logging.error(f"API 权限错误: {e}")
        logging.error("请检查: 1) API Key 是否正确 2) 是否开通合约交易权限 3) IP 白名单")
        sys.exit(1)
    except Exception as e:
        logging.error(f"API 连接失败: {e}")
        logging.error("请检查: 1) 网络连接 2) 代理设置 3) testnet 开关")
        sys.exit(1)

    # ── 主循环 ──
    if args.once:
        triggered = run_once(client, threshold, dry_run=dry_run)
        if triggered:
            logging.info("触发止损并已执行")
        else:
            logging.info("未触发止损")
        return

    logging.info("开始持续监控 (Ctrl+C 停止)...")
    consecutive_errors = 0

    try:
        while True:
            try:
                triggered = run_once(client, threshold, dry_run=dry_run)
                if triggered:
                    logging.warning("止损已触发，脚本退出。请检查账户并重启。")
                    break
                consecutive_errors = 0
            except Exception as e:
                consecutive_errors += 1
                logging.error(f"检查异常 ({consecutive_errors}): {e}")
                traceback.print_exc()

                if consecutive_errors >= 10:
                    logging.critical("连续 10 次失败，脚本退出")
                    break

                # 出错后等待较短时间再重试
                time.sleep(max(interval // 2, 15))
                continue

            time.sleep(interval)

    except KeyboardInterrupt:
        logging.info("收到停止信号，退出...")


if __name__ == "__main__":
    main()
