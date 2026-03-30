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
        {"user_text": "hãy tìm tất cả file config telegram rồi tóm tắt", "expected_mode": "escalate_to_codex", "expected_task_shape": "exploratory_local"},
        {"user_text": "xem repo này đang có gì", "expected_mode": "escalate_to_codex", "expected_task_shape": "exploratory_local"},
        {"user_text": "debug lỗi này trong project OmniMind", "expected_mode": "escalate_to_codex", "expected_task_shape": "coding_ops"},
        {"user_text": "sửa file config để bật bot", "expected_mode": "escalate_to_codex", "expected_task_shape": "local_ops"},
        {"user_text": "chạy test rồi báo lỗi", "expected_mode": "escalate_to_codex", "expected_task_shape": "coding_ops"},
        {"user_text": "kiểm tra project này đang lỗi gì", "expected_mode": "escalate_to_codex", "expected_task_shape": "coding_ops"},
        {"user_text": "tìm tất cả chỗ dùng ConfigManager trong repo", "expected_mode": "escalate_to_codex", "expected_task_shape": "exploratory_local"},
        {"user_text": "bạn đang làm việc trong workspace nào", "expected_mode": "tool_calling", "expected_task_shape": "exploratory_local"},
        {"user_text": "liệt kê file .md trong docs", "expected_mode": "tool_calling", "expected_task_shape": "exploratory_local"},
        {"user_text": "repo hiện tại là gì", "expected_mode": "tool_calling", "expected_task_shape": "exploratory_local"},
        {"user_text": "tìm file WORKING_PRINCIPLES", "expected_mode": "tool_calling", "expected_task_shape": "exploratory_local"},
        {"user_text": "mở file đó", "expected_mode": "ask_clarification", "expected_task_shape": "local_ops"},
    ]

    rows = []
    failed = False
    for item in cases:
        text = str(item.get("user_text") or "").strip()
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
                "expected_mode": str(item.get("expected_mode") or "").strip(),
                "expected_task_shape": str(item.get("expected_task_shape") or "").strip(),
                "decision": decision,
                "codex_prompt_preview": prompt_preview,
            }
        )
        if decision.get("mode") != item.get("expected_mode") or decision.get("task_shape") != item.get("expected_task_shape"):
            failed = True

    print(json.dumps(rows, ensure_ascii=False, indent=2))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
