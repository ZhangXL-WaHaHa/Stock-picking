import os
import sys
import logging
import requests
from datetime import datetime

from trade_tracker import settle_pending_trades, get_stats

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

WEBHOOK_URL = os.environ.get("FEISHU_WEBHOOK_URL", "")
SMTP_HOST = os.environ.get("SMTP_HOST", "")
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASS = os.environ.get("SMTP_PASS", "")
EMAIL_TO = os.environ.get("EMAIL_TO", "")


def build_settle_message(settled, stats):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if not settled:
        content = "今日无待结算交易"
    else:
        lines = []
        for t in settled:
            icon = "+" if t["result"] == "win" else ""
            lines.append(f"{'✅' if t['result'] == 'win' else '❌'} "
                         f"**{t['name']}**({t['code']}) "
                         f"买{t['buy_price']} → 卖{t['sell_price']} "
                         f"{icon}{t['profit_pct']}%")
        lines.append(f"\n---\n**累计胜率**: {stats['wins']}胜 {stats['losses']}负 "
                     f"共{stats['total']}场 胜率{stats['win_rate']}%")
        content = "\n".join(lines)

    return {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"tag": "plain_text", "content": f"一夜持股结算 - {now}"},
                "template": "green" if not settled or stats["win_rate"] >= 50 else "orange",
            },
            "elements": [{"tag": "markdown", "content": content}],
        },
    }


def send_feishu(message):
    if not WEBHOOK_URL:
        return
    try:
        resp = requests.post(WEBHOOK_URL, json=message, timeout=10)
        data = resp.json()
        if data.get("code") == 0:
            logger.info("飞书推送成功")
        else:
            logger.error(f"飞书推送失败: {data}")
    except Exception as e:
        logger.error(f"飞书推送异常: {e}")


def send_email(settled, stats):
    if not all([SMTP_HOST, SMTP_USER, SMTP_PASS, EMAIL_TO]):
        return

    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    subject = f"一夜持股结算 - {now} (胜率{stats['win_rate']}%)"

    if not settled:
        html = "<h2>今日无待结算交易</h2>"
    else:
        rows = ""
        for t in settled:
            color = "green" if t["result"] == "win" else "red"
            rows += (f"<tr><td>{t['name']}</td><td>{t['code']}</td>"
                     f"<td>{t['buy_price']}</td><td>{t['sell_price']}</td>"
                     f"<td style='color:{color}'>{t['profit_pct']:+.2f}%</td></tr>")
        html = f"""
        <h2>一夜持股结算 - {now}</h2>
        <table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse;font-size:14px">
        <tr style="background:#f0f0f0"><th>名称</th><th>代码</th><th>买入价</th><th>卖出价</th><th>盈亏</th></tr>
        {rows}
        </table>
        <p><b>累计胜率</b>: {stats['wins']}胜 {stats['losses']}负 共{stats['total']}场 胜率{stats['win_rate']}%</p>
        """

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = SMTP_USER
    msg["To"] = EMAIL_TO
    msg.attach(MIMEText(html, "html", "utf-8"))

    try:
        with smtplib.SMTP_SSL(SMTP_HOST, int(os.environ.get("SMTP_PORT", "465")), timeout=15) as server:
            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(SMTP_USER, EMAIL_TO.split(","), msg.as_string())
        logger.info(f"邮件推送成功 -> {EMAIL_TO}")
    except Exception as e:
        logger.error(f"邮件推送失败: {e}")


def main():
    logger.info("开始早盘结算...")
    settled = settle_pending_trades()
    stats = get_stats()
    logger.info(f"结算完成: {len(settled)}笔 | 累计{stats['total']}场 胜率{stats['win_rate']}%")

    message = build_settle_message(settled, stats)
    send_feishu(message)
    send_email(settled, stats)


if __name__ == "__main__":
    main()
