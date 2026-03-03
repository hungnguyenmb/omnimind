import logging
import os
import platform
import re
import shutil
import hashlib
import tarfile
import tempfile
import zipfile
from pathlib import Path
from typing import Callable, Optional

from engine.config_manager import ConfigManager
from engine.http_client import request_with_retry

logger = logging.getLogger(__name__)

DEFAULT_APP_VERSION = "1.0.0"


class UpdateManager:
    """
    Quản lý kiểm tra / tải / cài payload update cho OmniMind.
    Thiết kế theo cơ chế overlay code trong AppData để:
    - Không thay thế app bundle trên macOS (tránh mất quyền TCC).
    - Tương thích cả macOS và Windows.
    """

    def __init__(self):
        self.os_name = platform.system()
        self.app_data_dir = self._get_app_data_dir()
        self.app_data_dir.mkdir(parents=True, exist_ok=True)
        self.updates_dir = self.app_data_dir / "updates"
        self.payloads_dir = self.updates_dir / "payloads"
        self.updates_dir.mkdir(parents=True, exist_ok=True)
        self.payloads_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _emit_progress(progress_callback: Optional[Callable[[int, str], None]], percent: int, message: str):
        if not progress_callback:
            return
        try:
            bounded = max(0, min(100, int(percent)))
            progress_callback(bounded, message)
        except Exception:
            pass

    def _get_app_data_dir(self) -> Path:
        if self.os_name == "Windows":
            base = os.environ.get("LOCALAPPDATA", os.path.expanduser("~\\AppData\\Local"))
            return Path(base) / "OmniMind"
        if self.os_name == "Darwin":
            return Path(os.path.expanduser("~/Library/Application Support")) / "OmniMind"
        return Path(os.path.expanduser("~/.omnimind"))

    @staticmethod
    def _parse_version_tuple(version: str) -> tuple:
        if not version:
            return tuple()
        nums = [int(x) for x in re.findall(r"\d+", str(version))]
        if not nums:
            return tuple()
        return tuple(nums[:4])

    def is_newer_version(self, current_version: str, latest_version: str) -> bool:
        current = self._parse_version_tuple(current_version)
        latest = self._parse_version_tuple(latest_version)
        if not latest:
            return False
        if not current:
            return True
        return latest > current

    def get_current_version(self) -> str:
        payload_version = ConfigManager.get("app_payload_version", "").strip()
        stored_version = ConfigManager.get("app_current_version", "").strip()
        env_version = os.environ.get("OMNIMIND_APP_VERSION", "").strip()
        current = payload_version or stored_version or env_version or DEFAULT_APP_VERSION
        if current != stored_version:
            ConfigManager.set("app_current_version", current)
        return current

    def check_for_updates(self, api_base_url: str, current_version: Optional[str] = None) -> dict:
        current_version = (current_version or self.get_current_version()).strip()
        url = f"{api_base_url.rstrip('/')}/api/v1/omnimind/app/version"
        try:
            response = request_with_retry("GET", url, timeout=10, max_attempts=4)
            if response.status_code != 200:
                return {"success": False, "message": "Không nhận được phản hồi từ Server."}

            data = response.json() or {}
            latest_version = str(data.get("latest_version") or "").strip()
            has_update = self.is_newer_version(current_version, latest_version)
            return {
                "success": True,
                "current_version": current_version,
                "has_update": has_update,
                "latest_version": latest_version,
                "version_name": data.get("version_name") or latest_version,
                "download_url": data.get("download_url") or "",
                "checksum_sha256": str(data.get("checksum_sha256") or data.get("checksum") or "").strip().lower(),
                "package_size_bytes": data.get("package_size_bytes"),
                "release_date": data.get("release_date") or "",
                "changelogs": data.get("changelogs", []),
                "is_critical": bool(data.get("is_critical", False)),
            }
        except Exception as e:
            logger.error(f"Version check error: {e}")
            return {"success": False, "message": str(e)}

    def _resolve_payload_root(self, extracted_dir: Path) -> Path:
        if (extracted_dir / "src").is_dir():
            return extracted_dir

        children = [p for p in extracted_dir.iterdir() if p.is_dir()]
        if len(children) == 1 and (children[0] / "src").is_dir():
            return children[0]

        for src_dir in extracted_dir.rglob("src"):
            if src_dir.is_dir() and (src_dir / "engine").exists():
                return src_dir.parent

        raise RuntimeError("Gói update không hợp lệ: thiếu thư mục src.")

    def _cleanup_old_payloads(self, keep_version: str):
        dirs = [p for p in self.payloads_dir.iterdir() if p.is_dir()]
        dirs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        keep_count = 2
        kept = 0
        for folder in dirs:
            if folder.name == keep_version or kept < keep_count:
                kept += 1
                continue
            try:
                shutil.rmtree(folder, ignore_errors=True)
            except Exception:
                pass

    def download_and_install_update(
        self,
        download_url: str,
        target_version: str,
        expected_checksum: str = "",
        progress_callback: Optional[Callable[[int, str], None]] = None,
    ) -> dict:
        download_url = (download_url or "").strip()
        target_version = (target_version or "").strip()
        expected_checksum = str(expected_checksum or "").strip().lower()
        if expected_checksum.startswith("sha256:"):
            expected_checksum = expected_checksum.split(":", 1)[1].strip()
        if not download_url:
            return {"success": False, "message": "Thiếu link tải bản cập nhật."}
        if not target_version:
            return {"success": False, "message": "Thiếu phiên bản mục tiêu."}

        archive_path = self.updates_dir / f"update-{target_version}.pkg"
        extract_tmp_dir = Path(tempfile.mkdtemp(prefix="omnimind-update-", dir=str(self.updates_dir)))
        target_tmp_dir = self.payloads_dir / f".{target_version}.tmp"
        final_dir = self.payloads_dir / target_version

        try:
            self._emit_progress(progress_callback, 5, "Bắt đầu tải bản cập nhật...")
            hasher = hashlib.sha256() if expected_checksum else None
            with request_with_retry(
                "GET",
                download_url,
                timeout=30,
                max_attempts=4,
                stream=True,
                headers={"User-Agent": "OmniMind-App"},
            ) as response, open(archive_path, "wb") as out_file:
                if response.status_code != 200:
                    raise RuntimeError(f"Tải gói update thất bại (HTTP {response.status_code}).")
                total_size = int(response.headers.get("Content-Length", "0") or "0")
                downloaded = 0
                chunk_size = 1024 * 256
                for chunk in response.iter_content(chunk_size=chunk_size):
                    if not chunk:
                        continue
                    out_file.write(chunk)
                    downloaded += len(chunk)
                    if hasher:
                        hasher.update(chunk)
                    if total_size > 0:
                        pct = 5 + int((downloaded / total_size) * 55)
                    else:
                        pct = min(60, 5 + int(downloaded / (1024 * 1024)))
                    self._emit_progress(progress_callback, pct, "Đang tải gói cập nhật...")

            if hasher:
                self._emit_progress(progress_callback, 62, "Đang xác minh checksum update...")
                actual_checksum = hasher.hexdigest().lower()
                if actual_checksum != expected_checksum:
                    raise RuntimeError("Checksum update không khớp. Đã huỷ cài đặt để đảm bảo an toàn.")

            self._emit_progress(progress_callback, 65, "Đang giải nén gói cập nhật...")
            if zipfile.is_zipfile(archive_path):
                with zipfile.ZipFile(archive_path, "r") as zip_ref:
                    zip_ref.extractall(extract_tmp_dir)
            elif tarfile.is_tarfile(archive_path):
                with tarfile.open(archive_path, "r") as tar_ref:
                    tar_ref.extractall(extract_tmp_dir)
            else:
                raise RuntimeError("Định dạng gói update không hợp lệ (chỉ hỗ trợ zip/tar).")

            self._emit_progress(progress_callback, 78, "Đang kiểm tra payload cập nhật...")
            payload_root = self._resolve_payload_root(extract_tmp_dir)
            src_dir = payload_root / "src"
            if not src_dir.is_dir():
                raise RuntimeError("Payload cập nhật thiếu thư mục src.")

            if target_tmp_dir.exists():
                shutil.rmtree(target_tmp_dir, ignore_errors=True)
            shutil.copytree(payload_root, target_tmp_dir)

            self._emit_progress(progress_callback, 90, "Đang áp dụng bản cập nhật...")
            if final_dir.exists():
                shutil.rmtree(final_dir, ignore_errors=True)
            target_tmp_dir.rename(final_dir)

            prev_payload_path = ConfigManager.get("app_payload_path", "").strip()
            prev_payload_version = ConfigManager.get("app_payload_version", "").strip()
            ConfigManager.set("app_payload_path", str(final_dir))
            ConfigManager.set("app_payload_version", target_version)
            ConfigManager.set("app_current_version", target_version)
            ConfigManager.set("app_update_pending_restart", "true")
            ConfigManager.set("app_payload_prev_path", prev_payload_path)
            ConfigManager.set("app_payload_prev_version", prev_payload_version)
            ConfigManager.set("app_payload_boot_status", "pending")
            ConfigManager.set("app_payload_boot_attempts", "0")
            ConfigManager.set("app_payload_last_error", "")

            self._cleanup_old_payloads(target_version)
            self._emit_progress(progress_callback, 100, "Cài đặt bản cập nhật thành công.")
            return {
                "success": True,
                "version": target_version,
                "payload_path": str(final_dir),
                "checksum_verified": bool(expected_checksum),
            }
        except Exception as e:
            logger.error(f"Install update failed: {e}")
            return {"success": False, "message": f"Cài đặt cập nhật thất bại: {str(e)[:180]}"}
        finally:
            try:
                if archive_path.exists():
                    archive_path.unlink()
            except Exception:
                pass
            try:
                if extract_tmp_dir.exists():
                    shutil.rmtree(extract_tmp_dir, ignore_errors=True)
            except Exception:
                pass
            try:
                if target_tmp_dir.exists():
                    shutil.rmtree(target_tmp_dir, ignore_errors=True)
            except Exception:
                pass
