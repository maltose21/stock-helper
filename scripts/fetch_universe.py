#!/usr/bin/env python3
"""
fetch_universe.py - 拉全市场快照（A 股 5300+ 只 + 港股 50 只核心标的）。

策略：
- A 股代码：用 ak.stock_info_sh_name_code + sz_name_code（毫秒返回）
- 行情：批量调 hq.sinajs.cn（30 个/批，约 200 批，<60s）
- 港股：用静态名单 hk_universe.txt（季度更新一次）

输出：universe_quotes.json，下游 score_universe.py 消费。
"""

import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HK_LIST = ROOT / "scripts" / "hk_universe.txt"
OUT = ROOT / "knowledge_base" / "universe_quotes.json"
SINA_BASE = "https://hq.sinajs.cn/list="
HEADERS = {"Referer": "https://finance.sina.com.cn", "User-Agent": "Mozilla/5.0"}
BATCH_SIZE = 30


def get_a_codes() -> list[dict]:
    """全 A 股代码 + 名称。"""
    try:
        import akshare as ak
    except ImportError:
        print("❌ 需要安装 akshare: pip3 install akshare", file=sys.stderr)
        sys.exit(1)

    sh = ak.stock_info_sh_name_code(symbol="主板A股")
    # 沪市主板（60xxxx）
    sh_list = [
        {"code": f"sh{c}", "name": n, "market": "SH"}
        for c, n in zip(sh["证券代码"].astype(str), sh["证券简称"])
    ]

    # 科创板
    try:
        ksb = ak.stock_info_sh_name_code(symbol="科创板")
        sh_list += [
            {"code": f"sh{c}", "name": n, "market": "STAR"}
            for c, n in zip(ksb["证券代码"].astype(str), ksb["证券简称"])
        ]
    except Exception:
        pass

    sz = ak.stock_info_sz_name_code(symbol="A股列表")
    sz_list = [
        {"code": f"sz{c}", "name": n, "market": "SZ"}
        for c, n in zip(sz["A股代码"].astype(str), sz["A股简称"])
    ]
    return sh_list + sz_list


def get_hk_codes() -> list[dict]:
    """港股核心名单（静态文件 hk_universe.txt，一行 'CODE 名称 板块'）。"""
    if not HK_LIST.exists():
        return []
    out = []
    for line in HK_LIST.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(None, 2)
        if len(parts) < 2:
            continue
        code, name = parts[0], parts[1]
        sector = parts[2] if len(parts) > 2 else "?"
        out.append({"code": f"rt_hk{code}", "name": name, "market": "HK", "sector": sector})
    return out


def fetch_batch(codes: list[str]) -> dict[str, list[str]]:
    url = SINA_BASE + ",".join(codes)
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read().decode("gbk", errors="replace")
    except (urllib.error.URLError, TimeoutError) as e:
        sys.stderr.write(f"  batch fail: {e}\n")
        return {}
    result = {}
    for line in raw.splitlines():
        m = re.match(r'var hq_str_(\S+)="(.*)";', line)
        if not m:
            continue
        code, body = m.group(1), m.group(2)
        if not body:
            continue
        result[code] = body.split(",")
    return result


def parse_a(fields: list[str]) -> dict:
    """A 股 sina hq 字段：0=name 1=open 2=prev 3=current 4=high 5=low 8=volume 9=amount 30=date 31=time"""
    try:
        current = float(fields[3])
        prev = float(fields[2])
        return {
            "open": float(fields[1]),
            "prev_close": prev,
            "current": current,
            "high": float(fields[4]),
            "low": float(fields[5]),
            "volume": int(fields[8]) if fields[8] else 0,
            "amount": float(fields[9]) if fields[9] else 0,
            "change_pct": round((current - prev) / prev * 100, 2) if prev > 0 else 0,
        }
    except (ValueError, IndexError):
        return {}


def parse_hk(fields: list[str]) -> dict:
    """港股字段：1=name 2=open 3=prev 4=high 5=low 6=current 8=change_pct 11=amount 12=volume 13=pe 15=high52w 16=low52w"""
    try:
        current = float(fields[6])
        return {
            "open": float(fields[2]),
            "prev_close": float(fields[3]),
            "current": current,
            "high": float(fields[4]),
            "low": float(fields[5]),
            "change_pct": float(fields[8]) if fields[8] else 0,
            "amount": float(fields[11]) if fields[11] else 0,
            "volume": int(fields[12]) if fields[12] else 0,
            "pe": float(fields[13]) if fields[13] and fields[13] != "0.000" else None,
            "high_52w": float(fields[15]) if fields[15] else None,
            "low_52w": float(fields[16]) if fields[16] else None,
        }
    except (ValueError, IndexError):
        return {}


def main() -> int:
    t0 = time.time()
    print("📋 [1/3] 拉取 A 股代码列表…", file=sys.stderr)
    a_stocks = get_a_codes()
    print(f"  A 股: {len(a_stocks)} 只", file=sys.stderr)

    print("📋 [2/3] 读取港股核心名单…", file=sys.stderr)
    hk_stocks = get_hk_codes()
    print(f"  港股: {len(hk_stocks)} 只", file=sys.stderr)

    all_stocks = a_stocks + hk_stocks
    total = len(all_stocks)
    print(f"📊 [3/3] 拉取行情（{total} 只，{BATCH_SIZE} 个/批）…", file=sys.stderr)

    results = []
    batches = [all_stocks[i:i + BATCH_SIZE] for i in range(0, total, BATCH_SIZE)]
    n_ok = 0
    n_fail = 0
    for i, batch in enumerate(batches):
        codes = [s["code"] for s in batch]
        raw = fetch_batch(codes)
        for s in batch:
            fields = raw.get(s["code"])
            if not fields:
                n_fail += 1
                continue
            parsed = parse_hk(fields) if s["code"].startswith("rt_hk") else parse_a(fields)
            if not parsed:
                n_fail += 1
                continue
            # 复用 sina 返回里的 name（避免本地名单中文乱码）
            name_from_quote = fields[1] if s["code"].startswith("rt_hk") else fields[0]
            if name_from_quote and "?" not in name_from_quote:
                s = {**s, "name": name_from_quote}
            results.append({**s, **parsed})
            n_ok += 1
        if (i + 1) % 20 == 0:
            elapsed = time.time() - t0
            print(f"  {i+1}/{len(batches)} 批 | OK {n_ok} FAIL {n_fail} | {elapsed:.0f}s", file=sys.stderr)
        time.sleep(0.05)  # 轻度礼貌

    elapsed = time.time() - t0
    print(f"✅ 完成: {n_ok} 只成功, {n_fail} 只失败, 耗时 {elapsed:.0f}s", file=sys.stderr)

    output = {
        "fetched_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "count": n_ok,
        "fail": n_fail,
        "elapsed_sec": round(elapsed, 1),
        "quotes": results,
    }
    OUT.write_text(json.dumps(output, ensure_ascii=False), encoding="utf-8")
    print(f"💾 写入 {OUT} ({OUT.stat().st_size // 1024} KB)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
