import pandas as pd
import numpy as np
import logging
from typing import List
from data_fetcher import get_stock_klines, get_market_index_change

logger = logging.getLogger(__name__)


def screen(df: pd.DataFrame) -> List[dict]:
    logger.info("开始执行均线回踩策略筛选...")

    market_chg = get_market_index_change()
    if market_chg is not None and market_chg < -0.5:
        logger.warning(f"大盘偏弱(上证 {market_chg:+.2f}%)，跳过筛选")
        return []

    df = df[(df["涨跌幅"] >= -1) & (df["涨跌幅"] <= 3)]
    df = df[(df["流通市值"] >= 30) & (df["流通市值"] <= 500)]
    logger.info(f"基础过滤后: {len(df)} 只")

    results = []
    checked = 0
    for _, row in df.iterrows():
        code = str(row["代码"])
        klines = get_stock_klines(code, days=60)
        if len(klines) < 25:
            continue

        checked += 1
        if checked % 100 == 0:
            logger.info(f"均线回踩进度: {checked}/{len(df)}")

        closes = np.array([float(d[2]) for d in klines])
        volumes = np.array([float(d[5]) for d in klines])

        ma5 = np.mean(closes[-5:])
        ma10 = np.mean(closes[-10:])
        ma20 = np.mean(closes[-20:])

        if not (ma5 > ma10 > ma20):
            continue

        latest = closes[-1]
        dist_ma10 = abs(latest - ma10) / ma10 * 100
        if dist_ma10 > 2:
            continue

        recent_vol = np.mean(volumes[-3:])
        prev_vol = np.mean(volumes[-13:-3])
        if prev_vol > 0 and recent_vol >= prev_vol * 0.7:
            continue

        if closes[-1] <= closes[-2]:
            continue

        score = 5
        if dist_ma10 > 1:
            score -= 1
        if recent_vol / prev_vol > 0.5 if prev_vol > 0 else True:
            score -= 1

        results.append({
            "code": code,
            "name": str(row["名称"]),
            "price": float(row["最新价"]),
            "change_pct": float(row["涨跌幅"]),
            "volume_ratio": float(row["量比"]),
            "turnover_rate": float(row["换手率"]),
            "market_cap_yi": round(float(row["流通市值"]), 2),
            "priority_score": max(1, score),
            "ma5": round(ma5, 2),
            "ma10": round(ma10, 2),
            "ma20": round(ma20, 2),
            "vol_shrink": round((1 - recent_vol / prev_vol) * 100, 1) if prev_vol > 0 else 0,
        })

    results.sort(key=lambda x: x["priority_score"], reverse=True)
    logger.info(f"均线回踩筛选完成，找到 {len(results)} 只")
    return results
