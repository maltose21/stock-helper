#!/usr/bin/env python3
"""
daily_advice.py - 每日 19:00 全市场扫描 → 评分 → TOP 30 → claude 选 TOP 10。

流程：
1. fetch_universe.py: 拉 5300+ 只 A 股 + 50 只港股核心快照 (~35s)
2. score_universe.py: 多维评分 → TOP 30 → top30_candidates.json
3. 读 evergreen.md + recent.md + summary.md + 最近 50 篇文章标题
4. 拼 prompt → claude -p → TOP 10 markdown
5. 写到 ~/Documents/stock-helper/daily/YYYY-MM-DD.md
"""

import json
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KB = ROOT / "knowledge_base"
SCRIPTS = ROOT / "scripts"
TOP30 = KB / "top30_candidates.json"
OUT_DIR = Path.home() / "Documents" / "stock-helper" / "daily"
OUT_DIR.mkdir(parents=True, exist_ok=True)

CLAUDE_BIN = "claude"
CLAUDE_TIMEOUT_SEC = 900


def run(name: str, script: Path, timeout: int) -> bool:
    print(f"⚙️  执行 {name}…", file=sys.stderr)
    r = subprocess.run(["python3", str(script)], timeout=timeout)
    if r.returncode != 0:
        print(f"❌ {name} 失败 (exit={r.returncode})", file=sys.stderr)
        return False
    return True


def load_kb_inputs() -> dict:
    inputs = {}
    for fname in ("evergreen.md", "recent.md", "summary.md"):
        p = KB / fname
        inputs[fname] = p.read_text(encoding="utf-8") if p.exists() else f"(missing: {fname})"

    kb_json = KB / "knowledge_base.json"
    if kb_json.exists():
        kb = json.loads(kb_json.read_text(encoding="utf-8"))
        articles = kb.get("articles", [])
        articles.sort(key=lambda a: a.get("date", ""), reverse=True)
        recent_titles = [
            f"- {a.get('date', '?')} | {','.join(a.get('level', []))} | {a.get('title', '?')}"
            for a in articles[:50]
        ]
        inputs["recent_titles"] = "\n".join(recent_titles)
    else:
        inputs["recent_titles"] = "(missing: knowledge_base.json)"
    return inputs


def load_top30() -> dict:
    if not TOP30.exists():
        raise FileNotFoundError(f"缺少 {TOP30}")
    return json.loads(TOP30.read_text(encoding="utf-8"))


def format_candidates_table(rows: list, label: str) -> str:
    """格式化候选表，分主线/价值两组喂给 claude。"""
    lines = [f"\n### {label}（{len(rows)} 只）\n",
             "| # | 代码 | 名称 | 板块 | 现价 | 涨跌% | 成交亿 | PE | 距52w高% | 距52w低% | 评分 |",
             "|---|------|------|------|------|-------|--------|-----|----------|----------|------|"]
    for i, s in enumerate(rows, 1):
        pe = s.get("pe")
        pe_str = f"{pe:.1f}" if pe else "-"
        h52 = s.get("high_52w")
        l52 = s.get("low_52w")
        cur = s.get("current", 0)
        pct_h = f"{(cur - h52) / h52 * 100:+.1f}" if h52 else "-"
        pct_l = f"{(cur - l52) / l52 * 100:+.1f}" if l52 else "-"
        amt = s.get("amount", 0) / 1e8
        sector = s.get("sector_class") or s.get("sector", "?")
        lines.append(
            f"| {i} | {s['code']} | {s.get('name', '?')} | {sector} | "
            f"{cur:.2f} | {s.get('change_pct', 0):+.2f} | {amt:.1f} | {pe_str} | {pct_h} | {pct_l} | {s['score']:.1f} |"
        )
    return "\n".join(lines)


