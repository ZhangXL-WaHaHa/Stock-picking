import requests
import json
import logging
import time
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Set, Tuple

from database import (
    save_daily_snapshots, get_snapshot_by_date, get_cached_dates,
    get_snapshot_for_codes,
)

logger = logging.getLogger(__name__)

SINA_HQ_URL = "https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData"
TENCENT_KLINE_URL = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?_var=kline_dayqfq&param={},day,{},{},50,qfq"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36", "Referer": "https://finance.sina.com.cn"}
HEADERS_QQ = {"User-Agent": "Mozilla/5.0", "Referer": "https://finance.qq.com"}


def fetch_sina_snapshot() -> List[dict]:
    """通过新浪接口分页获取当日全市场快照"""
    all_rows = []
    page = 1
    while True:
        params = {
            "page": page,
            "num": 100,
            "sort": "symbol",
            "asc": 1,
            "node": "hs_a",
            "symbol": "",
            "_s_r_a": "auto",
        }
        try:
            resp = requests.get(SINA_HQ_URL, params=params, headers=HEADERS, timeout=15)
            resp.encoding = "gbk"
            data = json.loads(resp.text)
            if not data:
                break
            for s in data:
                code = s.get("code", "")
                if not (code.startswith("60") or code.startswith("00")):
                    continue
                name = s.get("name", "")
                if "ST" in name.upper():
                    continue
                all_rows.append({
                    "code": code,
                    "name": name,
                    "close": float(s.get("trade", 0)),
                    "open": float(s.get("open", 0)),
                    "high": float(s.get("high", 0)),
                    "low": float(s.get("low", 0)),
                    "change_pct": float(s.get("changepercent", 0)),
                    "volume": float(s.get("volume", 0)),
                    "amount": float(s.get("amount", 0)),
                    "turnover_rate": float(s.get("turnoverratio", 0)),
                    "circ_market_cap": float(s.get("nmc", 0)) / 10000,  # 万元 → 亿元
                })
            page += 1
            if page > 60:
                break
            time.sleep(0.15)
        except Exception as e:
            logger.warning(f"新浪快照第{page}页失败: {e}")
            break
    logger.info(f"新浪快照采集完成: {len(all_rows)} 只主板股票")
    return all_rows


def cache_today_snapshot():
    """缓存今日全市场快照"""
    today = datetime.now().strftime("%Y-%m-%d")
    rows = fetch_sina_snapshot()
    if not rows:
        return 0
    for r in rows:
        r["trade_date"] = today
    save_daily_snapshots(today, rows)
    logger.info(f"已缓存 {today} 快照: {len(rows)} 条")
    return len(rows)


def cache_date_range(start_date: str, end_date: str) -> Dict[str, int]:
    """缓存指定日期范围的数据（只能缓存今天的实时快照，历史日期用K线补算）"""
    cached = get_cached_dates()
    results = {}

    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    end_dt = datetime.strptime(end_date, "%Y-%m-%d")
    today = datetime.now().strftime("%Y-%m-%d")

    if end_date == today and today not in cached:
        n = cache_today_snapshot()
        results[today] = n

    d = start_dt
    dates_to_fill = []
    while d <= end_dt:
        ds = d.strftime("%Y-%m-%d")
        if d.weekday() < 5 and ds not in cached and ds != today:
            dates_to_fill.append(ds)
        d += timedelta(days=1)

    if dates_to_fill:
        n = _fill_history_from_kline(dates_to_fill)
        results.update(n)

    return results


