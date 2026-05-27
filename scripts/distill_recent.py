#!/usr/bin/env python3
"""
distill_recent.py - 用 LLM 把最近 30 天的刘备文章 + 今日新闻 + inbox 蒸馏成 recent.md

输入：
- knowledge_base/recent_30d_articles.json （由 build_knowledge_base.py 生成）
- knowledge_base/news_raw/YYYY-MM-DD/*.html （由 fetch_news.py 生成）
- knowledge_base/inbox/*.md （用户手工塞）

输出：
- knowledge_base/recent.md

依赖：claude CLI 在 PATH 中。若不可用，回退到"骨架模板 + 文章列表"。
"""

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parent.parent
KB_DIR = ROOT / "knowledge_base"
RECENT_30D = KB_DIR / "recent_30d_articles.json"
NEWS_RAW_DIR = KB_DIR / "news_raw"
INBOX_DIR = KB_DIR / "inbox"
OUTPUT = KB_DIR / "recent.md"

PROMPT_TEMPLATE = """你是刘备教授炒股助手的近期信息整理员。请把以下输入蒸馏成一份固定模板的 markdown 报告。

# 输入

## A. 刘备教授近 30 天文章（共 {n_articles} 篇）

{articles_block}

## B. 今日财经新闻原始页面（HTML，需要你自己抽取要点）

{news_block}

## C. 用户手工 inbox 重大事件

{inbox_block}

# 输出要求

严格按以下 markdown 模板输出。每节如果没有相关内容就写"暂无"。所有日期用 YYYY-MM-DD 格式。最后一节"与历史观点的冲突"是核心——必须主动识别近期事件对历史观点的冲销。

```markdown
# 近期市场观点（截至 {today}）

> 自动蒸馏自最近 30 天的刘备教授文章 + 今日财经新闻 + 手工 inbox。下游 agent 引用此文件时必须标注 `[基于 YYYY-MM-DD]`。

## 市场状态
- A 股：{{当前阶段判断，含成交量、热点、风险}}
- 港股：{{当前阶段判断}}
- 美股：{{当前阶段判断}}
- 中概：{{当前阶段判断}}

## 主要事件（最近 7 天）
- YYYY-MM-DD: {{事件 + 影响}}

## 法规/监管变化
- YYYY-MM-DD: {{监管要点 + 受影响标的}}

## 个股观点变化
- {{股票名}}：从 X 改为 Y（YYYY-MM-DD）
- ...

## 与历史观点的冲突
> 这一节是核心：识别近期变化对历史 KB 旧观点的冲销，避免下游 agent 把过时观点当作当下断言。
- 历史 KB 说 X（基于 YYYY-MM-DD），但近期已变化为 Y（基于 YYYY-MM-DD）
- ...
```

直接输出 markdown，不要加任何说明文字、不要包在代码块里。
"""


def load_recent_articles():
    if not RECENT_30D.exists():
        return []
    data = json.loads(RECENT_30D.read_text(encoding="utf-8"))
    return data.get("articles", [])


def load_news_today():
    today = datetime.now().strftime("%Y-%m-%d")
    day_dir = NEWS_RAW_DIR / today
    if not day_dir.exists():
        return []
    files = []
    for p in sorted(day_dir.glob("*")):
        if p.is_file():
            try:
                text = p.read_text(encoding="utf-8")
                # 截断防止 prompt 爆炸
                files.append((p.name, text[:20000]))
            except Exception:
                continue
    return files


def load_inbox():
    if not INBOX_DIR.exists():
        return []
    items = []
    for p in sorted(INBOX_DIR.glob("*.md")):
        try:
            items.append((p.name, p.read_text(encoding="utf-8")))
        except Exception:
            continue
    return items


def build_prompt():
    articles = load_recent_articles()
    news = load_news_today()
    inbox = load_inbox()

    articles_block = "\n\n".join(
        f"### {a['date']} - {a['title']}\n摘要：{a.get('summary', '')[:500]}\n标记：{a.get('level', [])}\n关联股票：{a.get('stocks', [])}\n关联行业：{a.get('industries', [])}"
        for a in articles[:30]
    ) or "暂无"

    news_block = "\n\n".join(
        f"### {name}\n```\n{text[:5000]}\n```"
        for name, text in news
    ) or "暂无"

    inbox_block = "\n\n".join(
        f"### {name}\n{text}"
        for name, text in inbox
    ) or "暂无"

    return PROMPT_TEMPLATE.format(
        today=datetime.now().strftime("%Y-%m-%d"),
        n_articles=len(articles),
        articles_block=articles_block,
        news_block=news_block,
        inbox_block=inbox_block,
    )


def call_claude(prompt):
    """通过 claude -p 非交互式调用"""
    if not shutil.which("claude"):
        return None
    try:
        result = subprocess.run(
            ["claude", "-p", prompt],
            capture_output=True,
            text=True,
            timeout=300,
        )
        if result.returncode != 0:
            print(f"❌ claude -p 返回非零: {result.returncode}", file=sys.stderr)
            print(result.stderr[:500], file=sys.stderr)
            return None
        return result.stdout.strip()
    except subprocess.TimeoutExpired:
        print("❌ claude -p 超时", file=sys.stderr)
        return None
    except Exception as e:
        print(f"❌ claude -p 异常: {e}", file=sys.stderr)
        return None


def fallback_skeleton(articles):
    """LLM 不可用时的兜底：列出最近 10 篇文章摘要"""
    today = datetime.now().strftime("%Y-%m-%d")
    lines = [
        f"# 近期市场观点（截至 {today}）",
        "",
        "> ⚠️ LLM 不可用，本文件为兜底模板。请运行 `bash scripts/refresh.sh` 在 claude CLI 可用时重新生成。",
        "",
        "## 市场状态",
        "- 暂无（待 LLM 蒸馏）",
        "",
        "## 主要事件（最近 7 天）",
    ]
    for a in articles[:10]:
        lines.append(f"- {a['date']}: {a['title']} - {a.get('summary', '')[:100]}")
    lines.extend([
        "",
        "## 法规/监管变化",
        "- 暂无",
        "",
        "## 个股观点变化",
        "- 暂无",
        "",
        "## 与历史观点的冲突",
        "- 暂无（需 LLM 分析）",
    ])
    return "\n".join(lines)


def main():
    print("📚 加载近期数据…")
    articles = load_recent_articles()
    print(f"   - 近 30 天文章: {len(articles)} 篇")
    news = load_news_today()
    print(f"   - 今日新闻源: {len(news)} 个")
    inbox = load_inbox()
    print(f"   - inbox 条目: {len(inbox)} 个")

    if not articles and not news and not inbox:
        print("⚠️  无输入数据，跳过", file=sys.stderr)
        return 1

    prompt = build_prompt()
    print(f"📝 prompt 长度: {len(prompt)} 字符")

    print("🤖 调用 claude -p 进行蒸馏…")
    result = call_claude(prompt)

    if result:
        # 简单清理可能的 markdown 代码块包裹
        result = re.sub(r"^```markdown\s*\n", "", result)
        result = re.sub(r"\n```\s*$", "", result)
        OUTPUT.write_text(result, encoding="utf-8")
        print(f"✅ 已写入 {OUTPUT} ({len(result)} 字符)")
    else:
        print("⚠️  LLM 失败，使用兜底模板", file=sys.stderr)
        fallback = fallback_skeleton(articles)
        OUTPUT.write_text(fallback, encoding="utf-8")
        print(f"✅ 已写入兜底版本 {OUTPUT}")
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
