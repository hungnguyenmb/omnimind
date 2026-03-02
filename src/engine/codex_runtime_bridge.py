import logging
import json
import os
import re
import subprocess
import time
import threading
from pathlib import Path
from queue import Empty, Queue
from typing import Callable, Optional, Any

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
    def _emit_event(callback: Callable[[dict[str, Any]], None] | None, payload: dict[str, Any]):
        if not callback:
            return
        try:
            callback(payload)
        except Exception as e:
            logger.warning(f"Runtime event callback error: {e}")

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
            if tag == "stderr":
                if on_event:
                    try:
                        on_event({"method": "runtime/stderr", "params": {"text": str(line)}})
                    except Exception as e:
                        logger.warning(f"stderr parser error (ignored): {e}")
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
                try:
                    done = bool(on_event(msg))
                except Exception as e:
                    logger.warning(f"app-server parser error (ignored): {e}")
                    done = False
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
        runtime_event_callback: Callable[[dict[str, Any]], None] | None = None,
        timeout_sec: int = 600,
    ) -> dict:
        cmd = self._build_command(prompt_text)
        cwd = self._resolve_workspace()
        env = self.env_manager.get_codex_env()
        self._emit_event(runtime_event_callback, {"kind": "status", "text": "Đang kết nối Codex app-server..."})

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

        def _extract_text(value: Any) -> str:
            if isinstance(value, str):
                return self._clean_chunk(value).strip()
            return ""

        def _extract_text_from_content(content: Any) -> str:
            if isinstance(content, str):
                return _extract_text(content)
            if isinstance(content, dict):
                direct = _extract_text(content.get("text"))
                if direct:
                    return direct
                return _extract_text(content.get("delta"))
            if isinstance(content, list):
                out: list[str] = []
                for part in content:
                    if isinstance(part, dict):
                        text = _extract_text(part.get("text"))
                        if not text:
                            text = _extract_text((part.get("data") or {}).get("text"))
                        if text:
                            out.append(text)
                    elif isinstance(part, str):
                        text = _extract_text(part)
                        if text:
                            out.append(text)
                return "\n".join(out).strip()
            return ""

        def _emit(kind: str, text: str, raw: dict | None = None):
            body = _extract_text(text)
            if not body:
                return
            payload: dict[str, Any] = {"kind": kind, "text": body}
            if raw is not None:
                payload["raw"] = raw
            self._emit_event(runtime_event_callback, payload)

        def handle_notification(msg: dict) -> bool:
            nonlocal final_text
            method = str(msg.get("method") or "")

            # Legacy wrapper: method codex/event/<event_type>.
            if method.startswith("codex/event/"):
                params = msg.get("params") or {}
                ev = params.get("msg") or {}
                ev_type = str(ev.get("type") or "")

                if ev_type in {"agent_reasoning_delta", "reasoning_content_delta", "agent_reasoning_raw_content_delta"}:
                    delta = self._clean_chunk(ev.get("delta", ""))
                    if delta:
                        _emit("reasoning", delta, raw=msg)
                        if on_chunk:
                            on_chunk("thinking\n" + delta + "\n")
                    return False

                if ev_type in {"agent_message_delta", "agent_message_content_delta"}:
                    delta = self._clean_chunk(ev.get("delta", ""))
                    if delta:
                        final_delta_parts.append(delta)
                        _emit("assistant_delta", delta, raw=msg)
                    return False

                if ev_type == "agent_message":
                    phase = str(ev.get("phase") or "")
                    message = self._clean_chunk(ev.get("message", ""))
                    if phase == "final_answer" and message:
                        final_text = message
                    if message:
                        _emit("assistant", message, raw=msg)
                    return False

                if ev_type in {"task_complete", "turn_complete"}:
                    last_agent = self._clean_chunk(ev.get("last_agent_message", ""))
                    if last_agent:
                        final_text = last_agent
                    _emit("status", "Codex đã hoàn tất lượt xử lý.", raw=msg)
                    return True

                if ev_type in {"error", "stream_error"}:
                    message = self._clean_chunk(ev.get("message", ""))
                    if message:
                        error_messages.append(message)
                        _emit("error", message, raw=msg)
                    return False

                return False

            if method == "thread/event":
                params = msg.get("params") or {}
                ev_type = str(params.get("type") or "").strip()
                event_obj = params.get("event")
                if isinstance(event_obj, dict):
                    event_payload = event_obj
                else:
                    event_payload = params
                ev_low = ev_type.lower()

                if any(x in ev_low for x in ("reasoning", "thinking")):
                    delta = _extract_text(event_payload.get("delta")) or _extract_text(event_payload.get("text"))
                    if not delta:
                        delta = _extract_text((event_payload.get("message") or {}).get("delta"))
                    if delta:
                        _emit("reasoning", delta, raw=msg)
                        if on_chunk:
                            on_chunk("thinking\n" + delta + "\n")
                    return False

                if any(x in ev_low for x in ("message.delta", "assistant_message.delta", "text.delta", "output_text.delta")):
                    delta = _extract_text(event_payload.get("delta")) or _extract_text(event_payload.get("text"))
                    if not delta:
                        delta = _extract_text((event_payload.get("message") or {}).get("delta"))
                    if delta:
                        final_delta_parts.append(delta)
                        _emit("assistant_delta", delta, raw=msg)
                    return False

                if any(x in ev_low for x in ("message.completed", "assistant_message.completed", "output_text.completed")):
                    message_text = _extract_text(event_payload.get("text"))
                    if not message_text:
                        message_text = _extract_text_from_content(event_payload.get("content"))
                    if message_text:
                        final_text = message_text
                        _emit("assistant", message_text, raw=msg)
                    return False

                if any(x in ev_low for x in ("tool", "command")):
                    tool_name = (
                        _extract_text(event_payload.get("tool_name"))
                        or _extract_text(event_payload.get("name"))
                        or _extract_text(event_payload.get("command"))
                    )
                    log_text = _extract_text(event_payload.get("message")) or _extract_text(event_payload.get("text"))
                    text = log_text or (f"Đang chạy tool: {tool_name}" if tool_name else "Đang chạy tool...")
                    _emit("tool", text, raw=msg)
                    return False

                if "log" in ev_low:
                    log_text = _extract_text(event_payload.get("message")) or _extract_text(event_payload.get("text"))
                    if log_text:
                        _emit("log", log_text, raw=msg)
                    return False

                if "error" in ev_low:
                    err_text = _extract_text(event_payload.get("message")) or _extract_text(event_payload.get("text"))
                    if err_text:
                        error_messages.append(err_text)
                        _emit("error", err_text, raw=msg)
                    return False

                if any(x in ev_low for x in ("turn.completed", "task.complete", "thread.completed", "response.completed")):
                    last_agent = _extract_text(event_payload.get("last_agent_message")) or _extract_text(
                        event_payload.get("message")
                    )
                    if last_agent:
                        final_text = last_agent
                    _emit("status", "Codex đã hoàn tất lượt xử lý.", raw=msg)
                    return True

                return False

            # V2 direct notifications fallback.
            if method in {"item/reasoning/textDelta", "item/reasoning/summaryTextDelta"}:
                delta = self._clean_chunk((msg.get("params") or {}).get("delta", ""))
                if delta:
                    _emit("reasoning", delta, raw=msg)
                    if on_chunk:
                        on_chunk("thinking\n" + delta + "\n")
                return False

            if method in {"item/tool/call", "item/commandExecution/status", "item/fileChange/status"}:
                params = msg.get("params") or {}
                name = _extract_text(params.get("name")) or _extract_text(params.get("tool_name"))
                status = _extract_text(params.get("status"))
                text = status or (f"Đang xử lý tool: {name}" if name else "Đang xử lý tool...")
                _emit("tool", text, raw=msg)
                return False

            if method in {"item/log", "runtime/log", "item/status"}:
                params = msg.get("params") or {}
                text = _extract_text(params.get("message")) or _extract_text(params.get("text"))
                if text:
                    _emit("log", text, raw=msg)
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
                        _emit("assistant", merged, raw=msg)
                return False

            if method in {"turn/completed"}:
                _emit("status", "Codex đã hoàn tất lượt xử lý.", raw=msg)
                return True

            if method == "runtime/stderr":
                text = _extract_text((msg.get("params") or {}).get("text"))
                if text:
                    _emit("log", text, raw=msg)
                return False

            # Generic parser fallback cho schema mới/chưa biết.
            params = msg.get("params") or {}
            method_low = method.lower()
            generic_text = (
                _extract_text(params.get("delta"))
                or _extract_text(params.get("text"))
                or _extract_text(params.get("message"))
                or _extract_text_from_content(params.get("content"))
            )

            if isinstance(params, dict):
                item = params.get("item")
                if isinstance(item, dict):
                    item_text = (
                        _extract_text(item.get("delta"))
                        or _extract_text(item.get("text"))
                        or _extract_text_from_content(item.get("content"))
                    )
                    if item_text and not generic_text:
                        generic_text = item_text

            if generic_text:
                if "reason" in method_low or "thinking" in method_low:
                    _emit("reasoning", generic_text, raw=msg)
                    if on_chunk:
                        on_chunk("thinking\n" + generic_text + "\n")
                    return False
                if any(x in method_low for x in ("assistant", "message", "response", "output")):
                    final_delta_parts.append(generic_text)
                    _emit("assistant_delta", generic_text, raw=msg)
                    return False
                if any(x in method_low for x in ("tool", "command", "approval", "exec")):
                    _emit("tool", generic_text, raw=msg)
                    return False
                _emit("log", generic_text, raw=msg)
                return False

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
            self._emit_event(runtime_event_callback, {"kind": "status", "text": "Kết nối app-server thành công."})

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
                    {"conversationId": conversation_id, "experimentalRawEvents": True},
                ),
            )
            self._wait_for_response(proc, msg_queue, listen_req, timeout_sec=8)
            self._emit_event(runtime_event_callback, {"kind": "status", "text": "Đang gửi yêu cầu cho Codex..."})

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
                on_event=handle_notification,
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
        runtime_event_callback: Callable[[dict[str, Any]], None] | None = None,
        timeout_sec: int = 600,
    ) -> dict:
        cmd = self._build_exec_command(prompt_text)
        cwd = self._resolve_workspace()
        env = self.env_manager.get_codex_env()
        started_at = time.monotonic()
        chunks: list[str] = []
        self._emit_event(runtime_event_callback, {"kind": "status", "text": "Đang chạy Codex fallback exec..."})

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
                    self._emit_event(runtime_event_callback, {"kind": "log", "text": clean.strip()})
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
        runtime_event_callback: Callable[[dict[str, Any]], None] | None = None,
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
                    runtime_event_callback=runtime_event_callback,
                    timeout_sec=timeout_sec,
                )
                if result.get("success"):
                    return result
                self._emit_event(
                    runtime_event_callback,
                    {
                        "kind": "warning",
                        "text": f"app-server lỗi, chuyển sang exec: {result.get('message', 'unknown error')}",
                    },
                )
                logger.warning(f"app-server failed, fallback exec: {result.get('message', '')}")
            except Exception as e:
                self._emit_event(
                    runtime_event_callback,
                    {"kind": "warning", "text": f"app-server exception, fallback exec: {e}"},
                )
                logger.warning(f"app-server exception, fallback exec: {e}")

        return self._stream_reply_exec(
            prompt_text=prompt_text,
            on_chunk=on_chunk,
            runtime_event_callback=runtime_event_callback,
            timeout_sec=timeout_sec,
        )
