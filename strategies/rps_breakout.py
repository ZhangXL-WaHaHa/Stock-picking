import pandas as pd
import numpy as np
import logging
from typing import List
from data_fetcher import get_stock_klines, get_market_index_change

logger = logging.getLogger(__name__)


def screen(df: pd.DataFrame) -> List[dict]:
    logger.info("开始执行RPS强势突破策略筛选...")

    market_chg = get_market_index_change()
    if market_chg is not None and market_chg < -0.5:
        logger.warning(f"大盘偏弱(上证 {market_chg:+.2f}%)，跳过筛选")
        return []

    df = df[(df["流通市值"] >= 30) & (df["流通市值"] <= 500)]
    logger.info(f"市值过滤后: {len(df)} 只")

    rps_data = []
    checked = 0
    for _, row in df.iterrows():
        code = str(row["代码"])
        klines = get_stock_klines(code, days=90)
        if len(klines) < 60:
            continue

        checked += 1
        if checked % 100 == 0:
            logger.info(f"RPS计算进度: {checked}/{len(df)}")

        closes = [float(d[2]) for d in klines]
        close_60_ago = closes[-60]
        close_now = closes[-1]
        gain_60d = (close_now - close_60_ago) / close_60_ago * 100 if close_60_ago > 0 else 0

        rps_data.append({
            "row": row,
            "klines": klines,
            "closes": closes,
            "gain_60d": gain_60d,
        })

    if not rps_data:
        return []

    gains = sorted([d["gain_60d"] for d in rps_data])
    total = len(gains)

    results = []
    for d in rps_data:
        rank = sum(1 for g in gains if g <= d["gain_60d"])
        rps = round(rank / total * 100, 1)
        if rps < 90:
            continue

        closes = d["closes"]
        high_20d = max(closes[-20:])
        if closes[-1] < high_20d * 0.98:
            continue

        recent_high = max(closes[-10:])
        recent_low = min(closes[-10:])
        if recent_low > 0:
            range_10d = (recent_high - recent_low) / recent_low * 100
        else:
            range_10d = 999
        if range_10d > 10:
            continue

        row = d["row"]
        score = 5 if rps >= 97 else (4 if rps >= 95 else 3)

        results.append({
            "code": str(row["代码"]),
            "name": str(row["名称"]),
            "price": float(row["最新价"]),
            "change_pct": float(row["涨跌幅"]),
            "volume_ratio": float(row["量比"]),
            "turnover_rate": float(row["换手率"]),
            "market_cap_yi": round(float(row["流通市值"]), 2),
            "priority_score": score,
            "rps": rps,
            "gain_60d": round(d["gain_60d"], 1),
            "range_10d": round(range_10d, 1),
        })

    results.sort(key=lambda x: x["rps"], reverse=True)
    logger.info(f"RPS突破筛选完成，找到 {len(results)} 只")
    return results
