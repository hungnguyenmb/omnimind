import logging
import json
import os
import platform
import re
import threading
import time
from datetime import datetime
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import requests

from engine.codex_runtime_bridge import CodexRuntimeBridge
from engine.config_manager import ConfigManager
from engine.memory_manager import MemoryManager
from engine.skill_manager import SkillManager

logger = logging.getLogger(__name__)


@dataclass
class _StreamState:
    message_ids: list[int] = field(default_factory=list)
    last_sent_at: float = 0.0


class TelegramStreamTransport:
    """
    Transport layer cho Telegram streaming:
    - Split text thành nhiều phần nhỏ.
    - Gửi lần đầu bằng sendMessage.
    - Các lần sau update bằng editMessageText.
    """

    MAX_CHUNK_SIZE = 3900

    def __init__(self, token: str):
        self.token = str(token or "").strip()
        self._session = requests.Session()

    def _api(self, method: str, payload: dict, timeout: int = 30) -> dict:
        url = f"https://api.telegram.org/bot{self.token}/{method}"
        resp = self._session.post(url, json=payload, timeout=timeout)
        data = resp.json() if resp.content else {}
        if not isinstance(data, dict):
            raise RuntimeError(f"Telegram API {method} response không hợp lệ.")
        if not data.get("ok"):
            raise RuntimeError(data.get("description") or f"Telegram API {method} lỗi.")
        return data.get("result", {}) or {}

    @classmethod
    def split_text(cls, text: str) -> list[str]:
        body = str(text or "").strip()
        if not body:
            return [""]
        return [body[i : i + cls.MAX_CHUNK_SIZE] for i in range(0, len(body), cls.MAX_CHUNK_SIZE)]

    def update_stream(self, chat_id: str, state: _StreamState, full_text: str):
        chunks = self.split_text(full_text)
        for idx, chunk in enumerate(chunks):
            if idx < len(state.message_ids):
                message_id = state.message_ids[idx]
                try:
                    self._api(
                        "editMessageText",
                        {
                            "chat_id": chat_id,
                            "message_id": message_id,
                            "text": chunk,
                            "disable_web_page_preview": True,
                        },
                        timeout=20,
                    )
                except Exception as e:
                    # "message is not modified" là lỗi bình thường khi text giữ nguyên.
                    err = str(e).lower()
                    if "not modified" not in err:
                        logger.warning(f"editMessageText error: {e}")
                continue

            result = self._api(
                "sendMessage",
                {
                    "chat_id": chat_id,
                    "text": chunk,
                    "disable_web_page_preview": True,
                },
                timeout=20,
            )
            message_id = int(result.get("message_id"))
            state.message_ids.append(message_id)

    def send_message(self, chat_id: str, text: str) -> int:
        result = self._api(
            "sendMessage",
            {
                "chat_id": chat_id,
                "text": str(text or ""),
                "disable_web_page_preview": True,
            },
            timeout=20,
        )
        return int(result.get("message_id"))

    def edit_message(self, chat_id: str, message_id: int, text: str):
        self._api(
            "editMessageText",
            {
                "chat_id": chat_id,
                "message_id": int(message_id),
                "text": str(text or ""),
                "disable_web_page_preview": True,
            },
            timeout=20,
        )

    def delete_message(self, chat_id: str, message_id: int):
        self._api(
            "deleteMessage",
            {
                "chat_id": chat_id,
                "message_id": int(message_id),
            },
            timeout=20,
        )

    def send_text_chunks(self, chat_id: str, full_text: str):
        for chunk in self.split_text(full_text):
            self.send_message(chat_id, chunk)

    def send_document(self, chat_id: str, file_path: str, caption: str = "") -> dict:
        url = f"https://api.telegram.org/bot{self.token}/sendDocument"
        with open(file_path, "rb") as f:
            files = {"document": f}
            data = {"chat_id": str(chat_id)}
            if caption:
                data["caption"] = str(caption)
            resp = self._session.post(url, data=data, files=files, timeout=120)
        payload = resp.json() if resp.content else {}
        if not isinstance(payload, dict) or not payload.get("ok"):
            raise RuntimeError((payload or {}).get("description") or "sendDocument lỗi.")
        return payload.get("result", {}) or {}


