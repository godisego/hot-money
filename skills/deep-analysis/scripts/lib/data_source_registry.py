"""Data source registry · v2.5.

Catalogs every data source UZI-Skill knows about with metadata: URL, which
markets/dims it covers, access method, and current health status. Used by:

1. Fetchers (to pick primary vs fallback sources)
2. Agent sub-tasks in HARD-GATE-QUALITATIVE (to pick browser URLs per dim)
3. AGENTS.md data source cheat-sheet generation

Design principles:
- Pure config, no I/O. Keeps the module cheap to import.
- Pattern mirrors `lib/investor_db.py` (list of dataclass + filter helpers).
- Registry is a hint, not truth — each fetcher still reports actual `source`
  in its return dict. If reality diverges from registry, trust the fetcher.

Tiers:
- 1 = HTTP primary — cheap, stable, belongs in fetcher fallback chains
- 2 = Playwright / browser — reliable but slow/heavy, use when tier-1 fails or
      when only JS-rendered pages work (雪球 / 问财 / 富途)
- 3 = Auxiliary — official disclosure portals, legal-source-of-truth but
      schema-heavy (SSE/SZSE/CNINFO/HKEXNews)
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class DataSource:
    id: str                         # stable short id, e.g. "aastocks_quote"
    name_cn: str                    # Chinese display name
    base_url: str                   # root or example endpoint
    markets: tuple[str, ...]        # "A", "H", "U"
    dims: tuple[str, ...]           # dimension keys this source can help fill
    tier: int                       # 1 HTTP primary, 2 Playwright, 3 official disclosure
    access: str                     # "http" | "akshare" | "mx_api" | "playwright" | "ddgs"
    health: str                     # "known_good" | "flaky" | "blocked_often" | "needs_browser"
    notes: str = ""


# ═══════════════════════════════════════════════════════════════
# Tier 1 · HTTP-accessible primary sources (safe for fetcher code)
# ═══════════════════════════════════════════════════════════════
_TIER1: list[DataSource] = [
    DataSource(
        "em_push2", "东方财富 push2",
        "https://push2.eastmoney.com/api/qt/stock/get",
        ("A", "H", "U"),
        ("0_basic", "2_kline", "10_valuation", "12_capital_flow"),
        1, "http", "blocked_often",
        "2026 常被反爬拦截（大陆 / 境外均可能 Empty reply）；建议走 MX API 或 XueQiu akshare 代抓"
    ),
    DataSource(
        "em_quote", "东方财富 quote 页",
        "https://quote.eastmoney.com/",
        ("A", "H", "U"),
        ("0_basic", "2_kline"),
        1, "http", "known_good",
        "push2 挂掉时 quote 子域通常仍可用（2026 验证：200 OK）"
    ),
    DataSource(
        "em_data", "东方财富 data 子域",
        "https://data.eastmoney.com/",
        ("A",),
        ("4_peers", "7_industry", "11_governance", "12_capital_flow", "16_lhb", "15_events", "6_research"),
        1, "http", "known_good",
        "龙虎榜 / 北向 / 融资融券 / 股东户数 / 研报 / 行业板块成分（akshare board_industry_cons_em 走这里）"
    ),
    DataSource(
        "xq_api", "雪球 akshare backend",
        "https://stock.xueqiu.com/",
        ("A", "H"),
        ("0_basic", "1_financials", "2_kline", "15_events", "17_sentiment"),
        1, "akshare", "known_good",
        "akshare.stock_individual_basic_info_xq / stock_individual_spot_xq"
    ),
    DataSource(
        "tencent_qt", "腾讯行情 qt",
        "https://qt.gtimg.cn/",
        ("A", "H", "U"),
        ("0_basic", "2_kline"),
        1, "http", "known_good",
        "realtime quote 兜底源；格式 ~-delimited 字符串"
    ),
    DataSource(
        "sina_quote", "新浪财经行情",
        "https://finance.sina.com.cn/",
        ("A", "H", "U"),
        ("0_basic", "2_kline", "15_events"),
        1, "http", "flaky",
        "hq.sinajs.cn 老接口 2026 返 403；主页 HTML 解析仍可用"
    ),
    DataSource(
        "cninfo", "巨潮资讯",
        "http://www.cninfo.com.cn/",
        ("A",),
        ("15_events", "7_industry", "1_financials"),
        1, "http", "known_good",
        "A 股公告原文的法定披露源；akshare.stock_industry_pe_ratio 也走这里"
    ),
    DataSource(
        "hkexnews", "HKEXNews 港交所披露易",
        "https://www1.hkexnews.hk/",
        ("H",),
        ("15_events", "11_governance"),
        1, "http", "known_good",
        "港股公告的法定披露源"
    ),
    DataSource(
        "aastocks", "AASTOCKS 港股",
        "https://www.aastocks.com/",
        ("H",),
        ("0_basic", "4_peers", "12_capital_flow", "15_events"),
        1, "http", "flaky",
        "港股 PE/PB/industry/南北向核心数据源；HTML regex 抓取 + Playwright 兜底"
    ),
    DataSource(
        "cls", "财联社 7x24 电报",
        "https://www.cls.cn/",
        ("A", "H", "U"),
        ("15_events", "3_macro"),
        1, "http", "known_good",
        "事件驱动首选；催化剂与突发新闻密度最高"
    ),
    DataSource(
        "yicai", "第一财经",
        "https://www.yicai.com/",
        ("A", "H"),
        ("15_events", "3_macro", "7_industry"),
        1, "http", "known_good",
        "行业与公司新闻、宏观产业专题；适合 agent 抽取定性评语"
    ),
    DataSource(
        "wallstreetcn", "华尔街见闻",
        "https://wallstreetcn.com/",
        ("A", "H", "U"),
        ("3_macro", "17_sentiment"),
        1, "http", "flaky",
        "快讯 + 海外联动；/live 端点 2026 返 404，走主页抓最新"
    ),
    DataSource(
        "cfi", "中财网",
        "https://quote.cfi.cn/",
        ("A",),
        ("0_basic", "1_financials", "15_events"),
        1, "http", "known_good",
        "个股资料 / 公告 / 研报 HTML 兜底"
    ),
    DataSource(
        "hexun", "和讯网",
        "https://stock.hexun.com/",
        ("A",),
        ("6_research", "15_events"),
        1, "http", "known_good",
        "研报转载 + 行业点评兜底"
    ),
    DataSource(
        "163money", "网易财经",
        "https://money.163.com/",
        ("A", "U"),
        ("0_basic", "15_events"),
        1, "http", "known_good",
        "新闻聚合 + 公告转载"
    ),
    DataSource(
        "jrj", "金融界",
        "https://stock.jrj.com.cn/",
        ("A",),
        ("15_events", "7_industry"),
        1, "http", "known_good",
        "题材联动 / 盘面复盘"
    ),
    DataSource(
        "investing", "Investing.com",
        "https://www.investing.com/",
        ("U",),
        ("3_macro", "9_futures"),
        1, "http", "known_good",
        "商品 / 外汇 / 海外指数 / 宏观日历"
    ),
    DataSource(
        "mx_api", "东方财富妙想 Skills Hub",
        "https://mkapi2.dfcfs.com/finskillshub/",
        ("A", "H", "U"),
        ("0_basic", "1_financials", "15_events"),
        1, "mx_api", "known_good",
        "v2.3 新增 · 需 MX_APIKEY；官方 NLP API，自动纠错中文名"
    ),
    DataSource(
        "akshare_lhb", "akshare 龙虎榜",
        "https://akshare.akfamily.xyz/",
        ("A",),
        ("16_lhb",),
        1, "akshare", "known_good",
        "ak.stock_lhb_detail_em 等；主 LHB 数据源"
    ),
    DataSource(
        "baostock", "BaoStock",
        "http://baostock.com/",
        ("A",),
        ("2_kline",),
        1, "akshare", "known_good",
        "K 线 fallback，官方接口无 key"
    ),
    DataSource(
        "yfinance", "Yahoo Finance",
        "https://finance.yahoo.com/",
        ("U", "H"),
        ("0_basic", "1_financials", "2_kline"),
        1, "akshare", "known_good",
        "美股主源、港股兜底"
    ),
    DataSource(
        "ddgs", "DuckDuckGo 搜索",
        "https://duckduckgo.com/",
        ("A", "H", "U"),
        ("3_macro", "13_policy", "14_moat", "15_events", "17_sentiment"),
        1, "ddgs", "flaky",
        "中文搜索质量不稳定；agent 建议二次过滤 garbage patterns"
    ),
]

# ═══════════════════════════════════════════════════════════════
# Tier 2 · Playwright / browser-only sources
# ═══════════════════════════════════════════════════════════════
_TIER2: list[DataSource] = [
    DataSource(
        "iwencai", "问财（同花顺 NLP 筛选）",
        "https://www.iwencai.com/",
        ("A",),
        ("4_peers", "5_chain", "7_industry"),
        2, "playwright", "needs_browser",
        "NLP 条件查询：'市值>100亿 行业=半导体'；需 cookie 流程"
    ),
    DataSource(
        "ths_f10", "同花顺 F10",
        "https://stockpage.10jqka.com.cn/",
        ("A", "H"),
        ("0_basic", "4_peers", "5_chain", "11_governance", "14_moat"),
        2, "playwright", "needs_browser",
        "主营 / 股东 / 同行 / 概念板块映射，A 股信息最齐全"
    ),
    DataSource(
        "xueqiu_f10", "雪球 F10 / 讨论",
        "https://xueqiu.com/",
        ("A", "H", "U"),
        ("11_governance", "15_events", "17_sentiment"),
        2, "playwright", "needs_browser",
        "HTTP 直抓常返 403；用 Playwright 可稳定抓社区观点与公告"
    ),
    DataSource(
        "legulegu", "乐咕乐股估值历史",
        "https://legulegu.com/",
        ("A",),
        ("10_valuation", "7_industry"),
        2, "playwright", "needs_browser",
        "PE/PB 5Y 分位、行业估值；HTTP 直访返 403"
    ),
    DataSource(
        "stockstar", "证券之星",
        "https://stock.stockstar.com/",
        ("A",),
        ("6_research", "15_events"),
        2, "playwright", "needs_browser",
        "数据中心 + 研报评级；HTTP 直访返 567"
    ),
    DataSource(
        "futu", "富途牛牛",
        "https://www.futunn.com/",
        ("H", "U"),
        ("0_basic", "1_financials", "17_sentiment"),
        2, "playwright", "needs_browser",
        "港美股页面 + 社区；HTTP 直访跳 403"
    ),
    DataSource(
        "yuncaijing", "云财经龙虎榜",
        "https://www.yuncaijing.com/",
        ("A",),
        ("16_lhb",),
        2, "playwright", "flaky",
        "游资席位 / 题材热度 / 龙虎榜补源"
    ),
]

# ═══════════════════════════════════════════════════════════════
# Tier 3 · Official disclosure portals (法定源，供 agent 交叉验证)
# ═══════════════════════════════════════════════════════════════
_TIER3: list[DataSource] = [
    DataSource(
        "sse", "上海证券交易所",
        "https://www.sse.com.cn/",
        ("A",),
        ("15_events", "11_governance"),
        3, "http", "known_good",
        "上交所披露 + 上证 e 互动"
    ),
    DataSource(
        "szse", "深圳证券交易所",
        "https://www.szse.cn/",
        ("A",),
        ("15_events", "11_governance"),
        3, "http", "known_good",
        "深交所披露 + 互动易"
    ),
    DataSource(
        "csrc", "中国证监会",
        "http://www.csrc.gov.cn/",
        ("A",),
        ("13_policy",),
        3, "http", "known_good",
        "监管政策原文"
    ),
    DataSource(
        "gov_cn", "国务院政策",
        "https://www.gov.cn/zhengce/",
        ("A", "H"),
        ("13_policy", "3_macro"),
        3, "http", "known_good",
        "顶层政策文件"
    ),
    DataSource(
        "miit", "工信部",
        "https://www.miit.gov.cn/",
        ("A",),
        ("13_policy", "7_industry"),
        3, "http", "known_good",
        "制造业行业政策"
    ),
    DataSource(
        "ndrc", "发改委",
        "https://www.ndrc.gov.cn/",
        ("A",),
        ("13_policy", "3_macro"),
        3, "http", "known_good",
        "发改委政策解读"
    ),
    DataSource(
        "samr", "市场监管总局",
        "https://www.samr.gov.cn/",
        ("A",),
        ("13_policy",),
        3, "http", "known_good",
        "反垄断 / 市场监管"
    ),
    DataSource(
        "shfe", "上海期货交易所",
        "https://www.shfe.com.cn/",
        ("A",),
        ("8_materials", "9_futures"),
        3, "http", "known_good",
        "黑色 / 有色 / 贵金属 / 原油期货日报"
    ),
    DataSource(
        "dce", "大连商品交易所",
        "https://www.dce.com.cn/",
        ("A",),
        ("8_materials", "9_futures"),
        3, "http", "known_good",
        "农产品 / 化工期货"
    ),
    DataSource(
        "czce", "郑州商品交易所",
        "https://www.czce.com.cn/",
        ("A",),
        ("8_materials", "9_futures"),
        3, "http", "known_good",
        "农产品 / 能源期货"
    ),
    DataSource(
        "100ppi", "生意社现货",
        "https://www.100ppi.com/",
        ("A",),
        ("8_materials",),
        3, "http", "known_good",
        "现货价格数据库"
    ),
]


# ═══════════════════════════════════════════════════════════════
# Public API
# ═══════════════════════════════════════════════════════════════

SOURCES: list[DataSource] = _TIER1 + _TIER2 + _TIER3


def by_id(source_id: str) -> DataSource | None:
    return next((s for s in SOURCES if s.id == source_id), None)


def by_dim(dim_key: str) -> list[DataSource]:
    return [s for s in SOURCES if dim_key in s.dims]


def by_market(market: str) -> list[DataSource]:
    return [s for s in SOURCES if market in s.markets]


def by_tier(tier: int) -> list[DataSource]:
    return [s for s in SOURCES if s.tier == tier]


def http_sources_for(dim_key: str, market: str) -> list[DataSource]:
    """Tier-1 HTTP sources matching a dim + market. Ordered by health (known_good first)."""
    health_rank = {"known_good": 0, "flaky": 1, "blocked_often": 2, "needs_browser": 3}
    hits = [s for s in SOURCES if s.tier == 1 and market in s.markets and dim_key in s.dims]
    return sorted(hits, key=lambda s: health_rank.get(s.health, 99))


def playwright_sources_for(dim_key: str, market: str) -> list[DataSource]:
    """Tier-2 sources requiring browser. Use when HTTP sources all fail or only JS-rendered."""
    return [s for s in SOURCES if s.tier == 2 and market in s.markets and dim_key in s.dims]


def official_sources_for(dim_key: str) -> list[DataSource]:
    """Tier-3 official disclosure sources (market-agnostic mostly)."""
    return [s for s in SOURCES if s.tier == 3 and dim_key in s.dims]


def assert_registry_sane() -> None:
    """Smoke test — called once from __main__ block. Ensures no duplicate IDs."""
    ids = [s.id for s in SOURCES]
    assert len(ids) == len(set(ids)), f"Duplicate source IDs: {set(x for x in ids if ids.count(x) > 1)}"


if __name__ == "__main__":
    assert_registry_sane()
    print(f"Registry OK · {len(SOURCES)} sources ({len(_TIER1)} tier-1, {len(_TIER2)} tier-2, {len(_TIER3)} tier-3)")
    print()
    print("Example lookups:")
    print(f"  by_dim('4_peers')          → {[s.id for s in by_dim('4_peers')]}")
    print(f"  by_market('H')             → {[s.id for s in by_market('H')]}")
    print(f"  http_sources_for('0_basic', 'H')   → {[s.id for s in http_sources_for('0_basic', 'H')]}")
    print(f"  playwright_sources_for('4_peers', 'A') → {[s.id for s in playwright_sources_for('4_peers', 'A')]}")
