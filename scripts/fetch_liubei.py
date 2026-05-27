#!/usr/bin/env python3
"""
fetch_liubei.py - 从 fugay.com RSS 拉取刘备教授新文章

行为：
1. 拉 https://www.fugay.com/index.xml 解析 RSS items
2. 对每条 item，检查 ~/Documents/刘备教授/YYYY-MM-DD - {title}.md 是否已存在
3. 不存在则 GET 文章页 → 提取 <article> 内容 → 转 markdown → 写盘
4. 命名严格匹配现有约定（YYYY-MM-DD - 标题.md）
"""

import re
import sys
import urllib.request
from pathlib import Path
from html.parser import HTMLParser
from email.utils import parsedate_to_datetime

ARTICLES_DIR = Path.home() / "Documents/刘备教授"
RSS_URL = "https://www.fugay.com/index.xml"
ARTICLE_URL_PATTERN = re.compile(r"^https?://www\.fugay\.com/\d{4}/\d{2}/\d{2}-")
USER_AGENT = "Mozilla/5.0 (stock-helper-fetch; +https://github.com/anthropics/claude-code)"
TIMEOUT = 15


def http_get(url):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return resp.read().decode("utf-8", errors="replace")


def parse_rss_items(xml_text):
    """轻量 RSS 解析（不依赖 feedparser）"""
    items = []
    for m in re.finditer(r"<item>(.*?)</item>", xml_text, re.DOTALL):
        block = m.group(1)
        title = _xml_field(block, "title")
        link = _xml_field(block, "link")
        pub_date = _xml_field(block, "pubDate")
        description = _xml_field(block, "description")
        if not (title and link and pub_date):
            continue
        try:
            dt = parsedate_to_datetime(pub_date)
            date_str = dt.strftime("%Y-%m-%d")
        except Exception:
            continue
        items.append({
            "title": title,
            "link": link,
            "date": date_str,
            "summary": description,
        })
    return items


def _xml_field(block, tag):
    m = re.search(rf"<{tag}>(.*?)</{tag}>", block, re.DOTALL)
    if not m:
        return ""
    text = m.group(1).strip()
    # 解 CDATA
    cdata = re.match(r"<!\[CDATA\[(.*?)\]\]>", text, re.DOTALL)
    if cdata:
        text = cdata.group(1).strip()
    return text


class ArticleExtractor(HTMLParser):
    """提取 <article> 标签内的纯文本"""
    def __init__(self):
        super().__init__()
        self.in_article = False
        self.depth = 0
        self.text_chunks = []
        self.skip_tags = {"script", "style", "nav", "footer", "aside"}
        self.in_skip = False

    def handle_starttag(self, tag, attrs):
        if tag == "article":
            self.in_article = True
            self.depth = 1
        elif self.in_article:
            self.depth += 1
            if tag in self.skip_tags:
                self.in_skip = True
            if tag in ("p", "h1", "h2", "h3", "h4", "li", "blockquote"):
                self.text_chunks.append("\n\n")

    def handle_endtag(self, tag):
        if tag == "article" and self.in_article:
            self.depth -= 1
            if self.depth <= 0:
                self.in_article = False
        elif self.in_article:
            self.depth -= 1
            if tag in self.skip_tags:
                self.in_skip = False

    def handle_data(self, data):
        if self.in_article and not self.in_skip:
            self.text_chunks.append(data)

    def get_text(self):
        text = "".join(self.text_chunks)
        # 清理多余空行
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()


def article_to_markdown(html_text, title, date, summary):
    """从文章页 HTML 提取并构造 markdown"""
    extractor = ArticleExtractor()
    try:
        extractor.feed(html_text)
    except Exception:
        pass
    body = extractor.get_text()

    # 清理摘要里的 HTML 实体
    summary_clean = re.sub(r"<[^>]+>", "", summary)
    summary_clean = (summary_clean
                     .replace("&lt;", "<").replace("&gt;", ">")
                     .replace("&amp;", "&").replace("&#34;", '"')
                     .replace("&#39;", "'").replace("&#xA;", "\n"))
    summary_clean = re.sub(r"\s+", " ", summary_clean).strip()

    md = f"# {title}\n\n"
    md += f"date: {date}\n\n"
    md += "---\n\n"
    md += f"{summary_clean}\n\n"
    md += "---\n\n"
    md += body
    return md


def safe_filename(date, title):
    """构造与现有约定一致的文件名 YYYY-MM-DD - title.md"""
    safe_title = re.sub(r'[/\\:*?"<>|]', '', title).strip()
    return f"{date} - {safe_title}.md"


def main():
    ARTICLES_DIR.mkdir(parents=True, exist_ok=True)
    print(f"📡 拉取 RSS: {RSS_URL}")

    try:
        xml_text = http_get(RSS_URL)
    except Exception as e:
        print(f"❌ RSS 拉取失败: {e}", file=sys.stderr)
        return 1

    items = parse_rss_items(xml_text)
    print(f"📄 RSS 共 {len(items)} 条")

    new_count = 0
    skip_count = 0
    fail_count = 0

    for item in items:
        # 只处理日期型文章 URL，跳过"关于"等非文章页
        if not ARTICLE_URL_PATTERN.match(item["link"]):
            continue

        fname = safe_filename(item["date"], item["title"])
        fpath = ARTICLES_DIR / fname

        if fpath.exists():
            skip_count += 1
            continue

        # 兼容历史命名（标题前可能有零宽字符等）
        existing = list(ARTICLES_DIR.glob(f"{item['date']} - *.md"))
        if existing:
            skip_count += 1
            continue

        try:
            print(f"⬇️  {item['date']} - {item['title']}")
            html_text = http_get(item["link"])
            md = article_to_markdown(html_text, item["title"], item["date"], item["summary"])
            fpath.write_text(md, encoding="utf-8")
            new_count += 1
        except Exception as e:
            print(f"   ❌ 失败: {e}", file=sys.stderr)
            fail_count += 1

    print(f"\n✅ 新增: {new_count}, 跳过: {skip_count}, 失败: {fail_count}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
