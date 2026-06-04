#!/bin/bash
# daily_run.sh - 每日 19:00 生成次日建议 + push 到 GitHub（Actions 自动转发飞书）
#
# 流程：
# 1. fetch_universe + score_universe + daily_advice（本机 LLM）
# 2. 把 ~/Documents/stock-helper/daily/YYYY-MM-DD.md 同步到 repo 的 daily/ 目录
# 3. git commit + push → GitHub Actions on push 触发 push_feishu.py 转发
#
# 为什么不本机直推飞书：aTrust 拦截 open.feishu.cn 的 TLS 握手，本机推必挂。
# GitHub Actions 跑在境外，绕过 aTrust。
#
# cron 行（工作日 19:00；周末跳过）：
#   0 19 * * 1-5 bash ~/.claude/skills/stock-helper/scripts/daily_run.sh >> ~/.claude/skills/stock-helper/daily.log 2>&1

set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(dirname "$SCRIPT_DIR")"
cd "$SKILL_DIR"

TS=$(date "+%F %T")
echo "[$TS] === daily_run begin ==="

# ─── Step 1: 检查 KB 时效性 ───────────────────────────────
META="$SKILL_DIR/knowledge_base/meta.json"
if [ -f "$META" ]; then
    LAST=$(python3 -c "import json; print(json.load(open('$META')).get('last_updated','?'))")
    echo "[$(date '+%F %T')] KB last_updated: $LAST"
else
    echo "[$(date '+%F %T')] ⚠️  meta.json 不存在，建议先运行 refresh.sh"
fi

# ─── Step 2: 生成次日建议（本机 LLM）────────────────────
echo "[$(date '+%F %T')] [1/3] daily_advice.py"
ADVICE_FILE=$(python3 "$SCRIPT_DIR/daily_advice.py" | tail -1)
RC=$?
if [ $RC -ne 0 ] || [ ! -f "$ADVICE_FILE" ]; then
    echo "[$(date '+%F %T')] ❌ daily_advice.py 失败 (exit=$RC)，终止"
    exit 1
fi
echo "[$(date '+%F %T')] ✅ 建议文件: $ADVICE_FILE"

# ─── Step 3: 复制到 repo 的 daily/ 目录 ─────────────────
echo "[$(date '+%F %T')] [2/3] 复制到 repo/daily/"
mkdir -p "$SKILL_DIR/daily"
DEST="$SKILL_DIR/daily/$(basename "$ADVICE_FILE")"
cp "$ADVICE_FILE" "$DEST"
echo "[$(date '+%F %T')] ✅ 复制到: $DEST"

# ─── Step 4: git commit + push ────────────────────────
echo "[$(date '+%F %T')] [3/3] git commit + push"
cd "$SKILL_DIR"
git add "daily/$(basename "$ADVICE_FILE")"
if git diff --cached --quiet; then
    echo "[$(date '+%F %T')] ⚠️  无变更，跳过 push"
else
    git commit -m "daily: $(basename "$ADVICE_FILE" .md) advice"
    if git push 2>&1; then
        echo "[$(date '+%F %T')] ✅ pushed → GitHub Actions will forward to Feishu"
    else
        echo "[$(date '+%F %T')] ❌ git push 失败，建议文件已落盘但未推送"
        exit 2
    fi
fi

echo "[$(date '+%F %T')] === daily_run end ==="
