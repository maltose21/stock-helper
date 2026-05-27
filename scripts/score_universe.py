#!/usr/bin/env python3
"""
score_universe.py - 读 universe_quotes.json，多维评分输出 TOP 30。

核心改进（v2）：
1. **动态主线识别**：不靠 recent.md 固定关键词，而是看今日全市场涨 >4% 的股
   按名称关键词聚类，找出"同板块 ≥ 5 只共涨" → 那就是今日主线
2. **主线龙头加分**：主线板块内按"成交额排名"加分（成交越大越是龙头）
3. **动量分修正**：涨 4-9% 主线龙头满分；只对涨停 (>9.5%) 扣分（已被资金锁定，次日很难进）
4. **TOP 30 分组**：主线龙头 20 + 价值股 10，下游 daily_advice 强制 6+4 配比

过滤硬条件：
- ST / 退市 → 出局
- 成交额 < 5000 万 → 出局
- 跌 < -9.5%（跌停）→ 出局
"""

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KB = ROOT / "knowledge_base"
UNIVERSE = KB / "universe_quotes.json"
RECENT = KB / "recent.md"
OUT = KB / "top30_candidates.json"

MIN_AMOUNT_YI = 0.5
GOOD_AMOUNT_YI = 5.0  # 5 亿为流动性满分

# 板块名称关键词聚类（用于动态主线识别）
# 注意：先匹配的优先（细→粗），避免"科技"误吞所有半导体股
SECTOR_KEYWORDS = {
    "半导体/芯片": ["半导体", "芯", "晶圆", "封测", "光电", "微电", "电子", "集成", "存储",
                  "君正", "华天", "扬杰", "士兰", "立昂", "三安", "华虹", "中芯",
                  "源杰", "国科微", "天岳", "沪硅", "新洁能", "三环", "风华", "水晶",
                  "天通", "沃格", "蓝思", "歌尔", "立讯", "舜宇", "兆易", "汇顶", "卓胜",
                  "韦尔", "斯达", "捷捷", "长电", "通富", "甬矽", "至纯", "盛美", "拓荆",
                  "北方华创", "中微", "鼎龙", "雅克"],
    "光模块/通信": ["光模块", "通信", "光通", "光迅", "光纤", "无线", "网络设备", "新易盛",
                  "中际旭创", "天孚", "永鼎", "亨通"],
    "AI算力": ["算力", "AI", "GPU", "云计算", "数据中心", "服务器", "工业富联", "浪潮", "中科曙光",
              "海光", "寒武纪", "云路"],
    "机器人": ["机器人", "宇树", "灵巧", "减速器", "谐波", "绿的", "拓斯达"],
    "新能源车": ["比亚迪", "理想", "蔚来", "小鹏", "长城汽车", "吉利", "广汽", "极氪",
                "宁德时代", "亿纬", "国轩", "孚能", "整车"],
    "新能源/光伏": ["光伏", "储能", "风电", "锦浪", "阳光电源", "隆基", "通威", "TCL中环",
                  "天合", "晶科", "晶澳"],
    "电力/能源": ["电力", "发电", "热电", "电网", "核电", "水电", "大唐", "京能", "国电"],
    "军工": ["航天", "航空", "电科", "兵器", "国防", "中航", "光启"],
    "医药/生物": ["医药", "生物", "制药", "疫苗", "药业", "药明", "恒瑞", "百济"],
    "金融": ["银行", "证券", "保险", "财险"],
    "煤炭": ["煤业", "煤炭", "焦煤", "兖矿", "神华", "陕西煤业", "中煤"],
    "白酒/消费": ["白酒", "茅台", "五粮液", "泸州", "酒鬼", "金徽", "金种子", "山西汾酒",
                "古井", "海底捞", "海天", "蒙牛", "伊利"],
    "高分红/水电": ["长江电力", "高速", "公路", "港口"],
    "互联网/平台": ["腾讯", "阿里", "美团", "京东", "百度", "快手", "携程", "哔哩", "网易",
                  "拼多多", "微博"],
}


def classify_sector(name: str) -> str:
    """按名称关键词归类。"""
    for sector, kws in SECTOR_KEYWORDS.items():
        if any(kw in name for kw in kws):
            return sector
    return "其他"


def detect_main_lines(quotes: list) -> dict[str, dict]:
    """
    动态识别今日主线：扫所有涨 > 4% 且成交 > 1 亿的股，按板块聚类，
    返回 {sector: {"members": [...], "total_amount": X, "is_main_line": True}}
    is_main_line=True 的条件：成员数 ≥ 5
    """
    strong = [q for q in quotes
              if q.get("change_pct", 0) > 4
              and q.get("amount", 0) > 1e8
              and "ST" not in q.get("name", "")
              and "退" not in q.get("name", "")]
    by_sector = defaultdict(list)
    for q in strong:
        sec = classify_sector(q.get("name", ""))
        if sec == "其他":
            continue  # 未归类不参与主线识别
        by_sector[sec].append(q)
    result = {}
    for sec, members in by_sector.items():
        members.sort(key=lambda q: -q.get("amount", 0))
        result[sec] = {
            "members": members,
            "count": len(members),
            "total_amount": sum(q.get("amount", 0) for q in members),
            "is_main_line": len(members) >= 5,
        }
    return result