class TelegramBotService:
    """
    Telegram bot runtime:
    - Long polling getUpdates.
    - Stream phản hồi theo cơ chế send/edit.
    - Log hội thoại vào assistant memory.
    """

    POLL_TIMEOUT_SEC = 25
    STREAM_THROTTLE_SEC = 0.8
    MAX_ARTIFACT_SEND_BYTES = 49 * 1024 * 1024
    RUNTIME_DEBUG_LOG_MAX_BYTES = 8 * 1024 * 1024
    MAX_RUNTIME_ACTION_DIRECTIVES = 3

    def __init__(self):
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.RLock()
        self._skill_manager = SkillManager()
        self._memory_mgr = MemoryManager()
        self._codex_bridge = CodexRuntimeBridge()
        self._session = requests.Session()
        self._path_token_re = re.compile(r"(/[^\s'\"`]+|[A-Za-z]:\\[^\s'\"`]+)")
        self._send_doc_directive_re = re.compile(
            r"\[\[OMNIMIND_SEND_DOCUMENT:(.*?)\]\]",
            re.IGNORECASE | re.DOTALL,
        )
        self._run_action_directive_re = re.compile(
            r"\[\[OMNIMIND_RUN_ACTION:(.*?)\]\]",
            re.IGNORECASE | re.DOTALL,
        )

    def is_running(self) -> bool:
        th = self._thread
        return bool(th and th.is_alive())

    def start(self) -> dict:
        with self._lock:
            if self.is_running():
                return {"success": True, "message": "Telegram bot đã chạy."}

            cfg = ConfigManager.get_telegram_config()
            token = str(cfg.get("token") or "").strip()
            chat_id = str(cfg.get("chat_id") or "").strip()
            if not token or not chat_id:
                return {"success": False, "message": "Thiếu Telegram Token hoặc Chat ID."}

            self._stop_event.clear()
            self._thread = threading.Thread(target=self._run_loop, name="omnimind-telegram-bot", daemon=True)
            self._thread.start()
            ConfigManager.set("bot_enabled", "True")
            return {"success": True, "message": "Đã bật Telegram bot runtime."}

    def stop(self) -> dict:
        with self._lock:
            if not self.is_running():
                ConfigManager.set("bot_enabled", "False")
                return {"success": True, "message": "Telegram bot đã dừng."}

            self._stop_event.set()
            th = self._thread
            if th:
                th.join(timeout=3)
            if th and th.is_alive():
                ConfigManager.set("bot_enabled", "False")
                return {"success": True, "message": "Telegram bot đang dừng nền, vui lòng đợi vài giây."}

            self._thread = None
            ConfigManager.set("bot_enabled", "False")
            return {"success": True, "message": "Đã tắt Telegram bot runtime."}

    def _get_updates(self, token: str, offset: int) -> list[dict]:
        url = f"https://api.telegram.org/bot{token}/getUpdates"
        params = {
            "offset": offset + 1,
            "timeout": self.POLL_TIMEOUT_SEC,
        }
        try:
            resp = self._session.get(url, params=params, timeout=self.POLL_TIMEOUT_SEC + 10)
            data = resp.json() if resp.content else {}
            if not isinstance(data, dict) or not data.get("ok"):
                logger.warning(f"getUpdates lỗi: {data}")
                return []
            items = data.get("result", [])
            return items if isinstance(items, list) else []
        except Exception as e:
            logger.warning(f"getUpdates exception: {e}")
            return []

    @staticmethod
    def _chat_match(message_chat_id, configured_chat_id: str) -> bool:
        if configured_chat_id == "":
            return True
        return str(message_chat_id) == configured_chat_id

    @staticmethod
    def _telegram_download_root() -> Path:
        if platform.system() == "Windows":
            base = os.environ.get("LOCALAPPDATA", os.path.expanduser("~\\AppData\\Local"))
            return Path(base) / "OmniMind" / "telegram_downloads"
        if platform.system() == "Darwin":
            return Path(os.path.expanduser("~/Library/Application Support")) / "OmniMind" / "telegram_downloads"
        return Path(os.path.expanduser("~/.omnimind")) / "telegram_downloads"

    @staticmethod
    def _safe_name(name: str, fallback: str) -> str:
        cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", str(name or "")).strip("._")
        return cleaned or fallback

    def _download_telegram_file(self, token: str, file_id: str, fallback_name: str) -> str:
        file_meta_url = f"https://api.telegram.org/bot{token}/getFile"
        meta_resp = self._session.get(file_meta_url, params={"file_id": file_id}, timeout=30)
        meta_payload = meta_resp.json() if meta_resp.content else {}
        if not isinstance(meta_payload, dict) or not meta_payload.get("ok"):
            raise RuntimeError((meta_payload or {}).get("description") or "getFile lỗi.")

        file_path = str((meta_payload.get("result") or {}).get("file_path") or "").strip()
        if not file_path:
            raise RuntimeError("Telegram không trả file_path.")

        original_name = Path(file_path).name or fallback_name
        day = datetime.now().strftime("%Y-%m-%d")
        root_dir = self._telegram_download_root() / day
        root_dir.mkdir(parents=True, exist_ok=True)

        target_name = self._safe_name(original_name, fallback_name)
        target_path = root_dir / target_name
        if target_path.exists():
            stem = target_path.stem
            suffix = target_path.suffix
            target_path = root_dir / f"{stem}_{int(time.time())}{suffix}"

        file_url = f"https://api.telegram.org/file/bot{token}/{file_path}"
        with self._session.get(file_url, stream=True, timeout=120) as r:
            r.raise_for_status()
            with open(target_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=1024 * 256):
                    if chunk:
                        f.write(chunk)
        return str(target_path)

    def _extract_existing_paths(self, text: str) -> list[str]:
        out = []
        seen = set()
        for match in self._path_token_re.findall(str(text or "")):
            candidate = str(match).strip().strip(".,;:!?)")
            if not candidate:
                continue
            expanded = os.path.expanduser(candidate)
            p = Path(expanded)
            if not p.is_file():
                continue
            try:
                resolved = str(p.resolve())
            except Exception:
                resolved = str(p)
            if resolved in seen:
                continue
            seen.add(resolved)
            out.append(resolved)
        return out

    @staticmethod
    def _looks_like_request_send_file(user_text: str, has_recent_paths: bool = False) -> bool:
        low = str(user_text or "").lower()
        if (
            ("gửi" in low and "file" in low)
            or ("gửi" in low and "tệp" in low)
            or ("gửi" in low and "tập tin" in low)
            or ("gửi" in low and "tài liệu" in low)
            or ("gửi lại" in low and "tài liệu" in low)
            or ("đính kèm" in low and "file" in low)
            or ("send" in low and "file" in low)
            or ("send" in low and "document" in low)
        ):
            return True

        if not has_recent_paths:
            return False

        pronoun_patterns = (
            r"\bgửi (nó|bản đó|cái đó|file đó|tệp đó|tài liệu đó)\b",
            r"\bsend (it|that file|that document)\b",
        )
        return any(re.search(pat, low) for pat in pronoun_patterns)

    @staticmethod
    def _extract_requested_filename(user_text: str) -> str:
        text = str(user_text or "")
        # Bắt tên file có extension phổ biến.
        match = re.search(
            r"([A-Za-z0-9._\- ]+\.(?:txt|md|csv|json|doc|docx|xls|xlsx|pdf|png|jpg|jpeg|zip))",
            text,
            re.IGNORECASE,
        )
        if not match:
            return ""
        return str(match.group(1)).strip()

    @staticmethod
    def _runtime_debug_log_path() -> Path:
        if platform.system() == "Windows":
            base = os.environ.get("LOCALAPPDATA", os.path.expanduser("~\\AppData\\Local"))
            root = Path(base) / "OmniMind" / "logs"
        elif platform.system() == "Darwin":
            root = Path(os.path.expanduser("~/Library/Application Support")) / "OmniMind" / "logs"
        else:
            root = Path(os.path.expanduser("~/.omnimind")) / "logs"
        root.mkdir(parents=True, exist_ok=True)
        return root / "codex_runtime_stream.jsonl"

    def _append_runtime_debug_log(self, payload: dict):
        try:
            log_path = self._runtime_debug_log_path()
            if log_path.exists() and log_path.stat().st_size > self.RUNTIME_DEBUG_LOG_MAX_BYTES:
                backup = log_path.with_suffix(".jsonl.1")
                try:
                    if backup.exists():
                        backup.unlink()
                except Exception:
                    pass
                log_path.rename(backup)

            row = {
                "ts": datetime.utcnow().isoformat() + "Z",
                **(payload or {}),
            }
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.warning(f"append runtime debug log failed: {e}")

    @staticmethod
    def _stream_preview_log_path() -> Path:
        if platform.system() == "Windows":
            base = os.environ.get("LOCALAPPDATA", os.path.expanduser("~\\AppData\\Local"))
            root = Path(base) / "OmniMind" / "logs"
        elif platform.system() == "Darwin":
            root = Path(os.path.expanduser("~/Library/Application Support")) / "OmniMind" / "logs"
        else:
            root = Path(os.path.expanduser("~/.omnimind")) / "logs"
        root.mkdir(parents=True, exist_ok=True)
        return root / "codex_stream_preview_sent.jsonl"

    def _append_stream_preview_log(self, payload: dict):
        try:
            log_path = self._stream_preview_log_path()
            if log_path.exists() and log_path.stat().st_size > self.RUNTIME_DEBUG_LOG_MAX_BYTES:
                backup = log_path.with_suffix(".jsonl.1")
                try:
                    if backup.exists():
                        backup.unlink()
                except Exception:
                    pass
                log_path.rename(backup)

            row = {
                "ts": datetime.utcnow().isoformat() + "Z",
                **(payload or {}),
            }
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.warning(f"append stream preview log failed: {e}")

    def _extract_send_document_directives(self, text: str) -> tuple[str, list[dict]]:
        directives: list[dict] = []

        def _replace(match: re.Match) -> str:
            payload = str(match.group(1) or "").strip()
            if not payload:
                return ""

            path_value = ""
            caption_value = ""
            for part in [x.strip() for x in payload.split(";") if x.strip()]:
                if "=" not in part:
                    if not path_value:
                        path_value = part
                    continue
                key, value = part.split("=", 1)
                key = key.strip().lower()
                value = value.strip().strip('"').strip("'")
                if key in {"path", "file", "filepath"}:
                    path_value = value
                elif key == "caption":
                    caption_value = value

            if path_value:
                directives.append({"path": path_value, "caption": caption_value})
            return ""

        cleaned = self._send_doc_directive_re.sub(_replace, str(text or ""))
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
        return cleaned, directives

    @staticmethod
    def _parse_bool_token(value: str, default: bool = False) -> bool:
        raw = str(value or "").strip().lower()
        if not raw:
            return default
        if raw in {"1", "true", "yes", "y", "on"}:
            return True
        if raw in {"0", "false", "no", "n", "off"}:
            return False
        return default

    def _extract_runtime_action_directives(self, text: str) -> tuple[str, list[dict]]:
        directives: list[dict] = []

        def _replace(match: re.Match) -> str:
            payload = str(match.group(1) or "").strip()
            if not payload:
                return ""

            record = {
                "skill_id": "omnimind-runtime",
                "action_id": "",
                "payload": {},
                "auto_request_permissions": True,
            }

            for part in [x.strip() for x in payload.split(";") if x.strip()]:
                if "=" not in part:
                    if not record["action_id"]:
                        record["action_id"] = part
                    continue
                key, value = part.split("=", 1)
                key = key.strip().lower()
                value = value.strip()

                if key in {"skill_id", "skill"}:
                    record["skill_id"] = value.strip().strip('"').strip("'") or "omnimind-runtime"
                    continue
                if key in {"action_id", "action"}:
                    record["action_id"] = value.strip().strip('"').strip("'")
                    continue
                if key in {"auto_request_permissions", "auto_request", "request_permissions"}:
                    record["auto_request_permissions"] = self._parse_bool_token(value, default=True)
                    continue
                if key in {"payload_json", "payload"}:
                    raw = value.strip().strip('"').strip("'")
                    if raw:
                        try:
                            parsed = json.loads(raw)
                            if isinstance(parsed, dict):
                                record["payload"] = parsed
                        except Exception:
                            # Nếu payload parse lỗi thì bỏ qua, giữ dict rỗng để runtime không crash.
                            record["payload"] = {}
                    continue

            action_id = str(record.get("action_id") or "").strip()
            if action_id:
                directives.append(record)
            return ""

        cleaned = self._run_action_directive_re.sub(_replace, str(text or ""))
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
        return cleaned, directives

    def _execute_runtime_action_directives(
        self,
        transport: TelegramStreamTransport,
        chat_id: str,
        directives: list[dict],
    ) -> dict:
        notes: list[str] = []
        artifact_paths: list[str] = []
        if not directives:
            return {"notes": notes, "artifact_paths": artifact_paths}

        for item in directives[: self.MAX_RUNTIME_ACTION_DIRECTIVES]:
            skill_id = str((item or {}).get("skill_id") or "omnimind-runtime").strip() or "omnimind-runtime"
            action_id = str((item or {}).get("action_id") or "").strip().lower()
            payload = (item or {}).get("payload") if isinstance((item or {}).get("payload"), dict) else {}
            auto_request = bool((item or {}).get("auto_request_permissions", True))
            if not action_id:
                continue

            transport.send_text_chunks(chat_id, f"⚙️ OmniMind đang thực thi action: `{action_id}`...")
            result = self._skill_manager.execute_builtin_skill_action(
                skill_id=skill_id,
                action_id=action_id,
                payload=payload,
                auto_request_permissions=auto_request,
            )

            if result.get("success"):
                msg = str(result.get("message") or "Action chạy thành công.").strip()
                code = str(result.get("code") or "").strip()
                artifact_path = str(result.get("artifact_path") or "").strip()
                if artifact_path:
                    artifact_paths.append(artifact_path)
                    msg = f"{msg}\nĐầu ra: {artifact_path}"

                transport.send_text_chunks(
                    chat_id,
                    f"✅ OmniMind đã chạy action `{action_id}` thành công."
                    + (f"\nMã kết quả: {code}" if code else "")
                    + (f"\n{msg}" if msg else ""),
                )
                notes.append(f"{action_id}: success - {msg}")
                continue

            code = str(result.get("code") or "").strip()
            msg = str(result.get("message") or "Action thất bại.").strip()

            if code == "PERMISSION_REQUIRED":
                preflight = result.get("preflight") or {}
                missing = preflight.get("missing_permissions") or []
                missing_names = ", ".join(
                    sorted({str(x.get("permission") or "").strip() for x in missing if str(x.get("permission") or "").strip()})
                )
                detail = f"\nQuyền còn thiếu: {missing_names}" if missing_names else ""
                transport.send_text_chunks(
                    chat_id,
                    f"🛡️ OmniMind chưa thể chạy action `{action_id}` do thiếu quyền hệ thống."
                    f"{detail}\n{msg}",
                )
                notes.append(f"{action_id}: permission_required - {missing_names or msg}")
            else:
                transport.send_text_chunks(
                    chat_id,
                    f"❌ OmniMind chạy action `{action_id}` thất bại.\n{msg}",
                )
                notes.append(f"{action_id}: failed - {msg}")

        return {"notes": notes, "artifact_paths": artifact_paths}

    def _extract_paths_from_recent_messages(self, recent_messages: list[dict], max_messages: int = 8) -> list[str]:
        out: list[str] = []
        seen = set()
        rows = list(recent_messages or [])
        for msg in reversed(rows[-max_messages:]):
            content = str((msg or {}).get("content") or "")
            for path in self._extract_existing_paths(content):
                if path in seen:
                    continue
                seen.add(path)
                out.append(path)
        return out

    @staticmethod
    def _resolve_directive_path(raw_path: str, recent_paths: list[str]) -> str:
        candidate = str(raw_path or "").strip()
        if not candidate:
            return ""

        expanded = os.path.expanduser(candidate)
        p = Path(expanded)
        if p.is_file():
            try:
                return str(p.resolve())
            except Exception:
                return str(p)

        target_name = Path(candidate).name.lower()
        if not target_name:
            return ""

        # Ưu tiên file gần nhất theo context.
        for rp in recent_paths:
            rp_obj = Path(rp)
            if rp_obj.name.lower() == target_name and rp_obj.is_file():
                try:
                    return str(rp_obj.resolve())
                except Exception:
                    return str(rp_obj)

        # Fallback: match gần đúng theo tên file.
        for rp in recent_paths:
            rp_obj = Path(rp)
            if target_name in rp_obj.name.lower() and rp_obj.is_file():
                try:
                    return str(rp_obj.resolve())
                except Exception:
                    return str(rp_obj)
        return ""

    @staticmethod
    def _is_meaningful_thinking_line(line: str) -> bool:
        text = str(line or "").strip()
        if not text:
            return False
        low = text.lower()
        noise_words = {
            "execute",
            "execution",
            "script",
            "file",
            "request",
            "review",
            "recreation",
            "create",
            "run",
            "tool",
        }
        if low in noise_words:
            return False
        if len(text) < 12 and re.search(r"[A-Za-z]", text):
            return False
        if len(text.split()) < 2 and not re.search(r"[,.!?;:]", text):
            return False
        return True

    def _finalize_assistant_message(
        self,
        transport: TelegramStreamTransport,
        chat_id: str,
        draft_id: int | None,
        final_text: str,
    ):
        body = str(final_text or "").strip() or "OmniMind không trả nội dung."
        try:
            transport.send_text_chunks(chat_id, body)
            if draft_id:
                try:
                    transport.delete_message(chat_id, draft_id)
                except Exception:
                    pass
        except Exception:
            if draft_id:
                try:
                    transport.edit_message(chat_id, draft_id, body)
                    return
                except Exception:
                    pass
            raise

    def _try_send_document_from_candidates(
        self,
        transport: TelegramStreamTransport,
        chat_id: str,
        requested_name: str,
        candidates: list[dict],
    ) -> bool:
        for item in candidates:
            raw_path = str((item or {}).get("path") or "").strip()
            if not raw_path:
                continue

            path_obj = Path(os.path.expanduser(raw_path))
            if not path_obj.is_file():
                continue

            file_name = path_obj.name.lower()
            if requested_name and requested_name not in file_name:
                continue

            try:
                real_path = str(path_obj.resolve())
            except Exception:
                real_path = str(path_obj)

            try:
                size = os.path.getsize(real_path)
                if size > self.MAX_ARTIFACT_SEND_BYTES:
                    logger.info(f"Skip artifact quá lớn: {real_path}")
                    continue
                caption = str((item or {}).get("caption") or "").strip() or f"Artifact từ OmniMind: {path_obj.name}"
                transport.send_document(chat_id=chat_id, file_path=real_path, caption=caption)
                return True
            except Exception as send_err:
                logger.warning(f"send_document failed ({real_path}): {send_err}")
        return False

    @staticmethod
    def _is_noise_line(line: str) -> bool:
        raw = str(line or "").strip()
        if not raw:
            return True
        low = raw.lower()
        if low in {"user", "codex", "thinking"}:
            return True
        prefixes = (
            "openai codex",
            "workdir:",
            "model:",
            "provider:",
            "approval:",
            "sandbox:",
            "reasoning effort:",
            "reasoning summaries:",
            "session id:",
            "mcp startup:",
            "tokens used",
        )
        if low.startswith(prefixes):
            return True
        if "warn codex_core::" in low:
            return True
        # Dòng chỉ chứa số token.
        if re.fullmatch(r"[0-9][0-9,._ ]*", raw):
            return True
        return False

    def _extract_final_response(self, raw_output: str) -> str:
        lines = [ln.rstrip() for ln in str(raw_output or "").splitlines()]
        if not lines:
            return ""

        lowered = [ln.strip().lower() for ln in lines]
        codex_idxs = [i for i, low in enumerate(lowered) if low == "codex"]
        if codex_idxs:
            start = codex_idxs[-1] + 1
            collected = []
            for ln in lines[start:]:
                if self._is_noise_line(ln):
                    continue
                collected.append(ln.strip())
            body = "\n".join([x for x in collected if x]).strip()
            if body:
                return body

        # Fallback: bỏ các dòng metadata/noise và block echo prompt user.
        filtered = []
        in_user_echo = False
        for ln in lines:
            low = ln.strip().lower()
            if low == "user":
                in_user_echo = True
                continue
            if low in {"thinking", "codex"}:
                in_user_echo = False
                continue
            if in_user_echo:
                continue
            if self._is_noise_line(ln):
                continue
            filtered.append(ln.strip())
        return "\n".join([x for x in filtered if x]).strip()

    @staticmethod
    def _dedupe_response_text(text: str) -> str:
        body = str(text or "").strip()
        if not body:
            return ""

        # 1) Loại dòng trùng liên tiếp.
        lines = [ln.strip() for ln in body.splitlines() if ln.strip()]
        if lines:
            compact = []
            for ln in lines:
                if compact and ln == compact[-1]:
                    continue
                compact.append(ln)
            body = "\n".join(compact).strip()

        if not body:
            return ""

        # 2) Nếu toàn bộ đoạn bị lặp 2 lần liên tiếp, giữ 1 lần.
        n = len(body)
        if n % 2 == 0:
            half = n // 2
            left = body[:half].strip()
            right = body[half:].strip()
            if left and left == right:
                return left

        # 3) Dò block lặp gần giống nhau (thường do codex in 2 lần phần final answer).
        lines = [ln.strip() for ln in body.splitlines() if ln.strip()]
        if len(lines) < 6:
            return body

        def norm_line(s: str) -> str:
            lowered = str(s or "").lower()
            lowered = re.sub(r"[`'\"*#\-:;,.!?()\[\]{}]", "", lowered)
            lowered = re.sub(r"\s+", " ", lowered).strip()
            return lowered

        norm = [norm_line(ln) for ln in lines]
        cutoff = None
        min_match = 4
        for i in range(0, len(norm) - min_match):
            for j in range(i + min_match, len(norm) - min_match + 1):
                if norm[i] != norm[j]:
                    continue
                matched = 0
                total = 0
                for k in range(min(12, len(norm) - j, len(norm) - i)):
                    total += 1
                    if norm[i + k] == norm[j + k]:
                        matched += 1
                if total >= min_match and matched / max(1, total) >= 0.75:
                    cutoff = j
                    break
            if cutoff is not None:
                break

        if cutoff is not None:
            body = "\n".join(lines[:cutoff]).strip()

        return body

    def _run_loop(self):
        logger.info("Telegram bot loop started.")
        while not self._stop_event.is_set():
            cfg = ConfigManager.get_telegram_config()
            token = str(cfg.get("token") or "").strip()
            chat_id = str(cfg.get("chat_id") or "").strip()
            if not token or not chat_id:
                time.sleep(2)
                continue

            try:
                last_offset = int(ConfigManager.get("telegram_last_update_id", "0") or 0)
            except Exception:
                last_offset = 0

            updates = self._get_updates(token, last_offset)
            if not updates:
                continue

            transport = TelegramStreamTransport(token)
            for update in updates:
                if self._stop_event.is_set():
                    break
                update_id = int(update.get("update_id") or 0)
                if update_id <= 0:
                    continue

                if update_id > last_offset:
                    last_offset = update_id
                    ConfigManager.set("telegram_last_update_id", str(last_offset))

                # Chỉ xử lý message mới; bỏ edited_message để tránh trả lời lặp khi user sửa tin nhắn.
                msg = update.get("message") or {}
                if not isinstance(msg, dict):
                    continue
                if not self._chat_match((msg.get("chat") or {}).get("id"), chat_id):
                    continue
                user_text = str(msg.get("text") or "").strip()
                caption = str(msg.get("caption") or "").strip()
                photos = msg.get("photo") if isinstance(msg.get("photo"), list) else []
                document = msg.get("document") if isinstance(msg.get("document"), dict) else None

                # text-only
                if user_text:
                    self._handle_text_message(
                        transport=transport,
                        chat_id=chat_id,
                        update_id=update_id,
                        message_id=int(msg.get("message_id") or 0),
                        user_text=user_text,
                    )
                    continue

                # photo/document
                if photos or document:
                    self._handle_file_message(
                        transport=transport,
                        token=token,
                        chat_id=chat_id,
                        update_id=update_id,
                        message_id=int(msg.get("message_id") or 0),
                        caption=caption,
                        photos=photos,
                        document=document,
                    )
                    continue
        logger.info("Telegram bot loop stopped.")

    def _handle_file_message(
        self,
        transport: TelegramStreamTransport,
        token: str,
        chat_id: str,
        update_id: int,
        message_id: int,
        caption: str,
        photos: list[dict],
        document: dict | None,
    ):
        try:
            if photos:
                largest = photos[-1]
                file_id = str(largest.get("file_id") or "").strip()
                if not file_id:
                    raise RuntimeError("Photo không có file_id.")
                local_path = self._download_telegram_file(token, file_id, "telegram_photo.jpg")
                prompt_text = (caption or "Hãy phân tích ảnh này.").strip()
            else:
                file_id = str((document or {}).get("file_id") or "").strip()
                if not file_id:
                    raise RuntimeError("Document không có file_id.")
                file_name = str((document or {}).get("file_name") or "telegram_document.bin")
                local_path = self._download_telegram_file(token, file_id, file_name)
                prompt_text = (caption or "Hãy phân tích file đính kèm này.").strip()

            merged_user_text = (
                f"{prompt_text}\n\n"
                f"Đường dẫn file local đã tải: {local_path}\n"
                "Nếu cần đọc file, hãy xử lý dựa trên đường dẫn này."
            )
            self._handle_text_message(
                transport=transport,
                chat_id=chat_id,
                update_id=update_id,
                message_id=message_id,
                user_text=merged_user_text,
            )
        except Exception as e:
            logger.exception("Handle file message failed")
            try:
                state = _StreamState()
                transport.update_stream(chat_id, state, f"Lỗi khi tải file từ Telegram: {str(e)[:220]}")
            except Exception:
                pass

    def _build_codex_prompt(self, user_text: str) -> tuple[str, dict]:
        context = self._skill_manager.get_runtime_conversation_context(
            message_limit=12,
            facts_limit=10,
            char_budget=5000,
        )
        rules_block = self._memory_mgr.build_rules_prompt(max_chars=2200)
        profile = context.get("profile") or {}
        facts = context.get("facts") or []
        summaries = context.get("summaries") or []
        latest_summary = (context.get("latest_summary") or {}).get("summary_text", "").strip()
        recent_turns = context.get("recent_turns") or []
        facts_hint = "\n".join([f"- {str(f.get('fact', '')).strip()}" for f in facts[:6] if f.get("fact")])
        summaries_hint = "\n".join(
            [f"- {str(item.get('summary_text', '')).strip()}" for item in summaries[-3:] if item.get("summary_text")]
        )
        turns_hint_rows = []
        for turn in recent_turns[-4:]:
            user_msg = str(((turn.get("user") or {}).get("content")) or "").strip()
            assistant_msg = str(((turn.get("assistant") or {}).get("content")) or "").strip()
            if user_msg:
                turns_hint_rows.append(f"- User: {user_msg[:220]}")
            if assistant_msg:
                turns_hint_rows.append(f"- Assistant: {assistant_msg[:220]}")
        turns_hint = "\n".join(turns_hint_rows)
        persona = str(profile.get("persona_prompt") or "").strip()
        display_name = str(profile.get("display_name") or "người dùng").strip()

        prompt_parts = [
            "Bạn là OmniMind - trợ lý AI cá nhân thông minh. Chủ nhân có thể đặt lại tên cho bạn và thiết lập rules để điều chỉnh hành vi của bạn, hãy luôn tuân thủ các chỉ dẫn đó.",
            "Hãy thấu hiểu người chủ dựa trên profile/rules/memory, chủ động hỗ trợ như một trợ lý chuyên nghiệp, luôn ưu tiên kết quả công việc tốt nhất cho chủ.",
            "Phản hồi ưu tiên bằng tiếng Việt (hoặc có thể bằng ngôn ngữ khác nếu chủ nhân của bạn yêu cầu), lịch sự, đôi lúc hài hước, dí dỏm theo ngữ cảnh, nhưng không dài dòng giải thích nếu không cần thiết.",
        ]
        if persona:
            prompt_parts.append(f"Persona assistant:\n{persona}")
        if rules_block:
            prompt_parts.append(
                "Working Principles bắt buộc tuân thủ (độ ưu tiên cao):\n"
                f"{rules_block}"
            )
        if latest_summary:
            prompt_parts.append(f"Tóm tắt ngữ cảnh gần nhất:\n{latest_summary[:1200]}")
        if summaries_hint:
            prompt_parts.append(f"Các summary gần đây:\n{summaries_hint}")
        if facts_hint:
            prompt_parts.append(f"Sự thật cần nhớ về người dùng:\n{facts_hint}")
        if turns_hint:
            prompt_parts.append(f"Recent turns:\n{turns_hint}")
        prompt_parts.append(
            "Tool mặc định luôn có sẵn:\n"
            "1) SEND_DOCUMENT_TO_TELEGRAM\n"
            "2) RUN_BUILTIN_ACTION\n\n"
            "A. Gửi file Telegram:\n"
            "Chỉ dùng khi người dùng yêu cầu gửi file/tài liệu.\n"
            "Nếu user yêu cầu gửi file mà thiếu chỉ thị tool thì coi như task CHƯA hoàn thành.\n"
            "Khi cần gửi file, thêm đúng 1 dòng lệnh máy ở CUỐI câu trả lời:\n"
            "[[OMNIMIND_SEND_DOCUMENT:path=<duong_dan_tuyet_doi>;caption=<mo_ta_ngan>]]\n"
            "Không thêm dòng này nếu người dùng không yêu cầu gửi file.\n"
            "Không nói \"đã gửi\" trước khi phát dòng chỉ thị này.\n\n"
            "B. Chạy action runtime:\n"
            "Chỉ dùng khi người dùng yêu cầu thao tác hệ thống.\n"
            "Các action hỗ trợ: runtime_ping, screen_capture, camera_snapshot, ui_automation_type_text, system_restart.\n"
            "Khi cần chạy action, thêm đúng 1 dòng lệnh máy ở CUỐI câu trả lời:\n"
            "[[OMNIMIND_RUN_ACTION:action_id=<action_id>;payload_json=<json>;auto_request_permissions=true]]\n"
            "Ví dụ payload_json: {\"text\":\"xin chào\"} hoặc {\"confirm\":true,\"dry_run\":true}.\n"
            "Không tự ý chạy action nguy hiểm nếu người dùng chưa xác nhận rõ."
        )
        prompt_parts.append(f"Tên hiển thị người dùng: {display_name}")
        prompt_parts.append(f"Yêu cầu hiện tại từ Telegram:\n{user_text}")
        prompt_parts.append("Trả lời trực tiếp, không giải thích dài dòng.")
        return "\n\n".join(prompt_parts).strip(), context

    def _stream_codex_response(
        self,
        transport: TelegramStreamTransport,
        chat_id: str,
        prompt: str,
        log_context: dict | None = None,
    ) -> tuple[str, int | None]:
        trace = dict(log_context or {})
        self._append_runtime_debug_log(
            {
                "phase": "start",
                "chat_id": str(chat_id),
                "prompt_preview": str(prompt or "")[:800],
                **trace,
            }
        )

        draft_id = None
        try:
            draft_id = transport.send_message(chat_id, "🤔 AI đang suy nghĩ câu trả lời...")
            self._append_stream_preview_log(
                {
                    "phase": "preview_init",
                    "chat_id": str(chat_id),
                    "draft_message_id": int(draft_id),
                    "preview_text": "🤔 AI đang suy nghĩ câu trả lời...",
                    **trace,
                }
            )
        except Exception:
            draft_id = None

        output_chunks: list[str] = []
        thinking_buffer = ""
        last_stream_sent = 0.0
        last_stream_text = ""
        chunk_index = 0
        runtime_event_stream_active = False

        def _is_system_noise(line: str) -> bool:
            low = str(line or "").strip().lower()
            if not low:
                return True
            banned_fragments = (
                "đang kết nối codex app-server",
                "kết nối app-server",
                "đang gửi yêu cầu cho codex",
                "codex_state::runtime",
                "failed to open state db",
                "resolved migrations",
                "httpconnectionpool(",
                "connection refused",
                "migration ",
                "warn ",
                "warning:",
                "runtime:",
            )
            if any(x in low for x in banned_fragments):
                return True
            if re.match(r"^\d{4}-\d{2}-\d{2}t\d{2}:\d{2}:\d{2}", low):
                return True
            return False

        def _normalize_thinking_text(text: str) -> str:
            body = str(text or "")
            if not body:
                return ""
            body = body.replace("\\n", "\n").replace("/n", "\n")
            body = body.replace("\r", "")
            body = body.replace("**", "")
            body = re.sub(r"[ \t]{2,}", " ", body)
            body = re.sub(r"\n{3,}", "\n\n", body)
            return body.strip()

        def _append_thinking_delta(delta: str):
            nonlocal thinking_buffer
            raw = str(delta or "")
            if not raw:
                return
            # Bỏ các delta chỉ là noise runtime.
            if _is_system_noise(raw):
                return
            thinking_buffer += raw
            if len(thinking_buffer) > 5000:
                thinking_buffer = thinking_buffer[-5000:]

        def _flush_thinking(force: bool = False):
            nonlocal last_stream_sent, last_stream_text
            if not draft_id:
                return
            now = time.monotonic()
            if not force and now - last_stream_sent < self.STREAM_THROTTLE_SEC:
                return
            text = "🤔 AI đang suy nghĩ câu trả lời..."
            normalized = _normalize_thinking_text(thinking_buffer)
            if normalized:
                lines = [ln.strip() for ln in normalized.splitlines() if ln.strip()]
                if lines:
                    snippet = "\n".join(lines[-3:])
                else:
                    snippet = normalized[-280:]
                if len(snippet) > 320:
                    snippet = "..." + snippet[-317:]
                text += "\n" + snippet
            if text == last_stream_text and not force:
                return
            try:
                transport.edit_message(chat_id, draft_id, text)
                last_stream_sent = now
                last_stream_text = text
                self._append_stream_preview_log(
                    {
                        "phase": "preview_sent",
                        "chat_id": str(chat_id),
                        "draft_message_id": int(draft_id),
                        "preview_text": text,
                        "thinking_snippet": text.replace("🤔 AI đang suy nghĩ câu trả lời...", "").strip(),
                        "thinking_buffer_tail": _normalize_thinking_text(thinking_buffer)[-1000:],
                        **trace,
                    }
                )
            except Exception:
                return

        def on_runtime_event(evt: dict):
            nonlocal runtime_event_stream_active
            try:
                kind = str((evt or {}).get("kind") or "").strip().lower()
                text = str((evt or {}).get("text") or "").strip()
                raw = (evt or {}).get("raw") or {}
                method = str(raw.get("method") or "").strip()
                params = raw.get("params") or {}
                delta_raw = str(params.get("delta") or "")

                self._append_runtime_debug_log(
                    {
                        "phase": "runtime_event",
                        "kind": kind,
                        "text": text,
                        "raw": (evt or {}).get("raw"),
                        **trace,
                    }
                )
                if not text:
                    return

                # Chỉ lấy stream từ item/* để tránh nhân bản 3 lần (item + codex/event + wrapper).
                if method and not method.startswith("item/"):
                    return
                runtime_event_stream_active = True

                if kind == "reasoning":
                    _append_thinking_delta(delta_raw or text)
                    _flush_thinking()
                    return
                if kind == "assistant_delta":
                    _append_thinking_delta(delta_raw or text)
                    _flush_thinking()
                    return
                if kind == "tool":
                    tool_line = str(text or "").strip()
                    if tool_line and not _is_system_noise(tool_line):
                        _append_thinking_delta("\n" + tool_line)
                        _flush_thinking()
            except Exception as e:
                logger.warning(f"on_runtime_event parse warning: {e}")

        def on_chunk(chunk: str):
            nonlocal chunk_index
            chunk_index += 1
            output_chunks.append(chunk)
            self._append_runtime_debug_log(
                {
                    "phase": "chunk",
                    "chunk_index": chunk_index,
                    "text": str(chunk or ""),
                    **trace,
                }
            )
            # Khi đã có luồng runtime_event chuẩn, bỏ parse chunk để tránh ghép trùng.
            if runtime_event_stream_active:
                return
            raw = str(chunk or "")
            if "thinking" not in raw.lower():
                return
            for line in raw.splitlines():
                stripped = line.strip()
                if stripped.lower() == "thinking":
                    continue
                _append_thinking_delta(stripped)
            _flush_thinking()

        result = self._codex_bridge.stream_reply(
            prompt=prompt,
            on_chunk=on_chunk,
            runtime_event_callback=on_runtime_event,
            timeout_sec=600,
        )
        self._append_runtime_debug_log(
            {
                "phase": "result",
                "success": bool(result.get("success")),
                "mode": str(result.get("mode") or ""),
                "message": str(result.get("message") or ""),
                "output_preview": str(result.get("output") or "")[:2000],
                **trace,
            }
        )
        final_text = self._extract_final_response(result.get("output") or "")
        if not result.get("success"):
            msg = str(result.get("message") or "").strip()
            if final_text:
                final_text = f"{final_text}\n\n[Lỗi OmniMind]: {msg}"
            else:
                final_text = f"Không thể xử lý bằng OmniMind: {msg or 'Lỗi không xác định.'}"

        if not final_text:
            final_text = self._extract_final_response("".join(output_chunks))
        if not final_text:
            final_text = "OmniMind không trả nội dung."
        final_text = self._dedupe_response_text(final_text) or "OmniMind không trả nội dung."
        self._append_runtime_debug_log(
            {
                "phase": "final_text",
                "final_text": final_text,
                **trace,
            }
        )
        return final_text, draft_id

    def _handle_text_message(
        self,
        transport: TelegramStreamTransport,
        chat_id: str,
        update_id: int,
        message_id: int,
        user_text: str,
    ):
        user_external_id = f"tg:{update_id}:user"
        assistant_external_id = f"tg:{update_id}:assistant"

        try:
            prompt, context = self._build_codex_prompt(user_text)
            raw_response, draft_id = self._stream_codex_response(
                transport,
                chat_id,
                prompt,
                log_context={
                    "telegram_update_id": update_id,
                    "telegram_message_id": message_id,
                },
            )
            cleaned_response, send_directives = self._extract_send_document_directives(raw_response)
            response, action_directives = self._extract_runtime_action_directives(cleaned_response)
            response = response or "OmniMind không trả nội dung."

            self._finalize_assistant_message(
                transport=transport,
                chat_id=chat_id,
                draft_id=draft_id,
                final_text=response,
            )

            action_runtime_result = self._execute_runtime_action_directives(
                transport=transport,
                chat_id=chat_id,
                directives=action_directives,
            )
            action_notes = action_runtime_result.get("notes") or []
            runtime_artifact_paths = action_runtime_result.get("artifact_paths") or []

            assistant_memory_text = response
            if action_notes:
                assistant_memory_text = (
                    response
                    + "\n\n[Runtime action logs]\n"
                    + "\n".join([f"- {x}" for x in action_notes[:8]])
                )

            self._skill_manager.record_runtime_interaction(
                user_text=user_text,
                assistant_text=assistant_memory_text,
                source="telegram",
                metadata={
                    "telegram_update_id": update_id,
                    "telegram_message_id": message_id,
                    "context_char_used": (context or {}).get("context_char_used", 0),
                },
                user_external_id=user_external_id,
                assistant_external_id=assistant_external_id,
            )

            recent_paths = self._extract_paths_from_recent_messages((context or {}).get("recent_messages") or [])
            for p in runtime_artifact_paths:
                if p and p not in recent_paths:
                    recent_paths.append(p)

            # Runtime chỉ gửi file khi OmniMind trả về directive tool hợp lệ.
            if send_directives:
                candidates: list[dict] = []
                for item in send_directives:
                    raw_path = str(item.get("path") or "").strip()
                    resolved_path = self._resolve_directive_path(raw_path, recent_paths)
                    candidates.append(
                        {
                            "path": resolved_path or raw_path,
                            "caption": str(item.get("caption") or "").strip(),
                        }
                    )
                # Fallback: thêm artifact vừa tạo từ runtime action nếu directive path chưa rõ.
                for artifact in runtime_artifact_paths:
                    if not artifact:
                        continue
                    candidates.append({"path": artifact, "caption": ""})
                sent = self._try_send_document_from_candidates(
                    transport=transport,
                    chat_id=chat_id,
                    requested_name="",
                    candidates=candidates,
                )
                if not sent:
                    transport.send_text_chunks(
                        chat_id,
                        "Không gửi được file vì chỉ thị gửi file chưa trỏ tới đường dẫn hợp lệ. "
                        "Hãy yêu cầu lại kèm tên file hoặc đường dẫn rõ ràng.",
                    )
        except Exception as e:
            logger.exception("Handle Telegram message failed")
            try:
                state = _StreamState()
                transport.update_stream(chat_id, state, f"Lỗi xử lý yêu cầu: {str(e)[:200]}")
            except Exception:
                pass


_GLOBAL_BOT_SERVICE: Optional[TelegramBotService] = None
_GLOBAL_BOT_LOCK = threading.Lock()


def get_global_telegram_bot_service() -> TelegramBotService:
    global _GLOBAL_BOT_SERVICE
    with _GLOBAL_BOT_LOCK:
        if _GLOBAL_BOT_SERVICE is None:
            _GLOBAL_BOT_SERVICE = TelegramBotService()
        return _GLOBAL_BOT_SERVICE


def stop_global_telegram_bot_service():
    try:
        get_global_telegram_bot_service().stop()
    except Exception:
        pass
