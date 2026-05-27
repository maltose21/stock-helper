#!/usr/bin/env python3
"""
刘备教授文章知识库构建脚本 v3
精确蒸馏 - 保证准确性和专业性
"""

import os
import re
import json
from pathlib import Path
from datetime import datetime
from collections import defaultdict

# 配置
ARTICLES_DIR = Path.home() / "Documents/刘备教授"
OUTPUT_DIR = Path(__file__).parent.parent / "knowledge_base"
OUTPUT_DIR.mkdir(exist_ok=True)

# ==================== 精确匹配模式定义 ====================

# 核心投资概念 - 必须带上下文的精确匹配
CORE_CONCEPTS = {
    # 投资理念（精确短语）
    "买在无人问津时": {
        "pattern": r"买在无人问津",
        "count_method": "exact",
        "description": "逆向投资核心思想，市场冷清无人关注时买入优质资产"
    },
    "做坏人买好票": {
        "pattern": r"做坏人?买好票",
        "count_method": "exact",
        "description": "价值投资理念，做好人买好票，长期持有"
    },
    "你我皆是凡人": {
        "pattern": r"你我皆是?凡人",
        "count_method": "exact",
        "description": "投资心理建设，承认人性弱点，不苛责自己"
    },
    "万物皆周期": {
        "pattern": r"万物皆周期",
        "count_method": "exact",
        "description": "所有行业和资产都有周期，关键看当前位置"
    },
    "活着比什么都重要": {
        "pattern": r"活着比什么都重要",
        "count_method": "exact",
        "description": "风险控制第一，不亏钱是投资第一要义"
    },
    "牛三阶段": {
        "pattern": r"牛三|牛市第三阶段",
        "count_method": "exact",
        "description": "牛市第三阶段最疯狂，此时应逐步减仓"
    },
    "买好公司": {
        "pattern": r"买好公司",
        "count_method": "exact",
        "description": "选择有真实盈利能力的行业龙头"
    },
    "好价格": {
        "pattern": r"好价格",
        "count_method": "exact",
        "description": "估值合理或偏低时有安全边际"
    },
    "高分红": {
        "pattern": r"高分红|高分红",
        "count_method": "exact",
        "description": "分红率>50%说明公司赚的是真钱"
    },
    "分红率50": {
        "pattern": r"分红率50%?|50[%％]以上分红",
        "count_method": "exact",
        "description": "分红率超过50%说明利润真实"
    },
    "股息率5": {
        "pattern": r"股息率5[%％]|5[%％]股息",
        "count_method": "exact",
        "description": "股息率超过5%是优质价值股标志"
    },
    "科技重新定价": {
        "pattern": r"科技重新定价|重新定价",
        "count_method": "exact",
        "description": "中国科技资产被低估，全球重新定价带来机会"
    },
    "六小龙": {
        "pattern": r"六小龙",
        "count_method": "exact",
        "description": "杭州六家科技公司，代表中国科技新力量"
    },
    "抱团": {
        "pattern": r"抱团|机构抱团",
        "count_method": "exact",
        "description": "A股以公募为主导，每3-5年出现一次抱团现象"
    },
    "公募主导": {
        "pattern": r"公募主导|以公募",
        "count_method": "exact",
        "description": "A股市场以公募基金为主，KPI考核趋同导致抱团"
    },
    "KPI趋同": {
        "pattern": r"KPI趋同|考核趋同",
        "count_method": "exact",
        "description": "公募基金考核指标相同导致投资行为趋同"
    },
    "不抄底": {
        "pattern": r"不抄底|不要抄底",
        "count_method": "exact",
        "description": "不要抄底无法判断底部的股票"
    },
    "10%止损": {
        "pattern": r"10[%％].*止损|止损.*10[%％]",
        "count_method": "exact",
        "description": "投机仓位亏损10%必须止损"
    },
    "杠杆风险": {
        "pattern": r"杠杆|加杠杆|去杠杆",
        "count_method": "exact",
        "description": "杠杆放大风险，建议不要使用杠杆"
    },
    "黑天鹅": {
        "pattern": r"黑天鹅",
        "count_method": "exact",
        "description": "无法预测的重大突发风险事件"
    },
    "逆向投资": {
        "pattern": r"逆向投资|逆向思维",
        "count_method": "exact",
        "description": "在市场恐慌时买入，在市场狂热时卖出"
    },
    "价值投资": {
        "pattern": r"价值投资",
        "count_method": "exact",
        "description": "买好公司、好价格、长期持有"
    },
    "赚的是真钱": {
        "pattern": r"赚的是真钱|真金白银",
        "count_method": "exact",
        "description": "高分红公司利润真实，不同于账面利润"
    },
    "假钱": {
        "pattern": r"赚的都是假钱|利润是假钱|高负债.*假钱",
        "count_method": "exact",
        "description": "高负债企业利润可能是假钱，需谨慎"
    },
    "中国资产重估": {
        "pattern": r"中国资产.*重估|资产重估",
        "count_method": "exact",
        "description": "中国优质资产需要被重新定价"
    },
    "确定性": {
        "pattern": r"确定性|确定性的",
        "count_method": "exact",
        "description": "投资追求确定性，有清晰股东回报规划"
    },
}

