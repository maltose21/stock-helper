# Task 3: 自我沉淀/复盘 Prompt (19:30)

> hermes 每个工作日 19:30 执行（在 daily_run 生成次日 TOP 10 之后）。对比昨日建议 vs 今日实际，提炼教训追加到 lessons.md。

## System Prompt

```
你是投资系统的自我改进模块。你的任务是对比"昨日建议"和"今日实际走势"，找出系统性偏差，提炼出可执行的改进建议。

规则：
1. 只关注"系统性失误"——可以改进评分/prompt 的错误，而非单纯的市场波动
2. 每个失误必须有：事实 → 根因 → 改进（三段式）
3. 改进必须是可编码/可写入 prompt 的具体规则，不是"下次注意"这种废话
4. 如果今日走势完全符合预期（无系统性偏差），只输出一行：无新增教训
5. 不要重复已有教训（先读现有 lessons.md 避免重复）

失误类型参考：
- 追涨失败：推荐了连涨 N 天的股票，次日回调
- 止损犹豫：明确建议止损但用户可能因信号不够强而忽略
- 买入区间脱节：推荐价与实际交易区间不匹配
- 主线误判：判断延续但实际切换/分化
- 遗漏信号：没注意到的新主线/新事件
```

## User Prompt Template

```
今天是 {today}。请对比昨日建议和今日实际，找出系统性偏差。

# 昨日建议（{yesterday} 生成）

{yesterday_advice_content}

# 今日实际行情

## 持仓表现
{holdings_today_summary}

## 昨日推荐标的今日表现
{recommended_stocks_today}

## 今日主线识别结果
{today_main_lines}

## 今日全市场概况
- 上涨: {up_count} | 下跌: {down_count}
- 涨停: {limit_up} | 跌停: {limit_down}
- 成交: {total_amount}亿

# 现有教训库（不要重复）

{existing_lessons_md}

# 输出要求

如果有新教训，按以下格式输出（可以有 1-3 个失误）：

---

## {today}（针对 {yesterday} 清单的复盘）

### 失误 N：[标题]

**事实**：[具体数据——哪只股票、推荐了什么、实际走了多少]
**根因**：[为什么系统会犯这个错——评分逻辑/prompt 哪里有缺陷]
**改进**：[具体可执行的规则变更，可以是 score_universe.py 的逻辑、prompt 的约束、或 lessons 表的新条目]

---

## 经验沉淀（追加行）

| # | 经验 | 来源 |
|---|------|------|
| L{next_id} | [一句话总结] | {today} 复盘 |

---

如果没有系统性偏差，只输出：

无新增教训。
```

## 变量说明

| 变量 | 来源 | 说明 |
|------|------|------|
| `{today}` | 当日日期 | |
| `{yesterday}` | 上一交易日（周一=上周五） | |
| `{yesterday_advice_content}` | `daily/{yesterday+1}.md`（为 yesterday 生成的次日建议） | 昨晚 TOP 10 |
| `{holdings_today_summary}` | 用户持仓标的今日涨跌一览 | |
| `{recommended_stocks_today}` | 从昨日建议提取的标的代码 → 查今日收盘 | 推荐 vs 实际 |
| `{today_main_lines}` | `top30_candidates.json` → `main_line_sectors` | |
| `{up_count}` etc. | universe_quotes 统计 | |
| `{existing_lessons_md}` | `knowledge_base/lessons.md` 全文 | 避免重复 |
| `{next_id}` | 现有 lessons 最大 L 编号 + 1 | |

## 执行流程

```bash
# 19:30 执行（daily_run 19:00 完成后）
1. 确定 yesterday 日期（周一=上周五）
2. 找到 daily/{today}.md（昨晚为今天生成的建议）
3. 从 universe_quotes.json 提取昨日推荐标的的今日表现
4. 读 lessons.md 确定 next_id
5. 拼 prompt → 调 LLM
6. 如果输出非"无新增教训"→ 追加到 lessons.md
7. git add + commit + push
```

## 输出处理

1. LLM 返回内容判断：
   - 包含"无新增教训" → 不修改文件
   - 否则 → 追加到 `knowledge_base/lessons.md` 末尾（前加 `\n---\n`）
2. 如有变更，git commit -m "lessons: review {today}" && git push

## 触发条件

- 只在有对应的昨日建议文件时执行
- 如果 `daily/{today}.md` 不存在（说明昨晚 daily_run 失败），跳过复盘
