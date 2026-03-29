#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path


def _bootstrap_src():
    project_root = Path(__file__).resolve().parents[1]
    src_dir = project_root / "src"
    if str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))
    return project_root


def main() -> int:
    _bootstrap_src()

    parser = argparse.ArgumentParser(description="Test multi-step tool loop for Central AI.")
    parser.add_argument(
        "prompt",
        nargs="?",
        default=(
            "Hãy dùng tool để làm đủ 2 việc sau rồi mới trả lời: "
            "1) lấy thông tin hệ thống hiện tại của máy này, "
            "2) đọc file mẫu tôi cung cấp. "
            "Sau đó tóm tắt cả hai phần trong một câu trả lời ngắn gọn."
        ),
    )
    args = parser.parse_args()

    from engine.central_ai_coordinator import CentralAiCoordinator

    with tempfile.TemporaryDirectory() as tmpdir:
        sample_path = Path(tmpdir) / "multi_step_demo.txt"
        sample_path.write_text(
            "Day la file demo cho Sprint 6.\n"
            "Muc tieu: kiem tra AI trung tam co the goi nhieu hon mot tool trong cung mot request.\n",
            encoding="utf-8",
        )
        prompt = f"{args.prompt}\n\nĐường dẫn file local: {sample_path}"

        coordinator = CentralAiCoordinator()
        request = coordinator.build_request(
            channel="ui",
            user_text=prompt,
            thread_id="script:test_multi_step_tool_loop",
            external_id="script:test_multi_step_tool_loop:user",
        )
        result = coordinator.handle_request(request, persist_turn=False, allow_codex_fallback=False)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        trace = result.get("trace") if isinstance(result.get("trace"), dict) else {}
        ok = bool(result.get("success")) and int(trace.get("tool_call_count") or 0) >= 2
        return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
