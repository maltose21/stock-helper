# Hermes 部署指南

## 概述

stock-helper 自动化投资助手，部署在 hermes Linux 服务器上，通过 cron 每日自动执行 5 个定时任务。

## 前置条件

### 系统依赖

```bash
# Python 3.9+
sudo apt install python3 python3-pip git

# Python 包
pip3 install akshare requests

# LLM CLI（二选一）
# 方案 A: claude CLI
curl -fsSL https://claude.ai/install | sh
claude auth login

# 方案 B: 自定义 LLM 调用脚本（替换 claude -p）
# 见下方"LLM 适配"章节
```

### 克隆仓库

```bash
cd ~
git clone https://github.com/maltose21/stock-helper.git
cd stock-helper
```

### 环境变量

在 `~/.bashrc` 或 `~/.profile` 中添加：

```bash
# 飞书推送（必填）
export FEISHU_WEBHOOK="https://open.feishu.cn/open-apis/bot/v2/hook/YOUR_HOOK_ID"
export FEISHU_SECRET="YOUR_SECRET"

# 可选：dry run 模式
# export FEISHU_DRY_RUN=1
```

## Cron 时间安排

```
# stock-helper 自动化任务（工作日执行）
# ┌───── 分钟 (0-59)
# │ ┌───── 小时 (0-23)
# │ │ ┌───── 日 (1-31)
# │ │ │ ┌───── 月 (1-12)
# │ │ │ │ ┌───── 星期 (1-5 = Mon-Fri)
# │ │ │ │ │

# 18:30 - KB 刷新（拉文章 + 新闻 + 重建知识库 + 蒸馏 recent.md）
30 18 * * 1-5 cd ~/stock-helper && bash scripts/refresh.sh >> logs/refresh.log 2>&1

# 19:00 - 次日 TOP 10 生成 + 推送 GitHub（Actions 转飞书）
0  19 * * 1-5 cd ~/stock-helper && bash scripts/daily_run.sh >> logs/daily.log 2>&1

# 19:30 - 自我复盘（对比昨日建议 vs 今日实际 → 沉淀 lessons）
30 19 * * 1-5 cd ~/stock-helper && bash scripts/hermes_self_review.sh >> logs/review.log 2>&1

# 08:30 - 开盘建议（基于持仓 + 昨晚数据 → 推送飞书）
30  8 * * 1-5 cd ~/stock-helper && bash scripts/hermes_morning.sh >> logs/morning.log 2>&1

# 15:30 - 收盘总结（拉行情 + 计算盈亏 → 推送飞书）
30 15 * * 1-5 cd ~/stock-helper && bash scripts/hermes_evening.sh >> logs/evening.log 2>&1
```

安装 cron：

```bash
mkdir -p ~/stock-helper/logs
crontab -e  # 粘贴上面的内容
```

## 任务执行顺序图

```
         18:30         19:00         19:30
  ┌──────────┐  ┌──────────┐  ┌──────────┐
  │ refresh  │→│ daily_run │→│  review  │
  │  (KB)    │  │ (TOP 10) │  │(lessons) │
  └──────────┘  └──────────┘  └──────────┘
                                    ↓
         08:30                   lessons.md 更新
  ┌──────────┐
  │ morning  │ ← 读 top30 + portfolio + lessons
  │(开盘建议)│
  └──────────┘
         ↓
       飞书推送
         
         15:30
  ┌──────────┐
  │ evening  │ ← 拉今日行情 + 对比早间建议
  │(收盘总结)│
  └──────────┘
         ↓
       飞书推送 + 更新 portfolio.json
```

## 需要新建的 Hermes 脚本

以下三个脚本需要在 hermes 上创建（现有 refresh.sh / daily_run.sh 直接复用）：

### `scripts/hermes_morning.sh`

```bash
#!/bin/bash
set -uo pipefail
cd "$(dirname "$0")/.."

DOW=$(date +%u)
[ "$DOW" -gt 5 ] && exit 0

TODAY=$(date +%F)
WEEKDAY=$(date +%A)

# 读取输入文件
PORTFOLIO=$(cat scripts/prompts/user_portfolio.json)
RECENT=$(cat knowledge_base/recent.md)
EVERGREEN=$(cat knowledge_base/evergreen.md)
LESSONS=$(cat knowledge_base/lessons.md)
TOP30=$(cat knowledge_base/top30_candidates.json)

# 提取主线摘要
MAIN_LINES=$(python3 -c "
import json
d = json.loads(open('knowledge_base/top30_candidates.json').read())
print(', '.join(d.get('main_line_sectors', ['无明显主线'])))
")

# 格式化候选表（用 Python 辅助）
TABLES=$(python3 -c "
import json
d = json.loads(open('knowledge_base/top30_candidates.json').read())
# ... 格式化逻辑同 daily_advice.py 中的 format_candidates_table
")

# 拼 prompt（从 morning_advice_prompt.md 模板填充变量）
PROMPT=$(python3 scripts/hermes_build_prompt.py morning "$TODAY" "$WEEKDAY")

# 调 LLM
RESULT=$(echo "$PROMPT" | claude -p --max-tokens 2000)

# 写文件
mkdir -p morning
echo "$RESULT" > "morning/$TODAY.md"

# 推送飞书
python3 scripts/push_feishu.py "morning/$TODAY.md"

echo "[$(date '+%F %T')] ✅ morning advice done"
```

