"""Dimension 4 · 同行对比 — 产出 peer_table + peer_comparison."""
from __future__ import annotations

import json
import sys

import akshare as ak  # type: ignore
from lib import data_sources as ds
from lib.market_router import parse_ticker


def _float(v, default=0.0):
    try:
        s = str(v).replace(",", "").replace("%", "")
        if s in ("", "nan", "-", "--", "None"):
            return default
        return float(s)
    except (ValueError, TypeError):
        return default


def main(ticker: str) -> dict:
    ti = parse_ticker(ticker)
    basic = ds.fetch_basic(ti)
    industry = basic.get("industry") or ""
    peers_raw: list = []
    peer_table: list = []
    peer_comparison: list = []

    # v2.5 · HK 分支：用 akshare HK valuation/scale comparison 给出 rank-in-HK-universe，
    # 没有具体同行名单（akshare 港股没有按行业列表函数；agent 可走 AASTOCKS Playwright 兜底）
    if ti.market == "H":
        ranks = (basic.get("_ranks") or {})
        val = ranks.get("valuation") or {}
        scale = ranks.get("scale") or {}
        growth = ranks.get("growth") or {}
        # 用 PE/PB/Mcap 排名构造一行 self
        self_row = {
            "name": basic.get("name") or ti.full,
            "code": ti.full,
            "pe": f"{val.get('pe_ttm', 0):.1f}" if val.get("pe_ttm") else "—",
            "pb": f"{val.get('pb_mrq', 0):.2f}" if val.get("pb_mrq") else "—",
            "roe": "—",
            "revenue_growth": f"{growth.get('revenue_yoy', 0):.1f}%" if growth.get("revenue_yoy") else "—",
            "is_self": True,
        }
        peer_table = [self_row]
        peer_comparison = [
            {"name": "PE-TTM 排名 (HK 全市场)", "self": val.get("pe_ttm_rank"), "peer": "—"},
            {"name": "PB-MRQ 排名 (HK 全市场)", "self": val.get("pb_mrq_rank"), "peer": "—"},
            {"name": "总市值排名 (HK 全市场)", "self": scale.get("market_cap_rank"), "peer": "—"},
            {"name": "营收 YoY 排名", "self": growth.get("revenue_yoy_rank"), "peer": "—"},
        ]
        # rank string for the report
        mcap_rank = scale.get("market_cap_rank")
        rank_str = f"HK 第 {mcap_rank} 位（按总市值）" if mcap_rank else "—"
        return {
            "ticker": ti.full,
            "data": {
                "industry": industry or "未分类（akshare HK 无行业聚合）",
                "self": basic,
                "peer_table": peer_table,
                "peer_comparison": peer_comparison,
                "rank": rank_str,
                "peers_top20_raw": [],
                "_note": "HK peer LIST 需走 AASTOCKS Playwright 或问财；本字段提供 rank-in-universe 作替代",
            },
            "source": "akshare:hk_valuation_comparison_em + scale_comparison_em + growth_comparison_em",
            "fallback": False,
        }

    if ti.market == "A" and industry:
        try:
            df = ak.stock_board_industry_cons_em(symbol=industry)
            if df is not None and not df.empty:
                # Sort by 市值 desc, take top 5 + self
                df = df.copy()
                df["_mcap"] = df["总市值"].apply(_float) if "总市值" in df.columns else 0
                df = df.sort_values("_mcap", ascending=False)
                peers_raw = df.head(20).to_dict("records")

                # Build peer_table: self + top 5 peers
                self_row = None
                peers_top5 = []
                for r in peers_raw:
                    code = str(r.get("代码", ""))
                    name = r.get("名称", "")
                    entry = {
                        "name": name,
                        "code": code,
                        "pe": f"{_float(r.get('市盈率-动态')):.1f}" if _float(r.get("市盈率-动态")) > 0 else "—",
                        "pb": f"{_float(r.get('市净率')):.2f}" if _float(r.get("市净率")) > 0 else "—",
                        "roe": "—",  # 需要单独查 stock_financial_analysis_indicator
                        "revenue_growth": "—",  # 同上
                    }
                    if code == ti.code:
                        entry["is_self"] = True
                        self_row = entry
                    elif len(peers_top5) < 5:
                        peers_top5.append(entry)

                peer_table = ([self_row] if self_row else []) + peers_top5

                # Comparison: self vs industry avg
                def _avg(col: str) -> float:
                    if col not in df.columns:
                        return 0.0
                    vals = [_float(v) for v in df[col] if _float(v) > 0]
                    return round(sum(vals) / len(vals), 2) if vals else 0.0

                self_pe = _float(basic.get("pe_ttm"))
                ind_pe = _avg("市盈率-动态")
                self_pb = _float(basic.get("pb"))
                ind_pb = _avg("市净率")
                peer_comparison = [
                    {"name": "PE (越低越好)", "self": self_pe, "peer": ind_pe},
                    {"name": "PB (越低越好)", "self": self_pb, "peer": ind_pb},
                ]
        except Exception as e:
            peers_raw = [{"error": str(e)}]

    return {
        "ticker": ti.full,
        "data": {
            "industry": industry,
            "self": basic,
            "peer_table": peer_table,
            "peer_comparison": peer_comparison,
            "rank": "—",  # 真实排名需要 聚合查询
            "peers_top20_raw": peers_raw[:20],
        },
        "source": "akshare:stock_board_industry_cons_em",
        "fallback": False,
    }


if __name__ == "__main__":
    print(json.dumps(main(sys.argv[1] if len(sys.argv) > 1 else "002273.SZ"), ensure_ascii=False, indent=2, default=str))
