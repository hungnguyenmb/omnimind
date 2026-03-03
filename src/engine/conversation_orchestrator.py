from __future__ import annotations

from typing import Any


class ConversationOrchestrator:
    """
    Orchestrate runtime context cho trợ lý cá nhân:
    - Gom profile + facts + summaries + recent turns.
    - Áp dụng char budget để prompt ổn định khi lịch sử lớn.
    """

    DEFAULT_SUMMARY_LIMIT = 4
    MIN_CHAR_BUDGET = 2000

    def __init__(self, memory_manager):
        self.memory_manager = memory_manager

    @staticmethod
    def _safe_len(value: Any) -> int:
        return len(str(value or ""))

    def _build_turns(self, messages: list[dict[str, Any]], max_turns: int) -> list[dict[str, Any]]:
        turns: list[dict[str, Any]] = []
        current: dict[str, Any] | None = None

        for msg in messages:
            role = str((msg or {}).get("role") or "").strip().lower()
            if role == "user":
                if current:
                    turns.append(current)
                current = {
                    "user": msg,
                    "assistant": None,
                    "tools": [],
                    "created_at": (msg or {}).get("created_at", ""),
                }
                continue

            if role == "assistant":
                if not current:
                    current = {"user": None, "assistant": msg, "tools": [], "created_at": (msg or {}).get("created_at", "")}
                    turns.append(current)
                    current = None
                    continue

                current["assistant"] = msg
                turns.append(current)
                current = None
                continue

            # tool/system khác: ghim vào turn hiện tại nếu có.
            if current:
                current["tools"].append(msg)

        if current:
            turns.append(current)

        if max_turns > 0 and len(turns) > max_turns:
            turns = turns[-max_turns:]
        return turns

    def build_context(
        self,
        message_limit: int = 20,
        facts_limit: int = 20,
        summary_limit: int = DEFAULT_SUMMARY_LIMIT,
        char_budget: int = 12000,
    ) -> dict[str, Any]:
        budget = max(self.MIN_CHAR_BUDGET, int(char_budget or 12000))
        take_messages = max(6, min(200, int(message_limit or 20) * 2))
        take_facts = max(2, min(80, int(facts_limit or 20)))
        take_summaries = max(1, min(20, int(summary_limit or self.DEFAULT_SUMMARY_LIMIT)))

        profile = self.memory_manager.get_profile()
        facts = self.memory_manager.get_active_facts(limit=take_facts)
        summaries = self.memory_manager.get_recent_summaries(limit=take_summaries)
        latest_summary = summaries[-1] if summaries else self.memory_manager.get_latest_summary()
        messages = self.memory_manager.get_recent_messages(limit=take_messages)
        turns = self._build_turns(messages, max_turns=max(4, min(40, int(message_limit or 20))))

        spent = 0
        compact_facts: list[dict[str, Any]] = []
        compact_summaries: list[dict[str, Any]] = []
        compact_turns: list[dict[str, Any]] = []

        # Ưu tiên summary gần nhất -> facts -> turns.
        for summary in reversed(summaries):
            text = str((summary or {}).get("summary_text") or "").strip()
            if not text:
                continue
            if spent + self._safe_len(text) > budget:
                continue
            compact_summaries.append(summary)
            spent += self._safe_len(text)
        compact_summaries.reverse()

        for fact in facts:
            text = str((fact or {}).get("fact") or "").strip()
            if not text:
                continue
            if spent + self._safe_len(text) > budget:
                break
            compact_facts.append(fact)
            spent += self._safe_len(text)

        for turn in reversed(turns):
            user_text = str(((turn.get("user") or {}).get("content")) or "")
            assistant_text = str(((turn.get("assistant") or {}).get("content")) or "")
            turn_chars = self._safe_len(user_text) + self._safe_len(assistant_text)
            if turn_chars <= 0:
                continue
            if spent + turn_chars > budget:
                break
            compact_turns.append(turn)
            spent += turn_chars
        compact_turns.reverse()

        recent_messages: list[dict[str, Any]] = []
        for turn in compact_turns:
            user_msg = turn.get("user")
            assistant_msg = turn.get("assistant")
            if user_msg:
                recent_messages.append(user_msg)
            if assistant_msg:
                recent_messages.append(assistant_msg)

        return {
            "profile": profile,
            "latest_summary": latest_summary,
            "summaries": compact_summaries,
            "facts": compact_facts,
            "recent_turns": compact_turns,
            "recent_messages": recent_messages,
            "context_char_budget": budget,
            "context_char_used": spent,
            "context_breakdown": {
                "summary_count": len(compact_summaries),
                "fact_count": len(compact_facts),
                "turn_count": len(compact_turns),
            },
        }
