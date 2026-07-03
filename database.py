import sqlite3
import json
import os
from datetime import datetime
from typing import Optional, List, Dict

DB_PATH = os.path.join(os.path.dirname(__file__), "screening.db")


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS screening_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            screen_date TEXT NOT NULL,
            screen_time TEXT NOT NULL,
            results_json TEXT NOT NULL,
            total_found INTEGER NOT NULL
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_screen_date
        ON screening_records(screen_date)
    """)
    conn.commit()
    conn.close()


def save_screening_result(results: List[dict]) -> int:
    conn = get_connection()
    now = datetime.now()
    cursor = conn.execute(
        "INSERT INTO screening_records (screen_date, screen_time, results_json, total_found) VALUES (?, ?, ?, ?)",
        (now.strftime("%Y-%m-%d"), now.strftime("%Y-%m-%d %H:%M:%S"), json.dumps(results, ensure_ascii=False), len(results)),
    )
    conn.commit()
    record_id = cursor.lastrowid
    conn.close()
    return record_id


def get_history_dates() -> List[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, screen_date, screen_time, total_found FROM screening_records ORDER BY id DESC LIMIT 60"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_record_by_id(record_id: int) -> Optional[dict]:
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM screening_records WHERE id = ?", (record_id,)
    ).fetchone()
    conn.close()
    if row is None:
        return None
    record = dict(row)
    record["results"] = json.loads(record["results_json"])
    return record


def get_latest_record() -> Optional[dict]:
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM screening_records ORDER BY id DESC LIMIT 1"
    ).fetchone()
    conn.close()
    if row is None:
        return None
    record = dict(row)
    record["results"] = json.loads(record["results_json"])
    return record
