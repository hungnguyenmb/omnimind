import datetime as dt
import os
import platform
import re
import shlex
import subprocess
from pathlib import Path


class SkillActionRunnerRegistry:
    """
    Runner registry cho các runtime actions built-in.
    Các action này chạy qua SkillRuntimeManager + ActionExecutor để đảm bảo gate quyền.
    """

    ACTIONS = {
        "runtime_ping": {"capabilities": [], "runner": "_run_runtime_ping"},
        "screen_capture": {"capabilities": ["screen_capture"], "runner": "_run_screen_capture"},
        "camera_snapshot": {"capabilities": ["camera_access"], "runner": "_run_camera_snapshot"},
        "ui_automation_type_text": {"capabilities": ["ui_automation"], "runner": "_run_ui_automation_type_text"},
        "system_restart": {"capabilities": ["system_restart"], "runner": "_run_system_restart"},
    }

    def __init__(self):
        self.os_name = platform.system()
        self.artifacts_dir = self._resolve_artifacts_dir()
        try:
            self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            fallback = Path(os.environ.get("OMNIMIND_RUNTIME_ARTIFACTS_DIR", "")).expanduser()
            if not str(fallback).strip():
                fallback = Path.cwd() / ".omnimind_runtime_artifacts"
            fallback.mkdir(parents=True, exist_ok=True)
            self.artifacts_dir = fallback

    @staticmethod
    def _safe_name(name: str, fallback: str) -> str:
        cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", str(name or "")).strip("._")
        return cleaned or fallback

    @staticmethod
    def _quote_ps_single(value: str) -> str:
        # Escape single quote for PowerShell string literal.
        return str(value).replace("'", "''")

    def _resolve_artifacts_dir(self) -> Path:
        env_dir = os.environ.get("OMNIMIND_RUNTIME_ARTIFACTS_DIR", "").strip()
        if env_dir:
            return Path(env_dir).expanduser()
        if self.os_name == "Windows":
            base = os.environ.get("LOCALAPPDATA", os.path.expanduser("~\\AppData\\Local"))
            return Path(base) / "OmniMind" / "runtime_artifacts"
        if self.os_name == "Darwin":
            return Path(os.path.expanduser("~/Library/Application Support")) / "OmniMind" / "runtime_artifacts"
        return Path(os.path.expanduser("~/.omnimind")) / "runtime_artifacts"

    def get_action_meta(self, action_id: str) -> dict:
        key = str(action_id or "").strip().lower()
        return dict(self.ACTIONS.get(key, {}))

    def execute(self, action_id: str, payload: dict | None = None) -> dict:
        payload = payload or {}
        key = str(action_id or "").strip().lower()
        meta = self.ACTIONS.get(key)
        if not meta:
            return {"success": False, "code": "ACTION_NOT_SUPPORTED", "message": f"Action không hỗ trợ: {action_id}"}

        runner = getattr(self, meta["runner"], None)
        if not runner:
            return {"success": False, "code": "RUNNER_MISSING", "message": f"Thiếu runner cho action: {action_id}"}
        return runner(payload)

    def _build_output_path(self, prefix: str, ext: str, subdir: str = "") -> Path:
        now = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_prefix = self._safe_name(prefix, "artifact")
        safe_ext = self._safe_name(ext.lstrip("."), "bin")
        out_dir = self.artifacts_dir
        if subdir:
            out_dir = out_dir / self._safe_name(subdir, "default")
        out_dir.mkdir(parents=True, exist_ok=True)
        return out_dir / f"{safe_prefix}_{now}.{safe_ext}"

    @staticmethod
    def _windows_hidden_subprocess_kwargs() -> dict:
        if platform.system() != "Windows":
            return {}
        kwargs: dict = {}
        create_no_window = int(getattr(subprocess, "CREATE_NO_WINDOW", 0) or 0)
        if create_no_window:
            kwargs["creationflags"] = create_no_window
        startupinfo_cls = getattr(subprocess, "STARTUPINFO", None)
        if startupinfo_cls:
            startupinfo = startupinfo_cls()
            startupinfo.dwFlags |= int(getattr(subprocess, "STARTF_USESHOWWINDOW", 0) or 0)
            startupinfo.wShowWindow = int(getattr(subprocess, "SW_HIDE", 0) or 0)
            kwargs["startupinfo"] = startupinfo
        return kwargs

    @staticmethod
    def _run_cmd(args, timeout=20):
        proc = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            **SkillActionRunnerRegistry._windows_hidden_subprocess_kwargs(),
        )
        return {
            "ok": proc.returncode == 0,
            "returncode": proc.returncode,
            "stdout": (proc.stdout or "").strip(),
            "stderr": (proc.stderr or "").strip(),
        }

    def _run_runtime_ping(self, payload: dict) -> dict:
        return {
            "success": True,
            "code": "PONG",
            "message": "Runtime action pipeline hoạt động.",
            "payload": payload or {},
        }

    def _run_screen_capture(self, payload: dict) -> dict:
        subdir = str((payload or {}).get("subdir", "screenshots")).strip() or "screenshots"
        out_path = self._build_output_path("screen", "png", subdir=subdir)

        if self.os_name == "Darwin":
            rs = self._run_cmd(["screencapture", "-x", str(out_path)], timeout=30)
            if not rs["ok"]:
                return {
                    "success": False,
                    "code": "SCREEN_CAPTURE_FAILED",
                    "message": rs["stderr"] or "Không thể chụp màn hình trên macOS.",
                }
            return {
                "success": out_path.exists(),
                "code": "SCREEN_CAPTURED" if out_path.exists() else "SCREEN_CAPTURE_FAILED",
                "message": "Đã chụp màn hình thành công." if out_path.exists() else "Không tìm thấy file ảnh sau khi chụp.",
                "artifact_path": str(out_path),
            }

        if self.os_name == "Windows":
            ps_script = (
                "Add-Type -AssemblyName System.Windows.Forms; "
                "Add-Type -AssemblyName System.Drawing; "
                "$b=[System.Windows.Forms.SystemInformation]::VirtualScreen; "
                "$bmp=New-Object System.Drawing.Bitmap $b.Width,$b.Height; "
                "$g=[System.Drawing.Graphics]::FromImage($bmp); "
                "$g.CopyFromScreen($b.X,$b.Y,0,0,$bmp.Size); "
                f"$bmp.Save('{self._quote_ps_single(str(out_path))}',[System.Drawing.Imaging.ImageFormat]::Png); "
                "$g.Dispose(); $bmp.Dispose();"
            )
            rs = self._run_cmd(["powershell", "-NoProfile", "-Command", ps_script], timeout=40)
            if not rs["ok"]:
                return {
                    "success": False,
                    "code": "SCREEN_CAPTURE_FAILED",
                    "message": rs["stderr"] or rs["stdout"] or "Không thể chụp màn hình trên Windows.",
                }
            return {
                "success": out_path.exists(),
                "code": "SCREEN_CAPTURED" if out_path.exists() else "SCREEN_CAPTURE_FAILED",
                "message": "Đã chụp màn hình thành công." if out_path.exists() else "Không tìm thấy file ảnh sau khi chụp.",
                "artifact_path": str(out_path),
            }

        rs = self._run_cmd(["sh", "-lc", f"import -window root {shlex.quote(str(out_path))}"], timeout=30)
        if not rs["ok"]:
            return {
                "success": False,
                "code": "SCREEN_CAPTURE_NOT_AVAILABLE",
                "message": "HĐH hiện tại chưa có runner chụp màn hình (cần ImageMagick: import).",
            }
        return {
            "success": out_path.exists(),
            "code": "SCREEN_CAPTURED" if out_path.exists() else "SCREEN_CAPTURE_FAILED",
            "message": "Đã chụp màn hình thành công." if out_path.exists() else "Không tìm thấy file ảnh sau khi chụp.",
            "artifact_path": str(out_path),
        }

    def _run_camera_snapshot(self, payload: dict) -> dict:
        return {
            "success": False,
            "code": "CAMERA_RUNNER_TODO",
            "message": "Runner camera snapshot chưa được cài đặt binary capture phù hợp trên máy.",
        }

    def _run_ui_automation_type_text(self, payload: dict) -> dict:
        text = str((payload or {}).get("text", "")).strip()
        if not text:
            return {"success": False, "code": "INVALID_PAYLOAD", "message": "Thiếu payload.text để nhập liệu."}

        if self.os_name == "Darwin":
            escaped = text.replace("\\", "\\\\").replace('"', '\\"')
            rs = self._run_cmd(["osascript", "-e", f'tell application "System Events" to keystroke "{escaped}"'])
            if not rs["ok"]:
                return {
                    "success": False,
                    "code": "UI_AUTOMATION_FAILED",
                    "message": rs["stderr"] or "Không thể gửi keystroke qua System Events.",
                }
            return {"success": True, "code": "UI_AUTOMATION_DONE", "message": "Đã gửi keystroke thành công."}

        if self.os_name == "Windows":
            escaped = self._quote_ps_single(text)
            ps = (
                "Add-Type -AssemblyName System.Windows.Forms; "
                f"[System.Windows.Forms.SendKeys]::SendWait('{escaped}');"
            )
            rs = self._run_cmd(["powershell", "-NoProfile", "-Command", ps], timeout=20)
            if not rs["ok"]:
                return {
                    "success": False,
                    "code": "UI_AUTOMATION_FAILED",
                    "message": rs["stderr"] or rs["stdout"] or "Không thể gửi keystroke bằng SendKeys.",
                }
            return {"success": True, "code": "UI_AUTOMATION_DONE", "message": "Đã gửi keystroke thành công."}

        return {
            "success": False,
            "code": "UI_AUTOMATION_NOT_SUPPORTED",
            "message": "HĐH hiện tại chưa hỗ trợ runner UI automation type text.",
        }

    def _run_system_restart(self, payload: dict) -> dict:
        payload = payload or {}
        confirm = bool(payload.get("confirm"))
        dry_run = bool(payload.get("dry_run", True))
        if not confirm:
            return {
                "success": False,
                "code": "RESTART_CONFIRM_REQUIRED",
                "message": "Action restart yêu cầu payload.confirm=true.",
            }

        cmd = []
        if self.os_name == "Darwin":
            cmd = ["sudo", "shutdown", "-r", "now"]
        elif self.os_name == "Windows":
            cmd = ["shutdown", "/r", "/t", "0"]
        else:
            cmd = ["shutdown", "-r", "now"]

        if dry_run:
            return {
                "success": True,
                "code": "RESTART_DRY_RUN",
                "message": "Dry-run: đã xác nhận luồng restart, chưa thực thi lệnh.",
                "command_preview": " ".join(cmd),
            }

        rs = self._run_cmd(cmd, timeout=15)
        if not rs["ok"]:
            return {
                "success": False,
                "code": "RESTART_FAILED",
                "message": rs["stderr"] or rs["stdout"] or "Không thể gửi lệnh restart hệ thống.",
                "command_preview": " ".join(cmd),
            }
        return {
            "success": True,
            "code": "RESTART_TRIGGERED",
            "message": "Lệnh restart đã được gửi tới hệ điều hành.",
            "command_preview": " ".join(cmd),
        }
