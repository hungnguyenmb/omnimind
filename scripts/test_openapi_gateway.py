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
    from engine.ai_gateway_client import AiGatewayClient

    client = AiGatewayClient()
    report = client.probe_gateway()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not report.get("success"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
