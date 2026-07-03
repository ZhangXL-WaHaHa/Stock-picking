# 改良版一夜持股法 - 自动选股器

基于 FastAPI 的 A 股自动选股工具，通过多维度量化指标在尾盘时段筛选潜力股，支持 Web 界面查看、定时任务、飞书/邮件自动推送。

## 筛选规则

| 序号 | 规则 | 条件 |
|------|------|------|
| 1 | 涨幅区间 | 2% ~ 6% |
| 2 | 量比 | > 1 |
| 3 | 换手率 | 5% ~ 10% |
| 4 | 流通市值 | 50亿 ~ 300亿 |
| 5 | 近期涨停 | 15 个交易日内有涨停记录 |
| 6 | 分时参考 | VWAP 偏离度 + 尾盘量能变化（半自动） |

**优先级评分**：流通市值越接近 150 亿，星级越高（1~5 星）。

筛选结果还会标注每只股票所属的**题材概念**（数据来源：东方财富）。

## 快速开始

```bash
# 安装依赖
pip install -r requirements.txt

# 启动服务
python main.py
```

浏览器打开 http://localhost:8000

## 功能说明

### Web 界面

- **立即筛选**：点击按钮手动触发全市场扫描
- **定时筛选**：在页面上配置周一至周五的自动执行时间，支持多个时间点
- **实时结果**：每次刷新页面自动加载最新筛选数据

### GitHub Actions 自动推送

通过 GitHub Actions 在交易日尾盘自动执行筛选，并将结果推送到飞书/邮箱。

**触发时间**：周一至周五 14:30、14:40、14:50（北京时间）

也支持在 GitHub Actions 页面手动触发（workflow_dispatch）。

## 推送配置

在 GitHub 仓库 **Settings > Secrets and variables > Actions** 中添加以下 Secrets。

飞书和邮箱**各自独立**，配了哪个就推哪个，都不配则只执行筛选不推送。

### 飞书机器人

| Secret | 说明 |
|--------|------|
| `FEISHU_WEBHOOK_URL` | 飞书自定义机器人的 Webhook 地址 |

获取方式：飞书群 > 设置 > 群机器人 > 添加自定义机器人 > 复制 Webhook 地址。

### 邮箱推送

| Secret | 说明 | 示例 |
|--------|------|------|
| `SMTP_HOST` | SMTP 服务器地址 | `smtp.qq.com` / `smtp.163.com` |
| `SMTP_PORT` | SMTP 端口（默认 465） | `465` |
| `SMTP_USER` | 发件邮箱 | `xxx@qq.com` |
| `SMTP_PASS` | 邮箱授权码（非登录密码） | QQ邮箱：设置 > 账户 > 生成授权码 |
| `EMAIL_TO` | 收件邮箱，多个用逗号分隔 | `a@xx.com,b@xx.com` |

## 项目结构

```
stock-screener/
├── main.py              # FastAPI 主服务，Web 界面 + 定时任务
├── screener.py          # 选股核心逻辑，串联各筛选规则
├── data_fetcher.py      # 行情数据获取（腾讯财经 + 东方财富）
├── models.py            # 数据模型定义
├── database.py          # SQLite 数据库操作
├── notify_feishu.py     # 筛选 + 飞书/邮件推送脚本
├── requirements.txt     # Python 依赖
├── templates/
│   └── index.html       # Web 页面模板
├── static/
│   └── style.css        # 样式文件
└── .github/
    └── workflows/
        └── stock-screen.yml  # GitHub Actions 工作流
```

## 数据来源

| 数据 | 来源 | 用途 |
|------|------|------|
| 实时行情 | 腾讯财经 | 价格、涨跌幅、量比、换手率、流通市值 |
| 历史 K 线 | 腾讯财经 | 判断近 15 日是否涨停 |
| 分时数据 | 腾讯财经 | VWAP 偏离度、尾盘量能分析 |
| 题材概念 | 东方财富 | 股票所属概念板块标签 |

## API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/` | Web 主页 |
| GET | `/api/screen` | 手动触发筛选，返回结果 |
| GET | `/api/latest` | 获取最近一次筛选结果（缓存） |
| GET | `/api/schedules` | 获取定时任务配置 |
| POST | `/api/schedules` | 更新定时任务配置 |

## 打赏支持

如果这个项目对你有帮助，欢迎请作者喝杯咖啡 :)

| 微信 | 支付宝 |
|:---:|:---:|
| <img src="static/1e9d13b16e2c520096243e2f38b754db_compress.jpg" width="200"> | <img src="static/05903b5e59f212d261700d101fc197c8_compress.jpg" width="200"> |
