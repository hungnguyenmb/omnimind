#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path


def _bootstrap_src_path():
    repo_root = Path(__file__).resolve().parents[1]
    src_dir = repo_root / "src"
    if str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))


def main():
    _bootstrap_src_path()
    from engine.central_ai_coordinator import CentralAiCoordinator

    if len(sys.argv) < 2:
        raise SystemExit("Usage: python3 scripts/test_central_ai_coordinator.py '<message>'")

    user_text = " ".join(sys.argv[1:]).strip()
    coordinator = CentralAiCoordinator()
    result = coordinator.handle_request(
        coordinator.build_request(channel="ui", user_text=user_text)
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result.get("success"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