def extract_blacklist(recent_md: str) -> set[str]:
    blacklist: set[str] = set()
    for pat in [r"回避\s*([一-龥]{2,8})", r"踩雷\s*([一-龥]{2,8})",
                r"清仓\s*([一-龥]{2,8})", r"处罚.*?([一-龥]{2,8})"]:
        for m in re.finditer(pat, recent_md):
            blacklist.add(m.group(1))
    return blacklist


def score_main_line(q: dict, main_lines: dict, leader_rank: dict) -> dict:
    """主线龙头评分。"""
    name = q.get("name", "")
    sector = classify_sector(name)
    sector_data = main_lines.get(sector, {})

    # 流动性 0-25
    amount_yi = q.get("amount", 0) / 1e8
    liq = min(25, (amount_yi / GOOD_AMOUNT_YI) * 25)

    # 主线匹配 0-30（高于价值股的板块分上限，给予主线优势）
    if sector_data.get("is_main_line"):
        # 是主线板块；龙头加分
        rank = leader_rank.get(q["code"], 999)
        if rank <= 3:
            sector_score = 30
        elif rank <= 8:
            sector_score = 25
        else:
            sector_score = 18
    else:
        sector_score = 5  # 不是主线，主线评分系统下扣分

    # 动量 0-25
    pct = q.get("change_pct", 0)
    if pct > 9.5:
        momentum = 12  # 涨停，资金已锁，次日难追
    elif pct >= 6:
        momentum = 25  # 主线龙头标志
    elif pct >= 4:
        momentum = 22
    elif pct >= 2:
        momentum = 17
    elif pct >= 0:
        momentum = 10
    elif pct >= -3:
        momentum = 5
    else:
        momentum = 0

    # 安全（主线模式下权重低）0-20
    safety = 10
    h52, l52, cur = q.get("high_52w"), q.get("low_52w"), q.get("current", 0)
    if h52 and l52 and cur > 0:
        pos = (cur - l52) / max(h52 - l52, 0.01) * 100
        if pos < 50: safety = 15
        elif pos < 80: safety = 12
        else: safety = 8
    pe = q.get("pe")
    if pe is not None and pe < 0:
        safety = min(safety, 3)

    total = round(liq + sector_score + momentum + safety, 1)
    return {
        "score": total,
        "sector_class": sector,
        "is_main_line": sector_data.get("is_main_line", False),
        "score_detail": {
            "liquidity": round(liq, 1),
            "sector": round(sector_score, 1),
            "momentum": momentum,
            "safety": safety,
        },
        "score_type": "main_line",
    }


def score_value(q: dict, hot_value_sectors: dict[str, float]) -> dict:
    """价值股评分（高分红/低估值/防守）。"""
    name = q.get("name", "")

    # 流动性 0-25
    amount_yi = q.get("amount", 0) / 1e8
    liq = min(25, (amount_yi / GOOD_AMOUNT_YI) * 25)

    # 板块匹配 0-25（价值蓝筹白名单）
    value_anchors = {"招商银行","建设银行","工商银行","农业银行","中国银行",
                     "长江电力","中国神华","陕西煤业","宁沪高速",
                     "美的集团","贵州茅台","五粮液","中国平安","友邦保险",
                     "中国石油","中国石化","中海油","兖矿能源",
                     "腾讯控股","阿里巴巴","京东集团","美团"}
    if any(a in name for a in value_anchors):
        sector_score = 25
    elif "银行" in name or "保险" in name:
        sector_score = 20
    elif "电力" in name or "高速" in name or "煤" in name:
        sector_score = 18
    else:
        sector_score = 5  # 非价值蓝筹严重扣分

    # 动量 0-25（价值股不要太热）
    pct = q.get("change_pct", 0)
    if -2 <= pct <= 3:
        momentum = 25  # 横盘到温和上涨最理想
    elif -5 <= pct < -2:
        momentum = 22  # 小跌反而是机会
    elif pct < -5:
        momentum = 15
    elif 3 < pct <= 6:
        momentum = 18
    else:
        momentum = 8

    # 安全 0-25
    safety = 12
    h52, l52, cur = q.get("high_52w"), q.get("low_52w"), q.get("current", 0)
    if h52 and l52 and cur > 0:
        pos = (cur - l52) / max(h52 - l52, 0.01) * 100
        if pos < 30: safety = 25
        elif pos < 60: safety = 18
        elif pos < 85: safety = 12
        else: safety = 5
    pe = q.get("pe")
    if pe is not None:
        if pe < 0: safety = min(safety, 3)
        elif pe < 12: safety = min(25, safety + 5)

    total = round(liq + sector_score + momentum + safety, 1)
    return {
        "score": total,
        "sector_class": classify_sector(name),
        "score_detail": {
            "liquidity": round(liq, 1),
            "sector": round(sector_score, 1),
            "momentum": momentum,
            "safety": safety,
        },
        "score_type": "value",
    }