# ==================== 行业分析定义 ====================
INDUSTRY_VIEWS = {
    "银行": {
        "names": ["银行", "银行业", "银行股"],
        "key_stocks": ["招商银行", "兴业银行", "平安银行", "宁波银行"],
        "view": "招行管理最优；高负债银行需谨慎对待"
    },
    "煤炭": {
        "names": ["煤炭", "煤炭行业", "煤炭股", "煤企"],
        "key_stocks": ["中国神华", "陕西煤业", "淮北矿业", "兖矿能源"],
        "view": "高分红代表，稳定现金流"
    },
    "水电": {
        "names": ["水电", "水电行业", "电力", "水电股"],
        "key_stocks": ["长江电力", "华能水电", "国投电力"],
        "view": "稳定现金流，类债券资产"
    },
    "高速": {
        "names": ["高速", "高速公路", "高速路"],
        "key_stocks": ["宁沪高速", "沪杭甬", "浙江沪杭甬", "山东高速"],
        "view": "稳定印钞机，分红稳定"
    },
    "家电": {
        "names": ["家电", "白电", "家电行业"],
        "key_stocks": ["美的集团", "格力电器", "海尔智家"],
        "view": "高分红高ROE，国补受益"
    },
    "新能源车": {
        "names": ["新能源车", "电动车", "电车", "新能源汽车"],
        "key_stocks": ["比亚迪", "理想汽车", "小鹏汽车", "蔚来", "吉利汽车", "长城汽车"],
        "view": "中国产业优势，海外扩张中"
    },
    "AI": {
        "names": ["人工智能", "AI", "大模型", "人工智能行业"],
        "key_stocks": ["腾讯", "阿里", "百度", "字节跳动", "科大讯飞"],
        "view": "软件/算力/应用多方向，警惕纯概念股"
    },
    "互联网": {
        "names": ["互联网", "互联网平台", "平台经济", "互联网巨头"],
        "key_stocks": ["腾讯", "阿里", "拼多多", "京东", "美团", "字节跳动", "网易", "百度"],
        "view": "平台价值被重新认识，竞争格局改善"
    },
    "半导体": {
        "names": ["半导体", "芯片", "集成电路", "半导体行业"],
        "key_stocks": ["中芯国际", "华虹半导体", "长鑫存储", "兆易创新"],
        "view": "国产替代逻辑，突破中"
    },
    "消费": {
        "names": ["消费", "消费品", "内需", "消费行业"],
        "key_stocks": ["贵州茅台", "五粮液", "中国中免"],
        "view": "分化严重，高端好于低端"
    },
    "猪周期": {
        "names": ["猪", "养猪", "猪周期", "猪肉"],
        "key_stocks": ["牧原股份", "温氏股份", "新希望"],
        "view": "强周期行业，关注产能"
    },
    "面板": {
        "names": ["面板", "显示面板", "LCD", "OLED"],
        "key_stocks": ["京东方A", "TCL科技", "深天马A"],
        "view": "周期性强，产能出清后有反转机会"
    },
    "存储": {
        "names": ["存储", "内存", "DRAM", "NAND"],
        "key_stocks": ["长鑫存储", "兆易创新", "澜起科技"],
        "view": "周期属性强，受全球价格影响"
    },
}

