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
    project_root = Path(__file__).resolve().parents[1]
    _bootstrap_src()
    from engine.artifact_manager import ArtifactManager
    from engine.central_ai_coordinator import CentralAiCoordinator
    from engine.config_manager import ConfigManager

    image_path = project_root / "src" / "ui" / "assets" / "omnimind-app.png"
    artifact = ArtifactManager.normalize_local_artifact(
        str(image_path),
        source_channel="ui",
        source_message_id="script:vision",
        metadata={"purpose": "vision_test"},
    )
    result = {
        "artifact": artifact,
    }

    if ConfigManager.get_openapi_proxy_api_key():
        coordinator = CentralAiCoordinator()
        request = coordinator.build_request(
            channel="ui",
            user_text="Hãy mô tả ngắn gọn ảnh local này.",
            thread_id="script:test_vision_artifact_flow",
            external_id="script:test_vision_artifact_flow:user",
            attachments=[artifact],
        )
        result["coordinator_result"] = coordinator.handle_request(
            request,
            persist_turn=False,
            allow_codex_fallback=False,
        )
    else:
        result["coordinator_result"] = {
            "success": True,
            "skipped": True,
            "message": "Bỏ qua vision flow vì chưa có OPENAPI_PROXY_API_KEY.",
        }

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["coordinator_result"].get("success") else 1


if __name__ == "__main__":
    raise SystemExit(main())
