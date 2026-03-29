#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _bootstrap_src():
    project_root = Path(__file__).resolve().parents[1]
    src_dir = project_root / "src"
    if str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))


def _load_cases(path: Path) -> list[dict]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("Case file phải là JSON array.")
    cases: list[dict] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        user_text = str(item.get("user_text") or "").strip()
        if not user_text:
            continue
        cases.append(dict(item))
    return cases


def _parse_args() -> argparse.Namespace:
    project_root = Path(__file__).resolve().parents[1]
    default_cases = project_root / "scripts" / "test_decision_contract_v2_cases.json"
    parser = argparse.ArgumentParser(description="Kiểm tra nhanh decision contract v2 của Central AI.")
    parser.add_argument("--cases", default=str(default_cases), help="Đường dẫn JSON file chứa danh sách utterance test.")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    _bootstrap_src()
    from engine.central_ai_coordinator import CentralAiCoordinator

    coordinator = CentralAiCoordinator()
    case_path = Path(args.cases).expanduser().resolve()
    cases = _load_cases(case_path)
    rows = []
    for item in cases:
        text = str(item.get("user_text") or "").strip()
        request = coordinator.build_request(channel="ui", user_text=text, thread_id="decision-v2-test", external_id="decision-v2-test:user")
        decision = coordinator.decide_route(request)
        rows.append(
            {
                "user_text": text,
                "expected_mode": str(item.get("expected_mode") or "").strip(),
                "expected_task_shape": str(item.get("expected_task_shape") or "").strip(),
                "notes": str(item.get("notes") or "").strip(),
                "decision": decision,
            }
        )
    print(json.dumps(rows, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