def _fill_history_from_kline(dates: List[str]) -> Dict[str, int]:
    """用腾讯K线数据补算历史日期的快照"""
    if not dates:
        return {}

    dates_sorted = sorted(dates)
    start = (datetime.strptime(dates_sorted[0], "%Y-%m-%d") - timedelta(days=10)).strftime("%Y-%m-%d")
    end = dates_sorted[-1]

    codes_sh = [f"sh60{str(i).zfill(4)}" for i in range(6000)]
    codes_sz = [f"sz00{str(i).zfill(4)}" for i in range(1, 4000)]
    all_codes = codes_sh + codes_sz

    date_data = {d: [] for d in dates_sorted}
    total = len(all_codes)

    # 同时用腾讯实时接口获取当前流通市值 → 推算流通股本
    circ_shares_map = _fetch_circ_shares(all_codes)

    for idx, symbol in enumerate(all_codes):
        try:
            url = TENCENT_KLINE_URL.format(symbol, start, end)
            resp = requests.get(url, headers=HEADERS_QQ, timeout=8)
            text = resp.text
            if "=" in text:
                text = text.split("=", 1)[1]
            data = json.loads(text)
            klines = data.get("data", {}).get(symbol, {})
            days = klines.get("qfqday", klines.get("day", []))

            if not days or len(days) < 2:
                continue

            code = symbol[2:]
            circ_shares = circ_shares_map.get(code, 0)

            for i, day in enumerate(days):
                day_date = day[0]
                if day_date not in date_data:
                    continue
                open_p = float(day[1])
                close_p = float(day[2])
                high_p = float(day[3])
                low_p = float(day[4])
                vol = float(day[5])

                if i > 0:
                    prev_close = float(days[i - 1][2])
                    pct = (close_p - prev_close) / prev_close * 100 if prev_close > 0 else 0
                else:
                    pct = (close_p - open_p) / open_p * 100 if open_p > 0 else 0

                circ_mv = circ_shares * close_p / 1e8 if circ_shares > 0 else 0

                date_data[day_date].append({
                    "trade_date": day_date,
                    "code": code,
                    "name": "",
                    "close": close_p,
                    "open": open_p,
                    "high": high_p,
                    "low": low_p,
                    "change_pct": round(pct, 2),
                    "volume": vol,
                    "amount": 0,
                    "turnover_rate": 0,
                    "circ_market_cap": round(circ_mv, 2),
                })

        except Exception:
            continue

        if (idx + 1) % 500 == 0:
            logger.info(f"K线数据采集进度: {idx + 1}/{total}")
            time.sleep(0.2)

    result_counts = {}
    for d, rows in date_data.items():
        if rows:
            save_daily_snapshots(d, rows)
            result_counts[d] = len(rows)
            logger.info(f"已缓存 {d}: {len(rows)} 条")

    return result_counts


def _fetch_circ_shares(symbols: List[str]) -> Dict[str, float]:
    """批量获取当前流通股本（股）"""
    BATCH = 80
    QQ_URL = "https://qt.gtimg.cn/q={}"
    result = {}
    for i in range(0, len(symbols), BATCH):
        batch = symbols[i:i + BATCH]
        query = ",".join(batch)
        try:
            resp = requests.get(QQ_URL.format(query), headers=HEADERS_QQ, timeout=15)
            resp.encoding = "gbk"
            for line in resp.text.strip().split(";"):
                if "~" not in line:
                    continue
                parts = line.split("~")
                if len(parts) < 50:
                    continue
                code = parts[2].strip()
                price = float(parts[3]) if parts[3] else 0
                circ_mv_yi = float(parts[45]) if parts[45] else 0
                if price > 0 and circ_mv_yi > 0:
                    result[code] = circ_mv_yi * 1e8 / price
        except Exception:
            continue
        if i > 0 and i % (BATCH * 20) == 0:
            time.sleep(0.2)
    return result


def _calc_volume_ratio(symbol: str, target_date: str, target_volume: float) -> float:
    """通过腾讯K线计算某日的量比（当日成交量/前5日平均成交量）"""
    start = (datetime.strptime(target_date, "%Y-%m-%d") - timedelta(days=15)).strftime("%Y-%m-%d")
    try:
        url = TENCENT_KLINE_URL.format(symbol, start, target_date)
        resp = requests.get(url, headers=HEADERS_QQ, timeout=8)
        text = resp.text
        if "=" in text:
            text = text.split("=", 1)[1]
        data = json.loads(text)
        klines = data.get("data", {}).get(symbol, {})
        days = klines.get("qfqday", klines.get("day", []))

        target_idx = None
        for i, d in enumerate(days):
            if d[0] == target_date:
                target_idx = i
                break

        if target_idx is not None and target_idx >= 5:
            prev_vols = [float(days[j][5]) for j in range(target_idx - 5, target_idx)]
            avg5 = sum(prev_vols) / 5
            if avg5 > 0:
                return round(float(days[target_idx][5]) / avg5, 2)
    except Exception:
        pass
    return 0


