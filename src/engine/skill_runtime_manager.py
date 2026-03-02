import logging
from typing import Callable, Iterable

from engine.action_executor import ActionExecutor
from engine.permission_manager import PermissionManager

logger = logging.getLogger(__name__)


class SkillRuntimeManager:
    """
    Runtime orchestrator cho skill actions:
    - Chuẩn hóa capability preflight trước khi execute.
    - Hỗ trợ auto-request quyền và retry preflight.
    - Trả lỗi chuẩn PERMISSION_REQUIRED cho UI/Telegram/Codex flow xử lý tiếp.
    """

    def __init__(
        self,
        skill_manager=None,
        action_executor: ActionExecutor | None = None,
        permission_manager: PermissionManager | None = None,
    ):
        self.skill_manager = skill_manager
        self.action_executor = action_executor or ActionExecutor()
        self.permission_manager = permission_manager or PermissionManager()

    @staticmethod
    def _normalize_capabilities(capabilities: Iterable[str] | str | None) -> list[str]:
        if capabilities is None:
            return []
        if isinstance(capabilities, str):
            capabilities = [capabilities]

        out = []
        for cap in capabilities:
            cap_val = str(cap or "").strip().lower().replace(" ", "_")
            if not cap_val:
                continue
            if cap_val not in out:
                out.append(cap_val)
        return out

    def _resolve_capabilities(self, skill_id: str, required_capabilities=None) -> list[str]:
        caps = self._normalize_capabilities(required_capabilities)
        if caps:
            return caps
        if not self.skill_manager:
            return []
        try:
            req = self.skill_manager.get_skill_runtime_requirements(skill_id)
            return self._normalize_capabilities(req.get("required_capabilities", []))
        except Exception as e:
            logger.warning(f"Cannot resolve capabilities for skill {skill_id}: {e}")
            return []

    def _request_missing_permissions(self, missing_permissions: list[dict]) -> list[dict]:
        opened = []
        seen = set()
        for item in missing_permissions or []:
            perm = str(item.get("permission", "")).strip().lower()
            if not perm or perm in seen:
                continue
            seen.add(perm)
            try:
                req = self.permission_manager.request(perm)
                opened.append(
                    {
                        "permission": perm,
                        "success": bool(req.get("success")),
                        "open_mode": req.get("open_mode", "failed"),
                        "platform": req.get("platform", ""),
                    }
                )
            except Exception as e:
                logger.warning(f"Request permission failed ({perm}): {e}")
                opened.append(
                    {
                        "permission": perm,
                        "success": False,
                        "open_mode": "failed",
                        "platform": "",
                    }
                )
        return opened

    def execute(
        self,
        skill_id: str,
        action_id: str,
        payload: dict | None = None,
        required_capabilities=None,
        runner: Callable[[dict], dict] | None = None,
        auto_request_permissions: bool = False,
    ) -> dict:
        skill_id = str(skill_id or "").strip()
        action_id = str(action_id or "").strip()
        payload = payload or {}

        if not skill_id:
            return {"success": False, "code": "INVALID_SKILL_ID", "message": "Thiếu skill_id."}
        if not action_id:
            return {"success": False, "code": "INVALID_ACTION_ID", "message": "Thiếu action_id."}

        capabilities = self._resolve_capabilities(skill_id, required_capabilities)
        op_id = f"skill:{skill_id}:{action_id}"
        preflight = self.action_executor.preflight_capabilities(capabilities, action_id=f"{op_id}:preflight")
        requested = []

        if not preflight.get("success") and auto_request_permissions:
            requested = self._request_missing_permissions(preflight.get("missing_permissions", []))
            preflight = self.action_executor.preflight_capabilities(capabilities, action_id=f"{op_id}:retry_preflight")

        if not preflight.get("success"):
            return {
                "success": False,
                "code": "PERMISSION_REQUIRED",
                "message": "Action chưa thể chạy do thiếu quyền hệ thống hoặc capability chưa hỗ trợ.",
                "skill_id": skill_id,
                "action_id": action_id,
                "required_capabilities": capabilities,
                "preflight": preflight,
                "requested_permissions": requested,
            }

        if runner is None:
            return self.action_executor.execute_action(
                action_id=op_id,
                capabilities=capabilities,
                runner=lambda: {
                    "success": True,
                    "code": "ACTION_READY",
                    "message": "Preflight thành công. Action sẵn sàng chạy.",
                    "skill_id": skill_id,
                    "action_id": action_id,
                    "required_capabilities": capabilities,
                },
            )

        return self.action_executor.execute_action(
            action_id=op_id,
            capabilities=capabilities,
            runner=lambda: runner(payload),
        )
