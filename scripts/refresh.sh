#!/bin/bash
# refresh.sh - stock-helper 知识库自动刷新管道
#
# 流程：拉刘备新文章 → 拉财经新闻 → 重建 KB → LLM 蒸馏 recent.md → 更新 meta
# 失败容忍：单步失败不阻塞后续步骤（除了最关键的 build_knowledge_base）
#
# cron 安装方式（工作日 18:30）：
#   crontab -e
#   30 18 * * 1-5 bash ~/.claude/skills/stock-helper/scripts/refresh.sh >> ~/.claude/skills/stock-helper/refresh.log 2>&1

set -u

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(dirname "$SCRIPT_DIR")"
cd "$ROOT"

ts() { date "+%Y-%m-%d %H:%M:%S"; }
log() { echo "[$(ts)] $*"; }

log "=== refresh start ==="

log "[1/4] fetch_liubei.py"
python3 "$SCRIPT_DIR/fetch_liubei.py" || log "  ⚠️ fetch_liubei 失败，继续"

log "[2/4] fetch_news.py"
python3 "$SCRIPT_DIR/fetch_news.py" || log "  ⚠️ fetch_news 失败，继续"

log "[3/4] build_knowledge_base.py（关键步骤）"
if ! python3 "$SCRIPT_DIR/build_knowledge_base.py"; then
    log "  ❌ build_knowledge_base 失败，终止"
    exit 1
fi

log "[4/4] distill_recent.py"
python3 "$SCRIPT_DIR/distill_recent.py" || log "  ⚠️ distill_recent 失败（可能因 claude CLI 不可用），continued with skeleton"

# 更新 meta.json
META="$ROOT/knowledge_base/meta.json"
NOW_UTC=$(date -u +%FT%TZ)
ARTICLE_COUNT=$(ls "$HOME/Documents/刘备教授" 2>/dev/null | grep -c '\.md$' || echo 0)
cat > "$META" <<EOF
{
  "last_updated": "$NOW_UTC",
  "article_count": $ARTICLE_COUNT,
  "refresh_script": "scripts/refresh.sh"
}
EOF

log "✅ refresh done. meta.json 已更新"
log "=== refresh end ==="
