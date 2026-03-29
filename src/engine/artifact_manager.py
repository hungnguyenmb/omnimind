from __future__ import annotations

import base64
import hashlib
import mimetypes
import os
from pathlib import Path


class ArtifactManager:
    IMAGE_MIME_PREFIX = "image/"
    DEFAULT_MAX_IMAGE_BYTES = 15 * 1024 * 1024
    DEFAULT_MAX_DOCUMENT_BYTES = 25 * 1024 * 1024
    TEXT_READABLE_SUFFIXES = {
        ".txt",
        ".md",
        ".json",
        ".csv",
        ".log",
        ".py",
        ".js",
        ".ts",
        ".yaml",
        ".yml",
        ".xml",
        ".html",
        ".css",
        ".ini",
        ".cfg",
        ".sql",
    }
    SUPPORTED_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}

    @staticmethod
    def _artifact_id(path_obj: Path, source_channel: str, source_message_id: str) -> str:
        raw = f"{source_channel}:{source_message_id}:{str(path_obj)}"
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]

    @staticmethod
    def _guess_mime(path_obj: Path) -> str:
        mime_type, _ = mimetypes.guess_type(path_obj.name)
        return str(mime_type or "application/octet-stream").strip()

    @classmethod
    def _base_contract(
        cls,
        *,
        path_obj: Path,
        source_channel: str,
        source_message_id: str,
        metadata: dict | None = None,
    ) -> dict:
        size_bytes = 0
        try:
            size_bytes = int(path_obj.stat().st_size or 0)
        except Exception:
            size_bytes = 0
        mime_type = cls._guess_mime(path_obj)
        suffix = path_obj.suffix.lower()
        artifact_type = "document"
        if mime_type.startswith(cls.IMAGE_MIME_PREFIX) or suffix in cls.SUPPORTED_IMAGE_SUFFIXES:
            artifact_type = "image"
        elif suffix not in cls.TEXT_READABLE_SUFFIXES:
            artifact_type = "binary"
        return {
            "artifact_id": cls._artifact_id(path_obj, source_channel, source_message_id),
            "type": artifact_type,
            "path": str(path_obj),
            "file_name": path_obj.name,
            "mime_type": mime_type,
            "size_bytes": size_bytes,
            "source_channel": str(source_channel or "").strip(),
            "source_message_id": str(source_message_id or "").strip(),
            "metadata": dict(metadata or {}),
            "is_valid": True,
            "code": "",
            "message": "",
            "user_hint": "",
            "vision_supported": artifact_type == "image",
            "text_read_supported": suffix in cls.TEXT_READABLE_SUFFIXES,
        }

    @staticmethod
    def build_invalid_artifact(
        *,
        path: str = "",
        source_channel: str,
        source_message_id: str,
        code: str,
        message: str,
        user_hint: str,
        metadata: dict | None = None,
    ) -> dict:
        return {
            "artifact_id": "",
            "type": "invalid",
            "path": str(path or "").strip(),
            "file_name": Path(str(path or "")).name if str(path or "").strip() else "",
            "mime_type": "",
            "size_bytes": 0,
            "source_channel": str(source_channel or "").strip(),
            "source_message_id": str(source_message_id or "").strip(),
            "metadata": dict(metadata or {}),
            "is_valid": False,
            "code": str(code or "INVALID_ATTACHMENT").strip(),
            "message": str(message or "Attachment không hợp lệ.").strip(),
            "user_hint": str(user_hint or "Hãy gửi lại file đúng định dạng.").strip(),
            "vision_supported": False,
            "text_read_supported": False,
        }

    @classmethod
    def normalize_local_artifact(
        cls,
        path: str,
        *,
        source_channel: str,
        source_message_id: str,
        metadata: dict | None = None,
        max_image_bytes: int | None = None,
        max_document_bytes: int | None = None,
    ) -> dict:
        raw_path = str(path or "").strip()
        if not raw_path:
            return cls.build_invalid_artifact(
                path="",
                source_channel=source_channel,
                source_message_id=source_message_id,
                code="ATTACHMENT_PATH_EMPTY",
                message="Thiếu đường dẫn attachment local.",
                user_hint="Hãy gửi lại file hoặc ảnh hợp lệ.",
                metadata=metadata,
            )

        path_obj = Path(os.path.expanduser(raw_path))
        if not path_obj.exists() or not path_obj.is_file():
            return cls.build_invalid_artifact(
                path=raw_path,
                source_channel=source_channel,
                source_message_id=source_message_id,
                code="ATTACHMENT_NOT_FOUND",
                message=f"Không tìm thấy file local: {raw_path}",
                user_hint="File tải về chưa hợp lệ. Hãy gửi lại file hoặc thử lại.",
                metadata=metadata,
            )

        try:
            resolved = path_obj.resolve()
        except Exception:
            resolved = path_obj
        artifact = cls._base_contract(
            path_obj=resolved,
            source_channel=source_channel,
            source_message_id=source_message_id,
            metadata=metadata,
        )
        size_bytes = int(artifact.get("size_bytes") or 0)
        max_img = int(max_image_bytes or cls.DEFAULT_MAX_IMAGE_BYTES)
        max_doc = int(max_document_bytes or cls.DEFAULT_MAX_DOCUMENT_BYTES)

        if artifact["type"] == "image" and size_bytes > max_img:
            artifact.update(
                {
                    "is_valid": False,
                    "code": "IMAGE_TOO_LARGE",
                    "message": f"Ảnh vượt giới hạn {max_img // (1024 * 1024)}MB.",
                    "user_hint": "Hãy gửi ảnh nhỏ hơn hoặc nén ảnh rồi thử lại.",
                }
            )
            return artifact

        if artifact["type"] in {"document", "binary"} and size_bytes > max_doc:
            artifact.update(
                {
                    "is_valid": False,
                    "code": "DOCUMENT_TOO_LARGE",
                    "message": f"File vượt giới hạn {max_doc // (1024 * 1024)}MB.",
                    "user_hint": "Hãy gửi file nhỏ hơn hoặc tách nhỏ tài liệu rồi thử lại.",
                }
            )
            return artifact

        if artifact["type"] == "binary" and not artifact.get("text_read_supported"):
            artifact.update(
                {
                    "is_valid": False,
                    "code": "UNSUPPORTED_ATTACHMENT_TYPE",
                    "message": "Loại file hiện chưa được hỗ trợ trực tiếp trong Sprint 8.",
                    "user_hint": "Hãy gửi ảnh hoặc file text như txt/md/json/csv/log.",
                }
            )
        return artifact

    @staticmethod
    def encode_file_base64(path: str) -> dict:
        raw_path = str(path or "").strip()
        path_obj = Path(os.path.expanduser(raw_path))
        if not path_obj.exists() or not path_obj.is_file():
            return {
                "success": False,
                "message": f"Không tìm thấy file để encode base64: {raw_path}",
                "mime_type": "",
                "base64": "",
            }
        try:
            content = path_obj.read_bytes()
        except Exception as e:
            return {
                "success": False,
                "message": f"Không đọc được file để encode base64: {str(e)[:200]}",
                "mime_type": "",
                "base64": "",
            }
        mime_type, _ = mimetypes.guess_type(path_obj.name)
        return {
            "success": True,
            "message": "OK",
            "mime_type": str(mime_type or "application/octet-stream"),
            "base64": base64.b64encode(content).decode("ascii"),
        }
