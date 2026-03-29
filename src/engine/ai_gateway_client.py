from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import requests

from engine.artifact_manager import ArtifactManager
from engine.config_manager import ConfigManager
from engine.http_client import request_with_retry

logger = logging.getLogger(__name__)


class AiGatewayClient:
    DEFAULT_TIMEOUT_SEC = 20

    def __init__(self):
        self._session = requests.Session()

    @staticmethod
    def _safe_json(response: requests.Response) -> dict | list | None:
        try:
            return response.json() if response.content else None
        except Exception:
            return None

    @staticmethod
    def _mask_key(value: str) -> str:
        text = str(value or "").strip()
        if len(text) <= 8:
            return "*" * len(text)
        return f"{text[:4]}***{text[-4:]}"

    def _headers(self) -> dict:
        api_key = ConfigManager.get_openapi_proxy_api_key()
        if not api_key:
            raise RuntimeError("Chưa cấu hình OpenAPI Gateway API key.")
        return {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    def _post_json(
        self,
        url: str,
        payload: dict,
        timeout_sec: int | float | None = None,
    ) -> dict:
        timeout = timeout_sec or self.DEFAULT_TIMEOUT_SEC
        try:
            response = request_with_retry(
                "POST",
                url,
                session=self._session,
                headers=self._headers(),
                json=payload,
                timeout=timeout,
                max_attempts=3,
            )
        except Exception as e:
            return {
                "success": False,
                "message": f"Lỗi kết nối OpenAPI Gateway: {str(e)[:220]}",
                "status_code": 0,
                "data": None,
                "raw": None,
            }

        data = self._safe_json(response)
        ok = 200 <= response.status_code < 300
        if ok:
            return {
                "success": True,
                "message": "OK",
                "status_code": int(response.status_code),
                "data": data,
                "raw": data,
            }
        err_msg = ""
        if isinstance(data, dict):
            err = data.get("error")
            if isinstance(err, dict):
                err_msg = str(err.get("message") or "").strip()
            if not err_msg:
                err_msg = str(data.get("message") or "").strip()
        if not err_msg:
            err_msg = f"OpenAPI Gateway trả HTTP {response.status_code}."
        return {
            "success": False,
            "message": err_msg,
            "status_code": int(response.status_code),
            "data": data,
            "raw": data,
        }

    def _get_json(self, url: str, timeout_sec: int | float | None = None) -> dict:
        timeout = timeout_sec or self.DEFAULT_TIMEOUT_SEC
        try:
            response = request_with_retry(
                "GET",
                url,
                session=self._session,
                headers=self._headers(),
                timeout=timeout,
                max_attempts=3,
            )
        except Exception as e:
            return {
                "success": False,
                "message": f"Lỗi kết nối OpenAPI Gateway: {str(e)[:220]}",
                "status_code": 0,
                "data": None,
                "raw": None,
            }

        data = self._safe_json(response)
        ok = 200 <= response.status_code < 300
        if ok:
            return {
                "success": True,
                "message": "OK",
                "status_code": int(response.status_code),
                "data": data,
                "raw": data,
            }
        err_msg = ""
        if isinstance(data, dict):
            err = data.get("error")
            if isinstance(err, dict):
                err_msg = str(err.get("message") or "").strip()
            if not err_msg:
                err_msg = str(data.get("message") or "").strip()
        if not err_msg:
            err_msg = f"OpenAPI Gateway trả HTTP {response.status_code}."
        return {
            "success": False,
            "message": err_msg,
            "status_code": int(response.status_code),
            "data": data,
            "raw": data,
        }

    @staticmethod
    def extract_text_from_chat_payload(payload: dict | None) -> str:
        if not isinstance(payload, dict):
            return ""
        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices:
            return ""
        first = choices[0] if isinstance(choices[0], dict) else {}
        message = first.get("message") if isinstance(first, dict) else {}
        if not isinstance(message, dict):
            return ""
        content = message.get("content")
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, dict):
                    text = item.get("text")
                    if isinstance(text, str) and text.strip():
                        parts.append(text.strip())
            return "\n".join(parts).strip()
        return ""

    @staticmethod
    def extract_tool_calls(payload: dict | None) -> list[dict]:
        if not isinstance(payload, dict):
            return []
        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices:
            return []
        first = choices[0] if isinstance(choices[0], dict) else {}
        message = first.get("message") if isinstance(first, dict) else {}
        if not isinstance(message, dict):
            return []
        tool_calls = message.get("tool_calls")
        if isinstance(tool_calls, list):
            return [item for item in tool_calls if isinstance(item, dict)]
        return []

    def list_models(self) -> dict:
        base = ConfigManager.get_openapi_proxy_base()
        return self._get_json(f"{base}/models", timeout_sec=15)

    def chat_completion(
        self,
        messages: list[dict],
        model: str = "",
        temperature: float | None = None,
        max_tokens: int | None = None,
        extra_payload: dict | None = None,
    ) -> dict:
        base = ConfigManager.get_openapi_proxy_base()
        payload: dict[str, Any] = {
            "model": str(model or ConfigManager.get_openapi_proxy_text_model()).strip(),
            "messages": messages or [],
        }
        if temperature is not None:
            payload["temperature"] = float(temperature)
        if max_tokens is not None:
            payload["max_tokens"] = int(max_tokens)
        if extra_payload:
            payload.update(extra_payload)
        result = self._post_json(f"{base}/chat/completions", payload, timeout_sec=45)
        if result.get("success"):
            result["text"] = self.extract_text_from_chat_payload(result.get("data"))
            result["tool_calls"] = self.extract_tool_calls(result.get("data"))
        return result

    def vision_completion(
        self,
        prompt_text: str,
        *,
        image_url: str = "",
        image_base64: str = "",
        image_mime_type: str = "image/jpeg",
        model: str = "",
        max_tokens: int | None = None,
    ) -> dict:
        image_url = str(image_url or "").strip()
        image_base64 = str(image_base64 or "").strip()
        if bool(image_url) == bool(image_base64):
            return {
                "success": False,
                "message": "Cần truyền đúng một trong hai: image_url hoặc image_base64.",
                "status_code": 0,
                "data": None,
                "raw": None,
            }
        if image_base64:
            image_ref = f"data:{image_mime_type};base64,{image_base64}"
        else:
            image_ref = image_url
        content = [
            {"type": "text", "text": str(prompt_text or "").strip()},
            {"type": "image_url", "image_url": {"url": image_ref}},
        ]
        return self.chat_completion(
            messages=[{"role": "user", "content": content}],
            model=model or ConfigManager.get_openapi_proxy_text_model(),
            max_tokens=max_tokens,
        )

    def vision_completion_from_local_file(
        self,
        prompt_text: str,
        *,
        local_path: str,
        model: str = "",
        max_tokens: int | None = None,
    ) -> dict:
        artifact = ArtifactManager.normalize_local_artifact(
            local_path,
            source_channel="local",
            source_message_id="vision_local_file",
        )
        if not artifact.get("is_valid"):
            return {
                "success": False,
                "message": str(artifact.get("message") or "Attachment không hợp lệ."),
                "status_code": 0,
                "data": {"artifact": artifact},
                "raw": None,
            }
        if artifact.get("type") != "image" or not artifact.get("vision_supported"):
            return {
                "success": False,
                "message": "File hiện tại không phải ảnh hợp lệ để dùng vision.",
                "status_code": 0,
                "data": {"artifact": artifact},
                "raw": None,
            }
        encoded = ArtifactManager.encode_file_base64(str(artifact.get("path") or ""))
        if not encoded.get("success"):
            return {
                "success": False,
                "message": encoded.get("message", "Không encode được ảnh local."),
                "status_code": 0,
                "data": {"artifact": artifact},
                "raw": None,
            }
        result = self.vision_completion(
            prompt_text=prompt_text,
            image_base64=str(encoded.get("base64") or ""),
            image_mime_type=str(encoded.get("mime_type") or "image/jpeg"),
            model=model,
            max_tokens=max_tokens,
        )
        if isinstance(result.get("data"), dict):
            result["data"]["artifact"] = artifact
        return result

    def chat_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
        *,
        tool_choice: str | dict | None = None,
        model: str = "",
        temperature: float | None = None,
        extra_payload: dict | None = None,
    ) -> dict:
        payload: dict[str, Any] = {
            "tools": tools or [],
        }
        if tool_choice is not None:
            payload["tool_choice"] = tool_choice
        if extra_payload:
            payload.update(extra_payload)
        return self.chat_completion(
            messages=messages,
            model=model or ConfigManager.get_openapi_proxy_text_model(),
            temperature=temperature,
            extra_payload=payload,
        )

    def probe_gateway(self) -> dict:
        report: dict[str, Any] = {
            "success": False,
            "models_ok": False,
            "text_ok": False,
            "tools_ok": False,
            "supports_tools": False,
            "message": "",
            "details": {},
        }

        models_res = self.list_models()
        report["details"]["models"] = {
            "success": bool(models_res.get("success")),
            "status_code": models_res.get("status_code", 0),
            "message": models_res.get("message", ""),
        }
        report["models_ok"] = bool(models_res.get("success"))
        if not models_res.get("success"):
            report["message"] = models_res.get("message", "Không gọi được /models.")
            return report

        text_res = self.chat_completion(
            messages=[
                {
                    "role": "system",
                    "content": "Bạn trả lời ngắn gọn, rõ ràng bằng tiếng Việt.",
                },
                {
                    "role": "user",
                    "content": "Hãy trả lời đúng duy nhất từ OK.",
                },
            ],
            temperature=0,
            max_tokens=30,
        )
        report["details"]["text"] = {
            "success": bool(text_res.get("success")),
            "status_code": text_res.get("status_code", 0),
            "message": text_res.get("message", ""),
            "text": text_res.get("text", ""),
        }
        report["text_ok"] = bool(text_res.get("success"))

        tool_res = self.chat_with_tools(
            messages=[
                {
                    "role": "user",
                    "content": "Nếu hỗ trợ function calling, hãy gọi hàm ping_gateway.",
                }
            ],
            tools=[
                {
                    "type": "function",
                    "function": {
                        "name": "ping_gateway",
                        "description": "Kiểm tra model có thể gọi tool hay không.",
                        "parameters": {
                            "type": "object",
                            "properties": {},
                            "additionalProperties": False,
                        },
                    },
                }
            ],
            tool_choice="auto",
            temperature=0,
        )
        tool_calls = tool_res.get("tool_calls") if isinstance(tool_res.get("tool_calls"), list) else []
        report["details"]["tools"] = {
            "success": bool(tool_res.get("success")),
            "status_code": tool_res.get("status_code", 0),
            "message": tool_res.get("message", ""),
            "tool_call_count": len(tool_calls),
            "text": tool_res.get("text", ""),
        }
        report["tools_ok"] = bool(tool_res.get("success"))
        report["supports_tools"] = bool(tool_res.get("success") and tool_calls)
        report["success"] = report["models_ok"] and report["text_ok"]
        if report["supports_tools"]:
            report["message"] = "Gateway hoạt động tốt và đã trả về tool_calls."
        elif report["tools_ok"]:
            report["message"] = "Gateway hoạt động với text, nhưng probe tools chưa trả về tool_calls."
        else:
            report["message"] = tool_res.get("message") or "Gateway hoạt động với text, nhưng probe tools chưa thành công."
        return report
