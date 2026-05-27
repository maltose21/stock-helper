#!/usr/bin/env python3
"""
score_universe.py - 读 universe_quotes.json，按多维度打分，输出 TOP 30 候选给 daily_advice。

评分维度（每项 0-25 分，满分 100）：
1. 流动性 / 体量：成交额 ≥ 1 亿入门，3 亿满分（避免低流动性陷阱）
2. 主线匹配：recent.md / evergreen.md 热点板块关键词命中（名称匹配 + sector）
3. 资金动能：当日涨幅 + 成交额排名分位（避免追涨过头：涨 > 7% 扣分）
4. 安全边际：港股看 PE / 距 52w 高低；A 股看是否接近年线（用 high/low 估算）

过滤硬条件：
- 名称含 "ST" / "*ST" / "退" → 出局
- 成交额 < 5000 万 → 出局
- 当日涨幅 < -9.5% 跌停 → 出局
- 港股 PE < 0 → 持有但降低优先级
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KB = ROOT / "knowledge_base"
UNIVERSE = KB / "universe_quotes.json"
RECENT = KB / "recent.md"
EVERGREEN = KB / "evergreen.md"
OUT = KB / "top30_candidates.json"

MIN_AMOUNT_YI = 0.5  # 5000 万
GOOD_AMOUNT_YI = 3.0  # 3 亿满分
TOP_N = 30


def extract_hot_sectors(recent_md: str, evergreen_md: str) -> dict[str, float]:
    """从 recent.md + evergreen.md 抽取热点板块/关键词，赋权重。"""
    weights: dict[str, float] = {}

    # 永恒推荐板块（来自 evergreen.md 的方法论）
    evergreen_anchors = {
        "银行": 0.8, "煤炭": 0.8, "水电": 0.8, "高速": 0.7, "家电": 0.7,
        "白酒": 0.6, "保险": 0.7, "石油": 0.6,
    }
    weights.update(evergreen_anchors)

    # recent.md 的高频提及板块（出现频率越高权重越高）
    text = recent_md.lower()
    sectors_check = {
        "互联网": ["互联网", "腾讯", "阿里", "美团", "京东", "百度", "快手", "b站", "哔哩"],
        "半导体": ["半导体", "芯片", "中芯", "寒武纪", "海光"],
        "算力": ["算力", "光模块", "ai"],
        "新能源车": ["新能源车", "比亚迪", "理想", "蔚来", "小鹏"],
        "新能源": ["新能源", "宁德"],
        "存储": ["存储", "长鑫", "兆易"],
        "机器人": ["机器人", "宇树"],
        "面板": ["面板", "京东方"],
        "猪周期": ["猪周期", "牧原"],
    }
    for sector, kws in sectors_check.items():
        hits = sum(text.count(kw) for kw in kws)
        if hits >= 3:
            weights[sector] = max(weights.get(sector, 0), min(1.0, hits / 10))
        elif hits >= 1:
            weights[sector] = max(weights.get(sector, 0), 0.4)

    return weights


def extract_blacklist(recent_md: str) -> set[str]:
    """从 recent.md 找 '回避 / 危险 / 处罚' 类关键词命中的股票名。"""
    blacklist: set[str] = set()
    # 简单规则：找 "回避 X" / "处罚 X" / "踩雷 X" 这种短语后面的中文名
    for pat in [r"回避\s*([一-龥]{2,8})", r"踩雷\s*([一-龥]{2,8})",
                r"清仓\s*([一-龥]{2,8})", r"处罚.*?([一-龥]{2,8})"]:
        for m in re.finditer(pat, recent_md):
            blacklist.add(m.group(1))
    return blacklist


def score_one(q: dict, hot: dict[str, float], blacklist: set[str]) -> dict:
    """对单只股票打分。"""
    name = q.get("name", "")
    if any(tag in name for tag in ("ST", "*ST", "退", "PT")):
        return {**q, "score": -1, "drop_reason": "ST/退市"}
    if name in blacklist or any(b in name for b in blacklist):
        return {**q, "score": -1, "drop_reason": "黑名单"}

    amount_yi = q.get("amount", 0) / 1e8
    if amount_yi < MIN_AMOUNT_YI:
        return {**q, "score": -1, "drop_reason": f"成交额过低 {amount_yi:.2f}亿"}

    change_pct = q.get("change_pct", 0)
    if change_pct < -9.5:
        return {**q, "score": -1, "drop_reason": "跌停"}

    # 1) 流动性 0-25
    liq_score = min(25, (amount_yi / GOOD_AMOUNT_YI) * 25)

    # 2) 主线匹配 0-25
    sector_score = 0.0
    sector = q.get("sector", "")
    if sector in hot:
        sector_score = hot[sector] * 25
    # 名称命中（个股直接被 recent 频繁点名的）
    name_kws = ["腾讯", "阿里", "美团", "京东", "百度", "招商银行", "中国神华",
                "长江电力", "美的", "茅台", "比亚迪", "理想", "宁德", "寒武纪",
                "中芯", "京东方", "牧原", "海光"]
    if any(kw in name for kw in name_kws):
        sector_score = max(sector_score, 18)

    # 3) 资金动能 0-25
    if change_pct > 7:
        momentum = 5  # 追高扣分
    elif change_pct > 3:
        momentum = 22
    elif change_pct > 0:
        momentum = 20
    elif change_pct > -3:
        momentum = 15
    elif change_pct > -7:
        momentum = 8
    else:
        momentum = 3

    # 4) 安全边际 0-25
    safety = 12  # 基础分
    high_52w = q.get("high_52w")
    low_52w = q.get("low_52w")
    current = q.get("current", 0)
    if high_52w and low_52w and current > 0:
        # 距 52 周高低位置百分位（0=最低, 100=最高）
        pos = (current - low_52w) / max(high_52w - low_52w, 0.01) * 100
        if pos < 30:
            safety = 25  # 左侧机会
        elif pos < 60:
            safety = 18
        elif pos < 85:
            safety = 10
        else:
            safety = 3  # 接近 52 周高，不安全

    pe = q.get("pe")
    if pe is not None:
        if pe < 0:
            safety = min(safety, 5)
        elif pe < 12:
            safety = min(25, safety + 5)

    total = round(liq_score + sector_score + momentum + safety, 1)

    return {
        **q,
        "score": total,
        "score_detail": {
            "liquidity": round(liq_score, 1),
            "sector": round(sector_score, 1),
            "momentum": momentum,
            "safety": safety,
        },
    }


def main() -> int:
    if not UNIVERSE.exists():
        print(f"❌ 缺少 {UNIVERSE}，先跑 fetch_universe.py", file=sys.stderr)
        return 1

    universe = json.loads(UNIVERSE.read_text(encoding="utf-8"))
    quotes = universe.get("quotes", [])
    print(f"📥 候选: {len(quotes)} 只", file=sys.stderr)

    recent_md = RECENT.read_text(encoding="utf-8") if RECENT.exists() else ""
    evergreen_md = EVERGREEN.read_text(encoding="utf-8") if EVERGREEN.exists() else ""

    hot = extract_hot_sectors(recent_md, evergreen_md)
    blacklist = extract_blacklist(recent_md)
    print(f"🔥 热点板块: {dict(sorted(hot.items(), key=lambda x: -x[1])[:8])}", file=sys.stderr)
    print(f"🚫 黑名单: {blacklist or '(无)'}", file=sys.stderr)

    scored = [score_one(q, hot, blacklist) for q in quotes]
    valid = [s for s in scored if s["score"] >= 0]
    valid.sort(key=lambda s: -s["score"])
    top = valid[:TOP_N]

    n_drop = len(scored) - len(valid)
    print(f"✅ 评分完成: {len(valid)} 只入围, {n_drop} 只剔除, TOP{TOP_N} score 区间 [{top[-1]['score']:.1f} ~ {top[0]['score']:.1f}]",
          file=sys.stderr)

    output = {
        "scored_at": universe["fetched_at"],
        "universe_size": len(quotes),
        "valid_count": len(valid),
        "hot_sectors": hot,
        "blacklist": list(blacklist),
        "top": top,
    }
    OUT.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"💾 写入 {OUT}", file=sys.stderr)

    # 控制台打印 TOP 30 摘要
    print("\n📊 TOP 30：", file=sys.stderr)
    for i, s in enumerate(top, 1):
        d = s["score_detail"]
        print(f"  {i:2d}. {s.get('name', '?'):8s} ({s['code']:12s}) "
              f"score={s['score']:5.1f}  L{d['liquidity']:.0f}+S{d['sector']:.0f}+M{d['momentum']}+Sa{d['safety']}  "
              f"现价 {s.get('current', 0):8.2f}  涨{s.get('change_pct', 0):+5.2f}%  "
              f"额{s.get('amount', 0)/1e8:.1f}亿",
              file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
