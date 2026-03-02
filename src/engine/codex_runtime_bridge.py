import logging
import json
import os
import re
import subprocess
import time
import threading
from pathlib import Path
from queue import Empty, Queue
from typing import Callable, Optional

from engine.config_manager import ConfigManager
from engine.environment_manager import EnvironmentManager

logger = logging.getLogger(__name__)

_ANSI_ESCAPE_RE = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")


class CodexRuntimeBridge:
    """
    Adapter chạy Codex CLI theo kiểu subprocess streaming:
    - Nhận prompt đã được inject context.
    - Stream output qua callback.
    - Trả final output để persist vào memory.
    """

    def __init__(self, env_manager: Optional[EnvironmentManager] = None):
        self.env_manager = env_manager or EnvironmentManager()
        self._request_id = 1

    @staticmethod
    def _clean_chunk(text: str) -> str:
        body = _ANSI_ESCAPE_RE.sub("", str(text or ""))
        return body.replace("\r\n", "\n").replace("\r", "\n")

    def _resolve_workspace(self) -> str:
        configured = str(ConfigManager.get_workspace_path() or "").strip()
        if configured and Path(configured).expanduser().is_dir():
            return str(Path(configured).expanduser())
        return os.getcwd()

    def _build_command(self, prompt: str) -> list[str]:
        codex_cmd = self.env_manager.resolve_codex_command()
        # Ưu tiên app-server để stream event chuẩn; giữ fallback exec nếu app-server lỗi.
        if str(ConfigManager.get("codex_runtime_mode", "app-server")).strip().lower() == "exec":
            return [codex_cmd, "exec", str(prompt or "")]
        return [codex_cmd, "app-server", "--listen", "stdio://"]

    def _build_exec_command(self, prompt: str) -> list[str]:
        codex_cmd = self.env_manager.resolve_codex_command()
        return [codex_cmd, "exec", str(prompt or "")]

    @staticmethod
    def _pump_stream(stream, queue: Queue, tag: str):
        try:
            for line in iter(stream.readline, ""):
                queue.put((tag, line))
        finally:
            queue.put((tag, None))

    def _next_request_id(self) -> int:
        rid = self._request_id
        self._request_id += 1
        return rid

    @staticmethod
    def _jsonrpc_request(method: str, req_id: int, params):
        return {"jsonrpc": "2.0", "id": req_id, "method": method, "params": params}

    @staticmethod
    def _jsonrpc_notification(method: str, params=None):
        payload = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            payload["params"] = params
        return payload

    @staticmethod
    def _send_json(proc: subprocess.Popen, payload: dict):
        raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        proc.stdin.write(raw + "\n")
        proc.stdin.flush()

    def _wait_for_response(
        self,
        proc: subprocess.Popen,
        msg_queue: Queue,
        target_id: int,
        timeout_sec: int,
        on_event=None,
    ) -> dict:
        deadline = time.monotonic() + max(3, int(timeout_sec))
        while time.monotonic() < deadline:
            if proc.poll() is not None and msg_queue.empty():
                return {"success": False, "message": "app-server đã thoát sớm."}

            try:
                tag, line = msg_queue.get(timeout=0.2)
            except Empty:
                continue

            if line is None:
                continue
            if tag != "stdout":
                continue

            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except Exception:
                continue

            msg_id = msg.get("id")
            method = msg.get("method")
            if msg_id == target_id and "result" in msg:
                return {"success": True, "result": msg.get("result")}
            if msg_id == target_id and "error" in msg:
                err = msg.get("error") or {}
                return {"success": False, "message": str(err.get("message") or "app-server request error")}

            # Server initiated request, trả lời để tránh deadlock.
            if method and msg_id is not None:
                self._handle_server_request(proc, msg)
                continue

            if method and on_event:
                done = bool(on_event(msg))
                if done:
                    return {"success": True, "result": {"done": True}}

        return {"success": False, "message": "Timeout chờ phản hồi app-server."}

    @staticmethod
    def _handle_server_request(proc: subprocess.Popen, msg: dict):
        method = str(msg.get("method") or "")
        req_id = msg.get("id")
        if req_id is None:
            return

        decision_map = {
            "item/commandExecution/requestApproval": {"decision": "decline"},
            "item/fileChange/requestApproval": {"decision": "decline"},
            "execCommandApproval": {"decision": "denied"},
            "applyPatchApproval": {"decision": "denied"},
            "item/tool/requestUserInput": {"answers": {}},
            "item/tool/call": {"success": False, "contentItems": [{"type": "inputText", "text": "Tool này chưa hỗ trợ trong OmniMind runtime."}]},
        }
        result = decision_map.get(method, {})
        payload = {"jsonrpc": "2.0", "id": req_id, "result": result}
        try:
            raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
            proc.stdin.write(raw + "\n")
            proc.stdin.flush()
        except Exception:
            pass

    def _stream_reply_app_server(
        self,
        prompt_text: str,
        on_chunk: Callable[[str], None] | None = None,
        timeout_sec: int = 600,
    ) -> dict:
        cmd = self._build_command(prompt_text)
        cwd = self._resolve_workspace()
        env = self.env_manager.get_codex_env()

        proc = subprocess.Popen(
            cmd,
            cwd=cwd,
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )

        msg_queue: Queue = Queue()
        stdout_thread = threading.Thread(target=self._pump_stream, args=(proc.stdout, msg_queue, "stdout"), daemon=True)
        stderr_thread = threading.Thread(target=self._pump_stream, args=(proc.stderr, msg_queue, "stderr"), daemon=True)
        stdout_thread.start()
        stderr_thread.start()

        final_text = ""
        final_delta_parts: list[str] = []
        error_messages: list[str] = []

        def on_event(msg: dict) -> bool:
            nonlocal final_text
            method = str(msg.get("method") or "")

            # Legacy wrapper: method codex/event/<event_type>.
            if method.startswith("codex/event/"):
                params = msg.get("params") or {}
                ev = params.get("msg") or {}
                ev_type = str(ev.get("type") or "")

                if ev_type in {"agent_reasoning_delta", "reasoning_content_delta", "agent_reasoning_raw_content_delta"}:
                    delta = self._clean_chunk(ev.get("delta", ""))
                    if delta and on_chunk:
                        on_chunk("thinking\n" + delta + "\n")
                    return False

                if ev_type in {"agent_message_delta", "agent_message_content_delta"}:
                    delta = self._clean_chunk(ev.get("delta", ""))
                    if delta:
                        final_delta_parts.append(delta)
                    return False

                if ev_type == "agent_message":
                    phase = str(ev.get("phase") or "")
                    message = self._clean_chunk(ev.get("message", ""))
                    if phase == "final_answer" and message:
                        final_text = message
                    return False

                if ev_type in {"task_complete", "turn_complete"}:
                    last_agent = self._clean_chunk(ev.get("last_agent_message", ""))
                    if last_agent:
                        final_text = last_agent
                    return True

                if ev_type in {"error", "stream_error"}:
                    message = self._clean_chunk(ev.get("message", ""))
                    if message:
                        error_messages.append(message)
                    return False

                return False

            # V2 direct notifications fallback.
            if method in {"item/reasoning/textDelta", "item/reasoning/summaryTextDelta"}:
                delta = self._clean_chunk((msg.get("params") or {}).get("delta", ""))
                if delta and on_chunk:
                    on_chunk("thinking\n" + delta + "\n")
                return False

            if method in {"item/completed"}:
                item = (msg.get("params") or {}).get("item") or {}
                if str(item.get("type") or "").lower() in {"assistantmessage", "assistant_message", "assistantmessageitem"}:
                    content = item.get("content") or []
                    text_buf = []
                    for part in content:
                        if isinstance(part, dict) and str(part.get("type") or "").lower() == "text":
                            text_buf.append(str(part.get("text") or ""))
                    merged = self._clean_chunk("\n".join(text_buf).strip())
                    if merged:
                        final_text = merged
                return False

            if method in {"turn/completed"}:
                return True

            return False

        try:
            # initialize
            init_id = self._next_request_id()
            self._send_json(
                proc,
                self._jsonrpc_request(
                    "initialize",
                    init_id,
                    {
                        "clientInfo": {"name": "omnimind", "title": "OmniMind", "version": "1.0.0"},
                        "capabilities": {"experimentalApi": False},
                    },
                ),
            )
            init_resp = self._wait_for_response(proc, msg_queue, init_id, timeout_sec=8)
            if not init_resp.get("success"):
                return {"success": False, "message": init_resp.get("message", "initialize thất bại"), "output": ""}

            # initialized notif
            self._send_json(proc, self._jsonrpc_notification("initialized"))

            # new conversation
            conv_id_req = self._next_request_id()
            self._send_json(
                proc,
                self._jsonrpc_request(
                    "newConversation",
                    conv_id_req,
                    {
                        "model": None,
                        "modelProvider": None,
                        "profile": None,
                        "cwd": cwd,
                        "approvalPolicy": None,
                        "sandbox": None,
                        "config": None,
                        "baseInstructions": None,
                        "developerInstructions": None,
                        "compactPrompt": None,
                        "includeApplyPatchTool": False,
                    },
                ),
            )
            conv_resp = self._wait_for_response(proc, msg_queue, conv_id_req, timeout_sec=12)
            if not conv_resp.get("success"):
                return {"success": False, "message": conv_resp.get("message", "newConversation thất bại"), "output": ""}
            conversation_id = str((conv_resp.get("result") or {}).get("conversationId") or "").strip()
            if not conversation_id:
                return {"success": False, "message": "Không lấy được conversationId từ app-server.", "output": ""}

            # listener
            listen_req = self._next_request_id()
            self._send_json(
                proc,
                self._jsonrpc_request(
                    "addConversationListener",
                    listen_req,
                    {"conversationId": conversation_id, "experimentalRawEvents": False},
                ),
            )
            self._wait_for_response(proc, msg_queue, listen_req, timeout_sec=8)

            # send user message
            send_req = self._next_request_id()
            self._send_json(
                proc,
                self._jsonrpc_request(
                    "sendUserMessage",
                    send_req,
                    {
                        "conversationId": conversation_id,
                        "items": [{"type": "text", "data": {"text": prompt_text, "text_elements": []}}],
                    },
                ),
            )
            send_resp = self._wait_for_response(proc, msg_queue, send_req, timeout_sec=10)
            if not send_resp.get("success"):
                return {"success": False, "message": send_resp.get("message", "sendUserMessage thất bại"), "output": ""}

            # stream until turn complete
            turn_done = self._wait_for_response(
                proc,
                msg_queue,
                target_id=-999999,  # dummy id, we only rely on on_event done signal.
                timeout_sec=timeout_sec,
                on_event=on_event,
            )
            if not turn_done.get("success"):
                partial = final_text or "".join(final_delta_parts).strip()
                return {
                    "success": False,
                    "message": turn_done.get("message", "Không nhận được turn complete từ app-server."),
                    "output": partial,
                }

            output = final_text.strip() or "".join(final_delta_parts).strip()
            if not output and error_messages:
                return {"success": False, "message": "; ".join(error_messages[-2:]), "output": ""}
            if not output:
                return {"success": False, "message": "app-server không trả nội dung final.", "output": ""}
            return {"success": True, "message": "OK", "output": output, "mode": "app-server"}
        finally:
            try:
                proc.terminate()
                proc.wait(timeout=1.5)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass

    def _stream_reply_exec(
        self,
        prompt_text: str,
        on_chunk: Callable[[str], None] | None = None,
        timeout_sec: int = 600,
    ) -> dict:
        cmd = self._build_exec_command(prompt_text)
        cwd = self._resolve_workspace()
        env = self.env_manager.get_codex_env()
        started_at = time.monotonic()
        chunks: list[str] = []

        try:
            proc = subprocess.Popen(
                cmd,
                cwd=cwd,
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
        except FileNotFoundError:
            return {"success": False, "message": "Không tìm thấy lệnh codex.", "output": ""}
        except Exception as e:
            return {"success": False, "message": f"Không thể khởi chạy Codex: {e}", "output": ""}

        try:
            stream = proc.stdout
            if stream is not None:
                while True:
                    if time.monotonic() - started_at > max(30, int(timeout_sec)):
                        proc.kill()
                        return {"success": False, "message": "Codex xử lý quá thời gian chờ.", "output": "".join(chunks)}

                    line = stream.readline()
                    if line == "" and proc.poll() is not None:
                        break
                    if not line:
                        time.sleep(0.05)
                        continue

                    clean = self._clean_chunk(line)
                    if not clean.strip():
                        continue
                    chunks.append(clean)
                    if on_chunk:
                        on_chunk(clean)

            return_code = proc.wait(timeout=3)
            output = "".join(chunks).strip()
            if return_code != 0:
                message = output or f"Codex trả về mã lỗi {return_code}."
                return {"success": False, "message": message, "output": output}
            return {"success": True, "message": "OK", "output": output, "mode": "exec"}
        except subprocess.TimeoutExpired:
            proc.kill()
            return {"success": False, "message": "Codex không phản hồi khi kết thúc tiến trình.", "output": "".join(chunks)}
        except Exception as e:
            try:
                proc.kill()
            except Exception:
                pass
            return {"success": False, "message": f"Lỗi runtime Codex: {e}", "output": "".join(chunks)}

    def stream_reply(
        self,
        prompt: str,
        on_chunk: Callable[[str], None] | None = None,
        timeout_sec: int = 600,
    ) -> dict:
        prompt_text = str(prompt or "").strip()
        if not prompt_text:
            return {"success": False, "message": "Prompt rỗng.", "output": ""}

        auth_status = self.env_manager.verify_codex_auth()
        if not auth_status.get("success"):
            return {
                "success": False,
                "message": auth_status.get("message", "Codex chưa sẵn sàng xác thực."),
                "output": "",
            }

        mode = str(ConfigManager.get("codex_runtime_mode", "app-server")).strip().lower()
        if mode != "exec":
            try:
                result = self._stream_reply_app_server(
                    prompt_text=prompt_text,
                    on_chunk=on_chunk,
                    timeout_sec=timeout_sec,
                )
                if result.get("success"):
                    return result
                logger.warning(f"app-server failed, fallback exec: {result.get('message', '')}")
            except Exception as e:
                logger.warning(f"app-server exception, fallback exec: {e}")

        return self._stream_reply_exec(
            prompt_text=prompt_text,
            on_chunk=on_chunk,
            timeout_sec=timeout_sec,
        )