def _check_zt_in_range(symbol: str, target_date: str, lookback: int = 15) -> bool:
    """检查目标日期前 lookback 天内是否有涨停"""
    start = (datetime.strptime(target_date, "%Y-%m-%d") - timedelta(days=lookback + 10)).strftime("%Y-%m-%d")
    try:
        url = TENCENT_KLINE_URL.format(symbol, start, target_date)
        resp = requests.get(url, headers=HEADERS_QQ, timeout=8)
        text = resp.text
        if "=" in text:
            text = text.split("=", 1)[1]
        data = json.loads(text)
        klines = data.get("data", {}).get(symbol, {})
        days = klines.get("qfqday", klines.get("day", []))

        target_idx = None
        for i, d in enumerate(days):
            if d[0] == target_date:
                target_idx = i
                break

        if target_idx is not None and target_idx >= 2:
            check_start = max(1, target_idx - lookback)
            for j in range(check_start, target_idx):
                prev_close = float(days[j - 1][2])
                cur_close = float(days[j][2])
                if prev_close > 0:
                    pct = (cur_close - prev_close) / prev_close * 100
                    if pct >= 9.8:
                        return True
    except Exception:
        pass
    return False


def _get_next_day_return(symbol: str, target_date: str) -> Optional[Dict[str, float]]:
    """获取目标日期次日的收益率"""
    end = (datetime.strptime(target_date, "%Y-%m-%d") + timedelta(days=7)).strftime("%Y-%m-%d")
    try:
        url = TENCENT_KLINE_URL.format(symbol, target_date, end)
        resp = requests.get(url, headers=HEADERS_QQ, timeout=8)
        text = resp.text
        if "=" in text:
            text = text.split("=", 1)[1]
        data = json.loads(text)
        klines = data.get("data", {}).get(symbol, {})
        days = klines.get("qfqday", klines.get("day", []))

        target_idx = None
        for i, d in enumerate(days):
            if d[0] == target_date:
                target_idx = i
                break

        if target_idx is not None and target_idx + 1 < len(days):
            buy_close = float(days[target_idx][2])
            next_day = days[target_idx + 1]
            next_open = float(next_day[1])
            next_close = float(next_day[2])
            next_high = float(next_day[3])
            next_low = float(next_day[4])

            return {
                "next_date": next_day[0],
                "buy_price": buy_close,
                "next_open": next_open,
                "next_close": next_close,
                "next_high": next_high,
                "next_low": next_low,
                "return_open": round((next_open - buy_close) / buy_close * 100, 2),
                "return_close": round((next_close - buy_close) / buy_close * 100, 2),
            }
    except Exception:
        pass
    return None


def calculate_priority(market_cap_yi: float) -> int:
    target = 150.0
    deviation = abs(market_cap_yi - target) / target
    if deviation <= 0.15:
        return 5
    elif deviation <= 0.30:
        return 4
    elif deviation <= 0.50:
        return 3
    elif deviation <= 0.70:
        return 2
    return 1


