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


def _create_sample_skill(root_dir: Path, skill_id: str) -> Path:
    skill_dir = root_dir / skill_id
    scripts_dir = skill_dir / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)

    (skill_dir / "SKILL.md").write_text(
        "---\n"
        f"name: {skill_id}\n"
        "description: Demo skill cho Sprint 5.\n"
        "version: 1.0.0\n"
        "skill_type: TOOL\n"
        "---\n\n"
        "# Demo Skill\n",
        encoding="utf-8",
    )
    (skill_dir / "tool_manifest.json").write_text(
        json.dumps(
            {
                "manifest_version": "1.0",
                "skill_id": skill_id,
                "functions": [
                    {
                        "name": "generate_greeting",
                        "description": "Tạo một lời chào ngắn gọn, thân thiện cho tên được cung cấp.",
                        "input_schema": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                            },
                            "required": ["name"],
                            "additionalProperties": False,
                        },
                        "execution": {
                            "type": "python_script",
                            "entrypoint": "scripts/main.py",
                        },
                        "required_capabilities": [],
                        "approval_policy": "auto",
                        "supported_channels": ["ui", "telegram", "zalo"],
                        "timeout_seconds": 20,
                        "returns_artifacts": False,
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (scripts_dir / "main.py").write_text(
        "import argparse, json\n"
        "parser = argparse.ArgumentParser()\n"
        "parser.add_argument('--name', required=True)\n"
        "args = parser.parse_args()\n"
        "print(json.dumps({\n"
        "  'success': True,\n"
        "  'code': 'GREETING_READY',\n"
        "  'message': f'Da tao loi chao cho {args.name}.',\n"
        "  'greeting': f'Xin chao {args.name}, day la loi chao tu sample skill Sprint 5.'\n"
        "}, ensure_ascii=False))\n",
        encoding="utf-8",
    )
    return skill_dir


def main() -> int:
    _bootstrap_src()

    parser = argparse.ArgumentParser(description="Test local installed skill function loop.")
    parser.add_argument(
        "prompt",
        nargs="?",
        default="Hãy dùng skill demo-skill-function-loop để tạo một lời chào cho Lan, đừng tự viết tay nếu chưa gọi skill.",
    )
    args = parser.parse_args()

    from database.db_manager import db
    from engine.central_ai_coordinator import CentralAiCoordinator
    from engine.config_manager import ConfigManager
    from engine.function_executor import FunctionExecutor
    from engine.function_registry import FunctionRegistry
    from engine.skill_manager import SkillManager

    skill_id = "demo-skill-function-loop"
    with tempfile.TemporaryDirectory() as tmpdir:
        skill_dir = _create_sample_skill(Path(tmpdir), skill_id)
        db.execute_query(
            """
            INSERT INTO installed_skills (skill_id, name, version, local_path, installed_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(skill_id) DO UPDATE SET
                name = excluded.name,
                version = excluded.version,
                local_path = excluded.local_path,
                installed_at = CURRENT_TIMESTAMP
            """,
            (skill_id, "Demo Skill Function Loop", "1.0.0", str(skill_dir)),
            commit=True,
        )

        try:
            skill_manager = SkillManager()
            functions = skill_manager.get_installed_skill_tool_functions(supported_channel="ui")
            registry = FunctionRegistry(skill_manager=skill_manager)
            executor = FunctionExecutor(registry=registry, skill_manager=skill_manager)
            function_name = skill_manager._safe_tool_function_name(skill_id, "generate_greeting")
            exec_result = executor.execute_function(function_name, {"name": "Lan"})
            if ConfigManager.get_openapi_proxy_api_key():
                coordinator = CentralAiCoordinator(function_registry=registry, function_executor=executor)
                request = coordinator.build_request(
                    channel="ui",
                    user_text=str(args.prompt or "").strip(),
                    thread_id="script:test_skill_function_loop",
                    external_id="script:test_skill_function_loop:user",
                )
                ai_result = coordinator.handle_request(request, persist_turn=False, allow_codex_fallback=False)
            else:
                ai_result = {
                    "success": True,
                    "skipped": True,
                    "message": "Bỏ qua bước AI loop vì chưa có OPENAPI_PROXY_API_KEY.",
                }
            print(
                json.dumps(
                    {
                        "installed_functions": functions,
                        "executor_result": exec_result,
                        "ai_result": ai_result,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            ok = bool(functions) and bool(exec_result.get("success")) and bool(ai_result.get("success"))
            return 0 if ok else 1
        finally:
            db.execute_query("DELETE FROM installed_skills WHERE skill_id = ?", (skill_id,), commit=True)


if __name__ == "__main__":
    raise SystemExit(main())
