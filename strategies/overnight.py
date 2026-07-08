import pandas as pd
import numpy as np
import logging
from typing import List
from data_fetcher import get_zt_codes_recent, get_stock_intraday, get_stock_themes, get_market_index_change

logger = logging.getLogger(__name__)


def _filter_change_pct(df, low=2.0, high=6.0):
    return df[(df["涨跌幅"] >= low) & (df["涨跌幅"] <= high)]


def _filter_volume_ratio(df, min_ratio=1.0):
    return df[df["量比"] > min_ratio]


def _filter_turnover_rate(df, low=5.0, high=10.0):
    return df[(df["换手率"] >= low) & (df["换手率"] <= high)]


def _filter_market_cap(df, low_yi=50.0, high_yi=300.0):
    return df[(df["流通市值"] >= low_yi) & (df["流通市值"] <= high_yi)]


def _filter_close_position(df, min_ratio=0.5):
    spread = df["最高"] - df["最低"]
    position = (df["最新价"] - df["最低"]) / spread.replace(0, np.nan)
    return df[position >= min_ratio]


def _calculate_priority(market_cap_yi):
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
    else:
        return 1


def _get_intraday_reference(code):
    default = {"vwap_info": "暂无分时数据", "late_info": "暂无分时数据", "vwap_ok": False, "late_ok": False}
    df = get_stock_intraday(code)
    if df is None or df.empty:
        return default

    try:
        df = df.copy()
        df["成交额"] = pd.to_numeric(df["成交额"], errors="coerce")
        df["成交量"] = pd.to_numeric(df["成交量"], errors="coerce")
        df["收盘"] = pd.to_numeric(df["收盘"], errors="coerce")

        df["分钟成交量"] = df["成交量"].diff().fillna(df["成交量"].iloc[0])

        total_amount = df["成交额"].iloc[-1]
        total_volume = df["成交量"].iloc[-1]
        vwap = total_amount / (total_volume * 100) if total_volume > 0 else df["收盘"].iloc[-1]

        latest_price = df["收盘"].iloc[-1]
        vwap_dev = (latest_price - vwap) / vwap * 100
        above_ratio = (df["收盘"] > vwap).sum() / len(df) * 100
        vwap_ok = vwap_dev >= 0 and above_ratio >= 50

        if vwap_dev > 0.5 and above_ratio > 60:
            vwap_info = f"偏离+{vwap_dev:.2f}% | {above_ratio:.0f}%在均价上方 [良好]"
        elif vwap_dev > 0:
            vwap_info = f"偏离+{vwap_dev:.2f}% | {above_ratio:.0f}%在均价上方 [一般]"
        else:
            vwap_info = f"偏离{vwap_dev:.2f}% | {above_ratio:.0f}%在均价上方 [偏弱]"

        late_ok = True
        n = len(df)
        if n >= 15:
            late_vol = df["分钟成交量"].iloc[-15:].mean()
            earlier_vol = df["分钟成交量"].iloc[:-15].mean()
            vol_change = (late_vol - earlier_vol) / earlier_vol * 100 if earlier_vol > 0 else 0
            late_prices = df["收盘"].iloc[-15:]
            price_drop = (late_prices.iloc[-1] - late_prices.iloc[0]) / late_prices.iloc[0] * 100

            if vol_change > 50 and price_drop < -1:
                late_info = f"尾盘量变+{vol_change:.0f}% 价跌{price_drop:.2f}% [警告:放量跳水]"
                late_ok = False
            elif vol_change > 30:
                late_info = f"尾盘量变+{vol_change:.0f}% 价变{price_drop:+.2f}% [注意:量能放大]"
            else:
                late_info = f"尾盘量变{vol_change:+.0f}% 价变{price_drop:+.2f}% [正常]"
        else:
            late_info = "分时数据不足"

        return {"vwap_info": vwap_info, "late_info": late_info, "vwap_ok": vwap_ok, "late_ok": late_ok}
    except Exception as e:
        logger.warning(f"分时计算失败 {code}: {e}")
        return {"vwap_info": "计算异常", "late_info": "计算异常", "vwap_ok": False, "late_ok": False}


def screen(df: pd.DataFrame) -> List[dict]:
    logger.info("开始执行一夜持股法筛选...")

    market_chg = get_market_index_change()
    if market_chg is not None:
        logger.info(f"上证指数: {market_chg:+.2f}%")
        if market_chg < -0.5:
            logger.warning(f"大盘偏弱(上证 {market_chg:+.2f}%)，跳过筛选")
            return []

    df = _filter_change_pct(df)
    logger.info(f"涨幅2-6%: {len(df)} 只")

    df = _filter_volume_ratio(df)
    logger.info(f"量比>1: {len(df)} 只")

    df = _filter_turnover_rate(df)
    logger.info(f"换手率5-10%: {len(df)} 只")

    df = _filter_market_cap(df)
    logger.info(f"流通市值50-300亿: {len(df)} 只")

    df = _filter_close_position(df)
    logger.info(f"收盘价上半区: {len(df)} 只")

    zt_codes = get_zt_codes_recent(df["代码"].astype(str).tolist(), days=15)
    df = df[df["代码"].astype(str).isin(zt_codes)]
    logger.info(f"涨停+缩量回调: {len(df)} 只")

    results = []
    for _, row in df.iterrows():
        code = str(row["代码"])
        market_cap_yi = float(row["流通市值"])

        intraday = _get_intraday_reference(code)
        if not intraday["vwap_ok"] or not intraday["late_ok"]:
            continue

        themes = get_stock_themes(code)
        high, low = float(row["最高"]), float(row["最低"])
        spread = high - low
        close_pos = round((float(row["最新价"]) - low) / spread, 2) if spread > 0 else 0.5

        results.append({
            "code": code,
            "name": str(row["名称"]),
            "price": float(row["最新价"]),
            "change_pct": float(row["涨跌幅"]),
            "volume_ratio": float(row["量比"]),
            "turnover_rate": float(row["换手率"]),
            "market_cap_yi": round(market_cap_yi, 2),
            "priority_score": _calculate_priority(market_cap_yi),
            "close_position": close_pos,
            "vwap_info": intraday["vwap_info"],
            "late_volume_info": intraday["late_info"],
            "themes": "、".join(themes),
        })

    results.sort(key=lambda x: x["priority_score"], reverse=True)
    logger.info(f"一夜持股法筛选完成，找到 {len(results)} 只")
    return results
