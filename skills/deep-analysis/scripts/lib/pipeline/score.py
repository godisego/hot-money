"""pipeline.score · Rules 引擎 + 51 评委打分 · delegate wrapper (Phase 6a).

**本阶段不重写 legacy 逻辑** · 仅提供统一调用入口。
Phase 6（未来 session）：把 run_real_test 里的 build_dimensions/build_panel/compute_institutional 挪进来。

当前策略：
- `score_from_raw(raw)` · 假设 raw 已经 collect 好 · 调 legacy stage1 的 scoring 路径
- 实现方式：让 legacy stage1 用 resume 模式读已有 cache · 跳过 collect 只做 scoring

安全保证：run_real_test.py 不改 · 只从外部调用 · 零业务影响.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def score_from_cache(ticker: str) -> dict:
    """给定已有 .cache/<ticker>/raw_data.json · 执行 scoring 并落地 panel.json / dimensions.json.

    调 legacy stage1 · resume 模式 · 跳过 collect 只做 scoring.
    返回 {"dimensions": {...}, "panel": {...}} dict.
    """
    import run_real_test as rrt
    # legacy stage1 读 cache + 跑全流程（含 scoring）· 我们只关心 scoring 产出
    result = rrt.stage1(ticker)
    if not isinstance(result, dict):
        return {}
    # stage1 完成后 · 读落地的 panel.json / dimensions.json
    from lib.market_router import parse_ticker
    ti = parse_ticker(ticker)
    cache_dir = Path(rrt.__file__).parent / ".cache" / ti.full
    dimensions = _read_json(cache_dir / "dimensions.json") or {}
    panel = _read_json(cache_dir / "panel.json") or {}
    return {"dimensions": dimensions, "panel": panel}


def _read_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
