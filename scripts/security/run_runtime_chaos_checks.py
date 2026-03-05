#!/usr/bin/env python3
"""Sprint 6 - Item 5: chaos checks for Telegram/Codex runtime resilience."""

from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = PROJECT_ROOT / "src"
import sys

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from engine.codex_runtime_bridge import CodexRuntimeBridge
from engine.process_lock import InterProcessFileLock
from engine.telegram_bot_service import TelegramBotService, TelegramStreamTransport


class FakeResponse:
    def __init__(self, payload: Any = None, raise_json: bool = False):
        self._payload = payload
        self._raise_json = raise_json
        self.content = b"{}"

    def json(self):
        if self._raise_json:
            raise ValueError("invalid json")
        return self._payload


def _assert(condition: bool, message: str):
    if not condition:
        raise AssertionError(message)


def scenario_get_updates_409_conflict() -> dict:
    service = TelegramBotService()

    def fake_get(*args, **kwargs):
        return FakeResponse({"ok": False, "error_code": 409, "description": "Conflict"})

    service._session.get = fake_get
    result = service._get_updates("dummy", 0)
    _assert(result == [], "409 conflict phải trả [] thay vì crash")
    _assert(service._conflict_count >= 1, "Không tăng conflict counter")
    return {"ok": True, "conflict_count": service._conflict_count}


def scenario_get_updates_invalid_json() -> dict:
    service = TelegramBotService()

    def fake_get(*args, **kwargs):
        return FakeResponse(raise_json=True)

    service._session.get = fake_get
    result = service._get_updates("dummy", 0)
    _assert(result == [], "invalid json phải trả []")
    return {"ok": True}


def scenario_transport_retry_then_success() -> dict:
    transport = TelegramStreamTransport("dummy-token")
    calls = {"count": 0}
    payloads = [
        {"ok": False, "error_code": 429, "description": "Too Many Requests", "parameters": {"retry_after": 0}},
        {"ok": True, "result": {"message_id": 777}},
    ]

    def fake_post(*args, **kwargs):
        calls["count"] += 1
        current = payloads.pop(0) if payloads else {"ok": True, "result": {"message_id": 778}}
        return FakeResponse(current)

    transport._session.post = fake_post
    message_id = transport.send_message(chat_id="1", text="health-check")
    _assert(message_id == 777, "retry logic không lấy đúng message_id")
    _assert(calls["count"] == 2, "retry logic phải gọi đúng 2 lần")
    return {"ok": True, "attempts": calls["count"]}


def scenario_action_directive_parser_tolerates_bad_json() -> dict:
    service = TelegramBotService()
    raw = (
        "abc [[OMNIMIND_RUN_ACTION:action_id=telegram_send_document;"
        "payload_json={not-valid-json};auto_request_permissions=yes]] xyz"
    )
    cleaned, directives = service._extract_runtime_action_directives(raw)
    _assert(len(directives) == 1, "directive parser phải trả đúng 1 action")
    _assert(directives[0].get("action_id") == "telegram_send_document", "action_id parse sai")
    _assert(directives[0].get("payload") == {}, "payload parse lỗi phải fallback {}")
    _assert("OMNIMIND_RUN_ACTION" not in cleaned, "directive text chưa bị loại khỏi output")
    return {"ok": True}


def scenario_process_lock_single_owner() -> dict:
    with tempfile.TemporaryDirectory(prefix="omnimind-lock-chaos-") as td:
        lock_path = Path(td) / "telegram.lock"
        lock1 = InterProcessFileLock(lock_path)
        lock2 = InterProcessFileLock(lock_path)

        _assert(lock1.acquire() is True, "lock1 acquire thất bại")
        _assert(lock2.acquire() is False, "lock2 phải bị chặn khi lock1 đang giữ")
        lock1.release()
        _assert(lock2.acquire() is True, "lock2 phải acquire được sau khi lock1 release")
        lock2.release()
    return {"ok": True}


def scenario_map_known_runtime_error() -> dict:
    bridge = CodexRuntimeBridge()
    mapped = bridge._map_known_runtime_error(
        "Not inside a trusted directory and --skip-git-repo-check was not specified."
    )
    _assert("Workspace chưa được tin cậy" in mapped, "known error mapper chưa map đúng thông điệp")
    return {"ok": True}


def main() -> int:
    scenarios = [
        ("get_updates_409_conflict", scenario_get_updates_409_conflict),
        ("get_updates_invalid_json", scenario_get_updates_invalid_json),
        ("transport_retry_then_success", scenario_transport_retry_then_success),
        ("action_directive_parser_bad_json", scenario_action_directive_parser_tolerates_bad_json),
        ("process_lock_single_owner", scenario_process_lock_single_owner),
        ("known_runtime_error_mapping", scenario_map_known_runtime_error),
    ]

    records: list[dict[str, Any]] = []
    failed = 0
    for name, fn in scenarios:
        started = datetime.now(timezone.utc).isoformat()
        try:
            payload = fn() or {}
            records.append({"name": name, "status": "passed", "started_at": started, "details": payload})
            print(f"[PASS] {name}")
        except Exception as e:
            failed += 1
            records.append({"name": name, "status": "failed", "started_at": started, "error": str(e)})
            print(f"[FAIL] {name}: {e}")

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "total": len(scenarios),
            "passed": len(scenarios) - failed,
            "failed": failed,
        },
        "scenarios": records,
    }
    report_dir = PROJECT_ROOT / "release-artifacts" / "security-reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / f"runtime_chaos_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Report: {report_path}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
