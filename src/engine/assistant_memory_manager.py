import hashlib
import json
import logging
import re
from typing import Any

from database.db_manager import db

logger = logging.getLogger(__name__)


class AssistantMemoryManager:
    """
    Memory pipeline cho trợ lý cá nhân (single-user):
    - Log hội thoại có idempotent key.
    - Auto summary theo batch.
    - Auto extract fact (heuristic, có confidence + hit_count).
    - Build context có budget để giảm payload prompt.
    """

    ALLOWED_ROLES = {"system", "user", "assistant", "tool"}

    SUMMARY_BATCH_SIZE = 12
    DEFAULT_KEEP_MESSAGES = 3000
    DEFAULT_KEEP_SUMMARIES = 300
    DEFAULT_MESSAGE_LIMIT = 20
    DEFAULT_FACT_LIMIT = 20
    DEFAULT_CONTEXT_CHAR_BUDGET = 12000

    FACT_PATTERNS = [
        re.compile(r"^\s*(tôi muốn|hãy luôn|ưu tiên|đừng|không được)\b.+", re.IGNORECASE),
        re.compile(r"^\s*(toi muon|hay luon|uu tien|dung|khong duoc)\b.+", re.IGNORECASE),
        re.compile(r"^\s*(my preference|always|never|prefer)\b.+", re.IGNORECASE),
    ]

    @staticmethod
    def _normalize_role(role: str) -> str:
        value = str(role or "").strip().lower()
        return value if value in AssistantMemoryManager.ALLOWED_ROLES else "user"

    @staticmethod
    def _normalize_external_id(value: str | None) -> str:
        return str(value or "").strip()

    @staticmethod
    def _estimate_token_count(text: str) -> int:
        # Ước lượng nhẹ: 1 token ~ 4 ký tự Latin trung bình.
        return max(1, len(str(text or "")) // 4)

    @staticmethod
    def _to_json(payload: dict[str, Any] | None) -> str:
        try:
            return json.dumps(payload or {}, ensure_ascii=False, separators=(",", ":"))
        except Exception:
            return "{}"

    @staticmethod
    def _from_json(raw: str) -> dict[str, Any]:
        try:
            data = json.loads(raw or "{}")
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    @staticmethod
    def _fact_key(fact: str) -> str:
        normalized = " ".join(str(fact or "").strip().lower().split())
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    @staticmethod
    def _clamp_importance(value: int | float | str) -> int:
        try:
            parsed = int(value)
        except Exception:
            parsed = 3
        return max(1, min(5, parsed))

    @staticmethod
    def _clamp_confidence(value: float | int | str) -> float:
        try:
            parsed = float(value)
        except Exception:
            parsed = 0.5
        return max(0.0, min(1.0, parsed))

    @staticmethod
    def _shorten(text: str, limit: int = 220) -> str:
        body = " ".join(str(text or "").split())
        if len(body) <= limit:
            return body
        return body[: max(1, limit - 1)].rstrip() + "…"

    def get_profile(self) -> dict[str, Any]:
        row = db.fetch_one(
            """
            SELECT id, display_name, persona_prompt, preferences_json, updated_at
            FROM assistant_profile
            WHERE id = 1
            """
        )
        if not row:
            return {
                "id": 1,
                "display_name": "",
                "persona_prompt": "",
                "preferences": {},
                "updated_at": "",
            }
        return {
            "id": row["id"],
            "display_name": row.get("display_name", "") or "",
            "persona_prompt": row.get("persona_prompt", "") or "",
            "preferences": self._from_json(row.get("preferences_json", "{}")),
            "updated_at": row.get("updated_at", ""),
        }

    def update_profile(
        self,
        display_name: str | None = None,
        persona_prompt: str | None = None,
        preferences: dict[str, Any] | None = None,
    ) -> bool:
        try:
            current = self.get_profile()
            merged_prefs = dict(current.get("preferences", {}))
            if isinstance(preferences, dict):
                merged_prefs.update(preferences)

            next_display = current.get("display_name", "") if display_name is None else str(display_name)
            next_persona = current.get("persona_prompt", "") if persona_prompt is None else str(persona_prompt)

            db.execute_query(
                """
                UPDATE assistant_profile
                SET display_name = ?, persona_prompt = ?, preferences_json = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = 1
                """,
                (next_display, next_persona, self._to_json(merged_prefs)),
                commit=True,
            )
            return True
        except Exception as e:
            logger.error(f"Error updating assistant profile: {e}")
            return False

    def append_message(
        self,
        role: str,
        content: str,
        source: str = "local",
        metadata: dict[str, Any] | None = None,
        external_id: str | None = None,
    ) -> int | None:
        body = str(content or "").strip()
        if not body:
            return None

        source_name = str(source or "local").strip() or "local"
        ext_id = self._normalize_external_id(external_id)
        if ext_id:
            existed = db.fetch_one(
                """
                SELECT id
                FROM conversation_messages
                WHERE source = ? AND external_id = ?
                LIMIT 1
                """,
                (source_name, ext_id),
            )
            if existed and existed.get("id"):
                return int(existed["id"])

        try:
            return db.execute_query(
                """
                INSERT INTO conversation_messages (role, content, source, external_id, token_estimate, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    self._normalize_role(role),
                    body,
                    source_name,
                    ext_id,
                    self._estimate_token_count(body),
                    self._to_json(metadata),
                ),
                commit=True,
            )
        except Exception as e:
            logger.error(f"Error appending conversation message: {e}")
            return None

    def get_recent_messages(self, limit: int = DEFAULT_MESSAGE_LIMIT) -> list[dict[str, Any]]:
        take = max(1, min(400, int(limit or self.DEFAULT_MESSAGE_LIMIT)))
        rows = db.fetch_all(
            """
            SELECT id, role, content, source, external_id, token_estimate, metadata_json, created_at
            FROM conversation_messages
            ORDER BY id DESC
            LIMIT ?
            """,
            (take,),
        )
        rows.reverse()
        out = []
        for row in rows:
            out.append(
                {
                    "id": row["id"],
                    "role": row.get("role", "user"),
                    "content": row.get("content", ""),
                    "source": row.get("source", "local"),
                    "external_id": row.get("external_id", ""),
                    "token_estimate": int(row.get("token_estimate", 0) or 0),
                    "metadata": self._from_json(row.get("metadata_json", "{}")),
                    "created_at": row.get("created_at", ""),
                }
            )
        return out

    def add_summary(
        self,
        summary_text: str,
        from_message_id: int | None = None,
        to_message_id: int | None = None,
        source: str = "auto",
    ) -> int | None:
        text = str(summary_text or "").strip()
        if not text:
            return None
        try:
            return db.execute_query(
                """
                INSERT INTO memory_summaries (summary_text, from_message_id, to_message_id, source)
                VALUES (?, ?, ?, ?)
                """,
                (text, from_message_id, to_message_id, str(source or "auto")),
                commit=True,
            )
        except Exception as e:
            logger.error(f"Error adding memory summary: {e}")
            return None

    def get_latest_summary(self) -> dict[str, Any] | None:
        row = db.fetch_one(
            """
            SELECT id, summary_text, from_message_id, to_message_id, source, created_at
            FROM memory_summaries
            ORDER BY id DESC
            LIMIT 1
            """
        )
        if not row:
            return None
        return dict(row)

    def get_recent_summaries(self, limit: int = 4) -> list[dict[str, Any]]:
        take = max(1, min(100, int(limit or 4)))
        rows = db.fetch_all(
            """
            SELECT id, summary_text, from_message_id, to_message_id, source, created_at
            FROM memory_summaries
            ORDER BY id DESC
            LIMIT ?
            """,
            (take,),
        )
        out = [dict(r) for r in rows]
        out.reverse()
        return out

    def _extract_fact_candidates(self, text: str) -> list[tuple[str, float]]:
        body = str(text or "").strip()
        if not body:
            return []

        candidates: list[tuple[str, float]] = []
        lines = [ln.strip(" -\t") for ln in body.splitlines() if ln.strip()]
        for line in lines:
            low = line.lower()
            for pattern in self.FACT_PATTERNS:
                if pattern.match(line):
                    confidence = 0.75
                    if any(token in low for token in ("luôn", "always", "never", "đừng", "không được")):
                        confidence = 0.85
                    candidates.append((self._shorten(line, 240), confidence))
                    break

        # Fallback: câu đơn preference trong đoạn ngắn.
        if not candidates and len(body) <= 240:
            low = body.lower()
            if any(token in low for token in ("tôi ", "my ", "ưu tiên", "prefer", "thích")):
                candidates.append((self._shorten(body, 220), 0.6))

        # Dedupe local.
        seen = set()
        out: list[tuple[str, float]] = []
        for fact, conf in candidates:
            key = self._fact_key(fact)
            if key in seen:
                continue
            seen.add(key)
            out.append((fact, conf))
        return out

    def upsert_fact(
        self,
        fact: str,
        importance: int = 3,
        confidence: float = 0.5,
        source_message_id: int | None = None,
        is_active: bool = True,
    ) -> bool:
        fact_text = str(fact or "").strip()
        if not fact_text:
            return False
        try:
            key = self._fact_key(fact_text)
            db.execute_query(
                """
                INSERT INTO memory_facts
                    (fact_key, fact, importance, confidence, hit_count, last_seen_at, source_message_id, is_active, updated_at)
                VALUES
                    (?, ?, ?, ?, 1, CURRENT_TIMESTAMP, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(fact_key) DO UPDATE SET
                    fact = excluded.fact,
                    importance = MAX(memory_facts.importance, excluded.importance),
                    confidence = MAX(memory_facts.confidence, excluded.confidence),
                    hit_count = COALESCE(memory_facts.hit_count, 0) + 1,
                    last_seen_at = CURRENT_TIMESTAMP,
                    source_message_id = COALESCE(excluded.source_message_id, memory_facts.source_message_id),
                    is_active = excluded.is_active,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    key,
                    fact_text,
                    self._clamp_importance(importance),
                    self._clamp_confidence(confidence),
                    source_message_id,
                    1 if is_active else 0,
                ),
                commit=True,
            )
            return True
        except Exception as e:
            logger.error(f"Error upserting memory fact: {e}")
            return False

    def get_active_facts(self, limit: int = DEFAULT_FACT_LIMIT) -> list[dict[str, Any]]:
        take = max(1, min(200, int(limit or self.DEFAULT_FACT_LIMIT)))
        rows = db.fetch_all(
            """
            SELECT id, fact, importance, confidence, hit_count, last_seen_at, source_message_id, created_at, updated_at
            FROM memory_facts
            WHERE is_active = 1
            ORDER BY importance DESC, confidence DESC, hit_count DESC, updated_at DESC, id DESC
            LIMIT ?
            """,
            (take,),
        )
        return [dict(row) for row in rows]

    def _get_unsummarized_messages(self) -> list[dict[str, Any]]:
        latest = self.get_latest_summary()
        last_to_id = int((latest or {}).get("to_message_id") or 0)
        rows = db.fetch_all(
            """
            SELECT id, role, content
            FROM conversation_messages
            WHERE id > ?
            ORDER BY id ASC
            """,
            (last_to_id,),
        )
        return [dict(r) for r in rows]

    def _build_auto_summary_text(self, messages: list[dict[str, Any]]) -> str:
        if not messages:
            return ""

        users = [m for m in messages if m.get("role") == "user"]
        assistants = [m for m in messages if m.get("role") == "assistant"]

        lines = []
        lines.append(f"Tóm tắt {len(messages)} lượt hội thoại gần nhất.")
        if users:
            lines.append("Nhu cầu chính của user:")
            for msg in users[-3:]:
                lines.append(f"- {self._shorten(msg.get('content', ''), 180)}")
        if assistants:
            lines.append("Phản hồi/chốt của assistant:")
            for msg in assistants[-2:]:
                lines.append(f"- {self._shorten(msg.get('content', ''), 180)}")
        return "\n".join(lines).strip()

    def maybe_auto_summarize(self, batch_size: int = SUMMARY_BATCH_SIZE) -> dict[str, Any]:
        window = self._get_unsummarized_messages()
        min_batch = max(4, int(batch_size or self.SUMMARY_BATCH_SIZE))
        if len(window) < min_batch:
            return {"created": False, "reason": "not_enough_messages"}

        chunk = window[:min_batch]
        summary_text = self._build_auto_summary_text(chunk)
        if not summary_text:
            return {"created": False, "reason": "empty_summary"}

        summary_id = self.add_summary(
            summary_text=summary_text,
            from_message_id=chunk[0].get("id"),
            to_message_id=chunk[-1].get("id"),
            source="auto",
        )
        return {
            "created": bool(summary_id),
            "summary_id": summary_id,
            "from_message_id": chunk[0].get("id"),
            "to_message_id": chunk[-1].get("id"),
        }

    def ingest_turn(
        self,
        user_text: str,
        assistant_text: str,
        source: str = "telegram",
        metadata: dict[str, Any] | None = None,
        user_external_id: str | None = None,
        assistant_external_id: str | None = None,
        auto_summary: bool = True,
        auto_fact: bool = True,
    ) -> dict[str, Any]:
        user_id = self.append_message(
            role="user",
            content=user_text,
            source=source,
            metadata=metadata,
            external_id=user_external_id,
        )
        assistant_id = self.append_message(
            role="assistant",
            content=assistant_text,
            source=source,
            metadata=metadata,
            external_id=assistant_external_id,
        )

        fact_count = 0
        if auto_fact and user_id:
            for fact_text, confidence in self._extract_fact_candidates(user_text):
                ok = self.upsert_fact(
                    fact=fact_text,
                    importance=3 if confidence < 0.8 else 4,
                    confidence=confidence,
                    source_message_id=user_id,
                    is_active=True,
                )
                if ok:
                    fact_count += 1

        summary_info = {"created": False}
        if auto_summary:
            summary_info = self.maybe_auto_summarize()

        return {
            "success": bool(user_id or assistant_id),
            "user_message_id": user_id,
            "assistant_message_id": assistant_id,
            "facts_upserted": fact_count,
            "summary": summary_info,
        }

    def build_runtime_context(
        self,
        message_limit: int = DEFAULT_MESSAGE_LIMIT,
        facts_limit: int = DEFAULT_FACT_LIMIT,
        char_budget: int = DEFAULT_CONTEXT_CHAR_BUDGET,
    ) -> dict[str, Any]:
        profile = self.get_profile()
        summary = self.get_latest_summary()
        facts = self.get_active_facts(limit=facts_limit)
        messages = self.get_recent_messages(limit=message_limit)

        budget = max(2000, int(char_budget or self.DEFAULT_CONTEXT_CHAR_BUDGET))
        spent = 0

        compact_facts = []
        for fact in facts:
            line = str(fact.get("fact", ""))
            if not line:
                continue
            if spent + len(line) > budget:
                break
            compact_facts.append(fact)
            spent += len(line)

        compact_messages = []
        for msg in reversed(messages):
            line = str(msg.get("content", ""))
            if not line:
                continue
            if spent + len(line) > budget:
                break
            compact_messages.append(msg)
            spent += len(line)
        compact_messages.reverse()

        return {
            "profile": profile,
            "latest_summary": summary,
            "facts": compact_facts,
            "recent_messages": compact_messages,
            "context_char_budget": budget,
            "context_char_used": spent,
        }

    def prune_history(
        self,
        keep_messages: int = DEFAULT_KEEP_MESSAGES,
        keep_summaries: int = DEFAULT_KEEP_SUMMARIES,
    ) -> dict[str, int]:
        keep_messages = max(100, int(keep_messages or self.DEFAULT_KEEP_MESSAGES))
        keep_summaries = max(20, int(keep_summaries or self.DEFAULT_KEEP_SUMMARIES))

        deleted_messages = 0
        deleted_summaries = 0

        try:
            before = db.fetch_one("SELECT COUNT(*) AS cnt FROM conversation_messages")
            db.execute_query(
                """
                DELETE FROM conversation_messages
                WHERE id NOT IN (
                    SELECT id FROM conversation_messages
                    ORDER BY id DESC
                    LIMIT ?
                )
                """,
                (keep_messages,),
                commit=True,
            )
            after = db.fetch_one("SELECT COUNT(*) AS cnt FROM conversation_messages")
            deleted_messages = max(0, int((before or {}).get("cnt", 0)) - int((after or {}).get("cnt", 0)))
        except Exception as e:
            logger.error(f"Error pruning conversation_messages: {e}")

        try:
            before = db.fetch_one("SELECT COUNT(*) AS cnt FROM memory_summaries")
            db.execute_query(
                """
                DELETE FROM memory_summaries
                WHERE id NOT IN (
                    SELECT id FROM memory_summaries
                    ORDER BY id DESC
                    LIMIT ?
                )
                """,
                (keep_summaries,),
                commit=True,
            )
            after = db.fetch_one("SELECT COUNT(*) AS cnt FROM memory_summaries")
            deleted_summaries = max(0, int((before or {}).get("cnt", 0)) - int((after or {}).get("cnt", 0)))
        except Exception as e:
            logger.error(f"Error pruning memory_summaries: {e}")

        return {
            "deleted_messages": deleted_messages,
            "deleted_summaries": deleted_summaries,
        }
