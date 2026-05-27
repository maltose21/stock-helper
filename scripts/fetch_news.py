#!/usr/bin/env python3
"""
fetch_news.py - 拉取财经新闻原始页面到 news_raw/

设计原则：本脚本只负责"抓取"，不负责"解析"。
- 把每个 source 的 HTML/JSON 存到 news_raw/YYYY-MM-DD/{source_name}.html
- distill_recent.py 再让 LLM 从这些原始内容中蒸馏要点
- 这样脚本零额外依赖（不需 BeautifulSoup/feedparser），失败容忍简单

读 sources.yaml 配置，对每个 enabled=true 的 source curl 拉取。
"""

import re
import sys
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parent.parent
SOURCES_FILE = ROOT / "scripts" / "sources.yaml"
NEWS_RAW_DIR = ROOT / "knowledge_base" / "news_raw"

USER_AGENT = "Mozilla/5.0 (stock-helper-fetch; +https://github.com/anthropics/claude-code)"
TIMEOUT = 20


def parse_yaml_lite(path):
    """轻量 YAML 解析（仅支持本项目 sources.yaml 的扁平 list-of-dict 结构，避免 PyYAML 依赖）"""
    sources = []
    current = None
    with open(path, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.rstrip("\n")
            # 跳过注释、空行
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if stripped == "sources:":
                continue

            # 新的 list item: "  - name: xxx"
            m = re.match(r"^\s*-\s*(\w+):\s*(.*)$", line)
            if m:
                if current is not None:
                    sources.append(current)
                current = {}
                current[m.group(1)] = _coerce(m.group(2))
                continue

            # 同一 item 内的 key: value
            m = re.match(r"^\s+(\w+):\s*(.*)$", line)
            if m and current is not None:
                current[m.group(1)] = _coerce(m.group(2))

    if current is not None:
        sources.append(current)
    return sources


def _coerce(val):
    val = val.strip()
    # 去掉行尾注释
    if "#" in val:
        val = val.split("#", 1)[0].strip()
    if val.lower() in ("true", "yes"):
        return True
    if val.lower() in ("false", "no"):
        return False
    return val


def http_get(url):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        ct = resp.headers.get("Content-Type", "")
        raw = resp.read()
        # 简单尝试编码
        for enc in ("utf-8", "gbk", "gb2312"):
            try:
                return raw.decode(enc), ct
            except UnicodeDecodeError:
                continue
        return raw.decode("utf-8", errors="replace"), ct


def main():
    if not SOURCES_FILE.exists():
        print(f"❌ 配置文件不存在: {SOURCES_FILE}", file=sys.stderr)
        return 1

    sources = parse_yaml_lite(SOURCES_FILE)
    print(f"📋 已加载 {len(sources)} 个新闻源")

    today = datetime.now().strftime("%Y-%m-%d")
    out_dir = NEWS_RAW_DIR / today
    out_dir.mkdir(parents=True, exist_ok=True)

    success = 0
    failed = 0
    skipped = 0

    for s in sources:
        name = s.get("name", "unknown")
        url = s.get("url", "")
        enabled = s.get("enabled", True)

        if not enabled:
            print(f"⏭  {name}: 已禁用")
            skipped += 1
            continue
        if s.get("type") == "rss":
            # RSS 类（如刘备）由专门脚本处理，这里不重复
            print(f"⏭  {name}: RSS 类源由 fetch_liubei.py 处理")
            skipped += 1
            continue

        try:
            print(f"⬇️  {name}: {url}")
            text, ct = http_get(url)
            ext = ".json" if "json" in ct.lower() else ".html"
            out_file = out_dir / f"{name}{ext}"
            out_file.write_text(text, encoding="utf-8")
            print(f"   ✓ {len(text)} 字节 → {out_file.relative_to(ROOT)}")
            success += 1
        except urllib.error.HTTPError as e:
            print(f"   ❌ HTTP {e.code}: {e.reason}", file=sys.stderr)
            failed += 1
        except Exception as e:
            print(f"   ❌ {type(e).__name__}: {e}", file=sys.stderr)
            failed += 1

    print(f"\n✅ 成功: {success}, 失败: {failed}, 跳过: {skipped}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
