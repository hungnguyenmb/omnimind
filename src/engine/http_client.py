import logging
import random
import socket
import time
from typing import Iterable

import requests

logger = logging.getLogger(__name__)

RETRYABLE_STATUS_CODES = {408, 425, 429, 500, 502, 503, 504}
_DNS_ERROR_PATTERNS = (
    "temporary failure in name resolution",
    "name or service not known",
    "nodename nor servname provided",
    "no address associated with hostname",
    "getaddrinfo failed",
)
_DEFAULT_SESSION = requests.Session()


def _looks_like_temporary_dns_error(exc: Exception) -> bool:
    text = str(exc or "").lower()
    if any(p in text for p in _DNS_ERROR_PATTERNS):
        return True
    cause = getattr(exc, "__cause__", None)
    return isinstance(cause, socket.gaierror)


def _is_retryable_exception(exc: Exception) -> bool:
    if isinstance(exc, (requests.Timeout, requests.ConnectionError)):
        return True
    return _looks_like_temporary_dns_error(exc)


def request_with_retry(
    method: str,
    url: str,
    *,
    session: requests.Session | None = None,
    timeout: int | float = 15,
    max_attempts: int = 3,
    backoff_base: float = 0.8,
    backoff_max: float = 6.0,
    retry_status_codes: Iterable[int] | None = None,
    **kwargs,
) -> requests.Response:
    """
    HTTP request có retry/backoff cho lỗi mạng tạm thời (DNS/timeout/5xx/429).
    - Trả về requests.Response cuối cùng nếu thành công hoặc khi không nên retry.
    - Ném exception khi lỗi mạng và đã hết số lần retry.
    """
    attempts = max(1, int(max_attempts))
    status_codes = set(retry_status_codes or RETRYABLE_STATUS_CODES)
    http = session or _DEFAULT_SESSION
    http_method = str(method or "GET").upper()

    for attempt in range(1, attempts + 1):
        try:
            resp = http.request(http_method, url, timeout=timeout, **kwargs)
        except Exception as exc:
            if attempt >= attempts or not _is_retryable_exception(exc):
                raise
            sleep_sec = min(backoff_max, backoff_base * (2 ** (attempt - 1))) + random.uniform(0.0, 0.25)
            logger.warning(
                "HTTP %s %s attempt %d/%d failed: %s. Retry in %.2fs",
                http_method,
                url,
                attempt,
                attempts,
                exc,
                sleep_sec,
            )
            time.sleep(sleep_sec)
            continue

        if resp.status_code in status_codes and attempt < attempts:
            sleep_sec = min(backoff_max, backoff_base * (2 ** (attempt - 1))) + random.uniform(0.0, 0.25)
            logger.warning(
                "HTTP %s %s returned %s (attempt %d/%d). Retry in %.2fs",
                http_method,
                url,
                resp.status_code,
                attempt,
                attempts,
                sleep_sec,
            )
            time.sleep(sleep_sec)
            continue

        return resp

    raise RuntimeError(f"Unexpected retry state for {http_method} {url}")