def main() -> int:
    if not UNIVERSE.exists():
        print(f"❌ 缺少 {UNIVERSE}", file=sys.stderr)
        return 1

    universe = json.loads(UNIVERSE.read_text(encoding="utf-8"))
    quotes = universe.get("quotes", [])
    recent_md = RECENT.read_text(encoding="utf-8") if RECENT.exists() else ""

    print(f"📥 候选: {len(quotes)} 只", file=sys.stderr)

    # 1. 动态识别今日主线
    main_lines = detect_main_lines(quotes)
    main_line_sectors = [s for s, d in main_lines.items() if d["is_main_line"]]
    if main_line_sectors:
        ml_summary = ", ".join(f"{s}({main_lines[s]['count']}只)" for s in main_line_sectors)
    else:
        ml_summary = "(无明显主线)"
    print(f"🔥 今日主线: {ml_summary}", file=sys.stderr)
    for s in main_line_sectors:
        d = main_lines[s]
        print(f"   {s}: {d['count']} 只共涨, 板块成交 {d['total_amount']/1e8:.0f} 亿", file=sys.stderr)

    # 2. 计算主线内龙头排名（按成交额）
    leader_rank: dict[str, int] = {}
    for sec in main_line_sectors:
        for i, m in enumerate(main_lines[sec]["members"], 1):
            leader_rank[m["code"]] = i

    # 3. 黑名单
    blacklist = extract_blacklist(recent_md)
    print(f"🚫 黑名单: {blacklist or '(无)'}", file=sys.stderr)

    # 4. 通用过滤
    filtered = []
    for q in quotes:
        name = q.get("name", "")
        if any(tag in name for tag in ("ST", "*ST", "退", "PT")): continue
        if name in blacklist or any(b in name for b in blacklist): continue
        amount_yi = q.get("amount", 0) / 1e8
        if amount_yi < MIN_AMOUNT_YI: continue
        if q.get("change_pct", 0) < -9.5: continue
        filtered.append(q)

    # 5. 双轨评分
    main_line_scored = []
    value_scored = []
    for q in filtered:
        name = q.get("name", "")
        sector = classify_sector(name)
        # 主线候选：在今日主线板块里 且 涨 > 0
        if main_lines.get(sector, {}).get("is_main_line") and q.get("change_pct", 0) > 0:
            r = score_main_line(q, main_lines, leader_rank)
            main_line_scored.append({**q, **r})
        # 价值候选：所有股都参与价值评分
        r2 = score_value(q, {})
        value_scored.append({**q, **r2})

    main_line_scored.sort(key=lambda s: -s["score"])
    value_scored.sort(key=lambda s: -s["score"])

    # 6. TOP 30 = 主线 20 + 价值 10（去重）
    top_main = main_line_scored[:20]
    main_codes = {s["code"] for s in top_main}
    top_value = [s for s in value_scored if s["code"] not in main_codes][:10]

    print(f"\n✅ 主线 TOP 20 (score 区间 [{top_main[-1]['score']:.1f} ~ {top_main[0]['score']:.1f}])：", file=sys.stderr)
    for i, s in enumerate(top_main, 1):
        d = s["score_detail"]
        print(f"  {i:2d}. {s.get('name','?'):12s} ({s['code']:12s}) "
              f"score={s['score']:5.1f} [{s['sector_class']:10s}] "
              f"涨{s.get('change_pct',0):+5.2f}% 额{s.get('amount',0)/1e8:5.1f}亿", file=sys.stderr)

    print(f"\n✅ 价值 TOP 10：", file=sys.stderr)
    for i, s in enumerate(top_value, 1):
        d = s["score_detail"]
        print(f"  {i:2d}. {s.get('name','?'):12s} ({s['code']:12s}) "
              f"score={s['score']:5.1f} "
              f"涨{s.get('change_pct',0):+5.2f}% 额{s.get('amount',0)/1e8:5.1f}亿", file=sys.stderr)

    output = {
        "scored_at": universe["fetched_at"],
        "universe_size": len(quotes),
        "main_line_sectors": main_line_sectors,
        "main_line_detail": {s: {"count": main_lines[s]["count"],
                                  "total_amount_yi": round(main_lines[s]["total_amount"]/1e8, 1)}
                              for s in main_line_sectors},
        "blacklist": list(blacklist),
        "top_main_line": top_main,
        "top_value": top_value,
    }
    OUT.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n💾 写入 {OUT}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
