import ctypes
import logging
import platform
import subprocess
import sys
from typing import Optional

logger = logging.getLogger(__name__)


class PermissionManager:
    """
    Quản lý trạng thái và luồng yêu cầu quyền hệ thống.
    Nguồn sự thật là trạng thái thực tế từ OS (best-effort), không dựa vào config cache.
    """

    SUPPORTED_PERMISSIONS = ("accessibility", "screenshot", "camera")

    @staticmethod
    def get_app_display_name() -> str:
        return "OmniMind" if bool(getattr(sys, "frozen", False)) else "Python"

    def get_status(self) -> dict:
        return {
            "accessibility": self.get_permission_state("accessibility"),
            "screenshot": self.get_permission_state("screenshot"),
            "camera": self.get_permission_state("camera"),
        }

    def get_permission_state(self, permission: str) -> Optional[bool]:
        if permission not in self.SUPPORTED_PERMISSIONS:
            return None

        sys_name = platform.system()
        if sys_name == "Darwin":
            return self._get_macos_permission_state(permission)

        # Windows/Linux: chưa có probe ổn định chung cho desktop app trong codebase hiện tại.
        return None

    def ensure(self, permission: str) -> dict:
        state = self.get_permission_state(permission)
        if state is True:
            return {"success": True, "granted": True, "permission": permission}
        if state is False:
            return {
                "success": False,
                "granted": False,
                "permission": permission,
                "code": "PERMISSION_REQUIRED",
                "message": f"Thiếu quyền hệ thống: {permission}",
            }
        return {
            "success": False,
            "granted": None,
            "permission": permission,
            "code": "PERMISSION_UNKNOWN",
            "message": f"Không xác định được trạng thái quyền: {permission}",
        }

    def request(self, permission: str) -> dict:
        if permission not in self.SUPPORTED_PERMISSIONS:
            return {
                "success": False,
                "permission": permission,
                "open_mode": "failed",
                "message": f"Permission không được hỗ trợ: {permission}",
            }

        sys_name = platform.system()
        if sys_name == "Darwin":
            prompted = self._request_macos_native_prompt(permission)
            mode = self._open_macos_settings(permission)
            return {
                "success": mode != "failed",
                "permission": permission,
                "platform": "Darwin",
                "open_mode": mode,
                "prompted": prompted,
            }

        if sys_name == "Windows":
            mode = self._open_windows_settings(permission)
            return {
                "success": mode != "failed",
                "permission": permission,
                "platform": "Windows",
                "open_mode": mode,
            }

        return {
            "success": False,
            "permission": permission,
            "platform": sys_name,
            "open_mode": "unsupported",
            "message": f"HĐH {sys_name} chưa hỗ trợ mở quyền tự động.",
        }

    def _get_macos_permission_state(self, permission: str) -> Optional[bool]:
        if permission == "accessibility":
            return self._get_macos_accessibility_state()
        if permission == "screenshot":
            return self._get_macos_screenshot_state()
        if permission == "camera":
            return self._get_macos_camera_state()
        return None

    @staticmethod
    def _open_target(cmd) -> bool:
        try:
            proc = subprocess.run(
                cmd,
                shell=isinstance(cmd, str),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                timeout=8,
                check=False,
            )
            if proc.returncode == 0:
                return True
            err = (proc.stderr or b"").decode(errors="ignore").strip()
            if err:
                logger.warning(f"Open permission settings failed: {err}")
            else:
                logger.warning(f"Open permission settings failed with return code {proc.returncode}")
        except Exception as e:
            logger.error(f"Open permission settings failed: {e}")
        return False

    def _open_macos_settings(self, permission: str) -> str:
        anchor_map = {
            "accessibility": "Privacy_Accessibility",
            "screenshot": "Privacy_ScreenCapture",
            "camera": "Privacy_Camera",
        }
        anchor = anchor_map.get(permission)
        if not anchor:
            return "failed"

        urls = [
            f"x-apple.systemsettings:com.apple.preference.security?{anchor}",
            f"x-apple.systempreferences:com.apple.preference.security?{anchor}",
        ]
        for url in urls:
            if self._open_target(["open", url]):
                return "anchor"
        if self._open_target(["open", "-a", "System Settings"]) or self._open_target(
            ["open", "-a", "System Preferences"]
        ):
            return "settings"
        return "failed"

    def _open_windows_settings(self, permission: str) -> str:
        cmd_map = {
            "accessibility": "start ms-settings:easeofaccess-keyboard",
            "screenshot": "start ms-settings:privacy",
            "camera": "start ms-settings:privacy-webcam",
        }
        cmd = cmd_map.get(permission)
        if not cmd:
            return "failed"
        return "settings" if self._open_target(cmd) else "failed"

    @staticmethod
    def _get_macos_accessibility_state() -> Optional[bool]:
        try:
            from ApplicationServices import AXIsProcessTrusted

            return bool(AXIsProcessTrusted())
        except Exception as e:
            logger.info(f"Permission probe accessibility unavailable via pyobjc: {e}")
            try:
                lib = ctypes.cdll.LoadLibrary(
                    "/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices"
                )
                lib.AXIsProcessTrusted.restype = ctypes.c_bool
                return bool(lib.AXIsProcessTrusted())
            except Exception as ee:
                logger.info(f"Permission probe accessibility unavailable via ctypes: {ee}")
                return None

    @staticmethod
    def _get_macos_screenshot_state() -> Optional[bool]:
        try:
            from Quartz import CGPreflightScreenCaptureAccess

            return bool(CGPreflightScreenCaptureAccess())
        except Exception as e:
            logger.info(f"Permission probe screenshot unavailable via pyobjc: {e}")
            try:
                lib = ctypes.cdll.LoadLibrary("/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics")
                probe = getattr(lib, "CGPreflightScreenCaptureAccess", None)
                if probe:
                    probe.restype = ctypes.c_bool
                    return bool(probe())
            except Exception as ee:
                logger.info(f"Permission probe screenshot unavailable via ctypes: {ee}")
            return None

    @staticmethod
    def _get_macos_camera_state() -> Optional[bool]:
        try:
            from AVFoundation import AVCaptureDevice, AVMediaTypeVideo

            status = int(AVCaptureDevice.authorizationStatusForMediaType_(AVMediaTypeVideo))
            # AVAuthorizationStatusAuthorized = 3 trên macOS.
            return status == 3
        except Exception as e:
            logger.info(f"Permission probe camera unavailable: {e}")
            return None

    @staticmethod
    def _request_macos_native_prompt(permission: str) -> bool:
        """
        Thử gọi prompt native nếu hệ thống có pyobjc.
        Nếu không khả dụng thì fallback qua mở Settings ở layer trên.
        """
        try:
            if permission == "accessibility":
                from ApplicationServices import AXIsProcessTrustedWithOptions, kAXTrustedCheckOptionPrompt

                AXIsProcessTrustedWithOptions({kAXTrustedCheckOptionPrompt: True})
                return True
            if permission == "screenshot":
                from Quartz import CGRequestScreenCaptureAccess

                CGRequestScreenCaptureAccess()
                return True
            if permission == "camera":
                from AVFoundation import AVMediaTypeVideo, AVCaptureDevice

                AVCaptureDevice.requestAccessForMediaType_completionHandler_(AVMediaTypeVideo, None)
                return True
        except Exception as e:
            logger.info(f"Native permission prompt unavailable ({permission}): {e}")
            # Fallback cho build không có pyobjc (đặc biệt các bản PyInstaller).
            if permission == "screenshot":
                try:
                    lib = ctypes.cdll.LoadLibrary("/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics")
                    req = getattr(lib, "CGRequestScreenCaptureAccess", None)
                    if req:
                        req.restype = ctypes.c_bool
                        req.argtypes = []
                        return bool(req())
                except Exception as ee:
                    logger.info(f"Native screenshot prompt unavailable via ctypes: {ee}")
        return False