# ==================== 时机信号定义 ====================
TIMING_SIGNALS = {
    "买入信号": {
        "技术面": ["成交量持续放大", "股价突破重要均线", "底部放量上涨"],
        "资金面": ["外资持续净流入", "机构仓位提升", "融资余额上升"],
        "政策面": ["重要政策利好出台", "行业支持政策", "宏观宽松信号"],
        "情绪面": ["市场恐慌情绪蔓延", "指数连续下跌", "估值处于历史低位"]
    },
    "卖出信号": {
        "技术面": ["高位放量滞涨", "跌破重要均线", "顶部形态形成"],
        "资金面": ["外资持续净流出", "机构减仓", "融资余额异常攀升"],
        "估值面": ["PE/PB处于历史高位", "股息率显著低于无风险利率"],
        "逻辑面": ["买入逻辑被证伪", "行业景气度下行", "公司竞争力下降"]
    }
}

# ==================== 风险预警 ====================
RISK_SIGNALS = {
    "高估值预警": ["市盈率处于历史高位", "股息率低于无风险利率", "市值远超内在价值"],
    "行业风险": ["行业数据连续下滑", "政策转向利空", "竞争格局恶化", "产能过剩"],
    "流动性风险": ["成交量持续萎缩", "跌停股票增多", "闪崩频发", "小票流动性枯竭"],
    "黑天鹅预警": ["地缘政治紧张", "政策突然转向", "重大突发事故", "行业重大利空"]
}


