import pandas as pd
import numpy as np
import logging
from typing import List, Tuple
from data_fetcher import get_realtime_quotes, get_zt_codes_recent, get_stock_intraday, get_stock_themes
from models import StockResult

logger = logging.getLogger(__name__)


def filter_main_board(df: pd.DataFrame) -> pd.DataFrame:
    """过滤主板股票：保留60xxxx（沪主板）和00xxxx（深主板），排除ST"""
    code_col = "代码"
    name_col = "名称"
    df = df[df[code_col].astype(str).str.match(r"^(60|00)\d{4}$")]
    df = df[~df[name_col].str.contains("ST", case=False, na=False)]
    return df


def filter_change_pct(df: pd.DataFrame, low: float = 2.0, high: float = 6.0) -> pd.DataFrame:
    """规则1：涨幅 2-6%"""
    return df[(df["涨跌幅"] >= low) & (df["涨跌幅"] <= high)]


def filter_volume_ratio(df: pd.DataFrame, min_ratio: float = 1.0) -> pd.DataFrame:
    """规则2：量比 > 1"""
    return df[df["量比"] > min_ratio]


def filter_turnover_rate(df: pd.DataFrame, low: float = 5.0, high: float = 10.0) -> pd.DataFrame:
    """规则3：换手率 5-10%"""
    return df[(df["换手率"] >= low) & (df["换手率"] <= high)]


def filter_market_cap(df: pd.DataFrame, low_yi: float = 50.0, high_yi: float = 300.0) -> pd.DataFrame:
    """规则4：流通市值 50-300亿（腾讯接口单位已是亿）"""
    return df[(df["流通市值"] >= low_yi) & (df["流通市值"] <= high_yi)]


def calculate_priority(market_cap_yi: float) -> int:
    """计算优先级评分：流通市值越接近150亿，分数越高（1-5星）"""
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


def get_intraday_reference(code: str) -> Tuple[str, str]:
    """规则6（半自动）：获取分时参考信息"""
    df = get_stock_intraday(code)
    if df is None or df.empty:
        return ("暂无分时数据", "暂无分时数据")

    try:
        df = df.copy()
        df["成交额"] = pd.to_numeric(df["成交额"], errors="coerce")
        df["成交量"] = pd.to_numeric(df["成交量"], errors="coerce")
        df["收盘"] = pd.to_numeric(df["收盘"], errors="coerce")

        # 腾讯分时数据是累计值，需要差分得到每分钟增量
        df["分钟成交量"] = df["成交量"].diff().fillna(df["成交量"].iloc[0])
        df["分钟成交额"] = df["成交额"].diff().fillna(df["成交额"].iloc[0])

        # 腾讯分时：成交量单位是手(100股)，成交额单位是元
        total_amount = df["成交额"].iloc[-1]
        total_volume = df["成交量"].iloc[-1]
        if total_volume > 0:
            vwap = total_amount / (total_volume * 100)
        else:
            vwap = df["收盘"].iloc[-1]

        latest_price = df["收盘"].iloc[-1]
        vwap_dev = (latest_price - vwap) / vwap * 100
        above_count = (df["收盘"] > vwap).sum()
        above_ratio = above_count / len(df) * 100

        if vwap_dev > 0.5 and above_ratio > 60:
            vwap_info = f"偏离+{vwap_dev:.2f}% | {above_ratio:.0f}%时间在均价线上方 [良好]"
        elif vwap_dev > 0:
            vwap_info = f"偏离+{vwap_dev:.2f}% | {above_ratio:.0f}%时间在均价线上方 [一般]"
        else:
            vwap_info = f"偏离{vwap_dev:.2f}% | {above_ratio:.0f}%时间在均价线上方 [偏弱]"

        n = len(df)
        if n >= 15:
            late_vol = df["分钟成交量"].iloc[-15:].mean()
            earlier_vol = df["分钟成交量"].iloc[:-15].mean()
            if earlier_vol > 0:
                vol_change = (late_vol - earlier_vol) / earlier_vol * 100
            else:
                vol_change = 0

            late_prices = df["收盘"].iloc[-15:]
            price_drop = (late_prices.iloc[-1] - late_prices.iloc[0]) / late_prices.iloc[0] * 100

            if vol_change > 50 and price_drop < -1:
                late_info = f"尾盘量变+{vol_change:.0f}% 价跌{price_drop:.2f}% [警告:放量跳水]"
            elif vol_change > 30:
                late_info = f"尾盘量变+{vol_change:.0f}% 价变{price_drop:+.2f}% [注意:量能放大]"
            else:
                late_info = f"尾盘量变{vol_change:+.0f}% 价变{price_drop:+.2f}% [正常]"
        else:
            late_info = "分时数据不足，无法判断尾盘"

        return (vwap_info, late_info)
    except Exception as e:
        logger.warning(f"计算分时参考失败 {code}: {e}")
        return ("计算异常", "计算异常")


def screen_stocks() -> List[dict]:
    """执行完整的选股筛选流程"""
    logger.info("=" * 50)
    logger.info("开始执行一夜持股法筛选...")

    df = get_realtime_quotes()
    if df.empty:
        logger.warning("未获取到任何行情数据，可能处于非交易时段或接口异常")
        return []
    total = len(df)
    logger.info(f"全市场主板共 {total} 只股票（已排除ST）")

    expected_cols = {"涨跌幅", "量比", "换手率", "流通市值"}
    missing = expected_cols - set(df.columns)
    if missing:
        raise RuntimeError(f"行情数据缺少字段: {missing}，接口可能已变更")

    df = filter_change_pct(df)
    logger.info(f"规则1 - 涨幅2-6%过滤后: {len(df)} 只")

    df = filter_volume_ratio(df)
    logger.info(f"规则2 - 量比>1过滤后: {len(df)} 只")

    df = filter_turnover_rate(df)
    logger.info(f"规则3 - 换手率5-10%过滤后: {len(df)} 只")

    df = filter_market_cap(df)
    logger.info(f"规则4 - 流通市值50-300亿过滤后: {len(df)} 只")

    zt_codes = get_zt_codes_recent(df["代码"].astype(str).tolist(), days=15)
    df = df[df["代码"].astype(str).isin(zt_codes)]
    logger.info(f"规则5 - 15日内有涨停过滤后: {len(df)} 只")

    results = []
    for _, row in df.iterrows():
        code = str(row["代码"])
        market_cap_yi = float(row["流通市值"])

        vwap_info, late_info = get_intraday_reference(code)
        themes = get_stock_themes(code)

        stock = StockResult(
            code=code,
            name=str(row["名称"]),
            price=float(row["最新价"]),
            change_pct=float(row["涨跌幅"]),
            volume_ratio=float(row["量比"]),
            turnover_rate=float(row["换手率"]),
            market_cap_yi=round(market_cap_yi, 2),
            priority_score=calculate_priority(market_cap_yi),
            has_zt_15d=True,
            vwap_info=vwap_info,
            late_volume_info=late_info,
            themes="、".join(themes),
        )
        results.append(stock.to_dict())

    results.sort(key=lambda x: x["priority_score"], reverse=True)

    logger.info(f"筛选完成，共找到 {len(results)} 只符合条件的股票")
    logger.info("=" * 50)
    return results
