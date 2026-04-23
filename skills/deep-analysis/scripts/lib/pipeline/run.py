"""pipeline.run · 编排入口 · collect → score → synthesize.

**opt-in · 默认关闭**：必须 `UZI_PIPELINE=1` 才会启用。
老路径 `run_real_test.stage1()/stage2()` 仍是默认 · 零业务影响.

用法：
    from lib.pipeline.run import run_pipeline
    report_path = run_pipeline("300470.SZ")
"""
from __future__ import annotations

import json
from pathlib import Path

from .collect import collect as pipeline_collect
from .score import score_from_cache
from .synthesize import synthesize_and_render


def run_pipeline(ticker: str, resume: bool = True) -> str:
    """完整管道入口（Phase 6a delegate 模式）.

    1. pipeline.collect · 用 22 BaseFetcher adapter 抓数据
    2. 把结果写到 .cache/<ticker>/raw_data.json（与 legacy 兼容）
    3. 调 legacy stage1 做 scoring（resume 模式复用我们写的 cache）
    4. 调 legacy stage2 生成报告

    **中间过渡状态** · collect 由新管道接管 · score/synthesize 仍走 legacy.
    Phase 6/7（未来 session）逐步把 score/synthesize 内部逻辑也迁进来.
    """
    print(f"🚀 [pipeline.run] collect · {ticker}")
    raw_previous = _load_cache(ticker) if resume else {}
    raw_dict = pipeline_collect(ticker, raw_previous=raw_previous, max_workers=1)

    # 组装 legacy 兼容 raw_data.json（dimensions + 顶层溢出字段）
    raw_data_compatible = {
        "ticker": ticker,
        "dimensions": {k: v for k, v in raw_dict.items()
                       if k not in ("fund_managers", "similar_stocks")},
    }
    for k in ("fund_managers", "similar_stocks"):
        if k in raw_dict:
            raw_data_compatible[k] = raw_dict[k]

    _write_cache(ticker, raw_data_compatible)
    print(f"✅ [pipeline.run] raw_data.json 已写 · 调 legacy scoring+synth")

    # 复用 legacy stage1 (resume · 跳 collect 只做 scoring) + stage2
    score_from_cache(ticker)
    return synthesize_and_render(ticker)


def _load_cache(ticker: str) -> dict:
    """读已有 raw_data.json · 用于 resume."""
    from lib.market_router import parse_ticker
    ti = parse_ticker(ticker)
    import run_real_test as rrt
    cache_path = Path(rrt.__file__).parent / ".cache" / ti.full / "raw_data.json"
    if not cache_path.exists():
        return {}
    try:
        return json.loads(cache_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_cache(ticker: str, raw: dict) -> None:
    """写 raw_data.json · 让 legacy stage1 的 resume 能复用."""
    from lib.market_router import parse_ticker
    ti = parse_ticker(ticker)
    import run_real_test as rrt
    cache_dir = Path(rrt.__file__).parent / ".cache" / ti.full
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / "raw_data.json"
    try:
        cache_path.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"   ⚠️ 写 cache 失败: {e}")
