# -*- coding: utf-8 -*-
"""Standalone smoke test for 多模态融合分析_Qwen3VL_Local.py.

Usage:
  python test_qwen3vl_local.py
  python test_qwen3vl_local.py "帖子文字" "C:\\path\\to\\image.jpg"
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from 多模态融合分析_Qwen3VL_Local import MultimodalRiskFusion


def main() -> None:
    post_text = sys.argv[1] if len(sys.argv) > 1 else "保本高收益，扫码进群，老师带单。"
    image_path = (
        Path(sys.argv[2])
        if len(sys.argv) > 2
        else BASE_DIR / "pics" / "cd11b4851a0b415cd1a7f7c98560708f.jpg"
    )

    analyzer = MultimodalRiskFusion(base_dir=str(BASE_DIR))
    start = time.perf_counter()
    result = analyzer.analyze(post_text, str(image_path))
    elapsed = time.perf_counter() - start

    print(f"\n[local-test] total elapsed: {elapsed:.3f}s")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
