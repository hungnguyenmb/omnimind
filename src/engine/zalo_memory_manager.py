from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from database.db_manager import db

logger = logging.getLogger(__name__)


class ZaloMemoryManager:
    DEFAULT_RECENT_LIMIT = 12
    DEFAULT_FACT_LIMIT = 6
    DEFAULT_SUMMARY_LIMIT = 2
    DEFAULT_CONTEXT_CHAR_BUDGET = 5000
    SUMMARY_SOURCE = "auto-rolling"

    FACT_PATTERNS = [
        re.compile(r"^\s*(tôi muốn|hãy luôn|ưu tiên|đừng|không được)\b.+", re.IGNORECASE),
        re.compile(r"^\s*(toi muon|hay luon|uu tien|dung|khong duoc)\b.+", re.IGNORECASE),
        re.compile(r"^\s*(my preference|always|never|prefer)\b.+", re.IGNORECASE),
    ]
    BOT_PREFIX_RE = re.compile(r"^\s*\*{0,2}\s*(trợ lý|tro ly|omnimind)\s*\*{0,2}\s*[:\-]?\s*", re.IGNORECASE)
    BOT_HEADER_RE = re.compile(r"^\s*\*{0,2}\s*(trả lời|tra loi|response|reply|trợ lý(?:\s+\w+){0,3}|tro ly(?:\s+\w+){0,3})\s*\*{0,2}\s*$", re.IGNORECASE)

    @staticmethod
    def _utc_now() -> datetime:
        return datetime.now(timezone.utc).replace(microsecond=0)

    @classmethod
    def _utc_now_iso(cls) -> str:
        return cls._utc_now().isoformat().replace("+00:00", "Z")

    @staticmethod
    def _to_json(payload: Any, fallback: str = "{}") -> str:
        try:
            return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        except Exception:
            return fallback

    @staticmethod
    def _from_json(raw: str, fallback):
        try:
            data = json.loads(raw or "")
            return data if isinstance(data, type(fallback)) else fallback
        except Exception:
            return fallback

    @staticmethod
    def _shorten(text: str, limit: int = 140) -> str:
        body = " ".join(str(text or "").split())
        if len(body) <= limit:
            return body
        return body[: max(1, limit - 1)].rstrip() + "…"

    @classmethod
    def _sanitize_message_text(cls, text: str, direction: str = "inbound") -> str:
        body = str(text or "").strip()
        if not body:
            return ""
        looks_like_json = (
            (body.startswith("{") and body.endswith("}"))
            or (body.startswith("[") and body.endswith("]"))
        )
        if looks_like_json:
            try:
                parsed = json.loads(body)
                if isinstance(parsed, (dict, list)):
                    return ""
            except Exception:
                pass
        if str(direction or "").strip().lower() == "outbound":
            body = cls.BOT_PREFIX_RE.sub("", body, count=1)
            rows = []
            for idx, raw_line in enumerate(body.splitlines()):
                line = str(raw_line or "").strip()
                if not line:
                    continue
                line = line.replace("**", "").replace("__", "")
                if idx == 0 and cls.BOT_HEADER_RE.match(line):
                    continue
                line = re.sub(r"^\s*[-–—]+\s+", "", line)
                line = re.sub(r"^\s*\d+[.)]\s+", "", line)
                if line:
                    rows.append(line)
            body = "\n".join(rows).strip()
        body = re.sub(r"\n{3,}", "\n\n", body).strip()
        return body

    @classmethod
    def _normalize_timestamp(cls, raw_value: str | int | float | None) -> str:
        if raw_value in (None, ""):
            return cls._utc_now_iso()
        value = str(raw_value).strip()
        if not value:
            return cls._utc_now_iso()
        if value.isdigit():
            try:
                number = int(value)
                if len(value) >= 13:
                    dt = datetime.fromtimestamp(number / 1000.0, tz=timezone.utc)
                else:
                    dt = datetime.fromtimestamp(number, tz=timezone.utc)
                return dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")
            except Exception:
                return cls._utc_now_iso()
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            else:
                dt = dt.astimezone(timezone.utc)
            return dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")
        except Exception:
            return cls._utc_now_iso()

    @staticmethod
    def _fact_key(thread_id: str, fact: str) -> str:
        normalized = f"{str(thread_id or '').strip()}::{ ' '.join(str(fact or '').strip().lower().split()) }"
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    def upsert_thread(
        self,
        thread_id: str,
        chat_type: str = "dm",
        display_name: str = "",
        participant_hint: str = "",
        last_message_at: str = "",
        bootstrap_done: bool | None = None,
        last_bootstrap_at: str = "",
    ) -> bool:
        tid = str(thread_id or "").strip()
        if not tid:
            return False
        existing = self.get_thread(tid)
        next_bootstrap = existing.get("bootstrap_done", 0) if existing else 0
        if bootstrap_done is not None:
            next_bootstrap = 1 if bootstrap_done else 0
        next_last_message_at = str(last_message_at or "").strip() or (existing or {}).get("last_message_at", "")
        next_last_bootstrap_at = str(last_bootstrap_at or "").strip() or (existing or {}).get("last_bootstrap_at", "")
        next_display_name = str(display_name or "").strip() or (existing or {}).get("display_name", "")
        next_participant = str(participant_hint or "").strip() or (existing or {}).get("participant_hint", "")
        next_chat_type = str(chat_type or "").strip() or (existing or {}).get("chat_type", "dm")
        try:
            db.execute_query(
                """
                INSERT INTO zalo_threads (
                    thread_id, chat_type, display_name, participant_hint,
                    last_message_at, last_bootstrap_at, bootstrap_done, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(thread_id) DO UPDATE SET
                    chat_type = excluded.chat_type,
                    display_name = CASE WHEN excluded.display_name != '' THEN excluded.display_name ELSE zalo_threads.display_name END,
                    participant_hint = CASE WHEN excluded.participant_hint != '' THEN excluded.participant_hint ELSE zalo_threads.participant_hint END,
                    last_message_at = CASE WHEN excluded.last_message_at != '' THEN excluded.last_message_at ELSE zalo_threads.last_message_at END,
                    last_bootstrap_at = CASE WHEN excluded.last_bootstrap_at != '' THEN excluded.last_bootstrap_at ELSE zalo_threads.last_bootstrap_at END,
                    bootstrap_done = excluded.bootstrap_done,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    tid,
                    next_chat_type,
                    next_display_name,
                    next_participant,
                    next_last_message_at,
                    next_last_bootstrap_at,
                    next_bootstrap,
                ),
                commit=True,
            )
            return True
        except Exception as e:
            logger.error(f"Cannot upsert Zalo thread {tid}: {e}")
            return False

    def get_thread(self, thread_id: str) -> dict:
        tid = str(thread_id or "").strip()
        if not tid:
            return {}
        try:
            return db.fetch_one("SELECT * FROM zalo_threads WHERE thread_id = ?", (tid,)) or {}
        except Exception as e:
            logger.error(f"Cannot fetch Zalo thread {tid}: {e}")
            return {}

    def has_thread_history(self, thread_id: str) -> bool:
        tid = str(thread_id or "").strip()
        if not tid:
            return False
        try:
            row = db.fetch_one(
                "SELECT COUNT(*) AS cnt FROM zalo_messages WHERE thread_id = ?",
                (tid,),
            )
            return bool(int((row or {}).get("cnt", 0) or 0))
        except Exception as e:
            logger.error(f"Cannot inspect Zalo history for {tid}: {e}")
            return False

    def append_message(
        self,
        thread_id: str,
        chat_type: str,
        sender_id: str,
        content: str,
        direction: str = "inbound",
        message_id: str = "",
        mentions: list[str] | None = None,
        raw_payload: dict | None = None,
        timestamp: str = "",
    ) -> int | None:
        tid = str(thread_id or "").strip()
        body = str(content or "").strip()
        if not tid or not body:
            return None
        direction_norm = "outbound" if str(direction or "").strip().lower() == "outbound" else "inbound"
        body = self._sanitize_message_text(body, direction_norm)
        if not body:
            return None
        msg_id = str(message_id or "").strip()
        ts = self._normalize_timestamp(timestamp)
        if msg_id:
            existed = db.fetch_one(
                "SELECT id FROM zalo_messages WHERE thread_id = ? AND message_id = ? LIMIT 1",
                (tid, msg_id),
            )
            if existed and existed.get("id"):
                return int(existed["id"])
        else:
            existed = db.fetch_one(
                """
                SELECT id FROM zalo_messages
                WHERE thread_id = ? AND sender_id = ? AND content = ? AND timestamp = ?
                LIMIT 1
                """,
                (tid, str(sender_id or "").strip(), body, ts),
            )
            if existed and existed.get("id"):
                return int(existed["id"])
        try:
            row_id = db.execute_query(
                """
                INSERT INTO zalo_messages (
                    thread_id, chat_type, sender_id, message_id,
                    direction, content, mentions_json, raw_json, timestamp
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    tid,
                    str(chat_type or "dm").strip() or "dm",
                    str(sender_id or "").strip(),
                    msg_id,
                    direction_norm,
                    body,
                    self._to_json(mentions or [], fallback="[]"),
                    self._to_json(raw_payload or {}, fallback="{}"),
                    ts,
                ),
                commit=True,
            )
            self.upsert_thread(thread_id=tid, chat_type=chat_type, last_message_at=ts)
            if direction_norm != "outbound":
                self._extract_thread_fact(tid, body, ts)
            return row_id
        except Exception as e:
            logger.error(f"Cannot append Zalo message {tid}/{msg_id or 'no-id'}: {e}")
            return None

    def import_recent_messages(
        self,
        thread_id: str,
        chat_type: str,
        messages: list[dict],
        self_user_id: str = "",
    ) -> int:
        count = 0
        tid = str(thread_id or "").strip()
        ctype = str(chat_type or "dm").strip() or "dm"
        own_id = str(self_user_id or "").strip()
        for item in messages or []:
            if not isinstance(item, dict):
                continue
            sender_id = self._find_first_value(item, ("senderId", "sender_id", "fromId", "uid", "userId", "actorId"))
            content = self._find_text_value(item)
            message_id = self._find_first_value(item, ("msgId", "messageId", "message_id", "cliMsgId"))
            timestamp = self._find_first_value(item, ("timestamp", "ts", "msgTime", "clientTimestamp", "time", "createdAt"))
            mentions = self._extract_mentions(item)
            direction = "outbound" if self._infer_is_self(item, sender_id, own_id) else "inbound"
            if not content:
                continue
            row_id = self.append_message(
                thread_id=tid,
                chat_type=ctype,
                sender_id=sender_id or ("self" if direction == "outbound" else ""),
                content=content,
                direction=direction,
                message_id=message_id,
                mentions=mentions,
                raw_payload=item,
                timestamp=timestamp,
            )
            if row_id:
                count += 1
        if tid:
            self.upsert_thread(thread_id=tid, chat_type=ctype, bootstrap_done=True, last_bootstrap_at=self._utc_now_iso())
        return count

    def get_recent_messages(self, thread_id: str, limit: int = DEFAULT_RECENT_LIMIT) -> list[dict]:
        tid = str(thread_id or "").strip()
        take = max(1, min(100, int(limit or self.DEFAULT_RECENT_LIMIT)))
        if not tid:
            return []
        try:
            rows = db.fetch_all(
                """
                SELECT id, thread_id, chat_type, sender_id, message_id, direction,
                       content, mentions_json, raw_json, timestamp, created_at
                FROM zalo_messages
                WHERE thread_id = ?
                ORDER BY timestamp DESC, id DESC
                LIMIT ?
                """,
                (tid, take),
            )
        except Exception as e:
            logger.error(f"Cannot fetch recent Zalo messages for {tid}: {e}")
            return []
        rows.reverse()
        out = []
        for row in rows:
            out.append(
                {
                    **row,
                    "mentions": self._from_json(row.get("mentions_json", "[]"), []),
                    "raw_payload": self._from_json(row.get("raw_json", "{}"), {}),
                }
            )
        return out

    def get_latest_summary(self, thread_id: str) -> dict:
        tid = str(thread_id or "").strip()
        if not tid:
            return {}
        try:
            return db.fetch_one(
                """
                SELECT id, thread_id, summary_text, from_ts, to_ts, message_count, source, updated_at
                FROM zalo_thread_summaries
                WHERE thread_id = ?
                ORDER BY updated_at DESC, id DESC
                LIMIT 1
                """,
                (tid,),
            ) or {}
        except Exception as e:
            logger.error(f"Cannot fetch latest Zalo summary for {tid}: {e}")
            return {}

    def get_recent_summaries(self, thread_id: str, limit: int = DEFAULT_SUMMARY_LIMIT, within_days: int = 30) -> list[dict]:
        tid = str(thread_id or "").strip()
        take = max(1, min(20, int(limit or self.DEFAULT_SUMMARY_LIMIT)))
        threshold = (self._utc_now() - timedelta(days=max(1, int(within_days or 30)))).strftime("%Y-%m-%d %H:%M:%S")
        if not tid:
            return []
        try:
            rows = db.fetch_all(
                """
                SELECT id, thread_id, summary_text, from_ts, to_ts, message_count, source, updated_at
                FROM zalo_thread_summaries
                WHERE thread_id = ? AND datetime(updated_at) >= datetime(?)
                ORDER BY updated_at DESC, id DESC
                LIMIT ?
                """,
                (tid, threshold, take),
            )
            rows.reverse()
            return rows
        except Exception as e:
            logger.error(f"Cannot fetch recent Zalo summaries for {tid}: {e}")
            return []

    def thread_has_usable_summary(self, thread_id: str) -> bool:
        summary = self.get_latest_summary(thread_id)
        return bool(str((summary or {}).get("summary_text") or "").strip())

    def get_thread_facts(self, thread_id: str, limit: int = DEFAULT_FACT_LIMIT) -> list[dict]:
        tid = str(thread_id or "").strip()
        take = max(1, min(20, int(limit or self.DEFAULT_FACT_LIMIT)))
        if not tid:
            return []
        try:
            return db.fetch_all(
                """
                SELECT id, thread_id, fact, confidence, hit_count, last_seen_at, created_at, updated_at
                FROM zalo_thread_facts
                WHERE thread_id = ?
                ORDER BY hit_count DESC, confidence DESC, updated_at DESC
                LIMIT ?
                """,
                (tid, take),
            )
        except Exception as e:
            logger.error(f"Cannot fetch Zalo facts for {tid}: {e}")
            return []

    def build_thread_context(
        self,
        thread_id: str,
        message_limit: int = 8,
        facts_limit: int = DEFAULT_FACT_LIMIT,
        summary_limit: int = DEFAULT_SUMMARY_LIMIT,
        char_budget: int = DEFAULT_CONTEXT_CHAR_BUDGET,
    ) -> dict:
        tid = str(thread_id or "").strip()
        budget = max(1500, int(char_budget or self.DEFAULT_CONTEXT_CHAR_BUDGET))
        take_messages = max(30, min(240, int(message_limit or 8) * 6))
        take_facts = max(1, min(20, int(facts_limit or self.DEFAULT_FACT_LIMIT)))
        take_summaries = max(1, min(6, int(summary_limit or self.DEFAULT_SUMMARY_LIMIT)))

        thread = self.get_thread(tid)
        facts = self.get_thread_facts(tid, limit=take_facts)
        summaries = self.get_recent_summaries(tid, limit=take_summaries)
        latest_summary = summaries[-1] if summaries else self.get_latest_summary(tid)
        messages = self.get_recent_messages(tid, limit=take_messages)
        turns = self._build_turns(messages, max_turns=max(12, min(120, int(message_limit or 8) * 3)))

        spent = 0
        compact_summaries: list[dict] = []
        compact_facts: list[dict] = []
        compact_turns: list[dict] = []

        for summary in reversed(summaries):
            text = str((summary or {}).get("summary_text") or "").strip()
            if not text:
                continue
            if spent + len(text) > budget:
                continue
            compact_summaries.append(summary)
            spent += len(text)
        compact_summaries.reverse()

        for fact in facts:
            text = str((fact or {}).get("fact") or "").strip()
            if not text:
                continue
            if spent + len(text) > budget:
                break
            compact_facts.append(fact)
            spent += len(text)

        for turn in reversed(turns):
            user_text = str(((turn.get("user") or {}).get("content")) or "")
            assistant_text = str(((turn.get("assistant") or {}).get("content")) or "")
            turn_chars = len(user_text) + len(assistant_text)
            if turn_chars <= 0:
                continue
            if spent + turn_chars > budget:
                break
            compact_turns.append(turn)
            spent += turn_chars
        compact_turns.reverse()

        return {
            "thread": thread,
            "latest_summary": latest_summary,
            "summaries": compact_summaries,
            "facts": compact_facts,
            "recent_turns": compact_turns,
            "context_char_budget": budget,
            "context_char_used": spent,
        }

    def refresh_thread_summary(self, thread_id: str, force: bool = False) -> dict:
        tid = str(thread_id or "").strip()
        messages = self.get_recent_messages(tid, limit=14)
        if len(messages) < 2:
            return {}
        last_summary = self.get_latest_summary(tid)
        current_to_ts = str((messages[-1] or {}).get("timestamp") or "").strip()
        if not force and str((last_summary or {}).get("to_ts") or "").strip() == current_to_ts:
            return last_summary
        summary_text = self._build_summary_text(messages)
        if not summary_text:
            return {}
        from_ts = str((messages[0] or {}).get("timestamp") or "").strip()
        try:
            db.execute_query(
                """
                INSERT INTO zalo_thread_summaries (
                    thread_id, summary_text, from_ts, to_ts, message_count, source, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """,
                (tid, summary_text, from_ts, current_to_ts, len(messages), self.SUMMARY_SOURCE),
                commit=True,
            )
        except Exception as e:
            logger.error(f"Cannot persist Zalo summary for {tid}: {e}")
            return {}
        return self.get_latest_summary(tid)

    def cleanup_expired_data(
        self,
        raw_retention_days: int = 3,
        summary_retention_days: int = 30,
        delete_raw_only_when_summarized: bool = True,
    ) -> dict:
        raw_cutoff = (self._utc_now() - timedelta(days=max(1, int(raw_retention_days or 3)))).isoformat().replace("+00:00", "Z")
        summary_cutoff = (self._utc_now() - timedelta(days=max(1, int(summary_retention_days or 30)))).strftime("%Y-%m-%d %H:%M:%S")
        deleted_raw = 0
        deleted_summaries = 0
        try:
            if delete_raw_only_when_summarized:
                row = db.fetch_one(
                    """
                    SELECT COUNT(*) AS cnt FROM zalo_messages
                    WHERE timestamp != '' AND timestamp < ?
                      AND thread_id IN (
                          SELECT DISTINCT thread_id
                          FROM zalo_thread_summaries
                          WHERE summary_text IS NOT NULL AND summary_text != ''
                      )
                    """,
                    (raw_cutoff,),
                )
                deleted_raw = int((row or {}).get("cnt", 0) or 0)
                if deleted_raw:
                    db.execute_query(
                        """
                        DELETE FROM zalo_messages
                        WHERE timestamp != '' AND timestamp < ?
                          AND thread_id IN (
                              SELECT DISTINCT thread_id
                              FROM zalo_thread_summaries
                              WHERE summary_text IS NOT NULL AND summary_text != ''
                          )
                        """,
                        (raw_cutoff,),
                        commit=True,
                    )
            else:
                row = db.fetch_one(
                    "SELECT COUNT(*) AS cnt FROM zalo_messages WHERE timestamp != '' AND timestamp < ?",
                    (raw_cutoff,),
                )
                deleted_raw = int((row or {}).get("cnt", 0) or 0)
                if deleted_raw:
                    db.execute_query(
                        "DELETE FROM zalo_messages WHERE timestamp != '' AND timestamp < ?",
                        (raw_cutoff,),
                        commit=True,
                    )
            row = db.fetch_one(
                "SELECT COUNT(*) AS cnt FROM zalo_thread_summaries WHERE datetime(updated_at) < datetime(?)",
                (summary_cutoff,),
            )
            deleted_summaries = int((row or {}).get("cnt", 0) or 0)
            if deleted_summaries:
                db.execute_query(
                    "DELETE FROM zalo_thread_summaries WHERE datetime(updated_at) < datetime(?)",
                    (summary_cutoff,),
                    commit=True,
                )
        except Exception as e:
            logger.error(f"Cannot cleanup Zalo memory data: {e}")
        return {
            "deleted_raw_messages": deleted_raw,
            "deleted_summaries": deleted_summaries,
            "raw_cutoff": raw_cutoff,
            "summary_cutoff": summary_cutoff,
        }

    def _extract_thread_fact(self, thread_id: str, text: str, seen_at: str):
        body = " ".join(str(text or "").split())
        if not body:
            return
        if not any(pattern.match(body) for pattern in self.FACT_PATTERNS):
            return
        fact = self._shorten(body, 220)
        try:
            existing = db.fetch_one(
                "SELECT id, hit_count FROM zalo_thread_facts WHERE thread_id = ? AND fact = ? LIMIT 1",
                (thread_id, fact),
            )
            if existing and existing.get("id"):
                db.execute_query(
                    """
                    UPDATE zalo_thread_facts
                    SET hit_count = COALESCE(hit_count, 0) + 1,
                        confidence = CASE WHEN confidence < 0.95 THEN confidence + 0.05 ELSE confidence END,
                        last_seen_at = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (seen_at, existing["id"]),
                    commit=True,
                )
                return
            db.execute_query(
                """
                INSERT INTO zalo_thread_facts (thread_id, fact, confidence, hit_count, last_seen_at, updated_at)
                VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """,
                (thread_id, fact, 0.65, 1, seen_at),
                commit=True,
            )
        except Exception as e:
            logger.error(f"Cannot upsert Zalo fact for {thread_id}: {e}")

    def _build_summary_text(self, messages: list[dict]) -> str:
        if not messages:
            return ""
        lines = ["Tóm tắt diễn biến gần đây của thread Zalo:"]
        for msg in messages[-10:]:
            direction = str((msg or {}).get("direction") or "inbound").strip().lower()
            speaker = "Người dùng" if direction != "outbound" else "Mình"
            body = self._sanitize_message_text(str((msg or {}).get("content") or "").strip(), direction)
            body = self._shorten(body, 160)
            if not body:
                continue
            lines.append(f"- {speaker}: {body}")
        return "\n".join(lines).strip()

    def _build_turns(self, messages: list[dict], max_turns: int) -> list[dict]:
        turns: list[dict[str, Any]] = []
        current: dict[str, Any] | None = None
        for msg in messages:
            direction = str((msg or {}).get("direction") or "").strip().lower()
            cleaned = self._sanitize_message_text(str((msg or {}).get("content") or "").strip(), direction)
            if not cleaned:
                continue
            msg = {**msg, "content": cleaned}
            role = "assistant" if direction == "outbound" else "user"
            if role == "user":
                if current:
                    turns.append(current)
                current = {
                    "user": msg,
                    "assistant": None,
                    "created_at": (msg or {}).get("timestamp", ""),
                }
                continue
            if not current:
                current = {"user": None, "assistant": msg, "created_at": (msg or {}).get("timestamp", "")}
                turns.append(current)
                current = None
                continue
            current["assistant"] = msg
            turns.append(current)
            current = None
        if current:
            turns.append(current)
        if max_turns > 0 and len(turns) > max_turns:
            turns = turns[-max_turns:]
        return turns

    @staticmethod
    def _find_first_value(node: Any, keys: tuple[str, ...]) -> str:
        queue = [node]
        while queue:
            current = queue.pop(0)
            if isinstance(current, dict):
                for key in keys:
                    if key in current:
                        value = current.get(key)
                        if value not in (None, "", [], {}):
                            return str(value).strip()
                for value in current.values():
                    if isinstance(value, (dict, list)):
                        queue.append(value)
            elif isinstance(current, list):
                for value in current:
                    if isinstance(value, (dict, list)):
                        queue.append(value)
        return ""

    @staticmethod
    def _find_text_value(node: Any) -> str:
        candidate_keys = ("content", "text", "body", "msg", "message")
        queue = [node]
        while queue:
            current = queue.pop(0)
            if isinstance(current, dict):
                for key in candidate_keys:
                    value = current.get(key)
                    if isinstance(value, str) and value.strip():
                        low = value.strip().lower()
                        if low not in {"message", "group", "direct"}:
                            return value.strip()
                for value in current.values():
                    if isinstance(value, (dict, list)):
                        queue.append(value)
            elif isinstance(current, list):
                for value in current:
                    if isinstance(value, (dict, list)):
                        queue.append(value)
        return ""

    @staticmethod
    def _extract_mentions(node: Any) -> list[str]:
        collected: list[str] = []
        seen = set()
        queue = [node]
        mention_keys = {"mentions", "mention", "taggedUsers", "taggedUids", "mentionTargets"}
        while queue:
            current = queue.pop(0)
            if isinstance(current, dict):
                for key, value in current.items():
                    if key in mention_keys:
                        values = value if isinstance(value, list) else [value]
                        for item in values:
                            if isinstance(item, dict):
                                uid = item.get("uid") or item.get("userId") or item.get("id")
                                uid_text = str(uid or "").strip()
                                if uid_text and uid_text not in seen:
                                    seen.add(uid_text)
                                    collected.append(uid_text)
                            else:
                                uid_text = str(item or "").strip()
                                if uid_text and uid_text not in seen:
                                    seen.add(uid_text)
                                    collected.append(uid_text)
                    elif isinstance(value, (dict, list)):
                        queue.append(value)
            elif isinstance(current, list):
                for value in current:
                    if isinstance(value, (dict, list)):
                        queue.append(value)
        return collected

    @staticmethod
    def _infer_is_self(node: dict, sender_id: str, self_user_id: str) -> bool:
        own_id = str(self_user_id or "").strip()
        sender = str(sender_id or "").strip()
        if own_id and sender and own_id == sender:
            return True
        truthy_keys = ("isSelf", "isMe", "fromMe", "outgoing", "self")
        queue = [node]
        while queue:
            current = queue.pop(0)
            if isinstance(current, dict):
                for key in truthy_keys:
                    if bool(current.get(key)):
                        return True
                for value in current.values():
                    if isinstance(value, (dict, list)):
                        queue.append(value)
            elif isinstance(current, list):
                for value in current:
                    if isinstance(value, (dict, list)):
                        queue.append(value)
        return False
