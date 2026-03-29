from __future__ import annotations

from copy import deepcopy
from typing import Any

from engine.skill_manager import SkillManager


class FunctionRegistry:
    """
    Registry cho built-in functions mà AI trung tâm có thể gọi.
    Sprint 4 mới hỗ trợ built-in functions nội bộ; skill functions sẽ nối ở Sprint 5.
    """

    def __init__(self, skill_manager: SkillManager | None = None):
        self.skill_manager = skill_manager or SkillManager()
        self._functions: dict[str, dict[str, Any]] = {}
        self._skill_function_names: set[str] = set()
        self._register_builtin_functions()

    def _refresh_skill_functions(self, supported_channel: str = ""):
        for name in list(self._skill_function_names):
            self._functions.pop(name, None)
        self._skill_function_names = set()

        for definition in self.skill_manager.get_installed_skill_tool_functions(
            supported_channel=supported_channel,
            include_invalid=False,
        ):
            name = str((definition or {}).get("name") or "").strip()
            if not name:
                continue
            self._functions[name] = deepcopy(definition)
            self._skill_function_names.add(name)

    def _register_builtin_functions(self):
        self.register_function(
            {
                "name": "get_system_info",
                "description": "Lay thong tin he thong va runtime hien tai cua OmniMind.",
                "input_schema": {
                    "type": "object",
                    "properties": {},
                    "additionalProperties": False,
                },
                "required_capabilities": [],
                "approval_policy": "auto",
                "execution_target": {"kind": "builtin", "handler": "get_system_info"},
            }
        )
        self.register_function(
            {
                "name": "get_current_workspace",
                "description": "Lay thong tin workspace, cwd va git repo hien tai de xac dinh context local.",
                "input_schema": {
                    "type": "object",
                    "properties": {},
                    "additionalProperties": False,
                },
                "required_capabilities": ["fs_read"],
                "approval_policy": "auto",
                "execution_target": {"kind": "builtin", "handler": "get_current_workspace"},
            }
        )
        self.register_function(
            {
                "name": "list_local_files",
                "description": "Liet ke file local theo thu muc va pattern de kham pha workspace mot cach read-only.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Thu muc can liet ke. Bo trong thi dung workspace hien tai."},
                        "pattern": {"type": "string", "description": "Pattern loc ten file, vi du *.md hoac config."},
                        "max_entries": {"type": "integer", "description": "So dong ket qua toi da."},
                        "max_depth": {"type": "integer", "description": "Do sau toi da khi di qua cay thu muc."},
                        "include_dirs": {"type": "boolean", "description": "Co bao gom thu muc hay khong."},
                    },
                    "additionalProperties": False,
                },
                "required_capabilities": ["fs_read"],
                "approval_policy": "auto",
                "execution_target": {"kind": "builtin", "handler": "list_local_files"},
            }
        )
        self.register_function(
            {
                "name": "search_files_by_name",
                "description": "Tim file theo ten, extension hoac chuoi truy van trong workspace hien tai theo che do read-only.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Ten file, extension hoac pattern can tim."},
                        "root_path": {"type": "string", "description": "Thu muc goc de tim. Bo trong thi uu tien repo/workspace hien tai."},
                        "max_entries": {"type": "integer", "description": "So ket qua toi da muon lay."},
                    },
                    "required": ["query"],
                    "additionalProperties": False,
                },
                "required_capabilities": ["fs_read"],
                "approval_policy": "auto",
                "execution_target": {"kind": "builtin", "handler": "search_files_by_name"},
            }
        )
        self.register_function(
            {
                "name": "get_git_repo_info",
                "description": "Lay thong tin git repo hien tai nhu repo root, branch va tom tat status ngan gon.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Thu muc muon xac dinh repo."},
                        "include_status": {"type": "boolean", "description": "Co lay them git status ngan gon hay khong."},
                    },
                    "additionalProperties": False,
                },
                "required_capabilities": ["fs_read"],
                "approval_policy": "auto",
                "execution_target": {"kind": "builtin", "handler": "get_git_repo_info"},
            }
        )
        self.register_function(
            {
                "name": "read_local_file",
                "description": "Doc noi dung text tu mot file local de phan tich hoặc tom tat.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Duong dan file local."},
                        "max_chars": {"type": "integer", "description": "So ky tu toi da muon doc."},
                    },
                    "required": ["path"],
                    "additionalProperties": False,
                },
                "required_capabilities": ["fs_read"],
                "approval_policy": "auto",
                "execution_target": {"kind": "builtin", "handler": "read_local_file"},
            }
        )
        self.register_function(
            {
                "name": "write_local_file",
                "description": "Ghi noi dung vao mot file local khi da co noi dung can luu.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Duong dan file local."},
                        "content": {"type": "string", "description": "Noi dung can ghi."},
                        "overwrite": {"type": "boolean", "description": "Cho phep ghi de neu file da ton tai."},
                    },
                    "required": ["path", "content"],
                    "additionalProperties": False,
                },
                "required_capabilities": ["fs_write"],
                "approval_policy": "on-request",
                "execution_target": {"kind": "builtin", "handler": "write_local_file"},
            }
        )
        self.register_function(
            {
                "name": "run_shell_command",
                "description": "Chay mot shell command an toan, uu tien cac lenh doc thong tin hoac kiem tra trang thai.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "command": {"type": "string", "description": "Lenh can chay."},
                        "cwd": {"type": "string", "description": "Thu muc lam viec neu can."},
                        "timeout_seconds": {"type": "integer", "description": "Timeout toi da theo giay."},
                    },
                    "required": ["command"],
                    "additionalProperties": False,
                },
                "required_capabilities": ["exec"],
                "approval_policy": "on-request",
                "execution_target": {"kind": "builtin", "handler": "run_shell_command"},
            }
        )
        self.register_function(
            {
                "name": "runtime_ping",
                "description": "Kiem tra nhanh runtime action pipeline cua OmniMind.",
                "input_schema": {
                    "type": "object",
                    "properties": {},
                    "additionalProperties": False,
                },
                "required_capabilities": [],
                "approval_policy": "auto",
                "execution_target": {
                    "kind": "builtin_action",
                    "action_id": "runtime_ping",
                },
            }
        )
        self.register_function(
            {
                "name": "screen_capture",
                "description": "Chup man hinh va tra ve duong dan artifact anh tao ra.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "subdir": {"type": "string", "description": "Thu muc con de luu artifact."},
                    },
                    "additionalProperties": False,
                },
                "required_capabilities": ["screen_capture"],
                "approval_policy": "on-request",
                "execution_target": {
                    "kind": "builtin_action",
                    "action_id": "screen_capture",
                },
            }
        )
        self.register_function(
            {
                "name": "camera_snapshot",
                "description": "Thu chup nhanh tu camera neu runtime co ho tro.",
                "input_schema": {
                    "type": "object",
                    "properties": {},
                    "additionalProperties": False,
                },
                "required_capabilities": ["camera_access"],
                "approval_policy": "on-request",
                "execution_target": {
                    "kind": "builtin_action",
                    "action_id": "camera_snapshot",
                },
            }
        )
        self.register_function(
            {
                "name": "ui_automation_type_text",
                "description": "Gui chuoi text vao cua so dang focus qua UI automation.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string", "description": "Noi dung can go vao cua so dang focus."},
                    },
                    "required": ["text"],
                    "additionalProperties": False,
                },
                "required_capabilities": ["ui_automation"],
                "approval_policy": "on-request",
                "execution_target": {
                    "kind": "builtin_action",
                    "action_id": "ui_automation_type_text",
                },
            }
        )
        self.register_function(
            {
                "name": "system_restart",
                "description": "Gui lenh restart he thong. Chi dung khi yeu cau rat ro rang.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "confirm": {"type": "boolean"},
                        "dry_run": {"type": "boolean"},
                    },
                    "required": ["confirm"],
                    "additionalProperties": False,
                },
                "required_capabilities": ["system_restart"],
                "approval_policy": "on-request",
                "execution_target": {
                    "kind": "builtin_action",
                    "action_id": "system_restart",
                },
            }
        )

    def register_function(self, definition: dict[str, Any]):
        name = str((definition or {}).get("name") or "").strip()
        if not name:
            raise ValueError("Function definition thiếu name.")
        self._functions[name] = deepcopy(definition)

    def get_definition(self, name: str) -> dict[str, Any] | None:
        self._refresh_skill_functions()
        key = str(name or "").strip()
        if not key or key not in self._functions:
            return None
        return deepcopy(self._functions[key])

    def list_definitions(self, supported_channel: str = "") -> list[dict[str, Any]]:
        self._refresh_skill_functions(supported_channel=supported_channel)
        return [deepcopy(item) for item in self._functions.values()]

    def list_tool_schemas(self, include_on_request: bool = True, supported_channel: str = "") -> list[dict[str, Any]]:
        self._refresh_skill_functions(supported_channel=supported_channel)
        out: list[dict[str, Any]] = []
        for definition in self._functions.values():
            approval_policy = str(definition.get("approval_policy") or "auto").strip().lower()
            if approval_policy == "on-request" and not include_on_request:
                continue
            out.append(
                {
                    "type": "function",
                    "function": {
                        "name": str(definition.get("name") or "").strip(),
                        "description": str(definition.get("description") or "").strip(),
                        "parameters": deepcopy(definition.get("input_schema") or {"type": "object", "properties": {}}),
                    },
                }
            )
        return out