### `scripts/hermes_evening.sh`

```bash
#!/bin/bash
set -uo pipefail
cd "$(dirname "$0")/.."

DOW=$(date +%u)
[ "$DOW" -gt 5 ] && exit 0

TODAY=$(date +%F)

# 1. 拉今日收盘行情
python3 scripts/fetch_universe.py
python3 scripts/score_universe.py

# 2. 拼 prompt + 调 LLM
PROMPT=$(python3 scripts/hermes_build_prompt.py evening "$TODAY")
RESULT=$(echo "$PROMPT" | claude -p --max-tokens 2000)

# 3. 写文件 + 推送
mkdir -p evening
echo "$RESULT" > "evening/$TODAY.md"
python3 scripts/push_feishu.py "evening/$TODAY.md"

# 4. 更新 portfolio.json 中的 current 字段
python3 scripts/hermes_update_portfolio.py

echo "[$(date '+%F %T')] ✅ evening summary done"
```

### `scripts/hermes_self_review.sh`

```bash
#!/bin/bash
set -uo pipefail
cd "$(dirname "$0")/.."

DOW=$(date +%u)
[ "$DOW" -gt 5 ] && exit 0

TODAY=$(date +%F)
# 周一回看周五的建议
if [ "$DOW" -eq 1 ]; then
    YESTERDAY=$(date -d "3 days ago" +%F)
else
    YESTERDAY=$(date -d "1 day ago" +%F)
fi

# 找昨日建议文件（为今天生成的）
ADVICE_FILE="daily/$TODAY.md"
[ ! -f "$ADVICE_FILE" ] && echo "No advice for $TODAY, skip" && exit 0

# 拼 prompt + 调 LLM
PROMPT=$(python3 scripts/hermes_build_prompt.py review "$TODAY" "$YESTERDAY")
RESULT=$(echo "$PROMPT" | claude -p --max-tokens 2000)

# 判断是否有新教训
if echo "$RESULT" | grep -q "无新增教训"; then
    echo "[$(date '+%F %T')] No new lessons"
    exit 0
fi

# 追加到 lessons.md
{
    echo ""
    echo "---"
    echo ""
    echo "$RESULT"
} >> knowledge_base/lessons.md

# commit + push
git add knowledge_base/lessons.md
git commit -m "lessons: review $TODAY (vs $YESTERDAY advice)"
git push || echo "push failed (non-fatal)"

echo "[$(date '+%F %T')] ✅ self-review done, lessons updated"
```

## LLM 适配

如果 hermes 不用 `claude` CLI 而用其他模型：

```bash
# 创建一个 wrapper 脚本 ~/bin/llm-call
#!/bin/bash
# 从 stdin 读 prompt，stdout 输出结果
# 替换为你的 API 调用（OpenAI / Anthropic / local model）
curl -s https://api.anthropic.com/v1/messages \
  -H "x-api-key: $ANTHROPIC_API_KEY" \
  -H "content-type: application/json" \
  -d "$(jq -n --arg p "$(cat)" '{model:"claude-sonnet-4-20250514",max_tokens:2000,messages:[{role:"user",content:$p}]}')" \
  | jq -r '.content[0].text'
```

然后在所有脚本中把 `claude -p` 替换为 `~/bin/llm-call`。

## 用户持仓更新

`scripts/prompts/user_portfolio.json` 需要保持最新：

1. **自动更新**：`hermes_evening.sh` 在收盘后自动用今日收盘价更新 `current` 字段
2. **手动更新**：用户买卖后需要修改 `shares` / 新增/删除持仓条目
3. **格式说明**：见 `user_portfolio.json` 文件内字段

## 监控

```bash
# 检查今天是否正常执行
tail -5 ~/stock-helper/logs/morning.log
tail -5 ~/stock-helper/logs/evening.log
tail -5 ~/stock-helper/logs/review.log

# 检查飞书是否收到
# → 看飞书群里有没有今天的消息

# 手动补跑
cd ~/stock-helper
bash scripts/hermes_morning.sh   # 开盘建议
bash scripts/hermes_evening.sh   # 收盘总结
bash scripts/hermes_self_review.sh  # 复盘
```

## 首次部署检查清单

- [ ] git clone 成功
- [ ] `python3 scripts/fetch_universe.py` 能拉到行情
- [ ] `FEISHU_DRY_RUN=1 python3 scripts/push_feishu.py daily/2026-06-02.md` 正常
- [ ] `claude -p "hello"` 或自定义 LLM wrapper 正常返回
- [ ] crontab -l 显示 5 条任务
- [ ] 等一个交易日验证完整链路
