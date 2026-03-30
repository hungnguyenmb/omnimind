#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path


def _bootstrap_src():
    project_root = Path(__file__).resolve().parents[1]
    src_dir = project_root / "src"
    if str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))


def main() -> int:
    _bootstrap_src()
    from engine.central_ai_coordinator import CentralAiCoordinator

    coordinator = CentralAiCoordinator()
    channels = ["ui", "telegram", "zalo"]
    cases = [
        "bạn đang làm việc trong workspace nào",
        "xem repo này đang có gì",
        "kiểm tra project này đang lỗi gì",
        "mở file đó",
    ]

    rows = []
    failed = False
    for text in cases:
        decisions = {}
        for channel in channels:
            req = coordinator.build_request(
                channel=channel,
                user_text=text,
                thread_id=f"sprint11-{channel}",
                external_id=f"sprint11:{channel}:{text}",
            )
            decision = coordinator.decide_route(req)
            decisions[channel] = {
                "mode": decision.get("mode"),
                "task_shape": decision.get("task_shape"),
                "reason": decision.get("reason"),
                "missing_context": decision.get("missing_context"),
                "preferred_tool": decision.get("preferred_tool"),
            }
        baseline = decisions["ui"]
        for channel in channels[1:]:
            if decisions[channel] != baseline:
                failed = True
        rows.append({"user_text": text, "decisions": decisions})

    print(json.dumps(rows, ensure_ascii=False, indent=2))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
