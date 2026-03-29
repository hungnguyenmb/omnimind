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
    project_root = _bootstrap_src()

    parser = argparse.ArgumentParser(description="Test built-in function loop for Central AI.")
    parser.add_argument(
        "prompt",
        nargs="?",
        default="Hãy đọc file mẫu do script tạo ra và tóm tắt nội dung ngắn gọn.",
    )
    parser.add_argument(
        "--with-sample-file",
        action="store_true",
        help="Tạo file mẫu tạm thời và nối path vào prompt.",
    )
    args = parser.parse_args()

    user_prompt = str(args.prompt or "").strip()
    if args.with_sample_file:
        tmp_path = Path(tempfile.gettempdir()) / "omnimind_builtin_tool_test.txt"
        tmp_path.write_text(
            "OmniMind Sprint 4 test file.\n"
            "Muc tieu: AI trung tam goi read_local_file va tom tat ket qua.\n"
            "Noi dung nay dung de kiem tra tool loop built-in.\n",
            encoding="utf-8",
        )
        user_prompt = f"{user_prompt}\n\nĐường dẫn file local: {tmp_path}"

    from engine.central_ai_coordinator import CentralAiCoordinator

    coordinator = CentralAiCoordinator()
    request = coordinator.build_request(
        channel="ui",
        user_text=user_prompt,
        thread_id="script:test_builtin_function_loop",
        external_id="script:test_builtin_function_loop:user",
        metadata={"cwd": str(project_root)},
    )
    result = coordinator.handle_request(request, persist_turn=False)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("success") else 1


if __name__ == "__main__":
    raise SystemExit(main())
