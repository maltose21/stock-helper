#!/bin/bash
# daily_run.sh - 每日 19:00 生成次日建议 + 推送到微信
#
# 前提：每日 18:30 refresh.sh 已跑完，knowledge_base 是最新的。
# 若 refresh.sh 当天没跑，distill_recent 的 last_updated 会大于 24h，建议先看 refresh.log。
#
# 环境变量：见 push_wechat.py 文件头
#
# cron 行（工作日 19:00；周末 A 股休市，跳过）：
#   0 19 * * 1-5 bash ~/.claude/skills/stock-helper/scripts/daily_run.sh >> ~/.claude/skills/stock-helper/daily.log 2>&1
#
# 也支持手动调用：bash daily_run.sh

set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(dirname "$SCRIPT_DIR")"
cd "$SKILL_DIR"

TS=$(date "+%F %T")
echo "[$TS] === daily_run begin ==="

# ─── Step 1: 检查 KB 时效性 ───────────────────────────────
META="$SKILL_DIR/knowledge_base/meta.json"
if [ -f "$META" ]; then
    LAST=$(python3 -c "import json,sys; print(json.load(open('$META')).get('last_updated','?'))")
    echo "[$(date '+%F %T')] KB last_updated: $LAST"
else
    echo "[$(date '+%F %T')] ⚠️  meta.json 不存在，建议先运行 refresh.sh"
fi

# ─── Step 2: 生成次日建议 ──────────────────────────────────
echo "[$(date '+%F %T')] [1/2] daily_advice.py"
ADVICE_FILE=$(python3 "$SCRIPT_DIR/daily_advice.py" | tail -1)
RC=$?
if [ $RC -ne 0 ] || [ ! -f "$ADVICE_FILE" ]; then
    echo "[$(date '+%F %T')] ❌ daily_advice.py 失败 (exit=$RC)，终止"
    exit 1
fi
echo "[$(date '+%F %T')] ✅ 建议文件: $ADVICE_FILE"

# ─── Step 3: 推送到微信 ────────────────────────────────────
echo "[$(date '+%F %T')] [2/2] push_wechat.py"
python3 "$SCRIPT_DIR/push_wechat.py" "$ADVICE_FILE"
PUSH_RC=$?
if [ $PUSH_RC -ne 0 ]; then
    echo "[$(date '+%F %T')] ⚠️  推送失败 (exit=$PUSH_RC)，建议文件已保存"
fi

echo "[$(date '+%F %T')] === daily_run end (advice=$ADVICE_FILE, push=$PUSH_RC) ==="
