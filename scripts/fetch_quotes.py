#!/usr/bin/env python3
"""
fetch_quotes.py - 拉取候选股票池的实时/收盘行情（新浪 hq.sinajs.cn 免费接口）。

A 股字段 (0=name, 1=open, 2=prevclose, 3=current, 4=high, 5=low, 8=volume, 9=amount, 30=date, 31=time)
港股字段 (0=symbol, 1=name, 2=open, 3=prevclose, 4=high, 5=low, 6=current, 7=change, 8=changePct, 9=bid, 10=ask, 11=amount, 12=volume, 13=PE, 14=yield, 15=high52w, 16=low52w, 17=date, 18=time)

输出 JSON 到 stdout，daily_advice.py 消费。
"""

import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WATCHLIST = ROOT / "scripts" / "watchlist.yaml"
SINA_BASE = "https://hq.sinajs.cn/list="
HEADERS = {"Referer": "https://finance.sina.com.cn", "User-Agent": "Mozilla/5.0"}


def parse_watchlist() -> list[dict]:
    text = WATCHLIST.read_text(encoding="utf-8")
    stocks = []
    # 提取 `- {code: ..., name: ..., sector: ..., type: ...}` 形式
    pat = re.compile(
        r"-\s*\{code:\s*(\S+?),\s*name:\s*(\S+?),\s*sector:\s*(\S+?),\s*type:\s*(\S+?)\s*\}"
    )
    for m in pat.finditer(text):
        stocks.append({"code": m.group(1), "name": m.group(2), "sector": m.group(3), "type": m.group(4)})
    return stocks


def fetch_batch(codes: list[str]) -> dict[str, list[str]]:
    """一次拉一批，新浪允许 ~80 个/次，我们 30 个一次就 OK。"""
    url = SINA_BASE + ",".join(codes)
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read().decode("gbk", errors="replace")
    except (urllib.error.URLError, TimeoutError) as e:
        print(f"❌ fetch error: {e}", file=sys.stderr)
        return {}

    result = {}
    for line in raw.splitlines():
        m = re.match(r'var hq_str_(\S+)="(.*)";', line)
        if not m:
            continue
        code, body = m.group(1), m.group(2)
        if not body:  # empty = invalid code or no data
            continue
        result[code] = body.split(",")
    return result


def parse_a_stock(fields: list[str]) -> dict:
    """A 股字段映射"""
    try:
        return {
            "name": fields[0],
            "open": float(fields[1]),
            "prev_close": float(fields[2]),
            "current": float(fields[3]),
            "high": float(fields[4]),
            "low": float(fields[5]),
            "volume": int(fields[8]) if fields[8] else 0,
            "amount": float(fields[9]) if fields[9] else 0,
            "date": fields[30] if len(fields) > 30 else "?",
            "time": fields[31] if len(fields) > 31 else "?",
        }
    except (ValueError, IndexError) as e:
        return {"error": f"parse_a_stock failed: {e}"}


def parse_hk_stock(fields: list[str]) -> dict:
    """港股字段映射（含 52 周高低）"""
    try:
        return {
            "symbol": fields[0],
            "name": fields[1],
            "open": float(fields[2]),
            "prev_close": float(fields[3]),
            "high": float(fields[4]),
            "low": float(fields[5]),
            "current": float(fields[6]),
            "change": float(fields[7]) if fields[7] else 0,
            "change_pct": float(fields[8]) if fields[8] else 0,
            "amount": float(fields[11]) if fields[11] else 0,
            "volume": int(fields[12]) if fields[12] else 0,
            "pe": float(fields[13]) if fields[13] and fields[13] != "0.000" else None,
            "high_52w": float(fields[15]) if fields[15] else None,
            "low_52w": float(fields[16]) if fields[16] else None,
            "date": fields[17] if len(fields) > 17 else "?",
            "time": fields[18] if len(fields) > 18 else "?",
        }
    except (ValueError, IndexError) as e:
        return {"error": f"parse_hk_stock failed: {e}"}


def enrich(quote: dict) -> dict:
    """加派生指标：涨跌幅、距 52 周高/低 %。"""
    if "error" in quote:
        return quote
    current = quote.get("current", 0)
    prev = quote.get("prev_close", 0)
    if prev > 0 and "change_pct" not in quote:
        quote["change_pct"] = round((current - prev) / prev * 100, 2)
    high52 = quote.get("high_52w")
    low52 = quote.get("low_52w")
    if current > 0:
        if high52 and high52 > 0:
            quote["pct_from_52w_high"] = round((current - high52) / high52 * 100, 2)
        if low52 and low52 > 0:
            quote["pct_from_52w_low"] = round((current - low52) / low52 * 100, 2)
    return quote


def main() -> int:
    stocks = parse_watchlist()
    if not stocks:
        print("❌ watchlist 为空", file=sys.stderr)
        return 1

    print(f"📊 拉取 {len(stocks)} 只股票实时行情…", file=sys.stderr)
    codes = [s["code"] for s in stocks]
    raw = fetch_batch(codes)

    quotes = []
    for s in stocks:
        code = s["code"]
        if code not in raw:
            quotes.append({**s, "error": "no data"})
            continue
        fields = raw[code]
        parsed = parse_hk_stock(fields) if code.startswith("rt_hk") else parse_a_stock(fields)
        parsed = enrich(parsed)
        quotes.append({**s, **parsed})

    ok = sum(1 for q in quotes if "error" not in q)
    print(f"✅ 成功 {ok}/{len(stocks)}（失败 {len(stocks) - ok}）", file=sys.stderr)

    output = {
        "fetched_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "count": len(quotes),
        "quotes": quotes,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
