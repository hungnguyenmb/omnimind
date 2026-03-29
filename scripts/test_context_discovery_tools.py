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
    from engine.function_executor import FunctionExecutor
    from engine.function_registry import FunctionRegistry

    project_root = Path(__file__).resolve().parents[1]
    registry = FunctionRegistry()
    executor = FunctionExecutor(registry=registry)
    coordinator = CentralAiCoordinator(function_registry=registry, function_executor=executor)

    checks = {
        "get_current_workspace": executor.execute_function("get_current_workspace", {}),
        "list_local_files": executor.execute_function(
            "list_local_files",
            {
                "path": str(project_root / "docs"),
                "pattern": "*.md",
                "max_entries": 8,
                "max_depth": 1,
            },
        ),
        "search_files_by_name": executor.execute_function(
            "search_files_by_name",
            {
                "query": "central_ai",
                "root_path": str(project_root / "docs"),
                "max_entries": 8,
            },
        ),
        "get_git_repo_info": executor.execute_function(
            "get_git_repo_info",
            {"path": str(project_root), "include_status": True},
        ),
    }

    route_cases = []
    for text in [
        "Bạn đang làm việc trong workspace nào",
        "Liệt kê file .md trong docs",
        "Repo hiện tại là gì",
        "Tìm file central_ai trong repo này",
    ]:
        req = coordinator.build_request(
            channel="ui",
            user_text=text,
            thread_id="sprint10-discovery-test",
            external_id=f"sprint10:{text}",
        )
        route_cases.append({"user_text": text, "decision": coordinator.decide_route(req)})

    print(
        json.dumps(
            {
                "checks": checks,
                "route_cases": route_cases,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
