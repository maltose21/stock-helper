# Task 2: 收盘总结 Prompt (15:30)

> hermes 每个工作日 15:30 执行。拉取今日收盘行情 → 计算持仓盈亏 → 对比早间建议 → 预判明日方向。

## System Prompt

```
你是基于刘备教授投资哲学的私人投资复盘助手。你的任务是每个交易日收盘后，给用户一份简洁的盘后总结，包括：
1. 持仓逐只今日盈亏和累计盈亏
2. 今日推荐的执行情况对比
3. 市场结构分析（主线/板块/资金流向）
4. 明日方向预判

你对用户的持仓了如指掌，直接给结论，不废话。数字精确到小数点后两位。
```

## User Prompt Template

```
今天是 {today}，A 股已收盘。请基于今日行情数据，给出我的持仓盘后总结。

# 我的持仓（成本价）

{user_portfolio_json}

# 今日行情数据（持仓标的）

{holdings_today_quotes}

# 今日全市场评分结果

今日主线：{main_line_summary}
上涨: {up_count} | 下跌: {down_count} | 涨停: {limit_up} | 跌停: {limit_down}
成交额: {total_amount}亿

## 主线 TOP 20
{main_line_table}

## 价值 TOP 10
{value_table}

# 今早的操作建议（用于对比）

{morning_advice_content}

# 昨晚的 TOP 10 推荐（用于对比）

{yesterday_top10_content}

# 输出要求

按以下模板输出，不超过 1200 字：

---

## {today} 盘后总结

### 一、持仓表现

| 标的 | 昨收 | 今收 | 今日涨跌 | 累计盈亏 | 今日盈亏(元) | 信号 |
|------|------|------|---------|---------|------------|------|
| ... | ... | ... | +x.xx% | -x.xx% | ±xxx | ✅/⚠️/❌ |

**账户汇总**：
- 总市值: xxx | 今日盈亏: ±xxx (±x.xx%) | 累计: ±xxx

### 二、早间建议执行对比

| 建议操作 | 是否执行 | 结果 |
|---------|---------|------|
| P0: 止损xxx | ✅/❌ | 执行/未执行 → 今天又跌了x% |
| P1: 买入xxx | ... | ... |

### 三、昨晚 TOP 10 表现

| 标的 | 建议价 | 今收 | 涨跌 | 评价 |
|------|--------|------|------|------|
| ... | ... | ... | ... | ✅命中/❌偏差 |

加权推荐收益: ±x.xx%

### 四、市场结构

- 主线：{today_main_lines}（连续第 N 天 / 新出现）
- 涨跌比：{up_count}/{down_count} = {ratio}
- 资金特征：[虹吸/普涨/普跌/分化]

### 五、明日预判

| 板块 | 概率 | 逻辑 |
|------|------|------|
| ... | 高/中/低 | 一句话 |

**持仓关注点**：
- [最需要关注的 1-2 个持仓的明日风险/机会]

---

⚠️ 不构成投资建议，实盘操作风险自担。
```

## 变量说明

| 变量 | 来源 | 说明 |
|------|------|------|
| `{today}` | `date +%Y-%m-%d` | 当日日期 |
| `{user_portfolio_json}` | `scripts/prompts/user_portfolio.json` | 持仓成本数据 |
| `{holdings_today_quotes}` | 脚本从 `universe_quotes.json` 或 sina API 提取持仓标的今日行情 | 今收/昨收/涨跌% |
| `{main_line_summary}` | `top30_candidates.json` → `main_line_sectors` | 今日主线 |
| `{up_count}` / `{down_count}` | 从 universe_quotes 统计 | 涨跌家数 |
| `{limit_up}` / `{limit_down}` | 涨跌停数 | |
| `{total_amount}` | 总成交额(亿) | |
| `{main_line_table}` | `top30_candidates.json` → `top_main_line` | 今日评分 TOP 20 |
| `{value_table}` | `top30_candidates.json` → `top_value` | 今日价值 TOP 10 |
| `{morning_advice_content}` | `morning/{today}.md` | 今早建议全文 |
| `{yesterday_top10_content}` | `daily/{yesterday}.md` | 昨晚 TOP 10 全文 |

## 执行流程

```bash
# 15:30 收盘后执行
1. python3 scripts/fetch_universe.py          # 拉今日收盘行情
2. python3 scripts/score_universe.py          # 评分（供明日参考）
3. 从 universe_quotes.json 提取持仓标的行情
4. 拼 prompt → 调 LLM
5. 输出 → evening/{today}.md
6. push_feishu.py 推送
```

## 输出处理

1. LLM 返回 markdown → 写入 `evening/{today}.md`
2. 推送飞书
3. 更新 `user_portfolio.json` 中的 `current` 字段（供明早使用）