def build_prompt(today_str: str, tomorrow_str: str, inputs: dict, top30: dict) -> str:
    main_line_table = format_candidates_table(top30.get("top_main_line", []), "今日主线龙头候选")
    value_table = format_candidates_table(top30.get("top_value", []), "价值股压舱候选")
    main_lines = top30.get("main_line_sectors", [])
    main_line_detail = top30.get("main_line_detail", {})
    if main_lines:
        ml_summary = ", ".join(
            f"{s}({main_line_detail.get(s, {}).get('count', '?')}只共涨,板块成交{main_line_detail.get(s, {}).get('total_amount_yi', '?')}亿)"
            for s in main_lines
        )
    else:
        ml_summary = "(今日无明显主线，市场分化或缩量)"

    return f"""你是基于刘备教授投资哲学的国际级别投资顾问。今天是 {today_str}，请基于「全市场动态主线扫描 + 价值压舱 + 知识库」为 **{tomorrow_str}（次日）** 生成 **TOP 10 操作清单**。

# 输入 1：今日全市场动态扫描结果

扫描范围：{top30.get('universe_size', '?')} 只 A 股 + 港股核心
**今日动态识别的主线**：{ml_summary}

候选分两组：
- **主线龙头候选**：今日板块共振涨 > 4% 的成员中按成交额排序的龙头
- **价值股压舱候选**：高分红/低估值蓝筹（银行/水电/煤炭/互联网平台等）

评分维度：L=流动性 / S=板块匹配 / M=资金动能 / Sa=安全边际
{main_line_table}

{value_table}

# 输入 2：永恒方法论（evergreen.md）

{inputs['evergreen.md']}

---

# 输入 3：近期市场观点（recent.md，距今最新）

{inputs['recent.md']}

---

# 输入 4：知识库摘要（summary.md）

{inputs['summary.md']}

---

# 输入 5：最近 50 篇文章标题（带 level 标签）

{inputs['recent_titles']}

---

# 输出要求（严格遵守）

按下面模板输出 markdown。**TOP 10 表是核心，其它部分都尽量精简。**

```
# 次日 TOP 10 操作清单 · {tomorrow_str}

> {today_str} 收盘后自动生成 | 扫描 {top30.get('universe_size', '?')} 只全市场 | 不构成投资建议

## 一、市场温度（一句话）

[当前市场状态 + 时机评级 ★★★☆☆，60 字以内，引用 recent.md]

## 二、TOP 10 关注名单

| # | 标的 | 当前价 | 买入价 | 目标价 | 止损价 | 仓位 | 周期 | 评级 | 核心逻辑（≤20字） |
|---|------|--------|--------|--------|--------|------|------|------|-------------------|
| 1 | 招商银行(600036) | 37.00 | 35.5-36.5 | 42.0 | 33.3 | 10% | 中长 | 强买入 | 银行分红龙头 |
| 2 | ... | ... | ... | ... | ... | ... | ... | ... | ... |

筛选规则（**强制遵守**）：
1. **必须 6 只来自「今日主线龙头候选」+ 4 只来自「价值股压舱候选」** —— 不允许越界，也不要选清单外的标的
2. 主线 6 只内部要求：板块上限 4 只（如半导体板块若有龙头富集，最多选 4 只，剩余 2 只必须换板块）；优先选评分 ≥ 75 且涨幅在 4-9% 区间的（不追涨停板，因次日难以接力）
3. 价值 4 只要求：板块分散（银行/水电/煤炭/互联网平台 各 1 只为佳），优先距 52w 高 > 10% 的（有安全边际）
4. 至少包含一只「减仓 / 回避」评级的标的：从主线候选里选距 52w 高 < 3% 且涨停的（已透支），或 recent.md 提示风险的标的
5. 主线龙头默认评级「强买入 / 逢回调买」；价值股默认「持有 / 逢回调买」

填表规则：
- 当前价：直接从上表读
- 买入价区间：
  · 距 52w 高 > 15% 的（左侧）：当前价 ±2%（可入）
  · 距 52w 高 5-15% 的：当前价 -3% ~ -8%（等回调）
  · 距 52w 高 < 5% 的：写"暂不追"或当前价 -10% 以下
- 目标价：基于 PE 修复 / 52w 高 / 行业空间合理推断（不要写翻倍）
- 止损价：投机仓 = 买入价 × 0.9（-10%）；投资仓 = 买入价 × 0.8（-20%）
- 仓位：单票 ≤ 20%，10 只总和约 60-80%；高分红价值股 10-15%，科技/题材 5-10%
- 评级：「强买入 / 逢回调买 / 持有 / 减仓 / 回避」5 档

## 三、板块倾向（3 行内）

- ✅ [板块 + 一句理由 + 引用 recent.md 日期]
- ⚠️ [板块 + 一句理由]
- ❌ [板块 + 一句理由]

## 四、风险提示（3 条内）

1. [系统/地缘/流动性风险]
2. [行业风险]
3. [跨周期风险，含历史观点冲突]

## 五、纪律提醒

- 永不满仓，单票 ≤ 20%，单一行业 ≤ 30%
- 投机仓 -10% 无条件止损，投资仓 -20% 可再判断
- 买在无人问津时，卖在人声鼎沸处 —— 距 52w 高 < 3% 的不追
```

强制要求：
1. 不要超过 1800 字
2. 不预测具体涨幅 / 不保证盈利
3. 不要包在 ```markdown 代码块里，直接输出 markdown
4. 引用 recent.md 内容标 `[基于 YYYY-MM-DD]`
"""


def call_claude(prompt: str) -> str:
    try:
        result = subprocess.run(
            [CLAUDE_BIN, "-p", prompt],
            capture_output=True,
            text=True,
            timeout=CLAUDE_TIMEOUT_SEC,
        )
        if result.returncode != 0:
            sys.stderr.write(f"claude exit {result.returncode}\nstderr: {result.stderr[:500]}\n")
            return ""
        return result.stdout.strip()
    except FileNotFoundError:
        sys.stderr.write(f"未找到 {CLAUDE_BIN}\n")
        return ""
    except subprocess.TimeoutExpired:
        sys.stderr.write(f"claude 调用超时 {CLAUDE_TIMEOUT_SEC}s\n")
        return ""


def main() -> int:
    now = datetime.now()
    today = now.strftime("%Y-%m-%d")
    tomorrow = (now + timedelta(days=1)).strftime("%Y-%m-%d")

    print(f"📊 生成 {tomorrow} TOP 10（{today} {now.strftime('%H:%M:%S')}）", file=sys.stderr)

    if not run("[1/4] fetch_universe.py", SCRIPTS / "fetch_universe.py", timeout=180):
        return 1
    if not run("[2/4] score_universe.py", SCRIPTS / "score_universe.py", timeout=60):
        return 1

    print("📚 [3/4] 读取知识库 + TOP30…", file=sys.stderr)
    inputs = load_kb_inputs()
    top30 = load_top30()
    prompt = build_prompt(today, tomorrow, inputs, top30)
    print(f"📝 prompt 长度: {len(prompt)} 字符", file=sys.stderr)

    print("🤖 [4/4] 调用 claude -p…", file=sys.stderr)
    advice = call_claude(prompt)
    if not advice:
        print("❌ claude 输出为空", file=sys.stderr)
        return 1

    out_path = OUT_DIR / f"{tomorrow}.md"
    out_path.write_text(advice, encoding="utf-8")
    print(f"✅ 写入 {out_path}（{len(advice)} 字符）", file=sys.stderr)
    print(out_path)  # 标准输出最后一行 = 文件路径
    return 0


if __name__ == "__main__":
    sys.exit(main())
