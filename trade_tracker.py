import os
import json
import logging
from datetime import datetime
from typing import List
from data_fetcher import get_next_day_open

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

        if won:
            data["stats"]["wins"] += 1
        else:
            data["stats"]["losses"] += 1
        data["stats"]["total"] += 1

        settled.append(trade)
        logger.info(f"{trade['name']}({trade['code']}) 买{trade['buy_price']}→卖{sell_price} "
                     f"{'盈利' if won else '亏损'}{profit_pct:+.2f}%")

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
