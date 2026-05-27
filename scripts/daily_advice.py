#!/usr/bin/env python3
"""
daily_advice.py - 每日 19:00 调用 claude -p 分析 KB + 实时行情，生成次日 TOP 10 买卖清单。

流程：
1. 跑 fetch_quotes.py 拉 30 只候选股最新行情（含 52 周高低、距高低 %）
2. 读 evergreen.md + recent.md + summary.md + 最近 50 篇文章标题
3. 拼 prompt → claude -p → markdown
4. 写到 ~/Documents/stock-helper/daily/YYYY-MM-DD.md
"""

import json
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KB = ROOT / "knowledge_base"
SCRIPTS = ROOT / "scripts"
OUT_DIR = Path.home() / "Documents" / "stock-helper" / "daily"
OUT_DIR.mkdir(parents=True, exist_ok=True)

CLAUDE_BIN = "claude"
CLAUDE_TIMEOUT_SEC = 600


def fetch_quotes() -> str:
    """跑 fetch_quotes.py 拉实时行情，返回 JSON 字符串。"""
    try:
        result = subprocess.run(
            ["python3", str(SCRIPTS / "fetch_quotes.py")],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            sys.stderr.write(f"fetch_quotes.py exit {result.returncode}\n{result.stderr[:500]}\n")
            return ""
        return result.stdout.strip()
    except Exception as e:
        sys.stderr.write(f"fetch_quotes.py 调用失败: {e}\n")
        return ""


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


def build_prompt(today_str: str, tomorrow_str: str, inputs: dict, quotes_json: str) -> str:
    return f"""你是基于刘备教授投资哲学的国际级别投资顾问。今天是 {today_str}，请基于下方"知识库+实时行情"为 **{tomorrow_str}（次日）** 生成 **TOP 10 操作清单**。

# 输入 1：30 只候选股最新行情（含 52 周高低、距高低%、PE）

```json
{quotes_json}
```

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

# 输出要求（严格遵守，否则视为失败）

按下面模板输出 markdown。**TOP 10 表是核心，其它部分都尽量精简。**

```
# 次日 TOP 10 操作清单 · {tomorrow_str}

> {today_str} 收盘后自动生成 | 不构成投资建议

## 一、市场温度（一句话）

[当前市场状态 + 时机评级 ★★★☆☆，60 字以内]

## 二、TOP 10 关注名单

| # | 标的 | 当前价 | 买入价 | 目标价 | 止损价 | 仓位 | 周期 | 评级 | 核心逻辑（≤20字） |
|---|------|--------|--------|--------|--------|------|------|------|-------------------|
| 1 | 招商银行(600036) | 37.00 | 35.5-36.5 | 42.0 | 33.0 | 10% | 中长 | 买入 | 银行分红龙头 |
| 2 | ... | ... | ... | ... | ... | ... | ... | ... | ... |

排序原则（优先级递减）：
1. **强买入**：recent.md 重点正面提及 + 行情在合理区间（不在 52 周高位）
2. **逢回调买**：recent.md 看好但当前已涨至 52 周高位附近（距高 < 5%）
3. **持有观察**：recent.md 持有偏多但需信号确认
4. **回避减仓**：recent.md 提示风险或题材见顶

填表规则：
- 当前价 / 距 52w 高 / 距 52w 低：直接从行情 JSON 读，不能凭空编
- 买入价区间：对 A股 / 港股 龙头通常取「当前价 -3% ~ -8%」做安全垫；对距 52w 高 > 15% 的可取「当前价 ±2%」
- 目标价：基于历史 PE / 52w 高 / 行业空间合理推断；不要写"翻倍""500元"这种激进数字
- 止损价：投机仓 = 买入价 × 0.9（-10%）；投资仓 = 买入价 × 0.8（-20%）
- 仓位：单票 ≤ 20%，10 只总和约 60-80%；高分红价值股 10-15%，科技/题材 5-10%
- 评级用：「强买入 / 逢回调买 / 持有 / 减仓 / 回避」5 档
- 至少包含：2 只高分红价值股 + 3 只港股互联网 + 2 只 A股科技 + 1-2 只周期/底仓 + 1 只回避对照

## 三、板块倾向（3 行内）

- ✅ [板块 + 一句理由]
- ⚠️ [板块 + 一句理由]
- ❌ [板块 + 一句理由]

## 四、风险提示（3 条内）

1. [风险点]
2. [风险点]
3. [风险点]

## 五、纪律提醒

- 永不满仓，单票 ≤ 20%，单一行业 ≤ 30%
- 投机仓 -10% 无条件止损，投资仓 -20% 可再判断
- 买在无人问津时，卖在人声鼎沸处 —— 距 52w 高 < 3% 的不追
```

强制要求：
1. TOP 10 的每一行**当前价必须从行情 JSON 实读**，不能瞎写或留空
2. recent.md 看不到该股观点时，标"无最新观点"且评级降到「持有」或「回避」
3. 买入价 / 目标价 / 止损价必须给具体数字（区间 OK），不能写"待定"
4. 不要预测具体涨幅 / 不保证盈利
5. **不要超过 1500 字**——这是给用户上班路上看的简报，不是研究报告
6. 直接输出 markdown 内容（不要包在 ```markdown 代码块里）
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
        sys.stderr.write(f"未找到 {CLAUDE_BIN}，请确认 claude CLI 在 PATH 中\n")
        return ""
    except subprocess.TimeoutExpired:
        sys.stderr.write(f"claude 调用超时 {CLAUDE_TIMEOUT_SEC}s\n")
        return ""


def main() -> int:
    now = datetime.now()
    today = now.strftime("%Y-%m-%d")
    tomorrow = (now + timedelta(days=1)).strftime("%Y-%m-%d")

    print(f"📊 生成 {tomorrow} TOP 10（{today} {now.strftime('%H:%M:%S')}）", file=sys.stderr)

    print("📈 [1/3] 拉取候选股实时行情…", file=sys.stderr)
    quotes_json = fetch_quotes()
    if not quotes_json:
        print("❌ 行情拉取失败，终止", file=sys.stderr)
        return 1

    print("📚 [2/3] 读取知识库…", file=sys.stderr)
    inputs = load_kb_inputs()
    prompt = build_prompt(today, tomorrow, inputs, quotes_json)
    print(f"📝 prompt 长度: {len(prompt)} 字符", file=sys.stderr)

    print("🤖 [3/3] 调用 claude -p…", file=sys.stderr)
    advice = call_claude(prompt)
    if not advice:
        print("❌ claude 输出为空，跳过写盘", file=sys.stderr)
        return 1

    out_path = OUT_DIR / f"{tomorrow}.md"
    out_path.write_text(advice, encoding="utf-8")
    print(f"✅ 已写入 {out_path}（{len(advice)} 字符）", file=sys.stderr)
    print(out_path)  # 标准输出最后一行 = 文件路径，便于 shell 串联
    return 0


if __name__ == "__main__":
    sys.exit(main())
