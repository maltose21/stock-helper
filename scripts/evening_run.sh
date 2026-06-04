#!/bin/bash
# evening_run.sh - 一键晚间流水线：刷新KB → 生成建议 → 复盘
#
# 合并 refresh.sh + daily_run.sh + 复盘步骤
# 使用 caffeinate -i 防止空闲休眠
#
# cron 行（工作日 19:00）：
#   0 19 * * 1-5 bash ~/.claude/skills/stock-helper/scripts/evening_run.sh >> ~/.claude/skills/stock-helper/evening.log 2>&1

set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(dirname "$SCRIPT_DIR")"
cd "$SKILL_DIR"

log() { echo "[$(date '+%F %T')] $*"; }

log "=== evening_run begin ==="

# ─── 周末跳过 ────────────────────────────────────────────
DOW=$(date +%u)
if [ "$DOW" -gt 5 ]; then
    log "Weekend (day=$DOW), skip"
    exit 0
fi

# ─── Step 1: 刷新知识库 ──────────────────────────────────
log "[1/3] refresh.sh (KB update)"
caffeinate -i bash "$SCRIPT_DIR/refresh.sh"
RC1=$?
if [ $RC1 -ne 0 ]; then
    log "refresh.sh exited $RC1 (non-fatal, continuing)"
fi

# ─── Step 2: 生成建议 + 推送 GitHub ──────────────────────
log "[2/3] daily_run.sh (advice + push)"
caffeinate -i bash "$SCRIPT_DIR/daily_run.sh"
RC2=$?
if [ $RC2 -ne 0 ]; then
    log "daily_run.sh exited $RC2 (non-fatal, continuing to review)"
fi

# ─── Step 3: 复盘（对比昨日建议 vs 今日实际）─────────────
log "[3/3] review (yesterday's advice vs today's actual)"

TODAY=$(date +%F)
# 周一回看周五
if [ "$DOW" -eq 1 ]; then
    YESTERDAY=$(date -v-3d +%F)
else
    YESTERDAY=$(date -v-1d +%F)
fi

YESTERDAY_FILE="$SKILL_DIR/daily/$YESTERDAY.md"

if [ ! -f "$YESTERDAY_FILE" ]; then
    log "No advice file for $YESTERDAY ($YESTERDAY_FILE), skip review"
    log "=== evening_run end ==="
    exit 0
fi

CANDIDATES_FILE="$SKILL_DIR/knowledge_base/top30_candidates.json"
if [ ! -f "$CANDIDATES_FILE" ]; then
    log "No top30_candidates.json, skip review"
    log "=== evening_run end ==="
    exit 0
fi

log "Reviewing: $YESTERDAY_FILE vs today's market data"

# 构建复盘 prompt
YESTERDAY_CONTENT=$(cat "$YESTERDAY_FILE")
CANDIDATES_SNIPPET=$(head -200 "$CANDIDATES_FILE")

REVIEW_PROMPT="你是投资复盘助手。对比昨日建议 vs 今日实际走势，找出预测偏差，提炼可执行的经验教训。

## 昨日建议（$YESTERDAY）

$YESTERDAY_CONTENT

## 今日实际行情数据（$TODAY）

$CANDIDATES_SNIPPET

## 输出要求

按 lessons.md 格式输出新增教训（如果有的话），格式：

## $TODAY（针对 $YESTERDAY 清单的复盘）

### 失误 N：标题
**事实**：...
**根因**：...
**改进**：...

如果今日走势与建议完全一致（无失误），仅输出一行：无新增教训。
不要输出其他内容。"

REVIEW_OUT=$(echo "$REVIEW_PROMPT" | caffeinate -i claude -p --max-tokens 2000 2>/dev/null)
RC3=$?

if [ $RC3 -ne 0 ]; then
    log "claude CLI failed (exit=$RC3), skip review"
    log "=== evening_run end ==="
    exit 0
fi

# 判断是否有新教训
if echo "$REVIEW_OUT" | grep -q "无新增教训"; then
    log "No new lessons today"
else
    # 追加到 lessons.md
    {
        echo ""
        echo "---"
        echo ""
        echo "$REVIEW_OUT"
    } >> "$SKILL_DIR/knowledge_base/lessons.md"
    log "New lessons appended to knowledge_base/lessons.md"

    # commit lessons 更新
    cd "$SKILL_DIR"
    git add "knowledge_base/lessons.md"
    if ! git diff --cached --quiet; then
        git commit -m "lessons: review $TODAY (vs $YESTERDAY advice)"
        git push 2>/dev/null || log "git push lessons failed (non-fatal)"
    fi
fi

log "=== evening_run end ==="
