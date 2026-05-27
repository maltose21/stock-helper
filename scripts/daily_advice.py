#!/usr/bin/env python3
"""
daily_advice.py - 每日 19:00 调用 claude -p 分析 KB，生成次日买卖建议。

输入：knowledge_base/{evergreen.md, recent.md, summary.md, knowledge_base.json}
输出：~/Documents/stock-helper/daily/YYYY-MM-DD.md（次日日期）
依赖：claude CLI 在 PATH 中
"""

import json
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KB = ROOT / "knowledge_base"
OUT_DIR = Path.home() / "Documents" / "stock-helper" / "daily"
OUT_DIR.mkdir(parents=True, exist_ok=True)

CLAUDE_BIN = "claude"
CLAUDE_TIMEOUT_SEC = 600


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


def build_prompt(today_str: str, tomorrow_str: str, inputs: dict) -> str:
    return f"""你是基于刘备教授投资哲学的国际级别投资顾问。今天是 {today_str}，请基于下方知识库为 **{tomorrow_str}（次日）** 生成完整的"次日买卖建议"。

# 输入：永恒方法论（evergreen.md）

{inputs['evergreen.md']}

---

# 输入：近期市场观点（recent.md，距今最新）

{inputs['recent.md']}

---

# 输入：知识库摘要（summary.md，全量统计）

{inputs['summary.md']}

---

# 输入：最近 50 篇文章标题（带 level 标签）

{inputs['recent_titles']}

---

# 任务

输出严格遵循下面的 markdown 模板，**所有判断都必须可追溯到上面输入**，引用 recent.md 内容时标 `[基于 YYYY-MM-DD]`，引用 30 天前历史观点标 `[原文 YYYY-MM-DD]`：

```
# 次日交易建议 · {tomorrow_str}

> 基于刘备教授投资体系，{today_str} 19:00 自动生成。本建议不构成投资建议，仅供学习参考。

## 一、市场状态判断
- A 股：[牛/熊/震荡，简述当前阶段]
- 港股：[同上]
- 美股 / 中概：[同上]
- 时机评级：⭐☆☆☆☆ 至 ★★★★★（简述依据）

## 二、关注名单（次日重点观察）

| 标的 | 方向 | 买入区间 | 止损位 | 仓位建议 | 持有周期 | 核心逻辑 |
|------|------|----------|--------|----------|----------|----------|
| 股票A | 加仓/减仓/持有/回避 | xxx-xxx | xxx | xx% | 短/中/长 | 一句话 |

（3-5 个标的，覆盖 recent.md 提到的高频股 / 板块龙头；不要给出具体价位预测，区间需结合方法论判断）

## 三、板块倾向
- ✅ 看好：[板块] —— [理由 + 来源]
- ⚠️ 谨慎：[板块] —— [理由 + 来源]
- ❌ 回避：[板块] —— [理由 + 来源]

## 四、仓位建议
- 当前建议总仓位：xx%
- 现金仓位：xx%
- 单一行业上限：xx%

## 五、风险点（必读）
1. [系统性 / 地缘 / 流动性等]
2. [行业风险]
3. [个股风险]

## 六、与历史观点的冲突
[若 recent.md 末节命中冲突，主动列出"历史 X → 近期 Y"]

## 七、纪律提醒
- 永不满仓，单票 ≤ 20%，单一行业 ≤ 30%
- 投机仓 -10% 无条件止损，投资仓 -20% 可再判断
- 买在无人问津时，卖在人声鼎沸处
```

强制要求：
1. **任何"现在能买/现在该卖"的判断必须来自 recent.md**；若 recent.md 缺数据，明确说"无最新数据，建议跳过该标的"
2. 关注名单不少于 3 个、不多于 5 个；不要追当下最热的题材（牛三阶段非热点滞涨原则）
3. 不预测具体涨幅，不保证盈利
4. 直接输出 markdown 内容（不要包在 ```markdown 代码块里）
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

    print(f"📊 生成 {tomorrow} 次日建议（{today} {now.strftime('%H:%M:%S')}）")

    inputs = load_kb_inputs()
    prompt = build_prompt(today, tomorrow, inputs)
    print(f"📝 prompt 长度: {len(prompt)} 字符，调用 claude -p…")

    advice = call_claude(prompt)
    if not advice:
        print("❌ claude 输出为空，跳过写盘", file=sys.stderr)
        return 1

    out_path = OUT_DIR / f"{tomorrow}.md"
    out_path.write_text(advice, encoding="utf-8")
    print(f"✅ 已写入 {out_path}（{len(advice)} 字符）")
    print(out_path)  # 标准输出最后一行 = 文件路径，便于 shell 串联
    return 0


if __name__ == "__main__":
    sys.exit(main())
