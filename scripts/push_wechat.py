#!/usr/bin/env python3
"""
push_wechat.py - 把次日建议推到个人微信（wechatbot-webhook 协议）。

参考：https://github.com/danni-cool/wechatbot-webhook
接口：POST {WECHATBOT_URL}?token={WECHATBOT_TOKEN}
请求体：{"to": "<昵称>", "data": {"content": "<文本>"}}

环境变量（必填）：
    WECHATBOT_URL          形如 http://host:3001/webhook/msg/v2
    WECHATBOT_TOKEN        webhook 鉴权 token
    WECHATBOT_TO           推送目标昵称（个人微信号备注名或群名）

可选：
    WECHATBOT_DRY_RUN=1    只打印不发送

调用：
    python3 push_wechat.py <markdown_file>
"""

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

CHUNK_SIZE = 1800  # 微信单条文本 ≤ ~2000 字，留余量


def chunk(text: str, size: int = CHUNK_SIZE) -> list[str]:
    """按段落优先切分，避免在句子中间断开。"""
    if len(text) <= size:
        return [text]
    chunks, buf = [], ""
    for para in text.split("\n\n"):
        if len(buf) + len(para) + 2 > size and buf:
            chunks.append(buf)
            buf = para
        else:
            buf = f"{buf}\n\n{para}" if buf else para
    if buf:
        chunks.append(buf)
    return chunks


def push(url: str, token: str, to: str, content: str, dry_run: bool = False) -> bool:
    payload = {"to": to, "data": {"content": content}}
    full_url = f"{url}?token={token}"
    if dry_run:
        print(f"[DRY-RUN] POST {full_url}")
        print(f"[DRY-RUN] payload: to={to}, content[{len(content)}]={content[:80]}…")
        return True

    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        full_url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            text = resp.read().decode("utf-8", errors="replace")
            print(f"✅ HTTP {resp.status} | {text[:200]}")
            return resp.status == 200
    except urllib.error.HTTPError as e:
        sys.stderr.write(f"❌ HTTPError {e.code}: {e.read().decode('utf-8', errors='replace')[:200]}\n")
        return False
    except (urllib.error.URLError, TimeoutError) as e:
        sys.stderr.write(f"❌ URLError: {e}\n")
        return False


def main() -> int:
    if len(sys.argv) < 2:
        sys.stderr.write("用法: push_wechat.py <markdown_file>\n")
        return 2

    md_path = Path(sys.argv[1]).expanduser()
    if not md_path.exists():
        sys.stderr.write(f"❌ 文件不存在: {md_path}\n")
        return 2

    url = os.environ.get("WECHATBOT_URL", "").strip()
    token = os.environ.get("WECHATBOT_TOKEN", "").strip()
    to = os.environ.get("WECHATBOT_TO", "").strip()
    dry_run = os.environ.get("WECHATBOT_DRY_RUN", "").strip() == "1"

    if not dry_run and not (url and token and to):
        sys.stderr.write(
            "❌ 缺少环境变量。请设置 WECHATBOT_URL / WECHATBOT_TOKEN / WECHATBOT_TO，"
            "或 WECHATBOT_DRY_RUN=1 试跑\n"
        )
        return 3

    content = md_path.read_text(encoding="utf-8")
    parts = chunk(content)
    print(f"📤 推送 {md_path.name}（{len(content)} 字符，切 {len(parts)} 段）→ {to or '(dry-run)'}")

    ok_count = 0
    for i, part in enumerate(parts, 1):
        prefix = f"[{i}/{len(parts)}] " if len(parts) > 1 else ""
        if push(url, token, to, prefix + part, dry_run=dry_run):
            ok_count += 1
        else:
            sys.stderr.write(f"⚠️  第 {i} 段推送失败\n")

    print(f"完成: {ok_count}/{len(parts)} 段成功")
    return 0 if ok_count == len(parts) else 1


if __name__ == "__main__":
    sys.exit(main())
