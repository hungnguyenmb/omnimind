from __future__ import annotations

import json
import logging
import os
import platform
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from engine.ai_gateway_client import AiGatewayClient
from engine.artifact_manager import ArtifactManager
from engine.assistant_memory_manager import AssistantMemoryManager
from engine.codex_runtime_bridge import CodexRuntimeBridge
from engine.config_manager import ConfigManager
from engine.conversation_orchestrator import ConversationOrchestrator
from engine.function_executor import FunctionExecutor
from engine.function_registry import FunctionRegistry

logger = logging.getLogger(__name__)


class CentralAiCoordinator:
    """
    Sprint 2 skeleton:
    - Chuẩn hóa request/response contract cho AI trung tâm.
    - Quyết định giữa direct reply và fallback/escalate sang Codex.
    - Ghi trace để sau này Telegram/Zalo có thể dùng chung.
    """

    LOCAL_INTENT_PATTERNS = [
        re.compile(r"\b(mở|đọc|xem|sửa|chỉnh|ghi|xóa|xoá|tạo file|chạy|run|exec|terminal|shell|skill)\b", re.IGNORECASE),
        re.compile(
            r"\b(file|thư mục|folder|workspace|repo|git|python|npm|node|script|log|hệ thống|thông tin hệ thống|system info|system information|máy này|máy tính này)\b",
            re.IGNORECASE,
        ),
        re.compile(r"(?:^|\s)(?:~/|/[\w.\-~/]+|[A-Za-z]:\\[^\s]+)"),
    ]
    SIMPLE_QA_PATTERNS = [
        re.compile(r"^\s*(là gì|thế nào|giải thích|mô tả|tóm tắt|viết|soạn|gợi ý)\b", re.IGNORECASE),
        re.compile(r"\?$"),
    ]
    CODING_PATTERNS = [
        re.compile(r"\b(code|viết code|sửa code|debug|bug|fix bug|chạy test|unit test|integration test|build|compile|refactor|source code|api mới)\b", re.IGNORECASE),
        re.compile(
            r"(?:(?:\b(kiểm tra|kiem tra|điều tra|dieu tra|phân tích|phan tich|xem log)\b.{0,40}\b(lỗi|loi|bug|issue|vấn đề|van de)\b)|(?:\b(lỗi|loi|bug|issue|vấn đề|van de)\b.{0,40}\b(kiểm tra|kiem tra|điều tra|dieu tra|phân tích|phan tich|xem log)\b))",
            re.IGNORECASE,
        ),
    ]
    EXPLORATORY_LOCAL_PATTERNS = [
        re.compile(
            r"\b(workspace nào|workspace này|repo này|repo hiện tại|repo hien tai|trong repo|trong project|cấu trúc thư mục|co gi|có gì|liệt kê file|liet ke file|list file|tìm file|tìm các file|tìm tất cả file|tim file|tim cac file|tim tat ca file|search file|search files|grep|rg|find|chỗ dùng|cho dung|all usages|find usages|tham chiếu|tham chieu|references?)\b",
            re.IGNORECASE,
        ),
    ]
    DOCUMENT_PATTERNS = [
        re.compile(r"\b(pdf|docx|excel|csv|json|log|tài liệu|document|file đính kèm|ảnh|image|screenshot|ocr)\b", re.IGNORECASE),
    ]
    BROWSER_PATTERNS = [
        re.compile(r"\b(web|website|url|trang web|browser|portal|dashboard|đăng nhập|login|site)\b", re.IGNORECASE),
    ]
    PERSONAL_OPS_PATTERNS = [
        re.compile(r"\b(email|mail|hộp thư|calendar|lịch|meeting|cuộc họp|task|todo|công việc)\b", re.IGNORECASE),
    ]
    HIGH_RISK_PATTERNS = [
        re.compile(r"\b(xóa|xoá|delete|remove|restart|reboot|shutdown|ghi đè|overwrite|deploy production|production)\b", re.IGNORECASE),
    ]
    SIMPLE_DISCOVERY_PATTERNS = [
        re.compile(r"\b(workspace nào|đang làm việc ở đâu|dang lam viec o dau|cwd|thư mục hiện tại|thu muc hien tai|current workspace)\b", re.IGNORECASE),
        re.compile(r"\b(repo hiện tại|repo hien tai|branch hiện tại|git status|repo nào)\b", re.IGNORECASE),
        re.compile(r"\b(liệt kê file|liet ke file|list file|có file nào|co file nao)\b", re.IGNORECASE),
        re.compile(r"\b(tìm file|tìm các file|tim file|tim cac file|search file|search files)\b", re.IGNORECASE),
    ]
    MULTI_STEP_OR_OPEN_ENDED_PATTERNS = [
        re.compile(r"\b(rồi|roi|sau đó|sau do|tiếp theo|tiep theo|tổng hợp|tong hop|phân tích|phan tich|so sánh|so sanh|đọc tất cả|doc tat ca|mọi file|toàn bộ|toan bo)\b", re.IGNORECASE),
    ]
    CODEX_REPO_MUTATION_PATTERNS = [
        re.compile(r"\b(sửa|chỉnh|thay đổi|cập nhật|cap nhat|fix|debug|kiểm tra|kiem tra|điều tra|dieu tra|bật|bat|tắt|tat)\b", re.IGNORECASE),
        re.compile(r"\b(repo|workspace|project|config|source|module|code|bot)\b", re.IGNORECASE),
    ]
    TOOL_FALLBACK_ERROR_CODES = {
        "FUNCTION_NOT_FOUND",
        "HANDLER_NOT_FOUND",
        "UNSUPPORTED_EXECUTION_TARGET",
        "SHELL_BLOCKED",
    }

    def __init__(
        self,
        memory_manager: AssistantMemoryManager | None = None,
        orchestrator: ConversationOrchestrator | None = None,
        ai_client: AiGatewayClient | None = None,
        codex_bridge: CodexRuntimeBridge | None = None,
        function_registry: FunctionRegistry | None = None,
        function_executor: FunctionExecutor | None = None,
    ):
        self.memory_manager = memory_manager or AssistantMemoryManager()
        self.orchestrator = orchestrator or ConversationOrchestrator(self.memory_manager)
        self.ai_client = ai_client or AiGatewayClient()
        self.codex_bridge = codex_bridge or CodexRuntimeBridge()
        self.function_registry = function_registry or FunctionRegistry()
        self.function_executor = function_executor or FunctionExecutor(registry=self.function_registry)
        self.artifact_manager = ArtifactManager()

    @staticmethod
    def _utc_now_iso() -> str:
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    @staticmethod
    def _runtime_root_dir() -> Path:
        env_db = os.environ.get("OMNIMIND_DB_PATH", "").strip()
        if env_db:
            db_path = Path(env_db).expanduser()
            data_dir = db_path.parent
            root = data_dir.parent if data_dir.name == "data" else data_dir
            root.mkdir(parents=True, exist_ok=True)
            return root
        sys_name = platform.system()
        if sys_name == "Windows":
            base = os.environ.get("LOCALAPPDATA", os.path.expanduser("~\\AppData\\Local"))
            root = Path(base) / "OmniMind"
        elif sys_name == "Darwin":
            root = Path(os.path.expanduser("~/Library/Application Support")) / "OmniMind"
        else:
            root = Path(os.path.expanduser("~/.omnimind"))
        root.mkdir(parents=True, exist_ok=True)
        return root

    @classmethod
    def _trace_log_path(cls) -> Path:
        logs_dir = cls._runtime_root_dir() / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        return logs_dir / "central_ai_runtime.jsonl"

    @classmethod
    def _append_trace_log(cls, payload: dict):
        try:
            with cls._trace_log_path().open("a", encoding="utf-8") as f:
                f.write(json.dumps(payload, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.warning(f"Cannot append central AI trace log: {e}")

    @staticmethod
    def _shorten(text: str, limit: int = 240) -> str:
        body = " ".join(str(text or "").split())
        if len(body) <= limit:
            return body
        return body[: max(1, limit - 1)].rstrip() + "…"

    def build_request(
        self,
        *,
        channel: str,
        user_text: str,
        thread_id: str = "",
        external_id: str = "",
        attachments: list[dict] | None = None,
        metadata: dict | None = None,
    ) -> dict[str, Any]:
        return {
            "channel": str(channel or "ui").strip() or "ui",
            "user_text": str(user_text or "").strip(),
            "thread_id": str(thread_id or "").strip(),
            "external_id": str(external_id or "").strip(),
            "attachments": list(attachments or []),
            "metadata": dict(metadata or {}),
            "requested_at": self._utc_now_iso(),
        }

    def _looks_like_local_execution_request(self, text: str) -> bool:
        body = str(text or "").strip()
        if not body:
            return False
        return any(pattern.search(body) for pattern in self.LOCAL_INTENT_PATTERNS)

    def _looks_like_simple_question(self, text: str) -> bool:
        body = str(text or "").strip()
        if not body:
            return False
        if len(body) <= 300 and any(pattern.search(body) for pattern in self.SIMPLE_QA_PATTERNS):
            return True
        return not self._looks_like_local_execution_request(body)

    @staticmethod
    def _extract_named_file_candidate(text: str) -> str:
        body = str(text or "").strip()
        if not body:
            return ""
        for candidate in re.findall(r"\b[\w.\-]+\.[A-Za-z0-9]{1,12}\b", body):
            low = candidate.lower()
            if low.startswith(("http.", "https.", "www.")):
                continue
            return candidate
        return ""

    @staticmethod
    def _matches_any(patterns: list[re.Pattern], text: str) -> bool:
        body = str(text or "").strip()
        if not body:
            return False
        return any(pattern.search(body) for pattern in patterns)

    def _classify_task_shape(self, request: dict[str, Any]) -> str:
        user_text = str(request.get("user_text") or "").strip()
        attachments = request.get("attachments") if isinstance(request.get("attachments"), list) else []
        valid_attachments = [item for item in attachments if isinstance(item, dict) and item.get("is_valid")]

        if any(str(item.get("type") or "").strip() == "image" for item in valid_attachments):
            return "document_analysis"
        if any(item.get("text_read_supported") for item in valid_attachments):
            return "document_analysis"
        if self._matches_any(self.HIGH_RISK_PATTERNS, user_text):
            return "high_risk_action"
        if self._matches_any(self.CODING_PATTERNS, user_text):
            return "coding_ops"
        if self._matches_any(self.EXPLORATORY_LOCAL_PATTERNS, user_text):
            return "exploratory_local"
        if self._matches_any(self.BROWSER_PATTERNS, user_text):
            return "browser_ops"
        if self._matches_any(self.PERSONAL_OPS_PATTERNS, user_text):
            return "personal_ops"
        if self._matches_any(self.DOCUMENT_PATTERNS, user_text):
            return "document_analysis"
        if self._looks_like_local_execution_request(user_text):
            return "local_ops"
        if self._looks_like_simple_question(user_text):
            return "knowledge"
        return "conversation"

    def _infer_missing_context(self, request: dict[str, Any], task_shape: str) -> list[str]:
        user_text = str(request.get("user_text") or "").strip()
        missing: list[str] = []
        if re.search(r"\b(file đó|file do|tệp đó|tap tin do)\b", user_text, re.IGNORECASE):
            missing.append("file_reference")
        if re.search(r"\b(repo đó|repo do|workspace đó|workspace do|thư mục đó|thu muc do)\b", user_text, re.IGNORECASE):
            missing.append("workspace_reference")
        if task_shape == "browser_ops" and not re.search(r"https?://|\bweb\b|\bsite\b|\bportal\b|\bdashboard\b", user_text, re.IGNORECASE):
            missing.append("url")
        if task_shape == "personal_ops" and re.search(r"\b(email|mail)\b", user_text, re.IGNORECASE):
            if not re.search(r"\b(gmail|outlook|inbox|hộp thư|hop thu)\b", user_text, re.IGNORECASE):
                missing.append("account")
        if task_shape in {"local_ops", "document_analysis"} and re.search(r"\b(đọc file|doc file|mở file|mo file)\b", user_text, re.IGNORECASE):
            if not re.search(r"(?:^|\s)(?:~/|/[\w.\-~/]+|[A-Za-z]:\\[^\s]+)", user_text):
                missing.append("path")
        return missing

    def _infer_preferred_tool(self, request: dict[str, Any], task_shape: str) -> str:
        user_text = str(request.get("user_text") or "").strip()
        attachments = request.get("attachments") if isinstance(request.get("attachments"), list) else []
        valid_attachments = [item for item in attachments if isinstance(item, dict) and item.get("is_valid")]
        if any(str(item.get("type") or "").strip() == "image" for item in valid_attachments):
            return "vision_completion"
        if re.search(r"\b(tạo file|tao file|ghi file|ghi vào file|write file)\b", user_text, re.IGNORECASE):
            return "write_local_file"
        if re.search(r"\b(workspace nào|workspace này|cwd|thư mục hiện tại|thu muc hien tai|current workspace|dang lam viec o dau|đang làm việc ở đâu)\b", user_text, re.IGNORECASE):
            return "get_current_workspace"
        if re.search(r"\b(repo hiện tại|repo hien tai|branch hiện tại|branch hien tai|git status|repo nào)\b", user_text, re.IGNORECASE):
            return "get_git_repo_info"
        if re.search(r"\b(liệt kê file|liet ke file|list file|có file nào|co file nao)\b", user_text, re.IGNORECASE):
            return "list_local_files"
        if re.search(r"\b(tìm file|tìm các file|tim file|tim cac file|search file|search files)\b", user_text, re.IGNORECASE):
            return "search_files_by_name"
        if "system info" in user_text.lower() or "hệ thống" in user_text.lower():
            return "get_system_info"
        if re.search(r"\b(đọc file|doc file|mở file|mo file)\b", user_text, re.IGNORECASE):
            if not re.search(r"(?:^|\s)(?:~/|/[\w.\-~/]+|[A-Za-z]:\\[^\s]+)", user_text):
                file_candidate = self._extract_named_file_candidate(user_text)
                if file_candidate:
                    return "search_files_by_name"
            return "read_local_file"
        if re.search(r"\b(list file|liệt kê file|liet ke file|tìm file|tim file|rg|find)\b", user_text, re.IGNORECASE):
            return "run_shell_command"
        if task_shape == "document_analysis":
            return "read_local_file"
        return ""

    def _should_ask_clarification(
        self,
        request: dict[str, Any],
        task_shape: str,
        missing_context: list[str],
        preferred_tool: str,
    ) -> bool:
        if not missing_context:
            return False
        missing = set(str(item or "").strip() for item in missing_context if str(item or "").strip())
        if not missing:
            return False
        if "file_reference" in missing or "workspace_reference" in missing:
            return True
        if task_shape == "high_risk_action":
            return True
        if task_shape in {"browser_ops", "personal_ops"}:
            return False
        if "path" in missing:
            file_candidate = self._extract_named_file_candidate(str(request.get("user_text") or ""))
            if preferred_tool == "search_files_by_name" and file_candidate:
                return False
            return task_shape in {"local_ops", "document_analysis", "coding_ops", "exploratory_local"}
        return False

    def _build_clarification_reply(self, request: dict[str, Any], task_shape: str, missing_context: list[str]) -> str:
        missing = set(str(item or "").strip() for item in missing_context if str(item or "").strip())
        file_candidate = self._extract_named_file_candidate(str(request.get("user_text") or ""))
        if "file_reference" in missing and "workspace_reference" in missing:
            return "Bạn đang nói tới file nào trong workspace/repo nào? Hãy gửi tên repo hoặc path file cụ thể."
        if "workspace_reference" in missing:
            return "Bạn muốn tôi làm trong workspace/repo nào? Hãy gửi tên repo hoặc path thư mục cụ thể."
        if "file_reference" in missing:
            return "Bạn muốn tôi dùng file nào? Hãy gửi path hoặc tên file cụ thể."
        if "path" in missing and task_shape == "high_risk_action":
            return "Tôi cần path hoặc đối tượng cụ thể trước khi làm thao tác này."
        if "path" in missing and file_candidate:
            return f"Bạn muốn tôi dùng file `{file_candidate}` ở thư mục nào? Hãy gửi path đầy đủ hoặc repo chứa file."
        if "path" in missing:
            return "Bạn muốn tôi mở file nào? Hãy gửi path hoặc tên file cụ thể."
        if "url" in missing:
            return "Bạn muốn tôi mở trang nào? Hãy gửi URL hoặc tên site cụ thể."
        if "account" in missing:
            return "Bạn muốn dùng tài khoản hoặc hộp thư nào?"
        return "Bạn có thể nói rõ hơn một chút để tôi lấy đúng context trước khi làm tiếp không?"

    def _is_simple_discovery_request(self, request: dict[str, Any]) -> bool:
        user_text = str(request.get("user_text") or "").strip()
        if not self._matches_any(self.SIMPLE_DISCOVERY_PATTERNS, user_text):
            return False
        if self._matches_any(self.MULTI_STEP_OR_OPEN_ENDED_PATTERNS, user_text):
            return False
        return True

    def _infer_needs_approval(self, request: dict[str, Any], task_shape: str, preferred_tool: str) -> bool:
        user_text = str(request.get("user_text") or "").strip()
        if task_shape == "high_risk_action":
            return True
        if preferred_tool in {"write_local_file", "run_shell_command"}:
            return True
        if re.search(r"\b(xóa|xoá|delete|remove|restart|reboot|shutdown|ghi đè|overwrite|chạy lệnh|run command|run shell)\b", user_text, re.IGNORECASE):
            return True
        return False

    def _infer_codex_handoff(
        self,
        request: dict[str, Any],
        task_shape: str,
        preferred_tool: str,
    ) -> tuple[str, str, str]:
        user_text = str(request.get("user_text") or "").strip()
        low = user_text.lower()
        if task_shape == "coding_ops":
            return (
                "coding_workflow",
                "coding_ops_primary_route",
                "Yêu cầu là workflow code/debug/test/build; Codex phù hợp hơn built-in tools.",
            )
        if task_shape == "exploratory_local":
            if preferred_tool in {
                "get_current_workspace",
                "get_git_repo_info",
                "list_local_files",
                "search_files_by_name",
            } and self._is_simple_discovery_request(request):
                return ("", "", "")
            if self._matches_any(self.MULTI_STEP_OR_OPEN_ENDED_PATTERNS, user_text):
                return (
                    "multi_step_local",
                    "exploratory_local_multi_step",
                    "Yêu cầu cần khám phá local nhiều bước rồi mới đọc/tóm tắt/chốt kết quả.",
                )
            return (
                "exploratory_local",
                "exploratory_local_primary_route",
                "Yêu cầu cần khám phá workspace/repo mở; Codex nên xử lý thay vì tool đơn lẻ.",
            )
        if task_shape == "local_ops":
            if self._matches_any(self.MULTI_STEP_OR_OPEN_ENDED_PATTERNS, user_text) and any(
                token in low for token in ("file", "repo", "workspace", "project", "config", "thư mục", "thu muc")
            ):
                return (
                    "multi_step_local",
                    "local_ops_multi_step",
                    "Yêu cầu local có nhiều bước nối tiếp, nên giao Codex để tự điều phối workflow.",
                )
            if all(pattern.search(user_text) for pattern in self.CODEX_REPO_MUTATION_PATTERNS):
                return (
                    "coding_workflow",
                    "repo_or_config_mutation",
                    "Yêu cầu sửa/điều tra trong repo hoặc file config, Codex là executor phù hợp hơn tool đơn lẻ.",
                )
        return ("", "", "")

    def _decide_routing_fields(self, request: dict[str, Any]) -> dict[str, Any]:
        task_shape = self._classify_task_shape(request)
        missing_context = self._infer_missing_context(request, task_shape)
        preferred_tool = self._infer_preferred_tool(request, task_shape)
        needs_approval = self._infer_needs_approval(request, task_shape, preferred_tool)
        codex_task_type, codex_reason, codex_why = self._infer_codex_handoff(request, task_shape, preferred_tool)
        if self._should_ask_clarification(request, task_shape, missing_context, preferred_tool):
            return {
                "mode": "ask_clarification",
                "task_shape": task_shape,
                "confidence": 0.84,
                "reason": "missing_context_requires_clarification",
                "missing_context": missing_context,
                "why_not_tool": "Thiếu context trọng yếu nên không nên tự đoán hoặc gọi tool mù.",
                "needs_approval": needs_approval,
                "preferred_tool": preferred_tool,
                "codex_reason": "",
                "codex_task_type": "",
            }
        if task_shape == "coding_ops":
            return {
                "mode": "escalate_to_codex",
                "task_shape": task_shape,
                "confidence": 0.96,
                "reason": "coding_ops_detected",
                "missing_context": missing_context,
                "why_not_tool": "Yêu cầu mang tính code/debug/test nhiều bước; built-in tools hiện tại không đủ mạnh.",
                "needs_approval": needs_approval,
                "preferred_tool": preferred_tool,
                "codex_reason": codex_reason,
                "codex_task_type": codex_task_type,
            }
        if task_shape == "exploratory_local":
            if preferred_tool in {
                "get_current_workspace",
                "get_git_repo_info",
                "list_local_files",
                "search_files_by_name",
            } and self._is_simple_discovery_request(request):
                return {
                    "mode": "tool_calling",
                    "task_shape": task_shape,
                    "confidence": 0.9,
                    "reason": "simple_context_discovery_detected",
                    "missing_context": missing_context,
                    "why_not_tool": "",
                    "needs_approval": False,
                    "preferred_tool": preferred_tool,
                    "codex_reason": "",
                    "codex_task_type": "",
                }
            return {
                "mode": "escalate_to_codex",
                "task_shape": task_shape,
                "confidence": 0.93,
                "reason": "exploratory_local_detected",
                "missing_context": missing_context,
                "why_not_tool": codex_why or "Yêu cầu cần khám phá workspace/repo hoặc tìm file trước khi xử lý.",
                "needs_approval": needs_approval,
                "preferred_tool": preferred_tool,
                "codex_reason": codex_reason,
                "codex_task_type": codex_task_type,
            }
        if codex_reason:
            return {
                "mode": "escalate_to_codex",
                "task_shape": task_shape,
                "confidence": 0.91,
                "reason": codex_reason,
                "missing_context": missing_context,
                "why_not_tool": codex_why,
                "needs_approval": needs_approval,
                "preferred_tool": preferred_tool,
                "codex_reason": codex_reason,
                "codex_task_type": codex_task_type,
            }
        if task_shape in {"local_ops", "document_analysis", "high_risk_action"}:
            return {
                "mode": "tool_calling",
                "task_shape": task_shape,
                "confidence": 0.88 if task_shape != "high_risk_action" else 0.9,
                "reason": f"{task_shape}_detected",
                "missing_context": missing_context,
                "why_not_tool": "",
                "needs_approval": needs_approval,
                "preferred_tool": preferred_tool,
                "codex_reason": "",
                "codex_task_type": "",
            }
        if task_shape in {"browser_ops", "personal_ops"}:
            return {
                "mode": "reply_direct",
                "task_shape": task_shape,
                "confidence": 0.62,
                "reason": f"{task_shape}_detected_without_integration",
                "missing_context": missing_context,
                "why_not_tool": "Chưa có integration/tool chuyên biệt đủ ổn định cho nhóm hành vi này.",
                "needs_approval": needs_approval,
                "preferred_tool": preferred_tool,
                "codex_reason": "",
                "codex_task_type": "",
            }
        if task_shape == "knowledge":
            return {
                "mode": "reply_direct",
                "task_shape": task_shape,
                "confidence": 0.82,
                "reason": "knowledge_request_detected",
                "missing_context": missing_context,
                "why_not_tool": "",
                "needs_approval": needs_approval,
                "preferred_tool": preferred_tool,
                "codex_reason": "",
                "codex_task_type": "",
            }
        return {
            "mode": "reply_direct",
            "task_shape": task_shape,
            "confidence": 0.7,
            "reason": "conversation_request_detected",
            "missing_context": missing_context,
            "why_not_tool": "",
            "needs_approval": needs_approval,
            "preferred_tool": preferred_tool,
            "codex_reason": "",
            "codex_task_type": "",
        }

    def _decide_mode(self, request: dict[str, Any]) -> dict[str, Any]:
        user_text = str(request.get("user_text") or "").strip()
        central_cfg = ConfigManager.get_central_ai_config()
        decision = {
            "mode": "reply_direct",
            "reason": "simple_question",
            "task_shape": "conversation",
            "confidence": 0.75,
            "tool_choice_confidence": 0.75,
            "missing_context": [],
            "why_not_tool": "",
            "needs_approval": False,
            "preferred_tool": "",
            "codex_reason": "",
            "codex_task_type": "",
        }

        if not central_cfg.get("enabled", True):
            decision.update({"mode": "escalate_to_codex", "reason": "central_ai_disabled", "tool_choice_confidence": 1.0})
            return decision

        routing = self._decide_routing_fields(request)
        if routing.get("mode") == "ask_clarification":
            decision.update(routing)
            decision["tool_choice_confidence"] = float(routing.get("confidence") or 0.75)
            return decision

        mode = str(central_cfg.get("mode") or "hybrid").strip().lower()
        if mode == "codex_only":
            decision.update({"mode": "escalate_to_codex", "reason": "central_ai_mode_codex_only", "tool_choice_confidence": 1.0})
            return decision

        if mode == "direct_only":
            decision.update(
                {
                    **routing,
                    "mode": "reply_direct",
                    "reason": "central_ai_mode_direct_only",
                    "confidence": 1.0,
                    "tool_choice_confidence": 1.0,
                }
            )
            return decision
        decision.update(routing)
        decision["tool_choice_confidence"] = float(routing.get("confidence") or 0.75)

        attachments = request.get("attachments") if isinstance(request.get("attachments"), list) else []
        valid_attachments = [item for item in attachments if isinstance(item, dict) and item.get("is_valid")]
        if valid_attachments:
            if any(str(item.get("type") or "").strip() == "image" and item.get("vision_supported") for item in valid_attachments):
                decision.update(
                    {
                        "mode": "vision_direct",
                        "task_shape": "document_analysis",
                        "reason": "image_attachment_detected",
                        "confidence": 0.9,
                        "tool_choice_confidence": 0.9,
                        "preferred_tool": "vision_completion",
                    }
                )
                return decision
            if any(item.get("text_read_supported") for item in valid_attachments):
                decision.update(
                    {
                        "mode": "tool_calling",
                        "task_shape": "document_analysis",
                        "reason": "document_attachment_detected",
                        "confidence": 0.88,
                        "tool_choice_confidence": 0.88,
                        "preferred_tool": "read_local_file",
                    }
                )
                return decision
        return decision

    def decide_route(self, request: dict[str, Any]) -> dict[str, Any]:
        return self._decide_mode(dict(request or {}))

    def _build_direct_messages(self, request: dict[str, Any], context: dict[str, Any]) -> list[dict[str, Any]]:
        profile = context.get("profile") or {}
        display_name = str(profile.get("display_name") or "").strip()
        persona_prompt = str(profile.get("persona_prompt") or "").strip()
        facts = context.get("facts") or []
        summaries = context.get("summaries") or []
        recent_messages = context.get("recent_messages") or []
        user_text = str(request.get("user_text") or "").strip()
        channel = str(request.get("channel") or "ui").strip()
        attachment_lines = self._build_attachment_hint_lines(request)

        system_parts = [
            "Bạn là lớp AI trung tâm của OmniMind.",
            "Nhiệm vụ của bạn trong Sprint 2 là trả lời nhanh các câu hỏi không cần thao tác local.",
            "Nếu câu hỏi mang tính giải thích, tư vấn, viết nội dung hoặc tóm tắt, hãy trả lời trực tiếp bằng tiếng Việt rõ ràng, ngắn gọn.",
            "Không tự nhận là đã đọc/sửa/chạy file hay thực thi lệnh trên máy khi bạn chưa thật sự làm việc đó.",
        ]
        if display_name:
            system_parts.append(f"Tên trợ lý ưu tiên: {display_name}")
        if persona_prompt:
            system_parts.append(f"Persona hiện tại:\n{persona_prompt}")
        if facts:
            fact_lines = [f"- {self._shorten(str((item or {}).get('fact') or ''), 160)}" for item in facts[:8]]
            fact_lines = [line for line in fact_lines if line != "- "]
            if fact_lines:
                system_parts.append("Facts/preferences cần lưu ý:\n" + "\n".join(fact_lines))
        if summaries:
            summary_lines = [
                f"- {self._shorten(str((item or {}).get('summary_text') or ''), 300)}"
                for item in summaries[-2:]
                if str((item or {}).get("summary_text") or "").strip()
            ]
            if summary_lines:
                system_parts.append("Tóm tắt hội thoại gần đây:\n" + "\n".join(summary_lines))

        messages: list[dict[str, Any]] = [
            {
                "role": "system",
                "content": "\n\n".join(system_parts).strip(),
            }
        ]

        for msg in recent_messages[-6:]:
            role = str((msg or {}).get("role") or "user").strip().lower()
            if role not in {"system", "user", "assistant"}:
                continue
            content = str((msg or {}).get("content") or "").strip()
            if content:
                messages.append({"role": role, "content": self._shorten(content, 700)})

        user_prompt = (
            f"Kênh hiện tại: {channel}\n"
            "Yêu cầu mới của người dùng:\n"
            f"{user_text}\n\n"
            f"{('Artifact đi kèm:\\n' + '\\n'.join(attachment_lines) + '\\n\\n') if attachment_lines else ''}"
            "Hãy trả lời trực tiếp nếu đây là câu hỏi không cần thao tác local."
        )
        messages.append({"role": "user", "content": user_prompt})
        return messages

    def _build_attachment_hint_lines(self, request: dict[str, Any]) -> list[str]:
        attachments = request.get("attachments") if isinstance(request.get("attachments"), list) else []
        lines: list[str] = []
        for item in attachments[:6]:
            if not isinstance(item, dict):
                continue
            path = str(item.get("path") or "").strip()
            file_name = str(item.get("file_name") or Path(path).name).strip()
            art_type = str(item.get("type") or "").strip()
            if item.get("is_valid"):
                lines.append(f"- {file_name} [{art_type}] path={path}")
            else:
                code = str(item.get("code") or "INVALID_ATTACHMENT").strip()
                message = str(item.get("message") or "").strip()
                lines.append(f"- {file_name or path or 'attachment'} [invalid:{code}] {message}")
        return lines

    def _normalize_request_attachments(self, request: dict[str, Any]) -> list[dict[str, Any]]:
        attachments = request.get("attachments") if isinstance(request.get("attachments"), list) else []
        source_channel = str(request.get("channel") or "ui").strip()
        source_message_id = str(request.get("external_id") or request.get("thread_id") or "message").strip()
        normalized: list[dict[str, Any]] = []
        for item in attachments:
            if not isinstance(item, dict):
                continue
            if "is_valid" in item and "path" in item:
                normalized.append(dict(item))
                continue
            path = str(item.get("path") or "").strip()
            metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
            normalized.append(
                self.artifact_manager.normalize_local_artifact(
                    path,
                    source_channel=source_channel,
                    source_message_id=source_message_id,
                    metadata=metadata,
                )
            )
        return normalized

    def _build_invalid_attachment_reply(self, attachments: list[dict[str, Any]]) -> str:
        rows = []
        for item in attachments[:4]:
            if item.get("is_valid"):
                continue
            hint = str(item.get("user_hint") or "").strip()
            msg = str(item.get("message") or "Attachment không hợp lệ.").strip()
            if hint:
                rows.append(f"- {msg} {hint}".strip())
            else:
                rows.append(f"- {msg}")
        if not rows:
            return ""
        return "Mình chưa xử lý được file/ảnh bạn gửi:\n" + "\n".join(rows)

    def _run_attachment_vision(
        self,
        request: dict[str, Any],
        attachments: list[dict[str, Any]],
        trace: dict[str, Any],
    ) -> dict[str, Any]:
        image_artifact = next(
            (
                item
                for item in attachments
                if isinstance(item, dict)
                and item.get("is_valid")
                and str(item.get("type") or "").strip() == "image"
                and item.get("vision_supported")
            ),
            None,
        )
        if not image_artifact:
            return {
                "success": False,
                "reply_text": "",
                "artifacts": [],
                "used_tools": [],
                "message": "Không có ảnh hợp lệ để dùng vision.",
            }

        prompt_text = str(request.get("user_text") or "").strip() or "Hãy mô tả và phân tích ảnh này bằng tiếng Việt."
        vision_result = self.ai_client.vision_completion_from_local_file(
            prompt_text=prompt_text,
            local_path=str(image_artifact.get("path") or ""),
            model=ConfigManager.get_central_ai_direct_model(),
            max_tokens=600,
        )
        if not vision_result.get("success"):
            return {
                "success": False,
                "reply_text": "",
                "artifacts": [str(image_artifact.get("path") or "")] if image_artifact.get("path") else [],
                "used_tools": ["vision_completion"],
                "message": vision_result.get("message", "Vision failed."),
            }
        reply_text = str(vision_result.get("text") or "").strip()
        trace["used_direct_ai"] = True
        trace["used_vision"] = True
        trace["vision_artifact_type"] = str(image_artifact.get("type") or "").strip()
        return {
            "success": bool(reply_text),
            "reply_text": reply_text,
            "artifacts": [str(image_artifact.get("path") or "")] if image_artifact.get("path") else [],
            "used_tools": ["vision_completion"],
            "message": vision_result.get("message", "OK"),
        }

    def _build_tool_messages(self, request: dict[str, Any], context: dict[str, Any]) -> list[dict[str, Any]]:
        messages = self._build_direct_messages(request, context)
        channel = str(request.get("channel") or "").strip().lower()
        tool_lines = []
        for definition in self.function_registry.list_definitions(supported_channel=channel):
            tool_name = str(definition.get("name") or "").strip()
            approval = str(definition.get("approval_policy") or "auto").strip()
            description = str(definition.get("description") or "").strip()
            tool_lines.append(f"- {tool_name} ({approval}): {description}")
        preferred_tool = self._infer_preferred_tool(request, self._classify_task_shape(request))
        preferred_hint = ""
        if preferred_tool:
            preferred_hint = f"\nTool nên ưu tiên trước cho yêu cầu này: {preferred_tool}."
        if messages and messages[0].get("role") == "system":
            base = str(messages[0].get("content") or "").strip()
            messages[0]["content"] = (
                f"{base}\n\n"
                "Bạn có thể dùng built-in functions của OmniMind nếu yêu cầu cần dữ liệu local hoặc thao tác runtime.\n"
                "Nếu người dùng hỏi workspace hiện tại, repo hiện tại, muốn liệt kê file hoặc tìm file theo tên, hãy ưu tiên các discovery tools read-only: get_current_workspace, get_git_repo_info, list_local_files, search_files_by_name.\n"
                "Chỉ dùng get_system_info hoặc run_shell_command khi discovery tools không đủ hoặc yêu cầu đã nêu rõ command cụ thể.\n"
                "Nếu người dùng yêu cầu rõ là phải dùng skill hoặc tool để làm việc, hãy ưu tiên gọi function phù hợp trước thay vì tự trả lời từ kiến thức chung.\n"
                "Chỉ gọi function khi thật sự cần thiết. Nếu function trả về approval_required hoặc lỗi, hãy giải thích ngắn gọn, không bịa kết quả.\n"
                f"{preferred_hint}\n"
                "Danh sách built-in functions hiện có:\n"
                + "\n".join(tool_lines)
            ).strip()
        return messages

    @staticmethod
    def _parse_tool_call(tool_call: dict[str, Any]) -> tuple[str, str, dict[str, Any]]:
        tool_id = str((tool_call or {}).get("id") or "").strip()
        fn = (tool_call or {}).get("function") if isinstance((tool_call or {}).get("function"), dict) else {}
        function_name = str((fn or {}).get("name") or "").strip()
        raw_args = (fn or {}).get("arguments")
        if isinstance(raw_args, dict):
            args = raw_args
        else:
            try:
                args = json.loads(str(raw_args or "{}"))
            except Exception:
                args = {}
        if not isinstance(args, dict):
            args = {}
        return tool_id, function_name, args

    def _build_tool_fallback_reply(self, results: list[dict[str, Any]]) -> str:
        if not results:
            return "OmniMind chưa xử lý được yêu cầu này bằng built-in function."
        lines = []
        for item in results[:4]:
            name = str(item.get("function_name") or "unknown").strip()
            message = str(item.get("message") or "").strip()
            if not message:
                message = "Không có chi tiết."
            lines.append(f"- {name}: {message}")
        return "Kết quả từ built-in function:\n" + "\n".join(lines)

    @staticmethod
    def _tool_call_signature(function_name: str, args: dict[str, Any]) -> str:
        try:
            payload = json.dumps(args or {}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        except Exception:
            payload = "{}"
        return f"{function_name}::{payload}"

    @staticmethod
    def _request_wants_file_contents(request: dict[str, Any]) -> bool:
        user_text = str((request or {}).get("user_text") or "").strip()
        if not user_text:
            return False
        return bool(
            re.search(
                r"\b(đọc|doc|mở|mo|xem nội dung|xem noi dung|nội dung|noi dung|tóm tắt|tom tat|tóm lược|tóm tắt nội dung|summary|summarize|phân tích file|phan tich file)\b",
                user_text,
                re.IGNORECASE,
            )
        )

    def _maybe_expand_search_result(
        self,
        *,
        request: dict[str, Any],
        execution_result: dict[str, Any],
        used_tools: list[str],
        artifacts: list[str],
        execution_results: list[dict[str, Any]],
        step_trace: dict[str, Any],
        step_messages: list[dict[str, Any]],
    ):
        if not self._request_wants_file_contents(request):
            return
        if str(execution_result.get("function_name") or "").strip() != "search_files_by_name":
            return
        if not execution_result.get("success"):
            return

        data = execution_result.get("data") if isinstance(execution_result.get("data"), dict) else {}
        matches = data.get("matches") if isinstance(data.get("matches"), list) else []
        if len(matches) != 1:
            return

        file_path = str((matches[0] or {}).get("path") or "").strip()
        if not file_path:
            return

        followup_result = self.function_executor.execute_function(
            "read_local_file",
            {
                "path": file_path,
                "max_chars": min(20000, ConfigManager.get_central_ai_function_read_max_chars()),
            },
            auto_approve=False,
        )
        execution_results.append(followup_result)
        used_tools.append("read_local_file")
        for artifact_path in followup_result.get("artifacts") or []:
            candidate = str(artifact_path or "").strip()
            if candidate and candidate not in artifacts:
                artifacts.append(candidate)

        step_trace["tool_calls"].append(
            {
                "function_name": "read_local_file",
                "arguments_preview": self._shorten(json.dumps({"path": file_path}, ensure_ascii=False), 220),
                "repeated": False,
                "success": bool(followup_result.get("success")),
                "code": str(followup_result.get("code") or "").strip(),
                "approval_required": bool(followup_result.get("approval_required")),
                "auto_followup": True,
            }
        )
        step_messages.append(
            {
                "role": "tool",
                "tool_call_id": f"auto_followup:read_local_file:{file_path}",
                "name": "read_local_file",
                "content": self.function_executor.build_tool_message_content(followup_result),
            }
        )

    def _build_loop_summary_reply(self, execution_results: list[dict[str, Any]]) -> str:
        if not execution_results:
            return "OmniMind chưa thu được kết quả nào từ tool loop."
        lines = []
        for item in execution_results[-6:]:
            fn = str(item.get("function_name") or "unknown").strip()
            code = str(item.get("code") or "").strip()
            msg = str(item.get("message") or "").strip()
            tail = f"{code}: {msg}" if code else msg
            lines.append(f"- {fn}: {tail or 'Không có chi tiết.'}")
        return "Tool loop đã chạy nhưng chưa sinh được câu trả lời cuối. Kết quả gần nhất:\n" + "\n".join(lines)

    def _build_tool_result_digest(self, execution_results: list[dict[str, Any]]) -> str:
        if not execution_results:
            return "Không có tool result."

        sections: list[str] = []
        for item in execution_results[-6:]:
            function_name = str(item.get("function_name") or "unknown").strip()
            success = bool(item.get("success"))
            code = str(item.get("code") or "").strip()
            message = str(item.get("message") or "").strip()
            data = item.get("data") if isinstance(item.get("data"), dict) else {}

            header = f"Tool: {function_name}"
            meta_bits = []
            meta_bits.append("success=true" if success else "success=false")
            if code:
                meta_bits.append(f"code={code}")
            if message:
                meta_bits.append(f"message={message}")
            block_lines = [header, "Meta: " + " | ".join(meta_bits)]

            if function_name == "get_current_workspace":
                block_lines.append(f"workspace_path: {str(data.get('workspace_path') or '').strip()}")
                block_lines.append(f"cwd: {str(data.get('cwd') or '').strip()}")
                git_root = str(data.get("git_repo_root") or "").strip()
                if git_root:
                    block_lines.append(f"git_repo_root: {git_root}")
            elif function_name == "get_git_repo_info":
                block_lines.append(f"repo_root: {str(data.get('repo_root') or '').strip()}")
                block_lines.append(f"branch: {str(data.get('branch') or '').strip()}")
                status_preview = data.get("status_preview") if isinstance(data.get("status_preview"), list) else []
                if status_preview:
                    block_lines.append("status_preview:")
                    for line in status_preview[:10]:
                        text = str(line or "").rstrip()
                        if text:
                            block_lines.append(f"- {text}")
            elif function_name == "list_local_files":
                entries = data.get("entries") if isinstance(data.get("entries"), list) else []
                block_lines.append(f"root_path: {str(data.get('root_path') or '').strip()}")
                block_lines.append(f"match_count: {int(data.get('match_count') or len(entries))}")
                if entries:
                    block_lines.append("entries:")
                    for entry in entries[:25]:
                        if not isinstance(entry, dict):
                            continue
                        rel_path = str(entry.get("relative_path") or entry.get("path") or "").strip()
                        entry_type = str(entry.get("type") or "file").strip()
                        if rel_path:
                            block_lines.append(f"- [{entry_type}] {rel_path}")
            elif function_name == "search_files_by_name":
                matches = data.get("matches") if isinstance(data.get("matches"), list) else []
                block_lines.append(f"root_path: {str(data.get('root_path') or '').strip()}")
                block_lines.append(f"query: {str(data.get('query') or '').strip()}")
                block_lines.append(f"match_count: {int(data.get('match_count') or len(matches))}")
                if matches:
                    block_lines.append("matches:")
                    for match in matches[:20]:
                        if not isinstance(match, dict):
                            continue
                        rel_path = str(match.get("relative_path") or match.get("path") or "").strip()
                        if rel_path:
                            block_lines.append(f"- {rel_path}")
            elif function_name == "read_local_file":
                path = str(data.get("path") or "").strip()
                content = str(data.get("content") or "")
                char_count = int(data.get("char_count") or len(content))
                truncated = bool(data.get("truncated"))
                block_lines.append(f"path: {path}")
                block_lines.append(f"char_count: {char_count}")
                block_lines.append(f"truncated: {str(truncated).lower()}")
                if content.strip():
                    excerpt = self._shorten(content, 4000)
                    block_lines.append("content_excerpt:")
                    block_lines.append(excerpt)
            elif function_name == "run_shell_command":
                command = str(data.get("command") or "").strip()
                stdout = str(data.get("stdout") or "").strip()
                stderr = str(data.get("stderr") or "").strip()
                if command:
                    block_lines.append(f"command: {command}")
                if stdout:
                    block_lines.append("stdout_excerpt:")
                    block_lines.append(self._shorten(stdout, 2200))
                if stderr:
                    block_lines.append("stderr_excerpt:")
                    block_lines.append(self._shorten(stderr, 1200))
            else:
                compact_data = self._shorten(json.dumps(data, ensure_ascii=False), 1200) if data else ""
                if compact_data:
                    block_lines.append("data:")
                    block_lines.append(compact_data)

            sections.append("\n".join(line for line in block_lines if line))
        return "\n\n".join(sections)

    def _build_user_friendly_tool_reply(
        self,
        request: dict[str, Any],
        execution_results: list[dict[str, Any]],
    ) -> str:
        if not execution_results:
            return self._build_loop_summary_reply(execution_results)

        user_text = str(request.get("user_text") or "").strip()
        successful = [item for item in execution_results if item.get("success")]
        latest_success = successful[-1] if successful else {}
        function_name = str(latest_success.get("function_name") or "").strip()
        data = latest_success.get("data") if isinstance(latest_success.get("data"), dict) else {}

        if function_name == "read_local_file":
            path = str(data.get("path") or "").strip()
            content = str(data.get("content") or "").strip()
            if content:
                if re.search(r"\b(tóm tắt|tom tat|tóm lược|summary|summarize|phân tích|phan tich)\b", user_text, re.IGNORECASE):
                    excerpt = self._shorten(content, 2200)
                    return (
                        f"Tôi đã đọc file `{Path(path).name or path}`.\n\n"
                        f"Nội dung trọng tâm tôi lấy được từ file là:\n{excerpt}"
                    )
                excerpt = self._shorten(content, 2600)
                return (
                    f"Tôi đã đọc file `{Path(path).name or path}` tại `{path}`.\n\n"
                    f"Nội dung trích ra:\n{excerpt}"
                )

        if function_name == "list_local_files":
            entries = data.get("entries") if isinstance(data.get("entries"), list) else []
            root_path = str(data.get("root_path") or "").strip()
            if entries:
                lines = []
                for entry in entries[:20]:
                    if not isinstance(entry, dict):
                        continue
                    rel_path = str(entry.get("relative_path") or entry.get("path") or "").strip()
                    if rel_path:
                        lines.append(f"- {rel_path}")
                if lines:
                    total = int(data.get("match_count") or len(lines))
                    suffix = "\n- ..." if total > len(lines) else ""
                    return (
                        f"Tôi đã liệt kê file trong `{root_path}`. "
                        f"Hiện có {total} mục khớp yêu cầu.\n\n"
                        + "\n".join(lines)
                        + suffix
                    )

        if function_name == "search_files_by_name":
            matches = data.get("matches") if isinstance(data.get("matches"), list) else []
            if matches:
                lines = []
                for match in matches[:20]:
                    if not isinstance(match, dict):
                        continue
                    rel_path = str(match.get("relative_path") or match.get("path") or "").strip()
                    if rel_path:
                        lines.append(f"- {rel_path}")
                if lines:
                    total = int(data.get("match_count") or len(lines))
                    return (
                        f"Tôi đã tìm được {total} file khớp yêu cầu.\n\n"
                        + "\n".join(lines)
                    )

        if function_name == "get_current_workspace":
            workspace_path = str(data.get("workspace_path") or "").strip()
            cwd = str(data.get("cwd") or "").strip()
            git_root = str(data.get("git_repo_root") or "").strip()
            reply = f"Tôi đang làm việc trong workspace `{workspace_path or cwd}`."
            if git_root:
                reply += f"\nGit repo root hiện tại là `{git_root}`."
            if cwd and cwd != workspace_path:
                reply += f"\nThư mục chạy hiện tại là `{cwd}`."
            return reply

        if function_name == "get_git_repo_info":
            repo_root = str(data.get("repo_root") or "").strip()
            branch = str(data.get("branch") or "").strip()
            status_preview = data.get("status_preview") if isinstance(data.get("status_preview"), list) else []
            reply = f"Tôi đã xác định repo hiện tại là `{repo_root}`."
            if branch:
                reply += f"\nBranch hiện tại: `{branch}`."
            if status_preview:
                preview_lines = [f"- {str(line or '').rstrip()}" for line in status_preview[:10] if str(line or "").strip()]
                if preview_lines:
                    reply += "\nMột số thay đổi hiện có:\n" + "\n".join(preview_lines)
            return reply

        if function_name == "run_shell_command":
            stdout = str(data.get("stdout") or "").strip()
            stderr = str(data.get("stderr") or "").strip()
            command = str(data.get("command") or "").strip()
            if stdout:
                return f"Tôi đã chạy lệnh `{command}` và lấy được kết quả:\n\n{self._shorten(stdout, 2600)}"
            if stderr:
                return f"Tôi đã chạy lệnh `{command}`. Hiện đầu ra lỗi là:\n\n{self._shorten(stderr, 1800)}"

        return self._build_loop_summary_reply(execution_results)

    @staticmethod
    def _looks_like_status_only_reply(text: str) -> bool:
        body = str(text or "").strip()
        if not body:
            return True
        upper_hits = re.findall(r"\b[A-Z][A-Z0-9_]{3,}\b", body)
        informative_markers = [
            "```",
            "/",
            ".md",
            ".py",
            "nội dung",
            "noi dung",
            "workspace",
            "repo",
            "branch",
            "- ",
        ]
        if upper_hits and not any(marker in body.lower() for marker in informative_markers):
            return True
        return False

    def _collect_codex_handoff_hints(self, request: dict[str, Any], context: dict[str, Any]) -> dict[str, list[str]]:
        important_paths: list[str] = []
        important_files: list[str] = []
        seen_paths = set()
        seen_files = set()

        cfg_workspace = str(ConfigManager.get_workspace_path() or "").strip()
        if cfg_workspace and cfg_workspace not in seen_paths:
            seen_paths.add(cfg_workspace)
            important_paths.append(cfg_workspace)

        attachments = request.get("attachments") if isinstance(request.get("attachments"), list) else []
        for item in attachments[:6]:
            if not isinstance(item, dict):
                continue
            path = str(item.get("path") or "").strip()
            file_name = str(item.get("file_name") or Path(path).name).strip()
            if path and path not in seen_paths:
                seen_paths.add(path)
                important_paths.append(path)
            if file_name and file_name not in seen_files:
                seen_files.add(file_name)
                important_files.append(file_name)

        for msg in (context.get("recent_messages") or [])[-8:]:
            meta = (msg or {}).get("metadata") if isinstance((msg or {}).get("metadata"), dict) else {}
            for path in meta.get("important_paths") or []:
                value = str(path or "").strip()
                if value and value not in seen_paths:
                    seen_paths.add(value)
                    important_paths.append(value)
            for file_name in meta.get("important_file_refs") or []:
                value = str(file_name or "").strip()
                if value and value not in seen_files:
                    seen_files.add(value)
                    important_files.append(value)

        return {
            "important_paths": important_paths[:8],
            "important_files": important_files[:12],
        }

    def _run_builtin_tool_round(
        self,
        request: dict[str, Any],
        context: dict[str, Any],
        trace: dict[str, Any],
    ) -> dict[str, Any]:
        messages = self._build_tool_messages(request, context)
        channel = str(request.get("channel") or "").strip().lower()
        tools = self.function_registry.list_tool_schemas(include_on_request=True, supported_channel=channel)
        if not tools:
            return {
                "success": False,
                "reply_text": "",
                "artifacts": [],
                "used_tools": [],
                "message": "Chưa có built-in function nào được đăng ký.",
            }

        model = ConfigManager.get_central_ai_direct_model()
        max_steps = ConfigManager.get_central_ai_tool_loop_max_steps()
        timeout_sec = ConfigManager.get_central_ai_tool_loop_timeout_sec()
        max_calls_per_step = ConfigManager.get_central_ai_tool_loop_max_calls_per_step()
        started_at = time.monotonic()
        used_tools: list[str] = []
        artifacts: list[str] = []
        execution_results: list[dict[str, Any]] = []
        approval_requests: list[dict[str, Any]] = []
        step_traces: list[dict[str, Any]] = []
        seen_signatures: set[str] = set()
        attachment_lines = self._build_attachment_hint_lines(request)
        step_messages = list(messages)
        if attachment_lines:
            step_messages.append(
                {
                    "role": "system",
                    "content": (
                        "Artifact local hiện có và có thể dùng cho tool loop:\n"
                        + "\n".join(attachment_lines)
                        + "\nNếu cần đọc file thì dùng đúng path đã cung cấp."
                    ),
                }
            )
        loop_end_reason = "unknown"
        reply_text = ""
        last_message = "Tool loop ended without final reply."

        for step_index in range(1, max_steps + 1):
            elapsed = time.monotonic() - started_at
            if elapsed >= timeout_sec:
                loop_end_reason = "timeout"
                last_message = f"Tool loop quá thời gian cho phép ({timeout_sec}s)."
                break

            pass_result = self.ai_client.chat_with_tools(
                messages=step_messages,
                tools=tools,
                tool_choice="auto",
                model=model,
                temperature=0.2,
            )
            if not pass_result.get("success"):
                loop_end_reason = "gateway_error"
                last_message = pass_result.get("message", "Tool calling failed.")
                break

            tool_calls = list(pass_result.get("tool_calls") or [])
            assistant_content = str(pass_result.get("text") or "").strip()
            step_trace = {
                "step": step_index,
                "assistant_text_preview": self._shorten(assistant_content, 220),
                "tool_call_count": len(tool_calls),
                "tool_calls": [],
            }

            if not tool_calls:
                if execution_results:
                    reply_text = assistant_content
                    loop_end_reason = "assistant_final"
                    last_message = "OK" if reply_text else "No tool call returned."
                else:
                    reply_text = ""
                    loop_end_reason = "no_tool_selected"
                    last_message = "Model không chọn được tool phù hợp cho yêu cầu local."
                step_traces.append(step_trace)
                break

            assistant_message = {
                "role": "assistant",
                "content": assistant_content,
                "tool_calls": tool_calls,
            }
            step_messages.append(assistant_message)

            repeated_only = True
            for tool_call in tool_calls[:max_calls_per_step]:
                tool_call_id, function_name, args = self._parse_tool_call(tool_call)
                signature = self._tool_call_signature(function_name, args)
                is_repeated = signature in seen_signatures
                if not is_repeated:
                    repeated_only = False
                    seen_signatures.add(signature)

                execution_result = self.function_executor.execute_function(
                    function_name,
                    args,
                    auto_approve=False,
                )
                execution_results.append(execution_result)
                if execution_result.get("approval_required"):
                    missing_names = ", ".join(
                        [
                            str(name).strip()
                            for name in (execution_result.get("data") or {}).get("required_capabilities") or []
                            if str(name).strip()
                        ]
                    )
                    approval_requests.append(
                        {
                            "kind": "function",
                            "function_name": function_name,
                            "arguments": dict(args or {}),
                            "missing_names": missing_names,
                            "message": str(execution_result.get("message") or "").strip(),
                            "required_capabilities": list((execution_result.get("data") or {}).get("required_capabilities") or []),
                        }
                    )
                if function_name:
                    used_tools.append(function_name)
                for artifact_path in execution_result.get("artifacts") or []:
                    candidate = str(artifact_path or "").strip()
                    if candidate and candidate not in artifacts:
                        artifacts.append(candidate)

                step_trace["tool_calls"].append(
                    {
                        "function_name": function_name,
                        "arguments_preview": self._shorten(json.dumps(args, ensure_ascii=False), 220),
                        "repeated": is_repeated,
                        "success": bool(execution_result.get("success")),
                        "code": str(execution_result.get("code") or "").strip(),
                        "approval_required": bool(execution_result.get("approval_required")),
                    }
                )
                step_messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call_id or function_name,
                        "name": function_name or "unknown_function",
                        "content": self.function_executor.build_tool_message_content(execution_result),
                    }
                )
                self._maybe_expand_search_result(
                    request=request,
                    execution_result=execution_result,
                    used_tools=used_tools,
                    artifacts=artifacts,
                    execution_results=execution_results,
                    step_trace=step_trace,
                    step_messages=step_messages,
                )

            step_traces.append(step_trace)
            if repeated_only:
                loop_end_reason = "repeated_tool_calls"
                last_message = "Model lặp lại cùng tool call mà không tạo tiến triển."
                break
        else:
            loop_end_reason = "max_steps_reached"
            last_message = f"Tool loop đã chạm giới hạn {max_steps} bước."

        fallback_error_hits = [
            item
            for item in execution_results
            if str(item.get("code") or "").strip() in self.TOOL_FALLBACK_ERROR_CODES
        ]
        if loop_end_reason == "no_tool_selected" and not execution_results:
            return {
                "success": False,
                "reply_text": "",
                "artifacts": artifacts,
                "used_tools": used_tools,
                "approval_requests": approval_requests,
                "message": last_message,
            }
        if fallback_error_hits and not any(item.get("success") for item in execution_results) and not approval_requests:
            return {
                "success": False,
                "reply_text": "",
                "artifacts": artifacts,
                "used_tools": used_tools,
                "approval_requests": approval_requests,
                "message": "Built-in tools hiện tại chưa đủ để xử lý yêu cầu này; fallback sang Codex.",
            }

        if not reply_text:
            tool_result_digest = self._build_tool_result_digest(execution_results)
            summary_prompt = [
                {
                    "role": "system",
                    "content": (
                        "Bạn là AI trung tâm của OmniMind.\n"
                        "Hãy trả lời người dùng dựa trên dữ liệu đầu ra thực tế của tools.\n"
                        "Bắt buộc sử dụng nội dung trong tool results như path, file list, nội dung file, stdout.\n"
                        "Không được chỉ lặp lại status code hoặc message kỹ thuật nếu tool đã có data hữu ích.\n"
                        "Nếu người dùng yêu cầu tóm tắt file, hãy tóm tắt từ content_excerpt.\n"
                        "Nếu chưa đủ dữ liệu để hoàn tất, hãy nói rõ đang thiếu gì.\n"
                        "Không được bịa thêm tool result mới."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Yêu cầu gốc của người dùng:\n{str(request.get('user_text') or '').strip()}\n\n"
                        f"Tool results:\n{tool_result_digest}"
                    ),
                }
            ]
            summary_pass = self.ai_client.chat_completion(
                messages=summary_prompt,
                model=model,
                temperature=0.2,
            )
            summary_text = str(summary_pass.get("text") or "").strip()
            if summary_text and not self._looks_like_status_only_reply(summary_text):
                reply_text = summary_text
                if loop_end_reason == "unknown":
                    loop_end_reason = "summary_final"
                last_message = summary_pass.get("message", "OK")
            else:
                reply_text = self._build_user_friendly_tool_reply(request, execution_results)

        trace["tool_call_count"] = len(execution_results)
        trace["tool_loop_steps"] = len(step_traces)
        trace["tool_loop_timeout_sec"] = timeout_sec
        trace["tool_loop_max_steps"] = max_steps
        trace["tool_loop_end_reason"] = loop_end_reason
        trace["used_tools"] = used_tools
        trace["pending_approval_requests"] = len(approval_requests)
        trace["tool_loop_trace"] = step_traces
        trace["tool_execution_preview"] = [
            {
                "function_name": str(item.get("function_name") or "").strip(),
                "success": bool(item.get("success")),
                "code": str(item.get("code") or "").strip(),
                "approval_required": bool(item.get("approval_required")),
            }
            for item in execution_results[:6]
        ]
        return {
            "success": bool(reply_text),
            "reply_text": reply_text,
            "artifacts": artifacts,
            "used_tools": used_tools,
            "approval_requests": approval_requests,
            "message": last_message,
        }

    def _build_codex_prompt(self, request: dict[str, Any], context: dict[str, Any]) -> str:
        profile = context.get("profile") or {}
        latest_summary = context.get("latest_summary") or {}
        recent_turns = context.get("recent_turns") or []
        facts = context.get("facts") or []
        channel = str(request.get("channel") or "ui").strip()
        user_text = str(request.get("user_text") or "").strip()
        decision = self._decide_mode(request)
        handoff_hints = self._collect_codex_handoff_hints(request, context)

        parts = [
            "Bạn đang xử lý một yêu cầu trong OmniMind cần khả năng thao tác local hoặc workflow phức tạp.",
            f"Kênh nhận yêu cầu: {channel}",
        ]
        display_name = str(profile.get("display_name") or "").strip()
        persona_prompt = str(profile.get("persona_prompt") or "").strip()
        if display_name:
            parts.append(f"Tên trợ lý: {display_name}")
        if persona_prompt:
            parts.append(f"Persona:\n{persona_prompt}")

        summary_text = str(latest_summary.get("summary_text") or "").strip()
        if summary_text:
            parts.append(f"Tóm tắt hội thoại gần nhất:\n{summary_text}")

        if facts:
            fact_lines = [f"- {self._shorten(str((item or {}).get('fact') or ''), 200)}" for item in facts[:8]]
            fact_lines = [line for line in fact_lines if line != "- "]
            if fact_lines:
                parts.append("Facts/preferences:\n" + "\n".join(fact_lines))

        handoff_lines = [
            f"- task_shape: {decision.get('task_shape') or ''}",
            f"- codex_task_type: {decision.get('codex_task_type') or ''}",
            f"- codex_reason: {decision.get('codex_reason') or decision.get('reason') or ''}",
            f"- why_not_tool: {decision.get('why_not_tool') or ''}",
            f"- preferred_tool: {decision.get('preferred_tool') or ''}",
            f"- missing_context: {', '.join(decision.get('missing_context') or [])}",
        ]
        parts.append("Codex handoff:\n" + "\n".join(handoff_lines))

        if handoff_hints.get("important_paths"):
            parts.append("Path quan trọng đã biết:\n" + "\n".join([f"- {p}" for p in handoff_hints["important_paths"]]))
        if handoff_hints.get("important_files"):
            parts.append("File quan trọng đã biết:\n" + "\n".join([f"- {f}" for f in handoff_hints["important_files"]]))

        turn_lines: list[str] = []
        for turn in recent_turns[-4:]:
            user_msg = (turn.get("user") or {}).get("content")
            assistant_msg = (turn.get("assistant") or {}).get("content")
            if user_msg:
                turn_lines.append(f"- Người dùng: {self._shorten(str(user_msg), 220)}")
            if assistant_msg:
                turn_lines.append(f"- Trợ lý: {self._shorten(str(assistant_msg), 220)}")
        if turn_lines:
            parts.append("Lịch sử gần đây:\n" + "\n".join(turn_lines))

        parts.append(f"Yêu cầu mới cần xử lý:\n{user_text}")
        parts.append(
            "Nếu cần thao tác local, hãy thực hiện cẩn thận và trả lời bằng tiếng Việt. "
            "Nếu chưa đủ chắc chắn hoặc thiếu quyền, hãy nói rõ thay vì suy đoán."
        )
        return "\n\n".join(parts).strip()

    def _persist_turn(
        self,
        request: dict[str, Any],
        reply_text: str,
        trace: dict[str, Any],
    ):
        external_id = str(request.get("external_id") or "").strip()
        source = str(request.get("channel") or "ui").strip() or "ui"
        metadata = {
            "channel": source,
            "thread_id": str(request.get("thread_id") or "").strip(),
            "trace": trace,
        }
        self.memory_manager.append_message(
            role="user",
            content=str(request.get("user_text") or "").strip(),
            source=source,
            metadata={"thread_id": metadata["thread_id"]},
            external_id=external_id or None,
        )
        self.memory_manager.append_message(
            role="assistant",
            content=str(reply_text or "").strip(),
            source=source,
            metadata=metadata,
        )

    def handle_request(
        self,
        request: dict[str, Any],
        *,
        on_codex_chunk: Callable[[str], None] | None = None,
        runtime_event_callback: Callable[[dict[str, Any]], None] | None = None,
        persist_turn: bool = True,
        allow_codex_fallback: bool | None = None,
    ) -> dict[str, Any]:
        req = dict(request or {})
        req["attachments"] = self._normalize_request_attachments(req)
        user_text = str(req.get("user_text") or "").strip()
        if not user_text and not req.get("attachments"):
            return {
                "success": False,
                "reply_text": "",
                "artifacts": [],
                "used_tools": [],
                "trace": {"mode": "invalid", "reason": "empty_user_text"},
                "message": "Thiếu nội dung yêu cầu.",
            }

        context = self.orchestrator.build_context()
        decision = self._decide_mode(req)
        invalid_attachments = [item for item in req.get("attachments") or [] if isinstance(item, dict) and not item.get("is_valid")]
        trace: dict[str, Any] = {
            "requested_at": req.get("requested_at") or self._utc_now_iso(),
            "channel": str(req.get("channel") or "ui").strip(),
            "mode": decision.get("mode"),
            "reason": decision.get("reason"),
            "task_shape": decision.get("task_shape"),
            "confidence": decision.get("confidence"),
            "tool_choice_confidence": decision.get("tool_choice_confidence"),
            "missing_context": list(decision.get("missing_context") or []),
            "why_not_tool": decision.get("why_not_tool", ""),
            "needs_approval": bool(decision.get("needs_approval")),
            "preferred_tool": decision.get("preferred_tool", ""),
            "codex_reason": decision.get("codex_reason", ""),
            "codex_task_type": decision.get("codex_task_type", ""),
            "context_char_used": context.get("context_char_used", 0),
            "used_direct_ai": False,
            "used_builtin_functions": False,
            "used_vision": False,
            "used_codex": False,
            "fallback_triggered": False,
            "attachment_count": len(req.get("attachments") or []),
        }

        if invalid_attachments and not any(item.get("is_valid") for item in req.get("attachments") or []):
            reply_text = self._build_invalid_attachment_reply(invalid_attachments)
            return {
                "success": bool(reply_text),
                "reply_text": reply_text,
                "artifacts": [],
                "used_tools": [],
                "trace": trace,
                "message": "Invalid attachment.",
            }

        if decision.get("mode") == "ask_clarification":
            reply_text = self._build_clarification_reply(
                req,
                str(decision.get("task_shape") or "").strip(),
                list(decision.get("missing_context") or []),
            )
            trace["clarification_prompt"] = reply_text
            if persist_turn:
                self._persist_turn(req, reply_text, trace)
            self._append_trace_log(
                {
                    "kind": "request_clarification",
                    "request": {
                        "channel": trace["channel"],
                        "thread_id": str(req.get("thread_id") or ""),
                        "user_text_preview": self._shorten(user_text, 180),
                    },
                    "trace": trace,
                    "reply_preview": self._shorten(reply_text, 220),
                }
            )
            return {
                "success": True,
                "reply_text": reply_text,
                "artifacts": [],
                "used_tools": [],
                "trace": trace,
                "message": "Clarification requested.",
            }

        if decision.get("mode") == "vision_direct":
            vision_result = self._run_attachment_vision(req, req.get("attachments") or [], trace)
            if vision_result.get("success") and str(vision_result.get("reply_text") or "").strip():
                reply_text = str(vision_result.get("reply_text") or "").strip()
                if persist_turn:
                    self._persist_turn(req, reply_text, trace)
                self._append_trace_log(
                    {
                        "kind": "request_completed",
                        "request": {
                            "channel": trace["channel"],
                            "thread_id": str(req.get("thread_id") or ""),
                            "user_text_preview": self._shorten(user_text, 180),
                        },
                        "trace": trace,
                        "reply_preview": self._shorten(reply_text, 220),
                    }
                )
                return {
                    "success": True,
                    "reply_text": reply_text,
                    "artifacts": list(vision_result.get("artifacts") or []),
                    "used_tools": list(vision_result.get("used_tools") or []),
                    "trace": trace,
                    "message": "OK",
                }

            fallback_to_codex = (
                ConfigManager.get_central_ai_fallback_to_codex()
                if allow_codex_fallback is None
                else bool(allow_codex_fallback)
            )
            if not fallback_to_codex:
                trace["vision_error"] = vision_result.get("message", "Vision failed.")
                return {
                    "success": False,
                    "reply_text": "",
                    "artifacts": list(vision_result.get("artifacts") or []),
                    "used_tools": list(vision_result.get("used_tools") or []),
                    "trace": trace,
                    "message": vision_result.get("message", "Vision failed."),
                }
            trace["fallback_triggered"] = True
            trace["fallback_reason"] = vision_result.get("message", "vision_failed")
            trace["mode"] = "escalate_to_codex"
            trace["codex_reason"] = trace.get("codex_reason") or "vision_failed_fallback"
            trace["codex_task_type"] = trace.get("codex_task_type") or "multi_step_local"

        if decision.get("mode") == "tool_calling":
            tool_result = self._run_builtin_tool_round(req, context, trace)
            if tool_result.get("success") and str(tool_result.get("reply_text") or "").strip():
                reply_text = str(tool_result.get("reply_text") or "").strip()
                trace["used_builtin_functions"] = bool(tool_result.get("used_tools"))
                if persist_turn:
                    self._persist_turn(req, reply_text, trace)
                self._append_trace_log(
                    {
                        "kind": "request_completed",
                        "request": {
                            "channel": trace["channel"],
                            "thread_id": str(req.get("thread_id") or ""),
                            "user_text_preview": self._shorten(user_text, 180),
                        },
                        "trace": trace,
                        "reply_preview": self._shorten(reply_text, 220),
                    }
                )
                return {
                    "success": True,
                    "reply_text": reply_text,
                    "artifacts": list(tool_result.get("artifacts") or []),
                    "used_tools": list(tool_result.get("used_tools") or []),
                    "approval_requests": list(tool_result.get("approval_requests") or []),
                    "trace": trace,
                    "message": "OK",
                }

            fallback_to_codex = (
                ConfigManager.get_central_ai_fallback_to_codex()
                if allow_codex_fallback is None
                else bool(allow_codex_fallback)
            )
            if not fallback_to_codex:
                trace["tool_error"] = tool_result.get("message", "Tool calling failed.")
                return {
                    "success": False,
                    "reply_text": str(tool_result.get("reply_text") or "").strip(),
                    "artifacts": list(tool_result.get("artifacts") or []),
                    "used_tools": list(tool_result.get("used_tools") or []),
                    "approval_requests": list(tool_result.get("approval_requests") or []),
                    "trace": trace,
                    "message": tool_result.get("message", "Tool calling failed."),
                }
            trace["fallback_triggered"] = True
            trace["fallback_reason"] = tool_result.get("message", "tool_calling_failed")
            trace["mode"] = "escalate_to_codex"
            trace["codex_reason"] = trace.get("codex_reason") or "tool_capability_insufficient"
            trace["codex_task_type"] = trace.get("codex_task_type") or "multi_step_local"

        if decision.get("mode") == "reply_direct":
            messages = self._build_direct_messages(req, context)
            model = ConfigManager.get_central_ai_direct_model()
            direct_result = self.ai_client.chat_completion(
                messages=messages,
                model=model,
                temperature=0.4,
            )
            if direct_result.get("success") and str(direct_result.get("text") or "").strip():
                reply_text = str(direct_result.get("text") or "").strip()
                trace["used_direct_ai"] = True
                trace["direct_model"] = model
                if persist_turn:
                    self._persist_turn(req, reply_text, trace)
                self._append_trace_log(
                    {
                        "kind": "request_completed",
                        "request": {
                            "channel": trace["channel"],
                            "thread_id": str(req.get("thread_id") or ""),
                            "user_text_preview": self._shorten(user_text, 180),
                        },
                        "trace": trace,
                        "reply_preview": self._shorten(reply_text, 220),
                    }
                )
                return {
                    "success": True,
                    "reply_text": reply_text,
                    "artifacts": [],
                    "used_tools": [],
                    "trace": trace,
                    "message": "OK",
                }

            fallback_to_codex = (
                ConfigManager.get_central_ai_fallback_to_codex()
                if allow_codex_fallback is None
                else bool(allow_codex_fallback)
            )
            if not fallback_to_codex:
                trace["direct_error"] = direct_result.get("message", "")
                self._append_trace_log(
                    {
                        "kind": "request_failed",
                        "request": {
                            "channel": trace["channel"],
                            "thread_id": str(req.get("thread_id") or ""),
                            "user_text_preview": self._shorten(user_text, 180),
                        },
                        "trace": trace,
                        "error": direct_result.get("message", "Direct AI failed."),
                    }
                )
                return {
                    "success": False,
                    "reply_text": "",
                    "artifacts": [],
                    "used_tools": [],
                    "trace": trace,
                    "message": direct_result.get("message", "Direct AI failed."),
                }

            trace["fallback_triggered"] = True
            trace["fallback_reason"] = direct_result.get("message", "direct_ai_failed")
            trace["mode"] = "escalate_to_codex"
            trace["codex_reason"] = trace.get("codex_reason") or "direct_ai_failed"
            trace["codex_task_type"] = trace.get("codex_task_type") or "multi_step_local"

        codex_prompt = self._build_codex_prompt(req, context)
        codex_result = self.codex_bridge.stream_reply(
            codex_prompt,
            on_chunk=on_codex_chunk,
            runtime_event_callback=runtime_event_callback,
            request_context={
                "channel": trace["channel"],
                "task_shape": trace.get("task_shape", ""),
                "codex_reason": trace.get("codex_reason", ""),
                "codex_task_type": trace.get("codex_task_type", ""),
                "thread_id": str(req.get("thread_id") or ""),
            },
        )
        if codex_result.get("success") and str(codex_result.get("output") or "").strip():
            reply_text = str(codex_result.get("output") or "").strip()
            trace["used_codex"] = True
            trace["codex_mode"] = codex_result.get("mode", "")
            if persist_turn:
                self._persist_turn(req, reply_text, trace)
            self._append_trace_log(
                {
                    "kind": "request_completed",
                    "request": {
                        "channel": trace["channel"],
                        "thread_id": str(req.get("thread_id") or ""),
                        "user_text_preview": self._shorten(user_text, 180),
                    },
                    "trace": trace,
                    "reply_preview": self._shorten(reply_text, 220),
                }
            )
            return {
                "success": True,
                "reply_text": reply_text,
                "artifacts": [],
                "used_tools": [],
                "trace": trace,
                "message": "OK",
            }

        trace["codex_error"] = codex_result.get("message", "Codex failed.")
        self._append_trace_log(
            {
                "kind": "request_failed",
                "request": {
                    "channel": trace["channel"],
                    "thread_id": str(req.get("thread_id") or ""),
                    "user_text_preview": self._shorten(user_text, 180),
                },
                "trace": trace,
                "error": codex_result.get("message", "Codex failed."),
            }
        )
        return {
            "success": False,
            "reply_text": "",
            "artifacts": [],
            "used_tools": [],
            "trace": trace,
            "message": codex_result.get("message", "Codex failed."),
        }
