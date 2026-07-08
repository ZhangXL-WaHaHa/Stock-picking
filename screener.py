import logging
from typing import List
from data_fetcher import get_realtime_quotes
from strategies import STRATEGIES

logger = logging.getLogger(__name__)


def screen_stocks(strategy: str = "overnight") -> List[dict]:
    if strategy not in STRATEGIES:
        raise ValueError(f"未知策略: {strategy}")

    logger.info("=" * 50)

    df = get_realtime_quotes()
    if df.empty:
        logger.warning("未获取到任何行情数据，可能处于非交易时段或接口异常")
        return []

    logger.info(f"全市场主板共 {len(df)} 只股票（已排除ST）")

    results = STRATEGIES[strategy]["fn"](df)

    logger.info(f"筛选完成，共找到 {len(results)} 只符合条件的股票")
    logger.info("=" * 50)
    return results
