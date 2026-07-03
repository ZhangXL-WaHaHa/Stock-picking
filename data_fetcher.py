import requests
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional, Set, List, Tuple
import logging
import time
import json

logger = logging.getLogger(__name__)

TENCENT_BATCH_URL = "https://qt.gtimg.cn/q={}"
TENCENT_MINUTE_URL = "https://web.ifzq.gtimg.cn/appstock/app/minute/query?_var=min_data&code={}"
TENCENT_KLINE_URL = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?_var=kline_dayqfq&param={},day,{},{},30,qfq"
EASTMONEY_CONCEPT_URL = "https://emweb.securities.eastmoney.com/PC_HSF10/CoreConception/PageAjax?code={}"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36", "Referer": "https://finance.qq.com"}
BATCH_SIZE = 80


def _generate_main_board_codes() -> List[str]:
    """生成全部主板可能的股票代码（sh60xxxx + sz00xxxx）"""
    codes = []
    for i in range(6000):
        codes.append(f"sh60{str(i).zfill(4)}")
    for i in range(1, 4000):
        codes.append(f"sz00{str(i).zfill(4)}")
    return codes


def _parse_tencent_quote(raw: str) -> Optional[dict]:
    """解析腾讯财经单条行情数据"""
    parts = raw.split("~")
    if len(parts) < 50:
        return None
    try:
        code = parts[2].strip()
        name = parts[1].strip()
        if not code or not name:
            return None
        price = float(parts[3]) if parts[3] else 0
        if price <= 0:
            return None
        if "ST" in name.upper():
            return None

        change_pct = float(parts[32]) if parts[32] else 0
        turnover_rate = float(parts[38]) if parts[38] else 0
        volume_ratio = float(parts[49]) if parts[49] else 0
        circ_mv = float(parts[45]) if parts[45] else 0

        return {
            "代码": code,
            "名称": name,
            "最新价": price,
            "涨跌幅": change_pct,
            "换手率": turnover_rate,
            "量比": volume_ratio,
            "流通市值": circ_mv,
        }
    except (ValueError, IndexError):
        return None


def get_realtime_quotes() -> pd.DataFrame:
    """通过腾讯财经接口批量获取全市场主板实时行情"""
    all_codes = _generate_main_board_codes()
    logger.info(f"正在分批获取主板实时行情（共 {len(all_codes)} 个代码）...")

    all_records = []
    for i in range(0, len(all_codes), BATCH_SIZE):
        batch = all_codes[i : i + BATCH_SIZE]
        query = ",".join(batch)
        try:
            resp = requests.get(TENCENT_BATCH_URL.format(query), headers=HEADERS, timeout=15)
            resp.encoding = "gbk"
            for line in resp.text.strip().split(";"):
                if "~" not in line:
                    continue
                record = _parse_tencent_quote(line)
                if record:
                    all_records.append(record)
        except Exception as e:
            logger.warning(f"批次 {i // BATCH_SIZE} 获取失败: {e}")
        if i > 0 and i % (BATCH_SIZE * 20) == 0:
            time.sleep(0.2)
            logger.info(f"行情获取进度: {i}/{len(all_codes)}")

    df = pd.DataFrame(all_records)
    logger.info(f"实时行情获取完成，共 {len(df)} 只有效股票")
    return df


def _check_stock_zt(code: str, start_date: str, end_date: str) -> bool:
    """通过腾讯历史K线检查某只股票在指定时间段内是否涨停过"""
    prefix = "sh" if code.startswith("6") else "sz"
    symbol = f"{prefix}{code}"
    try:
        url = TENCENT_KLINE_URL.format(symbol, start_date, end_date)
        resp = requests.get(url, headers=HEADERS, timeout=8)
        text = resp.text
        if text.startswith("kline_dayqfq="):
            text = text[len("kline_dayqfq="):]
        data = json.loads(text)

        klines = data.get("data", {}).get(symbol, {})
        days = klines.get("qfqday", klines.get("day", []))
        if not days or len(days) < 2:
            return False

        for j in range(1, len(days)):
            prev_close = float(days[j - 1][1])  # 前日开盘→用收盘
            close = float(days[j][2])            # 当日收盘
            if prev_close > 0:
                pct = (close - prev_close) / prev_close * 100
                if pct >= 9.8:
                    return True
    except Exception:
        pass
    return False


def get_zt_codes_recent(candidate_codes: List[str], days: int = 15) -> Set[str]:
    """检查候选股票中哪些在近 N 天内有涨停记录"""
    logger.info(f"正在检查 {len(candidate_codes)} 只候选股票的近{days}日涨停记录...")
    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=days + 10)).strftime("%Y-%m-%d")

    zt_codes = set()
    for idx, code in enumerate(candidate_codes):
        if _check_stock_zt(code, start_date, end_date):
            zt_codes.add(code)
        if (idx + 1) % 20 == 0:
            time.sleep(0.1)
        if (idx + 1) % 50 == 0:
            logger.info(f"涨停检查进度: {idx + 1}/{len(candidate_codes)}，已找到 {len(zt_codes)} 只")

    logger.info(f"涨停检查完成，{len(zt_codes)}/{len(candidate_codes)} 只近{days}日有涨停")
    return zt_codes


def get_stock_intraday(code: str) -> Optional[pd.DataFrame]:
    """通过腾讯财经接口获取个股当日分时数据"""
    prefix = "sh" if code.startswith("6") else "sz"
    symbol = f"{prefix}{code}"
    try:
        resp = requests.get(TENCENT_MINUTE_URL.format(symbol), headers=HEADERS, timeout=10)
        text = resp.text
        if text.startswith("min_data="):
            text = text[len("min_data="):]
        data = json.loads(text)

        minute_data = data.get("data", {}).get(symbol, {}).get("data", {}).get("data", [])
        if not minute_data:
            return None

        records = []
        for line in minute_data:
            parts = line.split(" ")
            if len(parts) >= 4:
                records.append({
                    "时间": parts[0],
                    "收盘": float(parts[1]),
                    "成交量": int(parts[2]),
                    "成交额": float(parts[3]),
                })
        if records:
            return pd.DataFrame(records)
    except Exception as e:
        logger.debug(f"获取 {code} 分时数据失败: {e}")
    return None


def get_stock_themes(code: str) -> List[str]:
    prefix = "SH" if code.startswith("6") else "SZ"
    symbol = f"{prefix}{code}"
    try:
        resp = requests.get(
            EASTMONEY_CONCEPT_URL.format(symbol),
            headers={"User-Agent": HEADERS["User-Agent"]},
            timeout=8,
        )
        data = resp.json()
        boards = data.get("ssbk", [])
        return [b["BOARD_NAME"] for b in boards if b.get("IS_PRECISE") == "1"]
    except Exception as e:
        logger.debug(f"获取 {code} 题材概念失败: {e}")
        return []


def is_trade_time() -> bool:
    now = datetime.now()
    if now.weekday() >= 5:
        return False
    t = now.hour * 100 + now.minute
    return (930 <= t <= 1130) or (1300 <= t <= 1500)


def is_late_session() -> bool:
    now = datetime.now()
    if now.weekday() >= 5:
        return False
    t = now.hour * 100 + now.minute
    return 1430 <= t <= 1500
