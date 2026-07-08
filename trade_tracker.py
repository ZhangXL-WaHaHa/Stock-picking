import os
import json
import logging
from datetime import datetime
from typing import List
from data_fetcher import get_next_day_open, get_analysis_data

logger = logging.getLogger(__name__)

TRADES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "trades.json")


def _load():
    if os.path.exists(TRADES_FILE):
        with open(TRADES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"trades": [], "stats": {"wins": 0, "losses": 0, "total": 0}}


def _save(data):
    with open(TRADES_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def add_pending_trades(results: List[dict]):
    data = _load()
    today = datetime.now().strftime("%Y-%m-%d")

    existing = {(t["code"], t["pick_date"]) for t in data["trades"]}

    added = 0
    for s in results:
        if s["priority_score"] < 5:
            continue
        key = (s["code"], today)
        if key in existing:
            continue
        data["trades"].append({
            "code": s["code"],
            "name": s["name"],
            "pick_date": today,
            "buy_price": s["price"],
            "sell_date": None,
            "sell_price": None,
            "profit_pct": None,
            "result": "pending",
        })
        added += 1

    if added:
        _save(data)
        logger.info(f"已记录 {added} 只5星股票为待结算交易")
    else:
        logger.info("无新增5星股票待记录")


def _analyze_trade(trade: dict) -> str:
    """分析交易结果的原因"""
    if trade["result"] == "win":
        return "正常"

    reasons = []
    try:
        data = get_analysis_data(trade["code"], trade["pick_date"], trade["sell_date"])

        # 1. 大盘拖累：结算日上证低开
        market_sell = data.get("market_sell_day")
        market_prev = data.get("market_prev_day")
        if market_sell and market_prev:
            market_open = float(market_sell[1])
            market_prev_close = float(market_prev[2])
            if market_prev_close > 0:
                market_gap = (market_open - market_prev_close) / market_prev_close * 100
                if market_gap < -0.3:
                    reasons.append(f"大盘拖累({market_gap:+.1f}%)")

        # 2. 跳空低开：个股次日开盘跌超1%
        gap_pct = (trade["sell_price"] - trade["buy_price"]) / trade["buy_price"] * 100
        if gap_pct < -1:
            reasons.append(f"跳空低开({gap_pct:+.1f}%)")

        # 3. 追高接盘：选股日收盘在振幅上80%区间
        stock_pick = data.get("stock_pick_day")
        if stock_pick:
            high = float(stock_pick[3])
            low = float(stock_pick[4])
            close = float(stock_pick[2])
            spread = high - low
            if spread > 0:
                position = (close - low) / spread
                if position > 0.8:
                    reasons.append(f"追高接盘(位{position:.0%})")

        # 4. 放量滞涨：选股日量比前一日放大但涨幅有限
        # 通过K线数据检查
        if stock_pick:
            stock_days = []
            try:
                from data_fetcher import _get_kline_around
                prefix = "sh" if trade["code"].startswith("6") else "sz"
                stock_days = _get_kline_around(f"{prefix}{trade['code']}", trade["pick_date"])
            except Exception:
                pass
            for i, d in enumerate(stock_days):
                if d[0] == trade["pick_date"] and i > 0:
                    prev_vol = float(stock_days[i - 1][5])
                    cur_vol = float(d[5])
                    cur_close = float(d[2])
                    cur_open = float(d[1])
                    if prev_vol > 0 and cur_vol > prev_vol * 1.5:
                        intraday_gain = (cur_close - cur_open) / cur_open * 100
                        if intraday_gain < 1:
                            reasons.append("放量滞涨")
                    break

    except Exception as e:
        logger.warning(f"分析交易失败 {trade['code']}: {e}")

    return "|".join(reasons) if reasons else "原因不明"


def settle_pending_trades() -> List[dict]:
    data = _load()
    settled = []

    for trade in data["trades"]:
        if trade["result"] != "pending":
            continue

        result = get_next_day_open(trade["code"], trade["pick_date"])
        if result is None:
            continue

        sell_date, sell_price = result
        profit_pct = round((sell_price - trade["buy_price"]) / trade["buy_price"] * 100, 2)
        won = profit_pct > 0

        trade["sell_date"] = sell_date
        trade["sell_price"] = sell_price
        trade["profit_pct"] = profit_pct
        trade["result"] = "win" if won else "loss"
        trade["analysis"] = _analyze_trade(trade)

        if won:
            data["stats"]["wins"] += 1
        else:
            data["stats"]["losses"] += 1
        data["stats"]["total"] += 1

        settled.append(trade)
        analysis_str = f" | {trade['analysis']}" if trade["result"] == "loss" else ""
        logger.info(f"{trade['name']}({trade['code']}) 买{trade['buy_price']}→卖{sell_price} "
                     f"{'盈利' if won else '亏损'}{profit_pct:+.2f}%{analysis_str}")

    if settled:
        _save(data)
        logger.info(f"本次结算 {len(settled)} 笔交易")

    return settled


def get_stats() -> dict:
    data = _load()
    stats = data["stats"]
    total = stats["total"]
    settled = [t for t in data["trades"] if t["result"] != "pending"]
    total_profit = sum(t.get("profit_pct", 0) or 0 for t in settled)
    return {
        "wins": stats["wins"],
        "losses": stats["losses"],
        "total": total,
        "win_rate": round(stats["wins"] / total * 100, 1) if total > 0 else 0,
        "total_profit": round(total_profit, 2),
    }


def get_pending_trades() -> List[dict]:
    data = _load()
    return [t for t in data["trades"] if t["result"] == "pending"]


def get_recent_trades(n: int = 20) -> List[dict]:
    data = _load()
    settled = [t for t in data["trades"] if t["result"] != "pending"]
    return settled[-n:]
