import logging
import threading
import time
from datetime import datetime, timezone
from typing import Optional

from engine.config_manager import ConfigManager
from engine.openzca_manager import OpenZcaManager

logger = logging.getLogger(__name__)


class ZaloConnectionMonitor:
    POLL_INTERVAL_SEC = 120
    ALERT_COOLDOWN_SEC = 30 * 60
    QR_WAIT_TIMEOUT_SEC = 120

    def __init__(self, openzca_manager: Optional[OpenZcaManager] = None):
        self._manager = openzca_manager or OpenZcaManager()
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    @staticmethod
    def _utc_now_iso() -> str:
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    @staticmethod
    def _parse_iso_ts(raw: str) -> float:
        text = str(raw or "").strip()
        if not text:
            return 0.0
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()
        except Exception:
            return 0.0

    def is_running(self) -> bool:
        thread = self._thread
        return bool(thread and thread.is_alive())

    def start(self):
        with self._lock:
            if self.is_running():
                return
            self._stop_event.clear()
            self._thread = threading.Thread(target=self._run_loop, name="omnimind-zalo-monitor", daemon=True)
            self._thread.start()

    def stop(self):
        with self._lock:
            self._stop_event.set()
            thread = self._thread
        if thread:
            thread.join(timeout=2)
        with self._lock:
            self._thread = None

    def get_status(self) -> dict:
        runtime = ConfigManager.get_zalo_runtime_config()
        conn = ConfigManager.get_zalo_connection_status()
        return {
            **runtime,
            **conn,
            "monitor_running": self.is_running(),
        }

    def mark_qr_required(self, qr_path: str = "") -> dict:
        ConfigManager.set("zalo_login_state", "qr_required")
        ConfigManager.set("zalo_qr_requested_at", self._utc_now_iso())
        if qr_path:
            ConfigManager.set("zalo_qr_path", str(qr_path))
        ConfigManager.set("zalo_last_monitor_error", "")
        return self.get_status()

    def mark_reauth_required(self, reason: str = "") -> dict:
        previous = ConfigManager.get_zalo_login_state()
        ConfigManager.set("zalo_login_state", "re_auth_required")
        if reason:
            ConfigManager.set("zalo_last_monitor_error", str(reason))
        self._maybe_send_telegram_alert(
            title="Zalo cần đăng nhập lại",
            detail=reason or "Session Zalo không còn hợp lệ.",
            previous_state=previous,
            new_state="re_auth_required",
        )
        return self.get_status()

    def _run_loop(self):
        while not self._stop_event.is_set():
            try:
                self.refresh_once()
            except Exception as e:
                logger.exception("Zalo monitor refresh failed")
                ConfigManager.set("zalo_last_monitor_error", str(e)[:220])
            self._stop_event.wait(self.POLL_INTERVAL_SEC)

    def refresh_once(self) -> dict:
        with self._lock:
            runtime = self._manager.inspect_runtime()
            current_state = ConfigManager.get_zalo_login_state()
            if not runtime.get("openzca_ready"):
                if current_state == "connected":
                    return self.mark_reauth_required("OpenZCA runtime không còn sẵn sàng.")
                ConfigManager.set("zalo_last_monitor_error", runtime.get("message", "OpenZCA chưa sẵn sàng."))
                return self.get_status()

            auth = self._manager.run_auth_status()
            now_iso = self._utc_now_iso()

            if auth.get("logged_in"):
                ConfigManager.set("zalo_login_state", "connected")
                ConfigManager.set("zalo_self_user_id", str(auth.get("self_user_id") or "").strip())
                if current_state != "connected":
                    ConfigManager.set("zalo_last_connected_at", now_iso)
                ConfigManager.set("zalo_last_auth_ok_at", now_iso)
                ConfigManager.set("zalo_last_heartbeat_at", now_iso)
                ConfigManager.set("zalo_last_monitor_error", "")
                ConfigManager.set("zalo_qr_requested_at", "")
                return self.get_status()

            if current_state == "qr_required":
                qr_requested_at = ConfigManager.get("zalo_qr_requested_at", "")
                started_ts = self._parse_iso_ts(qr_requested_at)
                if started_ts and (time.time() - started_ts) < self.QR_WAIT_TIMEOUT_SEC:
                    ConfigManager.set("zalo_last_monitor_error", "")
                    return self.get_status()
                ConfigManager.set("zalo_login_state", "not_logged_in")
                ConfigManager.set("zalo_qr_requested_at", "")
                ConfigManager.set("zalo_qr_path", "")
                ConfigManager.set("zalo_last_monitor_error", "")
                return self.get_status()

            had_session_before = bool(
                ConfigManager.get("zalo_last_connected_at", "").strip()
                or ConfigManager.get("zalo_last_auth_ok_at", "").strip()
                or current_state in {"connected", "re_auth_required"}
            )
            if had_session_before:
                return self.mark_reauth_required(auth.get("message", "Session Zalo không còn hợp lệ."))

            ConfigManager.set("zalo_login_state", "not_logged_in")
            ConfigManager.set("zalo_qr_requested_at", "")
            ConfigManager.set("zalo_last_monitor_error", "")
            return self.get_status()

    def _maybe_send_telegram_alert(self, title: str, detail: str, previous_state: str, new_state: str):
        if previous_state == new_state:
            return
        last_sent = self._parse_iso_ts(ConfigManager.get("zalo_last_reauth_alert_at", ""))
        now_ts = time.time()
        if last_sent and (now_ts - last_sent) < self.ALERT_COOLDOWN_SEC:
            return

        cfg = ConfigManager.get_telegram_config()
        token = str(cfg.get("token") or "").strip()
        chat_id = str(cfg.get("chat_id") or "").strip()
        if not token or not chat_id:
            return

        try:
            from engine.telegram_bot_service import TelegramStreamTransport

            transport = TelegramStreamTransport(token)
            body = (
                "⚠️ Cảnh báo Zalo OmniMind\n"
                f"Trạng thái: {title}\n"
                f"Chi tiết: {detail}\n"
                "Vui lòng mở phần cấu hình Zalo để đăng nhập lại."
            )
            transport.send_text_chunks(chat_id, body)
            ConfigManager.set("zalo_last_reauth_alert_at", self._utc_now_iso())
        except Exception as e:
            logger.warning(f"Cannot send Zalo Telegram alert: {e}")


_GLOBAL_ZALO_MONITOR: Optional[ZaloConnectionMonitor] = None
_GLOBAL_ZALO_MONITOR_LOCK = threading.Lock()


def get_global_zalo_connection_monitor() -> ZaloConnectionMonitor:
    global _GLOBAL_ZALO_MONITOR
    with _GLOBAL_ZALO_MONITOR_LOCK:
        if _GLOBAL_ZALO_MONITOR is None:
            _GLOBAL_ZALO_MONITOR = ZaloConnectionMonitor()
        return _GLOBAL_ZALO_MONITOR


def stop_global_zalo_connection_monitor():
    global _GLOBAL_ZALO_MONITOR
    with _GLOBAL_ZALO_MONITOR_LOCK:
        monitor = _GLOBAL_ZALO_MONITOR
    if monitor:
        try:
            monitor.stop()
        except Exception:
            pass
