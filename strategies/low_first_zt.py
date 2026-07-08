import pandas as pd
import numpy as np
import logging
from typing import List
from data_fetcher import get_stock_klines

logger = logging.getLogger(__name__)


def screen(df: pd.DataFrame) -> List[dict]:
    logger.info("开始执行低位首板策略筛选...")

    df = df[df["涨跌幅"] >= 9.8]
    df = df[(df["流通市值"] >= 30) & (df["流通市值"] <= 300)]
    logger.info(f"当日涨停+市值过滤后: {len(df)} 只")

    results = []
    for _, row in df.iterrows():
        code = str(row["代码"])
        klines = get_stock_klines(code, days=90)
        if len(klines) < 30:
            continue

        closes = [float(d[2]) for d in klines]
        high_60d = max(closes[-60:]) if len(closes) >= 60 else max(closes)
        current = closes[-1]

        drop_from_high = (current - high_60d) / high_60d * 100
        if drop_from_high > -30:
            continue

        zt_count = 0
        for j in range(1, min(60, len(klines))):
            idx = len(klines) - 1 - j
            if idx < 1:
                break
            prev_close = float(klines[idx - 1][2])
            day_close = float(klines[idx][2])
            if prev_close > 0:
                pct = (day_close - prev_close) / prev_close * 100
                if pct >= 9.8:
                    zt_count += 1

        if zt_count > 0:
            continue

        volumes = [float(d[5]) for d in klines]
        avg_vol_20 = np.mean(volumes[-20:]) if len(volumes) >= 20 else np.mean(volumes)
        today_vol = volumes[-1]
        vol_ratio = round(today_vol / avg_vol_20, 1) if avg_vol_20 > 0 else 0

        score = 5
        if drop_from_high > -40:
            score -= 1
        if vol_ratio < 2:
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
            "drop_from_high": round(drop_from_high, 1),
            "zt_vol_ratio": vol_ratio,
            "status": "观察中",
        })

    results.sort(key=lambda x: x["priority_score"], reverse=True)
    logger.info(f"低位首板筛选完成，找到 {len(results)} 只")
    return results