def run_backtest(target_date: str) -> dict:
    """对指定日期执行回测"""
    logger.info(f"开始回测 {target_date}...")

    snapshot = get_snapshot_by_date(target_date)
    if not snapshot:
        return {"success": False, "message": f"{target_date} 无缓存数据，请先缓存"}

    # 规则1: 涨幅 2-6%
    candidates = [s for s in snapshot if 2.0 <= s["change_pct"] <= 6.0]
    logger.info(f"规则1 涨幅2-6%: {len(candidates)} 只")

    # 规则3: 换手率 5-10%（如果有换手率数据）
    has_turnover = any(s["turnover_rate"] > 0 for s in candidates)
    if has_turnover:
        candidates = [s for s in candidates if 5.0 <= s["turnover_rate"] <= 10.0]
        logger.info(f"规则3 换手率5-10%: {len(candidates)} 只")

    # 规则4: 流通市值 50-300亿
    has_mcap = any(s["circ_market_cap"] > 0 for s in candidates)
    if has_mcap:
        candidates = [s for s in candidates if 50.0 <= s["circ_market_cap"] <= 300.0]
        logger.info(f"规则4 流通市值50-300亿: {len(candidates)} 只")

    # 规则2 & 5: 量比 > 1 和 15日内涨停（需逐只查K线）
    final = []
    for idx, s in enumerate(candidates):
        code = s["code"]
        prefix = "sh" if code.startswith("6") else "sz"
        symbol = f"{prefix}{code}"

        vol_ratio = _calc_volume_ratio(symbol, target_date, s["volume"])
        if vol_ratio <= 1.0:
            continue

        has_zt = _check_zt_in_range(symbol, target_date, lookback=15)
        if not has_zt:
            continue

        next_day = _get_next_day_return(symbol, target_date)

        mcap = s["circ_market_cap"]
        final.append({
            "code": code,
            "name": s["name"],
            "close": s["close"],
            "change_pct": s["change_pct"],
            "volume_ratio": vol_ratio,
            "turnover_rate": s["turnover_rate"],
            "market_cap_yi": mcap,
            "priority_score": calculate_priority(mcap),
            "next_day": next_day,
        })

        if (idx + 1) % 20 == 0:
            time.sleep(0.1)

    final.sort(key=lambda x: x["priority_score"], reverse=True)

    # 统计
    stats = _calc_stats(final)

    logger.info(f"回测完成: {target_date}, 筛出 {len(final)} 只, 胜率 {stats['win_rate']}%")
    return {
        "success": True,
        "date": target_date,
        "total_screened": len(final),
        "results": final,
        "stats": stats,
    }


def _calc_stats(results: List[dict]) -> dict:
    """计算回测统计指标"""
    if not results:
        return {"win_rate": 0, "avg_return_open": 0, "avg_return_close": 0,
                "max_gain": 0, "max_loss": 0, "win_count": 0, "lose_count": 0, "total": 0}

    returns_open = []
    returns_close = []
    for r in results:
        nd = r.get("next_day")
        if nd:
            returns_open.append(nd["return_open"])
            returns_close.append(nd["return_close"])

    if not returns_close:
        return {"win_rate": 0, "avg_return_open": 0, "avg_return_close": 0,
                "max_gain": 0, "max_loss": 0, "win_count": 0, "lose_count": 0, "total": 0}

    win_count = sum(1 for r in returns_close if r > 0)
    total = len(returns_close)
    return {
        "win_rate": round(win_count / total * 100, 1),
        "avg_return_open": round(sum(returns_open) / len(returns_open), 2),
        "avg_return_close": round(sum(returns_close) / len(returns_close), 2),
        "max_gain": round(max(returns_close), 2),
        "max_loss": round(min(returns_close), 2),
        "win_count": win_count,
        "lose_count": total - win_count,
        "total": total,
    }


def run_batch_backtest(start_date: str, end_date: str) -> dict:
    """批量回测日期范围"""
    cached = set(get_cached_dates())
    d = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")

    all_results = []
    all_returns = []

    while d <= end:
        ds = d.strftime("%Y-%m-%d")
        if d.weekday() < 5 and ds in cached:
            bt = run_backtest(ds)
            if bt["success"] and bt["results"]:
                for r in bt["results"]:
                    if r.get("next_day"):
                        all_returns.append(r["next_day"]["return_close"])
                all_results.append({
                    "date": ds,
                    "count": bt["total_screened"],
                    "stats": bt["stats"],
                })
        d += timedelta(days=1)

    total_stats = _calc_stats_from_returns(all_returns)
    return {
        "success": True,
        "start_date": start_date,
        "end_date": end_date,
        "days_tested": len(all_results),
        "daily_results": all_results,
        "total_stats": total_stats,
    }


def _calc_stats_from_returns(returns: List[float]) -> dict:
    if not returns:
        return {"win_rate": 0, "avg_return": 0, "max_gain": 0, "max_loss": 0,
                "win_count": 0, "lose_count": 0, "total": 0}
    win_count = sum(1 for r in returns if r > 0)
    return {
        "win_rate": round(win_count / len(returns) * 100, 1),
        "avg_return": round(sum(returns) / len(returns), 2),
        "max_gain": round(max(returns), 2),
        "max_loss": round(min(returns), 2),
        "win_count": win_count,
        "lose_count": len(returns) - win_count,
        "total": len(returns),
    }