def parse_article(filepath):
    """解析单篇文章"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()

        lines = content.split('\n')
        title = lines[0].strip().replace('# ', '').strip() if lines else "无标题"

        # 优先从文件名 YYYY-MM-DD - title.md 提取日期（最可靠）
        filename = Path(filepath).name
        fname_date = re.match(r'^(\d{4}-\d{2}-\d{2})', filename)
        if fname_date:
            date = fname_date.group(1)
        else:
            # 回退：扫 body 前 500 字找 YYYY-MM-DD 或 date: ...
            head = content[:500]
            date_match = re.search(r'(\d{4}-\d{2}-\d{2})', head)
            date = date_match.group(1) if date_match else "未知"

        summary_match = re.search(r'---\n\n(.+?)\n\n---', content, re.DOTALL)
        summary = summary_match.group(1).strip() if summary_match else ""

        body_start = content.find('---', content.find('---') + 3)
        body = content[body_start+3:].strip() if body_start > 0 else content

        return {
            "title": title,
            "date": date,
            "summary": summary,
            "body": body,
            "source": str(filepath)
        }
    except Exception as e:
        return {"error": str(e), "file": str(filepath)}


# ==================== 三级标记定义 ====================
# 核心概念词（命中即标 principle）
PRINCIPLE_KEYWORDS = [
    "买在无人问津", "做坏人买好票", "你我皆是凡人", "万物皆周期",
    "活着比什么都重要", "牛三", "买好公司", "好价格", "高分红",
    "分红率", "股息率", "杠杆", "止损", "价值投资", "逆向投资",
    "确定性", "抱团", "公募主导",
]

# 评级动词（命中 + 个股名 即标 observation）
RATING_VERBS = ["推荐", "看好", "看空", "建议买", "建议卖", "减仓", "加仓", "清仓", "持有", "重仓"]

# 事件词（命中即标 event）
EVENT_KEYWORDS = [
    "罢工", "谈判", "财报", "政策", "处罚", "监管", "停牌", "复牌",
    "增持", "减持", "回购", "并购", "重组", "ST", "退市", "停摆",
    "黑天鹅", "爆雷", "暴雷", "调查", "立案", "披露", "公告",
]


def classify_article_level(body, stocks):
    """对文章打三级标签（一篇可同时是多种）"""
    levels = []

    # principle: 命中核心概念词
    for kw in PRINCIPLE_KEYWORDS:
        if kw in body:
            levels.append("principle")
            break

    # observation: 个股名 + 评级动词同段出现
    if stocks:
        for verb in RATING_VERBS:
            if verb in body:
                levels.append("observation")
                break

    # event: 命中事件词
    for kw in EVENT_KEYWORDS:
        if kw in body:
            levels.append("event")
            break

    # 如果都没命中，至少给个 observation 兜底（包含个股）或 principle（不含个股）
    if not levels:
        levels.append("observation" if stocks else "principle")

    return levels


def count_concept(body, concept_info):
    """精确计算概念出现次数"""
    pattern = concept_info["pattern"]
    matches = re.findall(pattern, body)
    return len(matches)


def find_concepts_in_article(body, core_concepts):
    """查找文章中出现的所有概念"""
    found = []
    for concept_name, info in core_concepts.items():
        if re.search(info["pattern"], body):
            count = count_concept(body, info)
            found.append((concept_name, count))
    return found


def find_industries_in_article(body, industry_views):
    """查找文章中出现的行业"""
    found = []
    for industry_name, info in industry_views.items():
        for name in info["names"]:
            if name in body:
                found.append(industry_name)
                break
    return list(set(found))


def find_stocks_in_article(body):
    """查找文章中提到的股票"""
    stocks = []

    # 精确股票名称列表
    stock_names = [
        # 互联网/科技
        "腾讯", "阿里巴巴", "阿里", "美团", "小米", "京东", "拼多多", "网易", "百度",
        "字节跳动", "哔哩哔哩", "B站", "快手", "字节",
        # 新能源车
        "比亚迪", "理想汽车", "小鹏汽车", "蔚来", "吉利汽车", "长城汽车", "长安汽车", "奇瑞汽车",
        # 白酒
        "贵州茅台", "茅台", "五粮液", "泸州老窖", "汾酒", "洋河股份", "古井贡酒",
        # 银行
        "招商银行", "兴业银行", "平安银行", "宁波银行", "工商银行", "建设银行", "农业银行",
        # 煤炭
        "中国神华", "陕西煤业", "淮北矿业", "兖矿能源", "中煤能源",
        # 水电/电力
        "长江电力", "华能水电", "国投电力", "中国核电",
        # 高速
        "宁沪高速", "沪杭甬", "浙江沪杭甬", "山东高速",
        # 家电
        "美的集团", "格力电器", "海尔智家", "海信家电", "TCL",
        # 半导体
        "中芯国际", "华虹半导体", "长鑫存储", "兆易创新", "澜起科技", "寒武纪",
        # 面板
        "京东方A", "TCL科技", "深天马A",
        # 医药
        "药明康德", "恒瑞医药", "迈瑞医疗", "爱尔眼科", "通策医疗",
        # 新能源
        "宁德时代", "亿纬锂能", "恩捷股份", "天赐材料",
        # 其他
        "中国中免", "王府井", "万华化学", "恒力石化", "荣盛石化", "三六零", "金山办公",
        "科大讯飞", "海康威视", "大华股份",
    ]

    for stock in stock_names:
        if stock in body:
            stocks.append(stock)

    return list(set(stocks))


def extract_investment_opinions(body):
    """提取投资观点"""
    opinions = {
        "看多": [],
        "看空": [],
        "风险提示": []
    }

    # 看多信号
    buy_patterns = [
        (r'推荐[买入配置]|建议[买入配置]|值得关注|可以关注', "看多"),
        (r'看好|长期看好|坚定看好', "看多"),
        (r'值得拥有|值得持有|坚定持有', "看多"),
    ]

    # 看空信号
    sell_patterns = [
        (r'不建议|不要追|回避|谨慎', "看空"),
        (r'减仓|清仓|卖出', "看空"),
        (r'风险提示?|注意风险|警惕', "风险提示"),
    ]

    for pattern, sentiment in buy_patterns + sell_patterns:
        matches = re.findall(f'{pattern}[^。.;]*', body)
        key = "看多" if sentiment == "看多" else ("看空" if sentiment == "看空" else "风险提示")
        for m in matches[:3]:
            m = m.strip()
            if m and m not in opinions[key]:
                opinions[key].append(m)

    return opinions


def build_precise_knowledge_base():
    """构建精确知识库"""
    print(f"📚 开始精确蒸馏知识库...")
    print(f"=" * 50)

    articles = []
    concept_stats = defaultdict(int)
    industry_stats = defaultdict(int)
    stock_stats = defaultdict(int)
    concept_articles = defaultdict(list)  # 概念 -> 文章列表
    industry_articles = defaultdict(list)
    stock_articles = defaultdict(list)

    md_files = list(ARTICLES_DIR.glob("*.md"))
    print(f"📄 找到 {len(md_files)} 篇文章")
    print("=" * 50)

    for i, filepath in enumerate(md_files):
        if i % 50 == 0:
            print(f"  处理中... {i}/{len(md_files)} ({100*i/len(md_files):.1f}%)")

        article = parse_article(filepath)
        if "error" in article:
            continue

        body = article["body"]

        # 查找概念
        concepts = find_concepts_in_article(body, CORE_CONCEPTS)
        for concept_name, count in concepts:
            concept_stats[concept_name] += count
            concept_articles[concept_name].append({
                "date": article["date"],
                "title": article["title"]
            })

        # 查找行业
        industries = find_industries_in_article(body, INDUSTRY_VIEWS)
        for ind in industries:
            industry_stats[ind] += 1
            industry_articles[ind].append({
                "date": article["date"],
                "title": article["title"]
            })

        # 查找股票
        stocks = find_stocks_in_article(body)
        for stock in stocks:
            stock_stats[stock] += 1
            stock_articles[stock].append({
                "date": article["date"],
                "title": article["title"]
            })

        # 提取投资观点
        opinions = extract_investment_opinions(body)

        # 三级标记
        levels = classify_article_level(body, stocks)

        articles.append({
            "id": i + 1,
            "title": article["title"],
            "date": article["date"],
            "summary": article["summary"],
            "body": body[:3000],  # 限制长度但保留足够内容
            "concepts": [c[0] for c in concepts],
            "industries": industries,
            "stocks": stocks,
            "opinions": opinions,
            "level": levels
        })

    # 排序
    articles.sort(key=lambda x: x["date"], reverse=True)

    # 排序统计
    top_concepts = dict(sorted(concept_stats.items(), key=lambda x: -x[1])[:30])
    top_industries = dict(sorted(industry_stats.items(), key=lambda x: -x[1])[:20])
    top_stocks = dict(sorted(stock_stats.items(), key=lambda x: -x[1])[:50])

    # 计算 date_range：用真实日期，跳过"未知"
    valid_dates = sorted([a["date"] for a in articles if a["date"] != "未知"])
    if valid_dates:
        date_range = f"{valid_dates[0]} ~ {valid_dates[-1]}"
    else:
        date_range = "未知"

    # 提取最近 30 天文章供 distill_recent.py 消费
    from datetime import timedelta
    today = datetime.now().date()
    cutoff = (today - timedelta(days=30)).strftime("%Y-%m-%d")
    recent_articles = [a for a in articles if a["date"] != "未知" and a["date"] >= cutoff]

    # 构建知识库
    knowledge_base = {
        "metadata": {
            "build_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "total_articles": len(articles),
            "date_range": date_range
        },
        "core_concepts": CORE_CONCEPTS,
        "industry_views": INDUSTRY_VIEWS,
        "timing_signals": TIMING_SIGNALS,
        "risk_signals": RISK_SIGNALS,
        "statistics": {
            "concepts": {
                "total_mentions": sum(concept_stats.values()),
                "unique_concepts": len(concept_stats),
                "top_20": top_concepts
            },
            "industries": {
                "total_mentions": sum(industry_stats.values()),
                "unique_industries": len(industry_stats),
                "all": top_industries
            },
            "stocks": {
                "total_mentions": sum(stock_stats.values()),
                "unique_stocks": len(stock_stats),
                "top_30": top_stocks
            }
        },
        "top_concept_articles": {k: v[:5] for k, v in concept_articles.items()},
        "top_industry_articles": {k: v[:5] for k, v in industry_articles.items()},
        "top_stock_articles": {k: v[:10] for k, v in stock_articles.items()},
        "articles": articles
    }

    # 保存
    output_file = OUTPUT_DIR / "knowledge_base.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(knowledge_base, f, ensure_ascii=False, indent=2)

    # 同时输出最近 30 天的文章列表，供 distill_recent.py 消费
    recent_file = OUTPUT_DIR / "recent_30d_articles.json"
    with open(recent_file, 'w', encoding='utf-8') as f:
        json.dump({
            "cutoff_date": cutoff,
            "build_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "count": len(recent_articles),
            "articles": recent_articles
        }, f, ensure_ascii=False, indent=2)

    print(f"\n✅ 精确知识库构建完成!")
    print(f"=" * 50)
    print(f"📊 统计:")
    print(f"   - 文章总数: {len(articles)}")
    print(f"   - 概念种类: {len(concept_stats)}种, {sum(concept_stats.values())}次提及")
    print(f"   - 行业种类: {len(industry_stats)}种, {sum(industry_stats.values())}次提及")
    print(f"   - 股票种类: {len(stock_stats)}种, {sum(stock_stats.values())}次提及")
    print(f"\n📈 TOP 10 概念:")
    for concept, count in list(top_concepts.items())[:10]:
        print(f"   - {concept}: {count}次")
    print(f"\n📈 TOP 10 行业:")
    for ind, count in list(top_industries.items())[:10]:
        print(f"   - {ind}: {count}次")
    print(f"\n📈 TOP 10 股票:")
    for stock, count in list(top_stocks.items())[:10]:
        print(f"   - {stock}: {count}次")

    # 生成摘要
    summary_file = OUTPUT_DIR / "summary.md"
    with open(summary_file, 'w', encoding='utf-8') as f:
        f.write("# 刘备教授投资知识库 - 精确摘要\n\n")
        f.write(f"**构建时间**: {knowledge_base['metadata']['build_time']}\n")
        f.write(f"**文章总数**: {len(articles)} 篇\n")
        f.write(f"**时间范围**: {date_range}\n\n")

        f.write("---\n\n## 核心理念\n\n")
        f.write("- **核心理念**: 买在无人问津时，卖在人声鼎沸处\n")
        f.write("- **市场观点**: A股以公募为主导，每3-5年一个抱团周期\n")
        f.write("- **选股原则**: 买好公司、好价格、高分红、长期持有\n")
        f.write("- **风险控制**: 活着比什么都重要，10%止损纪律\n\n")

        f.write("---\n\n## 高频概念 TOP 20\n\n")
        for concept, count in list(top_concepts.items())[:20]:
            desc = CORE_CONCEPTS.get(concept, {}).get("description", "")
            f.write(f"- **{concept}** ({count}次): {desc}\n")

        f.write("\n---\n\n## 行业分析\n\n")
        for ind, info in INDUSTRY_VIEWS.items():
            mentions = industry_stats.get(ind, 0)
            if mentions > 0:
                f.write(f"### {ind} (提及{mentions}次)\n")
                f.write(f"- 观点: {info['view']}\n")
                f.write(f"- 标的: {', '.join(info['key_stocks'])}\n\n")

        f.write("\n---\n\n## TOP 30 股票统计\n\n")
        for stock, count in list(top_stocks.items())[:30]:
            f.write(f"- **{stock}**: {count}次提及\n")

    print(f"\n📝 摘要: {summary_file}")

    return knowledge_base


if __name__ == "__main__":
    build_precise_knowledge_base()