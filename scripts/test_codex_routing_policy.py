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
    cases = [
        "hãy tìm tất cả file config telegram rồi tóm tắt",
        "xem repo này đang có gì",
        "debug lỗi này trong project OmniMind",
        "sửa file config để bật bot",
        "chạy test rồi báo lỗi",
        "bạn đang làm việc trong workspace nào",
        "liệt kê file .md trong docs",
        "repo hiện tại là gì",
        "tìm file WORKING_PRINCIPLES",
    ]

    rows = []
    for text in cases:
        req = coordinator.build_request(
            channel="ui",
            user_text=text,
            thread_id="sprint11-codex-routing",
            external_id=f"sprint11:{text}",
        )
        decision = coordinator.decide_route(req)
        prompt_preview = ""
        if str(decision.get("mode") or "").strip() == "escalate_to_codex":
            context = coordinator.orchestrator.build_context()
            prompt_preview = coordinator._build_codex_prompt(req, context)[:900]
        rows.append(
            {
                "user_text": text,
                "decision": decision,
                "codex_prompt_preview": prompt_preview,
            }
        )

    print(json.dumps(rows, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
