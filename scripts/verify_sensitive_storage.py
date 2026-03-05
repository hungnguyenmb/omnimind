#!/usr/bin/env python3
import argparse
import os
import platform
import sqlite3
import sys
from pathlib import Path

ENC_PREFIX_V1 = "enc:v1:"


def resolve_db_path() -> Path:
    env_db = os.environ.get("OMNIMIND_DB_PATH", "").strip()
    if env_db:
        return Path(env_db).expanduser()

    sys_name = platform.system()
    if sys_name == "Windows":
        base = os.environ.get("LOCALAPPDATA", os.path.expanduser("~\\AppData\\Local"))
        return Path(base) / "OmniMind" / "data" / "omnimind.db"
    if sys_name == "Darwin":
        return Path(os.path.expanduser("~/Library/Application Support")) / "OmniMind" / "data" / "omnimind.db"
    return Path(os.path.expanduser("~/.omnimind")) / "data" / "omnimind.db"


def classify_value(raw: str) -> str:
    text = str(raw or "")
    if not text:
        return "EMPTY"
    if text.startswith(ENC_PREFIX_V1):
        return "ENCRYPTED"
    return "PLAINTEXT"


def check_app_config_sensitive(conn: sqlite3.Connection, key: str) -> tuple[str, str]:
    cur = conn.execute("SELECT value FROM app_configs WHERE key = ?", (key,))
    row = cur.fetchone()
    if not row:
        return "NOT_SET", ""
    value = row[0] if row[0] is not None else ""
    return classify_value(str(value)), str(value)


def check_vault_credentials(conn: sqlite3.Connection) -> tuple[int, int, list[int]]:
    total = conn.execute(
        "SELECT COUNT(*) FROM vault_resources WHERE COALESCE(credentials, '') <> ''"
    ).fetchone()[0]
    encrypted = conn.execute(
        "SELECT COUNT(*) FROM vault_resources WHERE credentials LIKE ?",
        (f"{ENC_PREFIX_V1}%",),
    ).fetchone()[0]
    plaintext_rows = conn.execute(
        """
        SELECT id
        FROM vault_resources
        WHERE COALESCE(credentials, '') <> ''
          AND credentials NOT LIKE ?
        ORDER BY id DESC
        LIMIT 20
        """,
        (f"{ENC_PREFIX_V1}%",),
    ).fetchall()
    ids = [int(r[0]) for r in plaintext_rows]
    return int(total), int(encrypted), ids


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify Sprint 2 sensitive data encryption in OmniMind local SQLite."
    )
    parser.add_argument("--db", default="", help="Override DB path (optional)")
    args = parser.parse_args()

    db_path = Path(args.db).expanduser() if args.db else resolve_db_path()
    if not db_path.exists():
        print(f"[ERROR] DB not found: {db_path}")
        return 2

    conn = sqlite3.connect(str(db_path))
    try:
        tg_state, _ = check_app_config_sensitive(conn, "telegram_token")
        jwt_state, _ = check_app_config_sensitive(conn, "license_jwt")
        vault_total, vault_enc, vault_plain_ids = check_vault_credentials(conn)

        print("== Sprint 2 Sensitive Storage Verify ==")
        print(f"DB: {db_path}")
        print(f"- app_configs.telegram_token: {tg_state}")
        print(f"- app_configs.license_jwt:   {jwt_state}")
        print(f"- vault_resources.credentials: encrypted={vault_enc}/{vault_total}")

        failed = False
        if tg_state == "PLAINTEXT":
            print("  [FAIL] telegram_token đang plaintext")
            failed = True
        if jwt_state == "PLAINTEXT":
            print("  [FAIL] license_jwt đang plaintext")
            failed = True
        if vault_plain_ids:
            print(f"  [FAIL] vault credentials plaintext rows (sample ids): {vault_plain_ids}")
            failed = True

        if failed:
            print("RESULT: FAILED")
            print("Hint: Mở app OmniMind để migration chạy, sau đó verify lại.")
            return 1

        print("RESULT: PASSED")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
