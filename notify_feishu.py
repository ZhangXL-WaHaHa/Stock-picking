import os
import sys
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import requests
from datetime import datetime

from screener import screen_stocks
from trade_tracker import add_pending_trades, get_stats

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

WEBHOOK_URL = os.environ.get("FEISHU_WEBHOOK_URL", "")
SMTP_HOST = os.environ.get("SMTP_HOST", "")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "465"))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASS = os.environ.get("SMTP_PASS", "")
EMAIL_TO = os.environ.get("EMAIL_TO", "")


def build_message(results, stats):
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

    if stats["total"] > 0:
        content += (f"\n\n---\n**一夜持股胜率**: {stats['wins']}胜 {stats['losses']}负 "
                    f"共{stats['total']}场 胜率**{stats['win_rate']}%**")

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
        logger.warning("FEISHU_WEBHOOK_URL 未设置，跳过飞书推送")
        return

    resp = requests.post(WEBHOOK_URL, json=message, timeout=10)
    data = resp.json()
    if data.get("code") == 0:
        logger.info("飞书推送成功")
    else:
        logger.error(f"飞书推送失败: {data}")


def build_email_html(results, stats):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if not results:
        return f"<h2>选股结果 - {now}</h2><p>未找到符合条件的股票</p>"

    rows = ""
    for s in results:
        stars = "★" * s["priority_score"] + "☆" * (5 - s["priority_score"])
        themes = s.get("themes", "")
        rows += (
            f"<tr>"
            f"<td>{stars}</td>"
            f"<td><b>{s['code']}</b></td>"
            f"<td>{s['name']}</td>"
            f"<td>{s['price']}</td>"
            f"<td style='color:red'>+{s['change_pct']}%</td>"
            f"<td>{s['volume_ratio']}</td>"
            f"<td>{s['turnover_rate']}%</td>"
            f"<td>{s['market_cap_yi']}亿</td>"
            f"<td style='font-size:12px'>{themes}</td>"
            f"</tr>"
        )

    html = f"""
    <h2>选股结果 - {now} ({len(results)}只)</h2>
    <table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse;font-size:14px">
    <tr style="background:#f0f0f0">
        <th>优先级</th><th>代码</th><th>名称</th><th>最新价</th>
        <th>涨跌幅</th><th>量比</th><th>换手率</th><th>流通市值</th><th>题材概念</th>
    </tr>
    {rows}
    </table>
    """

    if stats["total"] > 0:
        html += (f'<p style="margin-top:12px;color:#555"><b>一夜持股胜率</b>：'
                 f'{stats["wins"]}胜 {stats["losses"]}负 '
                 f'共{stats["total"]}场 胜率<b>{stats["win_rate"]}%</b></p>')

    return html


def send_email(results, stats):
    if not all([SMTP_HOST, SMTP_USER, SMTP_PASS, EMAIL_TO]):
        logger.warning("邮箱配置不完整，跳过邮件推送")
        return

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    count = len(results)
    subject = f"选股结果 - {now} ({count}只)" if count else f"选股结果 - {now} (无)"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = SMTP_USER
    msg["To"] = EMAIL_TO

    html = build_email_html(results, stats)
    msg.attach(MIMEText(html, "html", "utf-8"))

    try:
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=15) as server:
            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(SMTP_USER, EMAIL_TO.split(","), msg.as_string())
        logger.info(f"邮件推送成功 -> {EMAIL_TO}")
    except Exception as e:
        logger.error(f"邮件推送失败: {e}")


def main():
    logger.info("开始执行选股筛选...")
    results = screen_stocks()
    logger.info(f"筛选完成，找到 {len(results)} 只股票")

    stats = get_stats()
    message = build_message(results, stats)
    send_to_feishu(message)
    send_email(results, stats)
    add_pending_trades(results)


if __name__ == "__main__":
    main()
