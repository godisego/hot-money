"""Dimension 0 · 基础信息 (name, code, industry, price, mcap, PE, PB).

Returns either:
    - Success:       {"ticker", "market", "data", "source", "fallback": False}
    - Name error:    {"ticker", "error": "name_not_resolved", "user_input",
                     "suggestions": [...], "source": "name_resolver", "fallback": True}

The second shape lets stage1() early-return and hand off to the agent / user
for disambiguation, instead of silently running 22 fetchers with a garbage
ticker and producing a half-empty report (see the 北部港湾 incident).
"""
import json
import sys

from lib import data_sources as ds
from lib.market_router import is_chinese_name, parse_ticker


def main(user_input: str) -> dict:
    if is_chinese_name(user_input):
        r = ds.resolve_chinese_name_rich(user_input)
        if r["resolved"] is None:
            # Ambiguous or unresolvable — surface candidates for UI confirmation.
            return {
                "ticker": user_input,
                "market": None,
                "data": {},
                "error": "name_not_resolved",
                "user_input": user_input,
                "suggestions": r["candidates"][:5],
                "source": f"name_resolver:{r['source']}",
                "fallback": True,
            }
        ti = r["resolved"]
    else:
        ti = parse_ticker(user_input)

    data = ds.fetch_basic(ti)
    return {
        "ticker": ti.full,
        "market": ti.market,
        "data": data,
        "source": f"akshare:{ti.market}",
        "fallback": False,
    }


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else "002273"
    print(json.dumps(main(arg), ensure_ascii=False, indent=2, default=str))
