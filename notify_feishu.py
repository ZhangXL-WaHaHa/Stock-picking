import os
import sys
import logging
import requests
from datetime import datetime

from screener import screen_stocks

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

WEBHOOK_URL = os.environ.get("FEISHU_WEBHOOK_URL", "")


def build_message(results):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if not results:
        return {
            "msg_type": "interactive",
            "card": {
                "header": {
                    "title": {"tag": "plain_text", "content": f"选股结果 - {now}"},
                    "template": "grey",
                },
                "elements": [
                    {"tag": "markdown", "content": "未找到符合条件的股票"}
                ],
            },
        }

    lines = []
    for s in results:
        stars = "★" * s["priority_score"] + "☆" * (5 - s["priority_score"])
        themes = s.get("themes", "")
        themes_str = f"\n  题材: {themes}" if themes else ""
        lines.append(
            f"**{s['name']}** ({s['code']})  {stars}\n"
            f"  价格: {s['price']}  涨幅: +{s['change_pct']}%  "
            f"量比: {s['volume_ratio']}  换手: {s['turnover_rate']}%\n"
            f"  流通市值: {s['market_cap_yi']}亿  "
            f"VWAP: {s['vwap_info']}\n"
            f"  尾盘: {s['late_volume_info']}"
            f"{themes_str}"
        )

    content = "\n---\n".join(lines)

    return {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"tag": "plain_text", "content": f"选股结果 - {now} ({len(results)}只)"},
                "template": "red",
            },
            "elements": [
                {"tag": "markdown", "content": content}
            ],
        },
    }


def send_to_feishu(message):
    if not WEBHOOK_URL:
        logger.error("FEISHU_WEBHOOK_URL 环境变量未设置")
        sys.exit(1)

    resp = requests.post(WEBHOOK_URL, json=message, timeout=10)
    data = resp.json()
    if data.get("code") == 0:
        logger.info("飞书推送成功")
    else:
        logger.error(f"飞书推送失败: {data}")
        sys.exit(1)


def main():
    logger.info("开始执行选股筛选...")
    results = screen_stocks()
    logger.info(f"筛选完成，找到 {len(results)} 只股票")

    message = build_message(results)
    send_to_feishu(message)


if __name__ == "__main__":
    main()
