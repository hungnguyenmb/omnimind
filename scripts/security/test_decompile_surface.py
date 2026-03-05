#!/usr/bin/env python3
"""Sprint 6 - Item 1: decompile/reverse surface check for release artifact."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEXT_EXTENSIONS = {
    ".txt",
    ".md",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".cfg",
    ".env",
    ".xml",
    ".csv",
    ".log",
}
MAX_TEXT_BYTES = 2 * 1024 * 1024
MAX_BINARY_SAMPLE_BYTES = 4 * 1024 * 1024
ASCII_RE = re.compile(rb"[ -~]{6,}")

FAIL_PATTERNS = {
    "jwt_like_token": re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
    "private_key_block": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |)?PRIVATE KEY-----"),
}
TELEGRAM_TOKEN_RE = re.compile(r"\b(\d{8,10}):([A-Za-z0-9_-]{30,90})\b")
WARN_KEYWORDS = [
    "telegram_token",
    "license_jwt",
    "sepay",
    "webhook_secret",
    "vault_credentials",
]


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _extract_ascii_strings(blob: bytes) -> str:
    parts = [m.group(0).decode("ascii", errors="ignore") for m in ASCII_RE.finditer(blob)]
    return "\n".join(parts)


def _read_binary_sample(path: Path, max_bytes: int = MAX_BINARY_SAMPLE_BYTES) -> bytes:
    size = path.stat().st_size
    if size <= max_bytes:
        return path.read_bytes()
    head = max_bytes // 2
    tail = max_bytes - head
    with open(path, "rb") as f:
        first = f.read(head)
        f.seek(max(size - tail, 0))
        last = f.read(tail)
    return first + b"\n" + last


def _scan_content_for_patterns(content: str) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    failures: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    low = content.lower()

    for name, pattern in FAIL_PATTERNS.items():
        match = pattern.search(content)
        if match:
            snippet = content[max(0, match.start() - 20) : match.end() + 20].replace("\n", " ")
            failures.append({"type": name, "snippet": snippet[:220]})

    for match in TELEGRAM_TOKEN_RE.finditer(content):
        rhs = match.group(2)
        alpha_count = sum(1 for ch in rhs if ch.isalpha())
        if alpha_count < 6:
            continue
        snippet = content[max(0, match.start() - 20) : match.end() + 20].replace("\n", " ")
        failures.append({"type": "telegram_bot_token", "snippet": snippet[:220]})

    for key in WARN_KEYWORDS:
        if key in low:
            warnings.append({"type": "keyword", "keyword": key})
    return failures, warnings


def _scan_tree(root: Path) -> dict[str, Any]:
    plain_python_files: list[str] = []
    fail_findings: list[dict[str, str]] = []
    warn_findings: list[dict[str, str]] = []
    env_like_files: list[str] = []
    file_count = 0
    scanned_content_files = 0

    def _is_third_party(rel_path: str) -> bool:
        low = rel_path.lower()
        return (
            low.startswith("contents/frameworks/")
            or "pyqt5" in low
            or low.startswith("contents/resources/qt")
            or low.startswith("_internal/pyqt5")
        )

    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        file_count += 1
        rel = str(path.relative_to(root))
        suffix = path.suffix.lower()

        if suffix == ".py":
            plain_python_files.append(rel)

        if path.name.lower() in {".env", ".env.local", ".env.production"}:
            env_like_files.append(rel)

        try:
            size = path.stat().st_size
        except Exception:
            continue

        text_payload = ""
        if suffix in TEXT_EXTENSIONS and size <= MAX_TEXT_BYTES:
            try:
                text_payload = path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                text_payload = ""
        else:
            try:
                sample = _read_binary_sample(path)
                text_payload = _extract_ascii_strings(sample)
            except Exception:
                text_payload = ""

        if not text_payload:
            continue
        scanned_content_files += 1
        fails, warns = _scan_content_for_patterns(text_payload)
        for item in fails:
            if _is_third_party(rel) and item.get("type") in {"private_key_block", "telegram_bot_token"}:
                warn_findings.append({"file": rel, "type": "third_party_signature", "detail": item.get("type", "")})
                continue
            fail_findings.append({"file": rel, **item})
        for item in warns:
            warn_findings.append({"file": rel, **item})

    return {
        "files_total": file_count,
        "files_scanned_content": scanned_content_files,
        "plain_python_files": plain_python_files,
        "env_like_files": env_like_files,
        "fail_findings": fail_findings,
        "warn_findings": warn_findings,
    }


def _load_artifact_tree(artifact: Path) -> tuple[Path, tempfile.TemporaryDirectory | None]:
    if artifact.is_dir():
        return artifact, None
    if artifact.is_file() and artifact.suffix.lower() == ".zip":
        tmp = tempfile.TemporaryDirectory(prefix="omnimind-artifact-")
        with zipfile.ZipFile(artifact, "r") as zf:
            zf.extractall(tmp.name)
        return Path(tmp.name), tmp
    raise RuntimeError("Artifact phải là thư mục app hoặc file .zip")


def run_check(artifact: Path) -> dict[str, Any]:
    extracted_root, tmp_handle = _load_artifact_tree(artifact)
    try:
        scan = _scan_tree(extracted_root)
    finally:
        if tmp_handle:
            tmp_handle.cleanup()

    fail_reasons: list[str] = []
    if scan["plain_python_files"]:
        fail_reasons.append(f"Phát hiện {len(scan['plain_python_files'])} file .py trong artifact")
    if scan["fail_findings"]:
        fail_reasons.append(f"Phát hiện {len(scan['fail_findings'])} mẫu dữ liệu nhạy cảm")

    status = "failed" if fail_reasons else "passed"
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "artifact": str(artifact),
        "artifact_sha256": _sha256_file(artifact) if artifact.is_file() else "",
        "status": status,
        "fail_reasons": fail_reasons,
        "summary": {
            "files_total": scan["files_total"],
            "files_scanned_content": scan["files_scanned_content"],
            "plain_python_count": len(scan["plain_python_files"]),
            "fail_finding_count": len(scan["fail_findings"]),
            "warning_count": len(scan["warn_findings"]),
            "env_like_count": len(scan["env_like_files"]),
        },
        "details": scan,
    }
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sprint 6 item 1 - kiểm tra nhanh bề mặt reverse/decompile của release artifact."
    )
    parser.add_argument("--artifact", required=True, help="Đường dẫn artifact (.zip hoặc thư mục app).")
    parser.add_argument(
        "--report",
        default="",
        help="Đường dẫn file JSON report. Mặc định: release-artifacts/security-reports/",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    artifact = Path(args.artifact).expanduser().resolve()
    if not artifact.exists():
        print(f"[FAIL] Artifact không tồn tại: {artifact}")
        return 2

    report = run_check(artifact)
    report_dir = PROJECT_ROOT / "release-artifacts" / "security-reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_file = (
        Path(args.report).expanduser().resolve()
        if args.report
        else report_dir / f"decompile_surface_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    )
    report_file.parent.mkdir(parents=True, exist_ok=True)
    report_file.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("== Sprint 6 / Item 1: Decompile Surface ==")
    print(f"Artifact: {artifact}")
    print(f"Status:   {report['status'].upper()}")
    print(f"Report:   {report_file}")
    print(f"- Tổng file: {report['summary']['files_total']}")
    print(f"- File .py lộ ra: {report['summary']['plain_python_count']}")
    print(f"- Finding fail: {report['summary']['fail_finding_count']}")
    print(f"- Cảnh báo: {report['summary']['warning_count']}")

    if report["status"] != "passed":
        for reason in report.get("fail_reasons", []):
            print(f"[FAIL] {reason}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
