from __future__ import annotations

import ast
import json
import logging
import re
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path
from queue import Empty, Queue
from typing import Optional

from engine.codex_runtime_bridge import CodexRuntimeBridge
from engine.config_manager import ConfigManager
from engine.openzca_manager import OpenZcaManager
from engine.process_lock import InterProcessFileLock
from engine.skill_manager import SkillManager
from engine.zalo_memory_manager import ZaloMemoryManager
from engine.zalo_models import ZaloInboundEvent
from engine.zalo_prompt_builder import ZaloPromptBuilder

logger = logging.getLogger(__name__)


class ZaloBotService:
    MAX_CHUNK_SIZE = 1800
    MAX_RESTARTS = 3
    RESTART_DELAY_SEC = 2.0
    DEDUPE_TTL_SEC = 15 * 60
    TYPING_INTERVAL_SEC = 4.0
    DISPATCH_POLL_SEC = 0.25
    CLEANUP_INTERVAL_SEC = 30 * 60
    OUTBOUND_HEADER_RE = re.compile(r"^(trả lời|tra loi|response|reply|trợ lý(?:\s+\w+){0,3}|tro ly(?:\s+\w+){0,3})$", re.IGNORECASE)

    def __init__(self):
        self._lock = threading.RLock()
        self._thread_lock = threading.RLock()
        self._stop_event = threading.Event()
        self._listener_thread: Optional[threading.Thread] = None
        self._consumer_thread: Optional[threading.Thread] = None
        self._dispatch_thread: Optional[threading.Thread] = None
        self._cleanup_thread: Optional[threading.Thread] = None
        self._proc: Optional[subprocess.Popen] = None
        self._queue: Queue = Queue()
        self._dedupe_cache: dict[str, float] = {}
        self._thread_pending: dict[str, list[ZaloInboundEvent]] = {}
        self._thread_due_at: dict[str, float] = {}
        self._thread_active: set[str] = set()
        self._thread_workers: dict[str, threading.Thread] = {}
        self._manager = OpenZcaManager()
        self._skill_manager = SkillManager()
        self._zalo_memory = ZaloMemoryManager()
        self._codex_bridge = CodexRuntimeBridge()
        self._prompt_builder = ZaloPromptBuilder()
        self._self_user_id = str(ConfigManager.get("zalo_self_user_id", "")).strip()
        self._restart_count = 0
        self._listener_lock = InterProcessFileLock(Path(self._manager.get_app_data_root()) / "zalo_listener_omnimind.lock")

    def is_running(self) -> bool:
        th = self._listener_thread
        return bool(th and th.is_alive())

    def get_status(self) -> dict:
        listener = ConfigManager.get_zalo_listener_status()
        bot_cfg = ConfigManager.get_zalo_bot_config()
        return {
            **listener,
            **bot_cfg,
            "running": self.is_running(),
            "self_user_id": self._self_user_id,
        }

    def start(self) -> dict:
        with self._lock:
            if self.is_running():
                return {"success": True, "message": "Bot Zalo đã chạy."}

            runtime = self._manager.inspect_runtime()
            if not runtime.get("openzca_ready"):
                return {"success": False, "message": runtime.get("message", "Zalo chưa sẵn sàng.")}

            auth = self._manager.run_auth_status()
            if not auth.get("logged_in"):
                return {"success": False, "message": auth.get("message", "Chưa đăng nhập Zalo.")}

            if not self._listener_lock.acquire():
                owner_pid = self._listener_lock.read_owner_pid()
                msg = (
                    "Bộ lắng nghe Zalo đang chạy ở một phiên OmniMind khác"
                    + (f" (PID {owner_pid})" if owner_pid else "")
                    + "."
                )
                return {"success": False, "message": msg}

            self._self_user_id = str(auth.get("self_user_id") or self._self_user_id).strip()
            self._stop_event.clear()
            self._restart_count = 0
            self._queue = Queue()
            self._thread_pending = {}
            self._thread_due_at = {}
            self._thread_active = set()
            self._thread_workers = {}
            ConfigManager.set_zalo_listener_status(
                "starting",
                last_error="",
                last_started_at=self._utc_now_iso(),
                restart_count=self._restart_count,
            )
            try:
                self._consumer_thread = threading.Thread(target=self._consume_loop, name="omnimind-zalo-consumer", daemon=True)
                self._consumer_thread.start()
                self._dispatch_thread = threading.Thread(target=self._dispatch_loop, name="omnimind-zalo-dispatch", daemon=True)
                self._dispatch_thread.start()
                self._cleanup_thread = threading.Thread(target=self._cleanup_loop, name="omnimind-zalo-cleanup", daemon=True)
                self._cleanup_thread.start()
                self._listener_thread = threading.Thread(target=self._listen_loop, name="omnimind-zalo-listener", daemon=True)
                self._listener_thread.start()
            except Exception as e:
                self._listener_lock.release()
                ConfigManager.set_zalo_listener_status("crashed", last_error=str(e)[:220], last_stopped_at=self._utc_now_iso())
                return {"success": False, "message": f"Không thể khởi chạy bot Zalo: {str(e)[:180]}"}

            ConfigManager.set_zalo_bot_config(enabled=True)
            return {"success": True, "message": "Đã bật bot Zalo."}

    def stop(self, persist_disabled: bool = True) -> dict:
        with self._lock:
            self._stop_event.set()
            proc = self._proc
        if proc is not None:
            try:
                proc.terminate()
                proc.wait(timeout=2)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
        for th in (self._listener_thread, self._consumer_thread, self._dispatch_thread, self._cleanup_thread):
            if th:
                th.join(timeout=3)
        with self._thread_lock:
            workers = list(self._thread_workers.values())
        for th in workers:
            if th:
                th.join(timeout=1.5)
        with self._lock:
            self._listener_thread = None
            self._consumer_thread = None
            self._dispatch_thread = None
            self._cleanup_thread = None
            self._proc = None
            self._queue = Queue()
            self._listener_lock.release()
        with self._thread_lock:
            self._thread_pending = {}
            self._thread_due_at = {}
            self._thread_active = set()
            self._thread_workers = {}
        ConfigManager.set_zalo_listener_status("stopped", last_error="", last_stopped_at=self._utc_now_iso())
        if persist_disabled:
            ConfigManager.set_zalo_bot_config(enabled=False)
        return {"success": True, "message": "Đã tắt bot Zalo."}

    def restart(self) -> dict:
        self.stop(persist_disabled=False)
        time.sleep(0.2)
        return self.start()

    def refresh_group_catalog(self) -> dict:
        return self._manager.list_groups()

    @staticmethod
    def _utc_now_iso() -> str:
        return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"

    def _listen_loop(self):
        while not self._stop_event.is_set():
            should_restart = self._spawn_and_read_listener()
            if not should_restart:
                break
            self._restart_count += 1
            ConfigManager.set_zalo_listener_status(
                "restarting",
                last_error="Listener Zalo bị ngắt, đang khởi động lại...",
                restart_count=self._restart_count,
            )
            if self._restart_count > self.MAX_RESTARTS:
                ConfigManager.set_zalo_listener_status(
                    "crashed",
                    last_error="Listener Zalo bị ngắt quá nhiều lần.",
                    last_stopped_at=self._utc_now_iso(),
                    restart_count=self._restart_count,
                )
                break
            time.sleep(self.RESTART_DELAY_SEC)

        with self._lock:
            self._proc = None
        if self._stop_event.is_set():
            ConfigManager.set_zalo_listener_status("stopped", last_error="", last_stopped_at=self._utc_now_iso())
        self._listener_lock.release()

    def _spawn_and_read_listener(self) -> bool:
        cmd = self._manager.build_listen_command()
        env = self._manager.build_openzca_env()
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                cwd=self._manager.get_openzca_runtime_root(),
                env=env,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                **self._manager._windows_hidden_subprocess_kwargs(),
            )
        except Exception as e:
            ConfigManager.set_zalo_listener_status("crashed", last_error=f"Không thể khởi chạy listener: {str(e)[:220]}")
            return False

        with self._lock:
            self._proc = proc
        ConfigManager.set_zalo_listener_status(
            "running",
            last_error="",
            last_started_at=self._utc_now_iso(),
            restart_count=self._restart_count,
        )
        logger.info("Zalo listener started.")

        while not self._stop_event.is_set():
            line = proc.stdout.readline() if proc.stdout else ""
            if line == "" and proc.poll() is not None:
                break
            if not line:
                time.sleep(0.05)
                continue
            self._handle_listener_line(line.rstrip("\n"))

        if self._stop_event.is_set():
            try:
                proc.terminate()
            except Exception:
                pass
            return False
        return True

    def _handle_listener_line(self, line: str):
        text = str(line or "").strip()
        if not text:
            return
        logger.info(f"[ZaloListen] {text[:600]}")
        payload = self._parse_raw_line(text)
        if not payload:
            return
        if str(payload.get("kind") or "").strip().lower() == "lifecycle":
            event_name = str(payload.get("event") or "").strip().lower()
            if event_name == "connected":
                ConfigManager.set_zalo_listener_status("running", last_error="")
            return
        event = ZaloInboundEvent.from_raw_payload(payload)
        if not event:
            return
        self._queue.put(event)

    def _parse_raw_line(self, text: str) -> dict | None:
        body = str(text or "").strip()
        if not body:
            return None
        if body.startswith("b'") or body.startswith('b"'):
            try:
                decoded = ast.literal_eval(body)
                if isinstance(decoded, (bytes, bytearray)):
                    body = decoded.decode("utf-8", "replace").strip()
            except Exception:
                return None
        if not body.startswith("{"):
            return None
        try:
            return json.loads(body)
        except Exception:
            return None

    def _consume_loop(self):
        while not self._stop_event.is_set():
            try:
                item = self._queue.get(timeout=0.5)
            except Empty:
                self._prune_dedupe_cache()
                continue
            try:
                self._buffer_inbound_event(item)
            except Exception as e:
                logger.exception("Zalo inbound handler failed")
                ConfigManager.set_zalo_listener_status("running", last_error=str(e)[:220])

    def _dispatch_loop(self):
        while not self._stop_event.is_set():
            due_threads: list[str] = []
            now_ts = time.time()
            with self._thread_lock:
                for thread_id, due_at in list(self._thread_due_at.items()):
                    if due_at <= now_ts and thread_id not in self._thread_active and self._thread_pending.get(thread_id):
                        self._thread_active.add(thread_id)
                        due_threads.append(thread_id)
            for thread_id in due_threads:
                worker = threading.Thread(
                    target=self._process_thread_bundle,
                    args=(thread_id,),
                    name=f"omnimind-zalo-thread-{thread_id[-6:]}",
                    daemon=True,
                )
                with self._thread_lock:
                    self._thread_workers[thread_id] = worker
                worker.start()
            self._prune_dead_thread_workers()
            time.sleep(self.DISPATCH_POLL_SEC)

    def _cleanup_loop(self):
        while not self._stop_event.is_set():
            try:
                result = self._zalo_memory.cleanup_expired_data(
                    raw_retention_days=ConfigManager.get_zalo_raw_retention_days(),
                    summary_retention_days=ConfigManager.get_zalo_summary_retention_days(),
                    delete_raw_only_when_summarized=ConfigManager.get_zalo_delete_raw_only_when_summarized(),
                )
                if int(result.get("deleted_raw_messages", 0) or 0) or int(result.get("deleted_summaries", 0) or 0):
                    self._append_jsonl("zalo_listener_runtime.jsonl", {"kind": "cleanup", **result})
            except Exception:
                logger.exception("Zalo cleanup loop failed")
            if self._stop_event.wait(self.CLEANUP_INTERVAL_SEC):
                break

    def _prune_dedupe_cache(self):
        now = time.time()
        stale_keys = [key for key, ts in self._dedupe_cache.items() if (now - ts) > self.DEDUPE_TTL_SEC]
        for key in stale_keys:
            self._dedupe_cache.pop(key, None)

    def _prune_dead_thread_workers(self):
        with self._thread_lock:
            stale = [thread_id for thread_id, worker in self._thread_workers.items() if not worker or not worker.is_alive()]
            for thread_id in stale:
                self._thread_workers.pop(thread_id, None)

    def _dedupe_key(self, event: ZaloInboundEvent) -> str:
        if event.message_id:
            return f"{event.thread_id}:{event.message_id}"
        return f"{event.thread_id}:{event.sender_id}:{event.timestamp}:{event.content}"

    def _should_process_event(self, event: ZaloInboundEvent) -> tuple[bool, str]:
        cfg = ConfigManager.get_zalo_bot_config()
        if str(event.sender_id) == str(self._self_user_id):
            return False, "self_message"
        if not cfg.get("enabled"):
            return False, "bot_disabled"
        if not cfg.get("auto_reply"):
            return False, "auto_reply_off"
        if event.is_group:
            if not event.mentions_user(self._self_user_id):
                return False, "no_mention"
            if cfg.get("group_scope") == "selected":
                allowlist = set(cfg.get("group_allowlist") or [])
                if event.thread_id not in allowlist:
                    return False, "group_not_allowed"
        return True, ""

    def _buffer_inbound_event(self, event: ZaloInboundEvent):
        dedupe_key = self._dedupe_key(event)
        self._self_user_id = str(ConfigManager.get("zalo_self_user_id", self._self_user_id)).strip()
        if dedupe_key in self._dedupe_cache:
            logger.info("Skip Zalo message: duplicate")
            return
        self._dedupe_cache[dedupe_key] = time.time()
        if str(event.sender_id) == str(self._self_user_id):
            self._store_self_authored_event(event)
            logger.info("Recorded Zalo self-authored message for context only.")
            if event.is_group:
                self._zalo_memory.refresh_thread_summary(event.thread_id)
            return
        self._store_inbound_event(event)
        should_process, reason = self._should_process_event(event)
        if not should_process:
            logger.info(f"Skip Zalo reply: {reason}")
            if event.is_group:
                self._zalo_memory.refresh_thread_summary(event.thread_id)
            return
        debounce_ms = ConfigManager.get_zalo_thread_debounce_ms()
        if event.is_direct:
            debounce_ms = min(debounce_ms, 900)
        else:
            debounce_ms = max(1000, debounce_ms)
        due_at = time.time() + (max(500, debounce_ms) / 1000.0)
        should_send_typing_now = False
        with self._thread_lock:
            was_idle = not self._thread_pending.get(event.thread_id) and event.thread_id not in self._thread_active
            bucket = self._thread_pending.setdefault(event.thread_id, [])
            bucket.append(event)
            self._thread_due_at[event.thread_id] = due_at
            should_send_typing_now = was_idle
        if should_send_typing_now:
            try:
                self._manager.send_typing(event.thread_id, is_group=event.is_group)
            except Exception:
                logger.debug("Initial Zalo typing ping failed", exc_info=True)
        self._append_jsonl(
            "zalo_inbound_events.jsonl",
            {
                "kind": "buffered",
                "thread_id": event.thread_id,
                "chat_type": event.chat_type,
                "message_id": event.message_id,
                "sender_id": event.sender_id,
                "timestamp": event.timestamp,
                "content": event.content,
            },
        )

    def _process_thread_bundle(self, thread_id: str):
        base_event: ZaloInboundEvent | None = None
        typing_stop: threading.Event | None = None
        typing_thread: threading.Thread | None = None
        try:
            with self._thread_lock:
                events = list(self._thread_pending.pop(thread_id, []))
                self._thread_due_at.pop(thread_id, None)
            if not events:
                return
            base_event = events[0]
            typing_stop = threading.Event()
            typing_thread = threading.Thread(
                target=self._typing_heartbeat_loop,
                args=(base_event.thread_id, base_event.is_group, typing_stop),
                name="omnimind-zalo-typing",
                daemon=True,
            )
            typing_thread.start()
            self._ensure_thread_bootstrap(base_event)
            bundle_text = self._build_bundle_text(events)
            bundle_size = len(events)
            zalo_cfg = ConfigManager.get_zalo_bot_config()
            thread_context = self._zalo_memory.build_thread_context(
                thread_id=base_event.thread_id,
                message_limit=32,
                facts_limit=6,
                summary_limit=2,
                char_budget=12000,
            )
            prompt, context_meta = self._prompt_builder.build_prompt(
                thread_context=thread_context,
                bundle_text=bundle_text,
                bundle_size=bundle_size,
                thread_id=base_event.thread_id,
                chat_type=base_event.chat_type,
                zalo_principles=str(zalo_cfg.get("prompt_principles") or "").strip(),
            )
            result = self._codex_bridge.stream_reply(
                prompt=prompt,
                timeout_sec=600,
                model_override=str(zalo_cfg.get("model") or "").strip(),
            )
            final_text = self._sanitize_outbound_text(self._extract_final_text(result)) or "Mình chưa có nội dung phù hợp để gửi."
            self._stop_typing_loop(typing_stop, typing_thread)
            typing_stop = None
            typing_thread = None
            send_result = self._send_response(base_event, final_text)
            if not send_result.get("success"):
                raise RuntimeError(str(send_result.get("message") or "Gửi phản hồi Zalo thất bại."))
            self._store_outbound_message(base_event, final_text)
            self._zalo_memory.refresh_thread_summary(base_event.thread_id)
            user_external_id = f"zalo:{base_event.thread_id}:{base_event.message_id or base_event.timestamp}:user"
            assistant_external_id = f"zalo:{base_event.thread_id}:{base_event.message_id or base_event.timestamp}:assistant"
            self._skill_manager.record_runtime_interaction(
                user_text=bundle_text,
                assistant_text=final_text,
                source="zalo",
                metadata={
                    "thread_id": base_event.thread_id,
                    "chat_type": base_event.chat_type,
                    "message_id": base_event.message_id,
                    "bundle_size": bundle_size,
                    "context_char_used": int(context_meta.get("context_char_used", 0) or 0),
                },
                user_external_id=user_external_id,
                assistant_external_id=assistant_external_id,
            )
            self._append_jsonl(
                "zalo_outbound_events.jsonl",
                {
                    "thread_id": base_event.thread_id,
                    "chat_type": base_event.chat_type,
                    "bundle_size": bundle_size,
                    "reply_preview": final_text[:500],
                    "send_status": send_result,
                },
            )
        except Exception as e:
            logger.exception("Zalo thread bundle processing failed")
            ConfigManager.set_zalo_listener_status("running", last_error=str(e)[:220])
            self._append_jsonl(
                "zalo_dead_letter.jsonl",
                {"kind": "thread_bundle_failed", "thread_id": thread_id, "message": str(e)[:500]},
            )
        finally:
            self._stop_typing_loop(typing_stop, typing_thread)
            with self._thread_lock:
                self._thread_active.discard(thread_id)
                self._thread_workers.pop(thread_id, None)
                if self._thread_pending.get(thread_id) and thread_id not in self._thread_due_at:
                    self._thread_due_at[thread_id] = time.time() + (ConfigManager.get_zalo_thread_debounce_ms() / 1000.0)

    def _ensure_thread_bootstrap(self, event: ZaloInboundEvent):
        thread = self._zalo_memory.get_thread(event.thread_id)
        last_bootstrap = str((thread or {}).get("last_bootstrap_at") or "").strip()
        if bool(int((thread or {}).get("bootstrap_done", 0) or 0)):
            return
        if last_bootstrap:
            try:
                ts = datetime.fromisoformat(last_bootstrap.replace("Z", "+00:00"))
                if (datetime.now(ts.tzinfo) - ts).total_seconds() < 300:
                    return
            except Exception:
                pass
        self._zalo_memory.upsert_thread(
            thread_id=event.thread_id,
            chat_type=event.chat_type,
            last_bootstrap_at=self._utc_now_iso(),
        )
        bootstrap_count = ConfigManager.get_zalo_recent_bootstrap_count()
        if event.is_group:
            bootstrap_count = max(20, int(bootstrap_count or 0))
        res = self._manager.get_recent_messages(
            event.thread_id,
            is_group=event.is_group,
            count=bootstrap_count,
            timeout_sec=5,
        )
        if res.get("success"):
            imported = self._zalo_memory.import_recent_messages(
                thread_id=event.thread_id,
                chat_type=event.chat_type,
                messages=res.get("messages") or [],
                self_user_id=self._self_user_id,
            )
            self._append_jsonl(
                "zalo_listener_runtime.jsonl",
                {"kind": "bootstrap_history", "thread_id": event.thread_id, "imported_count": imported},
            )
            return
        self._append_jsonl(
            "zalo_dead_letter.jsonl",
            {
                "kind": "bootstrap_history_failed",
                "thread_id": event.thread_id,
                "chat_type": event.chat_type,
                "message": str(res.get("message") or ""),
            },
        )

    def _typing_heartbeat_loop(self, thread_id: str, is_group: bool, stop_event: threading.Event):
        while not stop_event.is_set():
            try:
                self._manager.send_typing(thread_id, is_group=is_group)
            except Exception:
                logger.debug("Zalo typing ping failed", exc_info=True)
            if stop_event.wait(self.TYPING_INTERVAL_SEC):
                break

    @staticmethod
    def _stop_typing_loop(stop_event: threading.Event | None, typing_thread: threading.Thread | None):
        try:
            if stop_event:
                stop_event.set()
            if typing_thread:
                typing_thread.join(timeout=0.5)
        except Exception:
            pass

    @staticmethod
    def _extract_final_text(result: dict) -> str:
        output = str((result or {}).get("output") or "").strip()
        message = str((result or {}).get("message") or "").strip()
        if not result.get("success"):
            if output:
                return f"{output}\n\n[Mình chưa xử lý trọn vẹn]: {message or 'Lỗi không xác định.'}".strip()
            return f"Mình chưa xử lý được yêu cầu này: {message or 'Lỗi không xác định.'}"
        body = output or message
        body = body.strip()
        if not body:
            return ""
        if len(body) % 2 == 0:
            half = len(body) // 2
            left = body[:half].strip()
            right = body[half:].strip()
            if left and left == right:
                body = left
        return body

    @classmethod
    def _sanitize_outbound_text(cls, text: str) -> str:
        body = str(text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
        if not body:
            return ""
        body = body.replace("**", "").replace("__", "")
        cleaned_lines: list[str] = []
        for idx, raw_line in enumerate(body.splitlines()):
            line = str(raw_line or "").strip()
            if not line:
                if cleaned_lines and cleaned_lines[-1] != "":
                    cleaned_lines.append("")
                continue
            line = re.sub(r"^\s*[>#]+\s*", "", line)
            line = re.sub(r"^\s*\*+\s*", "", line)
            line = re.sub(r"^\s*\d+[.)]\s+", "", line)
            line = re.sub(r"^\s*[-–—]+\s+", "", line)
            line = re.sub(r"\s{2,}", " ", line).strip()
            compact = re.sub(r"[^0-9A-Za-zÀ-ỹ]+", " ", line, flags=re.UNICODE).strip().lower()
            if idx == 0 and compact and cls.OUTBOUND_HEADER_RE.match(compact):
                continue
            if line:
                cleaned_lines.append(line)
        while cleaned_lines and cleaned_lines[0] == "":
            cleaned_lines.pop(0)
        while cleaned_lines and cleaned_lines[-1] == "":
            cleaned_lines.pop()
        if not cleaned_lines:
            return ""
        if len(cleaned_lines) <= 2:
            return " ".join(part for part in cleaned_lines if part).strip()
        rows: list[str] = []
        previous_blank = False
        for line in cleaned_lines:
            if not line:
                if rows and not previous_blank:
                    rows.append("")
                previous_blank = True
                continue
            rows.append(line)
            previous_blank = False
        return "\n".join(rows).strip()

    def _build_bundle_text(self, events: list[ZaloInboundEvent]) -> str:
        if not events:
            return ""
        if len(events) == 1:
            return str(events[0].content or "").strip()
        rows = [f"Người dùng vừa gửi liên tiếp {len(events)} tin nhắn trên Zalo:"]
        for idx, event in enumerate(events, start=1):
            text = str(event.content or "").strip()
            if text:
                rows.append(f"{idx}. {text}")
        return "\n".join(rows).strip()

    def _store_inbound_event(self, event: ZaloInboundEvent):
        self._zalo_memory.upsert_thread(thread_id=event.thread_id, chat_type=event.chat_type, bootstrap_done=None)
        self._zalo_memory.append_message(
            thread_id=event.thread_id,
            chat_type=event.chat_type,
            sender_id=event.sender_id,
            content=event.content,
            direction="inbound",
            message_id=event.message_id,
            mentions=event.mentions,
            raw_payload=event.raw_payload,
            timestamp=event.timestamp,
        )

    def _store_outbound_message(self, event: ZaloInboundEvent, text: str):
        self._zalo_memory.append_message(
            thread_id=event.thread_id,
            chat_type=event.chat_type,
            sender_id=self._self_user_id or "self",
            content=str(text or "").strip(),
            direction="outbound",
            message_id=f"reply:{event.message_id or event.timestamp or time.time()}",
            mentions=[],
            raw_payload={},
            timestamp=self._utc_now_iso(),
        )

    def _store_self_authored_event(self, event: ZaloInboundEvent):
        self._zalo_memory.upsert_thread(thread_id=event.thread_id, chat_type=event.chat_type, bootstrap_done=None)
        self._zalo_memory.append_message(
            thread_id=event.thread_id,
            chat_type=event.chat_type,
            sender_id=self._self_user_id or event.sender_id or "self",
            content=event.content,
            direction="outbound",
            message_id=event.message_id,
            mentions=event.mentions,
            raw_payload=event.raw_payload,
            timestamp=event.timestamp,
        )

    def _append_jsonl(self, filename: str, payload: dict):
        try:
            log_dir = Path(self._manager.get_openzca_logs_dir())
            log_dir.mkdir(parents=True, exist_ok=True)
            target = log_dir / str(filename or "zalo_runtime.jsonl")
            with target.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(payload or {}, ensure_ascii=False) + "\n")
        except Exception:
            logger.debug("Cannot append Zalo JSONL log", exc_info=True)

    def _send_response(self, event: ZaloInboundEvent, text: str) -> dict:
        body = str(text or "").strip()
        if not body:
            return {"success": False, "message": "Nội dung phản hồi rỗng.", "results": []}
        chunks = [body[i : i + self.MAX_CHUNK_SIZE] for i in range(0, len(body), self.MAX_CHUNK_SIZE)] or [body]
        results = []
        for chunk in chunks:
            last_result = None
            for attempt in range(2):
                last_result = self._manager.send_text_message(event.thread_id, chunk, is_group=event.is_group)
                if last_result.get("success"):
                    break
                if attempt == 0:
                    time.sleep(0.5)
            results.append(
                {
                    "success": bool((last_result or {}).get("success")),
                    "message": str((last_result or {}).get("message") or "").strip(),
                    "chunk_preview": chunk[:120],
                }
            )
            if not (last_result or {}).get("success"):
                self._append_jsonl(
                    "zalo_dead_letter.jsonl",
                    {
                        "kind": "send_response_failed",
                        "thread_id": event.thread_id,
                        "chat_type": event.chat_type,
                        "message_id": event.message_id,
                        "chunk_preview": chunk[:300],
                        "send_result": last_result or {},
                    },
                )
                return {
                    "success": False,
                    "message": str((last_result or {}).get("message") or "Không thể gửi phản hồi Zalo."),
                    "results": results,
                }
            time.sleep(0.35)
        return {"success": True, "message": "Đã gửi phản hồi Zalo.", "results": results}


_GLOBAL_ZALO_BOT_SERVICE: Optional[ZaloBotService] = None
_GLOBAL_ZALO_BOT_LOCK = threading.Lock()


def get_global_zalo_bot_service() -> ZaloBotService:
    global _GLOBAL_ZALO_BOT_SERVICE
    with _GLOBAL_ZALO_BOT_LOCK:
        if _GLOBAL_ZALO_BOT_SERVICE is None:
            _GLOBAL_ZALO_BOT_SERVICE = ZaloBotService()
        return _GLOBAL_ZALO_BOT_SERVICE


def stop_global_zalo_bot_service():
    global _GLOBAL_ZALO_BOT_SERVICE
    with _GLOBAL_ZALO_BOT_LOCK:
        service = _GLOBAL_ZALO_BOT_SERVICE
    if service:
        try:
            service.stop(persist_disabled=False)
        except Exception:
            pass
