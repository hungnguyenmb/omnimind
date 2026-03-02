import json
import logging
from typing import Callable, Iterable

from database.db_manager import db
from engine.permission_manager import PermissionManager

logger = logging.getLogger(__name__)


class ActionExecutor:
    """
    Cổng thực thi action nhạy cảm.
    - Map capability -> quyền hệ thống bắt buộc.
    - Preflight quyền trước khi chạy action.
    - Ghi audit log cho mọi lần preflight/execute.
    """

    CAPABILITY_MATRIX = {
        "screen_capture": {"permissions": ["screenshot"]},
        "camera_access": {"permissions": ["camera"]},
        "ui_automation": {"permissions": ["accessibility"]},
        # Khởi động lại máy thường cần quyền quản trị/elevation theo từng OS.
        "system_restart": {"permissions": []},
    }

    def __init__(self, permission_manager: PermissionManager | None = None):
        self.permission_manager = permission_manager or PermissionManager()

    def preflight_capabilities(self, capabilities: Iterable[str], action_id: str = "preflight") -> dict:
        caps = [str(c).strip() for c in (capabilities or []) if str(c).strip()]
        if not caps:
            result = {"success": True, "missing_permissions": [], "unknown_capabilities": [], "checked": []}
            self._audit(action_id, "", "allowed", result)
            return result

        unknown = [c for c in caps if c not in self.CAPABILITY_MATRIX]
        missing = []
        checked = []

        for cap in caps:
            matrix = self.CAPABILITY_MATRIX.get(cap, {})
            perms = matrix.get("permissions", []) or []
            for perm in perms:
                ensure = self.permission_manager.ensure(perm)
                checked.append({"capability": cap, "permission": perm, "result": ensure})
                if not ensure.get("success"):
                    missing.append(
                        {
                            "capability": cap,
                            "permission": perm,
                            "code": ensure.get("code", "PERMISSION_REQUIRED"),
                            "message": ensure.get("message", f"Thiếu quyền: {perm}"),
                        }
                    )

        success = not missing and not unknown
        payload = {
            "success": success,
            "missing_permissions": missing,
            "unknown_capabilities": unknown,
            "checked": checked,
        }
        self._audit(action_id, ",".join(caps), "allowed" if success else "blocked", payload)
        return payload

    def execute_action(
        self,
        action_id: str,
        capabilities: Iterable[str] | None = None,
        runner: Callable[[], dict] | None = None,
    ) -> dict:
        preflight = self.preflight_capabilities(capabilities or [], action_id=action_id)
        if not preflight.get("success"):
            return {
                "success": False,
                "code": "ACTION_BLOCKED",
                "message": "Action bị chặn do thiếu quyền hoặc capability không hợp lệ.",
                "preflight": preflight,
            }

        if runner is None:
            result = {"success": True, "message": "Preflight thành công. Chưa có runner thực thi."}
            self._audit(action_id, ",".join(capabilities or []), "noop", result)
            return result

        try:
            run_result = runner() or {}
            if not isinstance(run_result, dict):
                run_result = {"success": bool(run_result)}
            status = "success" if run_result.get("success", True) else "failed"
            self._audit(action_id, ",".join(capabilities or []), status, run_result)
            return run_result
        except Exception as e:
            logger.exception("Action executor runner failed")
            err = {"success": False, "code": "ACTION_EXCEPTION", "message": str(e)}
            self._audit(action_id, ",".join(capabilities or []), "failed", err)
            return err

    @staticmethod
    def _audit(action_id: str, capability: str, status: str, detail: dict):
        try:
            db.execute_query(
                """
                INSERT INTO action_audit_logs (action_id, capability, status, detail)
                VALUES (?, ?, ?, ?)
                """,
                (action_id, capability, status, json.dumps(detail, ensure_ascii=False)),
                commit=True,
            )
        except Exception as e:
            logger.warning(f"Cannot write action audit log: {e}")
