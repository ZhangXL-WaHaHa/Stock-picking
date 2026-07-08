import logging
import os
import json
from datetime import datetime
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from apscheduler.schedulers.background import BackgroundScheduler

from database import init_db
from screener import screen_stocks
from strategies import get_strategy_list, STRATEGIES
from trade_tracker import get_stats, get_recent_trades, get_pending_trades, add_pending_trades
from notify_feishu import build_message, send_to_feishu, send_email

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler()
SCHEDULE_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "schedule_config.json")
DEFAULT_SCHEDULES = [{"hour": 14, "minute": 50, "enabled": True}]

latest_results = {}


def load_schedule_config():
    if os.path.exists(SCHEDULE_CONFIG_PATH):
        with open(SCHEDULE_CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return DEFAULT_SCHEDULES


def save_schedule_config(schedules):
    with open(SCHEDULE_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(schedules, f, ensure_ascii=False)


def _update_latest(strategy, results):
    latest_results[strategy] = {
        "screen_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total_found": len(results),
        "results": results,
    }


def scheduled_screen():
    logger.info("定时任务触发：执行筛选...")
    try:
        results = screen_stocks("overnight")
        _update_latest("overnight", results)
        stats = get_stats()
        message = build_message(results, stats)
        send_to_feishu(message)
        send_email(results, stats)
        add_pending_trades(results)
        if results:
            logger.info(f"定时筛选完成，找到 {len(results)} 只，已推送通知")
        else:
            logger.info("定时筛选完成，未找到符合条件的股票，已推送通知")
    except Exception as e:
        logger.error(f"定时筛选异常: {e}")


def apply_schedules(schedules):
    existing = scheduler.get_jobs()
    for job in existing:
        if job.id.startswith("daily_screen_"):
            scheduler.remove_job(job.id)

    for i, s in enumerate(schedules):
        if s.get("enabled", True):
            scheduler.add_job(
                scheduled_screen,
                "cron",
                day_of_week="mon-fri",
                hour=s["hour"],
                minute=s["minute"],
                id=f"daily_screen_{i}",
                replace_existing=True,
            )
            logger.info(f"定时任务已设置：周一至周五 {s['hour']:02d}:{s['minute']:02d}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    schedules = load_schedule_config()
    apply_schedules(schedules)
    scheduler.start()
    yield
    scheduler.shutdown()


app = FastAPI(title="股票筛选器", lifespan=lifespan)

BASE_DIR = os.path.dirname(__file__)
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    schedules = load_schedule_config()
    return templates.TemplateResponse("index.html", {
        "request": request,
        "schedules": schedules,
    })


@app.get("/api/strategies")
async def api_strategies():
    return JSONResponse(get_strategy_list())


@app.get("/api/screen")
async def api_screen(strategy: str = Query("overnight")):
    if strategy not in STRATEGIES:
        return JSONResponse({"success": False, "message": f"未知策略: {strategy}"}, status_code=400)
    try:
        results = screen_stocks(strategy)
        _update_latest(strategy, results)
        return JSONResponse({"success": True, **latest_results[strategy]})
    except Exception as e:
        logger.error(f"筛选失败: {e}")
        return JSONResponse({"success": False, "message": str(e)}, status_code=500)


@app.get("/api/latest")
async def api_latest(strategy: str = Query("overnight")):
    data = latest_results.get(strategy, {"screen_time": None, "total_found": 0, "results": []})
    return JSONResponse(data)


@app.get("/api/winrate")
async def api_winrate():
    stats = get_stats()
    trades = get_recent_trades(20)
    pending = get_pending_trades()
    return JSONResponse({"stats": stats, "recent_trades": trades, "pending_trades": pending})


@app.get("/api/schedules")
async def api_get_schedules():
    return JSONResponse(load_schedule_config())


@app.post("/api/schedules")
async def api_set_schedules(request: Request):
    try:
        schedules = await request.json()
        for s in schedules:
            h, m = int(s["hour"]), int(s["minute"])
            if not (0 <= h <= 23 and 0 <= m <= 59):
                return JSONResponse({"success": False, "message": "时间格式不正确"}, status_code=400)
        save_schedule_config(schedules)
        apply_schedules(schedules)
        return JSONResponse({"success": True, "schedules": schedules})
    except Exception as e:
        return JSONResponse({"success": False, "message": str(e)}, status_code=400)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
