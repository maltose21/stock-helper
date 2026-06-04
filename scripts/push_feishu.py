#!/usr/bin/env python3
"""
push_feishu.py - 把次日建议推到飞书自定义机器人（签名校验模式）。

接口：POST {FEISHU_WEBHOOK}
请求体（text）：
    {"timestamp": "...", "sign": "...", "msg_type": "text", "content": {"text": "..."}}

环境变量（必填）：
    FEISHU_WEBHOOK  形如 https://open.feishu.cn/open-apis/bot/v2/hook/xxx
    FEISHU_SECRET   签名校验密钥（机器人创建时复制）

可选：
    FEISHU_DRY_RUN=1  只打印不发送

调用：
    python3 push_feishu.py <markdown_file>
"""

import base64
import hashlib
import hmac
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

CHUNK_SIZE = 28000  # 飞书 text 消息单条上限 ~30KB，留余量


def gen_sign(timestamp: int, secret: str) -> str:
    """飞书签名：HMAC-SHA256(secret, "{timestamp}\n{secret}") → base64"""
    string_to_sign = f"{timestamp}\n{secret}"
    hmac_code = hmac.new(
        string_to_sign.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).digest()
    return base64.b64encode(hmac_code).decode("utf-8")


def chunk(text: str, size: int = CHUNK_SIZE) -> list[str]:
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


def push(webhook: str, secret: str, text: str, dry_run: bool = False) -> bool:
    ts = int(time.time())
    sign = gen_sign(ts, secret)
    payload = {
        "timestamp": str(ts),
        "sign": sign,
        "msg_type": "text",
        "content": {"text": text},
    }
    if dry_run:
        print(f"[DRY-RUN] POST {webhook}")
        print(f"[DRY-RUN] sign={sign[:20]}… text[{len(text)}]={text[:80]}…")
        return True

    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        webhook,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            txt = resp.read().decode("utf-8", errors="replace")
            ok = resp.status == 200 and '"code":0' in txt.replace(" ", "")
            mark = "✅" if ok else "❌"
            print(f"{mark} HTTP {resp.status} | {txt[:200]}")
            return ok
    except urllib.error.HTTPError as e:
        sys.stderr.write(f"❌ HTTPError {e.code}: {e.read().decode('utf-8', errors='replace')[:200]}\n")
        return False
    except (urllib.error.URLError, TimeoutError) as e:
        sys.stderr.write(f"❌ URLError: {e}\n")
        return False


def main() -> int:
    if len(sys.argv) < 2:
        sys.stderr.write("用法: push_feishu.py <markdown_file>\n")
        return 2

    md_path = Path(sys.argv[1]).expanduser()
    if not md_path.exists():
        sys.stderr.write(f"❌ 文件不存在: {md_path}\n")
        return 2

    webhook = os.environ.get("FEISHU_WEBHOOK", "").strip()
    secret = os.environ.get("FEISHU_SECRET", "").strip()
    dry_run = os.environ.get("FEISHU_DRY_RUN", "").strip() == "1"

    if not dry_run and not (webhook and secret):
        sys.stderr.write("❌ 缺少 FEISHU_WEBHOOK / FEISHU_SECRET，或 FEISHU_DRY_RUN=1 试跑\n")
        return 3

    content = md_path.read_text(encoding="utf-8")
    parts = chunk(content)
    print(f"📤 推送 {md_path.name}（{len(content)} 字符，切 {len(parts)} 段）")

    ok_count = 0
    for i, part in enumerate(parts, 1):
        prefix = f"[{i}/{len(parts)}]\n\n" if len(parts) > 1 else ""
        if push(webhook, secret, prefix + part, dry_run=dry_run):
            ok_count += 1
        else:
            sys.stderr.write(f"⚠️  第 {i} 段推送失败\n")

    print(f"完成: {ok_count}/{len(parts)} 段成功")
    return 0 if ok_count == len(parts) else 1


if __name__ == "__main__":
    sys.exit(main())
