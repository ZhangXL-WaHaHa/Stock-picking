from pydantic import BaseModel
from datetime import datetime
from typing import List


class StockResult(BaseModel):
    code: str
    name: str
    price: float
    change_pct: float
    volume_ratio: float
    turnover_rate: float
    market_cap_yi: float  # 流通市值（亿元）
    priority_score: int   # 1-5 星
    has_zt_15d: bool
    vwap_info: str        # VWAP偏离参考信息
    late_volume_info: str # 尾盘量能参考信息

    def to_dict(self) -> dict:
        return self.model_dump()


class ScreeningResponse(BaseModel):
    success: bool
    screen_time: str
    total_found: int
    results: List[StockResult]
    message: str = ""
