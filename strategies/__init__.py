from strategies import overnight, ma_pullback, rps_breakout, low_first_zt

STRATEGIES = {
    "overnight": {
        "name": "一夜持股法",
        "desc": "尾盘买入、次日开盘卖出",
        "fn": overnight.screen,
        "columns": [
            {"key": "priority_score", "label": "优先级", "type": "stars"},
            {"key": "code", "label": "代码"},
            {"key": "name", "label": "名称"},
            {"key": "price", "label": "最新价"},
            {"key": "change_pct", "label": "涨跌幅%", "suffix": "%", "color": "red"},
            {"key": "volume_ratio", "label": "量比"},
            {"key": "turnover_rate", "label": "换手率%", "suffix": "%"},
            {"key": "market_cap_yi", "label": "流通市值(亿)"},
            {"key": "close_position", "label": "收盘位", "format": "percent"},
            {"key": "vwap_info", "label": "VWAP参考", "class": "ref-info"},
            {"key": "late_volume_info", "label": "尾盘量能", "class": "ref-info"},
            {"key": "themes", "label": "题材概念", "type": "themes"},
        ],
        "rules": [
            {"num": "0", "title": "大盘环境", "desc": "上证跌超0.5%时不出信号"},
            {"num": "1", "title": "涨跌幅 2-6%", "desc": "适中涨幅，有动能不追高"},
            {"num": "2", "title": "量比 > 1", "desc": "成交量高于近期均值"},
            {"num": "3", "title": "换手率 5-10%", "desc": "筹码交换活跃"},
            {"num": "4", "title": "流通市值 50-300亿", "desc": "中盘股弹性好"},
            {"num": "5", "title": "收盘价上半区", "desc": "排除冲高回落"},
            {"num": "6", "title": "涨停+缩量回调", "desc": "主力控盘信号"},
            {"num": "7", "title": "VWAP/尾盘信号", "desc": "全天走势健康"},
        ],
    },
    "ma_pullback": {
        "name": "均线回踩",
        "desc": "均线多头排列、缩量回踩MA10后企稳反弹",
        "fn": ma_pullback.screen,
        "columns": [
            {"key": "priority_score", "label": "优先级", "type": "stars"},
            {"key": "code", "label": "代码"},
            {"key": "name", "label": "名称"},
            {"key": "price", "label": "最新价"},
            {"key": "change_pct", "label": "涨跌幅%", "suffix": "%", "color": "red"},
            {"key": "volume_ratio", "label": "量比"},
            {"key": "turnover_rate", "label": "换手率%", "suffix": "%"},
            {"key": "market_cap_yi", "label": "流通市值(亿)"},
            {"key": "ma5", "label": "MA5"},
            {"key": "ma10", "label": "MA10"},
            {"key": "ma20", "label": "MA20"},
            {"key": "vol_shrink", "label": "缩量%", "suffix": "%"},
        ],
        "rules": [
            {"num": "0", "title": "大盘环境", "desc": "上证跌超0.5%时不出信号"},
            {"num": "1", "title": "MA5 > MA10 > MA20", "desc": "均线多头排列，趋势向上"},
            {"num": "2", "title": "回踩MA10", "desc": "收盘价距MA10在2%以内"},
            {"num": "3", "title": "缩量", "desc": "近3日均量<前10日均量的70%"},
            {"num": "4", "title": "企稳反弹", "desc": "当日收盘 > 前日收盘"},
        ],
    },
    "rps_breakout": {
        "name": "RPS强势突破",
        "desc": "相对强度排名前10%，横盘整理后突破新高",
        "fn": rps_breakout.screen,
        "columns": [
            {"key": "priority_score", "label": "优先级", "type": "stars"},
            {"key": "code", "label": "代码"},
            {"key": "name", "label": "名称"},
            {"key": "price", "label": "最新价"},
            {"key": "change_pct", "label": "涨跌幅%", "suffix": "%", "color": "red"},
            {"key": "volume_ratio", "label": "量比"},
            {"key": "market_cap_yi", "label": "流通市值(亿)"},
            {"key": "rps", "label": "RPS值"},
            {"key": "gain_60d", "label": "60日涨幅%", "suffix": "%"},
            {"key": "range_10d", "label": "10日振幅%", "suffix": "%"},
        ],
        "rules": [
            {"num": "0", "title": "大盘环境", "desc": "上证跌超0.5%时不出信号"},
            {"num": "1", "title": "RPS >= 90", "desc": "60日涨幅排名全市场前10%"},
            {"num": "2", "title": "创20日新高", "desc": "收盘价突破近20日最高价"},
            {"num": "3", "title": "10日振幅<10%", "desc": "突破前处于横盘整理状态"},
            {"num": "4", "title": "流通市值 30-500亿", "desc": "排除微小盘和超大盘"},
        ],
    },
    "low_first_zt": {
        "name": "低位首板",
        "desc": "低位首次涨停，等待缩量回调后介入",
        "fn": low_first_zt.screen,
        "columns": [
            {"key": "priority_score", "label": "优先级", "type": "stars"},
            {"key": "code", "label": "代码"},
            {"key": "name", "label": "名称"},
            {"key": "price", "label": "最新价"},
            {"key": "change_pct", "label": "涨跌幅%", "suffix": "%", "color": "red"},
            {"key": "volume_ratio", "label": "量比"},
            {"key": "market_cap_yi", "label": "流通市值(亿)"},
            {"key": "drop_from_high", "label": "距高点%", "suffix": "%"},
            {"key": "zt_vol_ratio", "label": "涨停量比"},
            {"key": "status", "label": "状态"},
        ],
        "rules": [
            {"num": "1", "title": "当日涨停", "desc": "涨幅>=9.8%"},
            {"num": "2", "title": "低位", "desc": "距60日最高点跌幅>30%"},
            {"num": "3", "title": "首次", "desc": "近60日内无其他涨停记录"},
            {"num": "4", "title": "流通市值 30-300亿", "desc": "排除微小盘和大盘"},
        ],
    },
}


def get_strategy_list():
    return [
        {"id": k, "name": v["name"], "desc": v["desc"], "rules": v["rules"], "columns": v["columns"]}
        for k, v in STRATEGIES.items()
    ]
