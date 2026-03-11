from __future__ import annotations

import re

class ZaloPromptBuilder:
    HEADER_ONLY_RE = re.compile(
        r"^\s*(trả lời|tra loi|response|reply|trợ lý(?:\s+\w+){0,3}|tro ly(?:\s+\w+){0,3})\s*$",
        re.IGNORECASE,
    )

    @classmethod
    def _clean_model_line(cls, line: str) -> str:
        body = str(line or "").replace("**", "").replace("__", "").strip()
        body = body.replace("OmniMind:", "Mình:")
        body = re.sub(r"^\s*[-–—]+\s+", "", body)
        body = re.sub(r"^\s*\d+[.)]\s+", "", body)
        compact = re.sub(r"[^0-9A-Za-zÀ-ỹ]+", " ", body, flags=re.UNICODE).strip().lower()
        if compact and cls.HEADER_ONLY_RE.match(compact):
            return ""
        return body.strip()

    @staticmethod
    def _shorten(text: str, limit: int = 220) -> str:
        body = " ".join(str(text or "").split())
        if len(body) <= limit:
            return body
        return body[: max(1, limit - 1)].rstrip() + "…"

    @staticmethod
    def _clean_summary_text(text: str, limit: int = 1400) -> str:
        rows = []
        for raw_line in str(text or "").splitlines():
            line = ZaloPromptBuilder._clean_model_line(str(raw_line or "").strip())
            if not line:
                continue
            if line.startswith("- Người dùng: {") and line.endswith("}"):
                continue
            if line:
                rows.append(line)
        cleaned = "\n".join(rows).strip()
        return cleaned[:limit].strip()

    @staticmethod
    def _clean_turn_text(text: str) -> str:
        body = ZaloPromptBuilder._clean_model_line(str(text or "").strip())
        if not body:
            return ""
        body = " ".join(body.split()).strip()
        return body

    def build_prompt(
        self,
        thread_context: dict | None,
        bundle_text: str,
        bundle_size: int,
        thread_id: str,
        chat_type: str,
        zalo_principles: str = "",
    ) -> tuple[str, dict]:
        context = thread_context or {}
        thread = context.get("thread") or {}
        latest_summary = str(((context.get("latest_summary") or {}).get("summary_text")) or "").strip()
        summaries = context.get("summaries") or []
        facts = context.get("facts") or []
        recent_turns = context.get("recent_turns") or []

        summary_rows = []
        for item in summaries[-2:]:
            text = self._clean_summary_text(str((item or {}).get("summary_text") or "").strip(), limit=500)
            if text:
                summary_rows.append(f"- {self._shorten(text, 500)}")

        fact_rows = []
        for item in facts[:6]:
            fact = str((item or {}).get("fact") or "").strip()
            if fact:
                fact_rows.append(f"- {self._shorten(fact, 180)}")

        turn_rows = []
        for turn in recent_turns[-6:]:
            user_text = self._clean_turn_text(str((((turn or {}).get("user") or {}).get("content")) or "").strip())
            assistant_text = self._clean_turn_text(str((((turn or {}).get("assistant") or {}).get("content")) or "").strip())
            if user_text:
                turn_rows.append(f"- Người dùng: {self._shorten(user_text, 220)}")
            if assistant_text:
                turn_rows.append(f"- Mình: {self._shorten(assistant_text, 220)}")

        thread_name = str(thread.get("display_name") or "").strip()
        participant_hint = str(thread.get("participant_hint") or "").strip()

        prompt_parts = [
            "Bạn đang thay mặt chủ tài khoản Zalo để trả lời dưới danh nghĩa của chính người đó.",
            "Giữ văn phong tự nhiên như người thật, bám đúng ngữ cảnh cuộc trò chuyện và tuyệt đối không tự nhận là bot, AI hay hệ thống tự động.",
        ]
        if zalo_principles:
            prompt_parts.append(f"Nguyên tắc trả lời Zalo:\n{zalo_principles}")
        if latest_summary:
            cleaned_latest_summary = self._clean_summary_text(latest_summary)
            if cleaned_latest_summary:
                prompt_parts.append(f"Thread summary hiện hành:\n{cleaned_latest_summary}")
        if summary_rows:
            prompt_parts.append(f"Các summary gần đây của thread:\n{chr(10).join(summary_rows)}")
        if fact_rows:
            prompt_parts.append(f"Các fact/preferences đã biết của thread:\n{chr(10).join(fact_rows)}")
        if turn_rows:
            prompt_parts.append(f"Lịch sử hội thoại gần đây của thread theo thứ tự thời gian:\n{chr(10).join(turn_rows)}")

        meta_rows = [
            f"Thread ID: {thread_id}",
            f"Loại chat: {'group' if str(chat_type) == 'group' else 'direct'}",
            f"Số message mới trong bundle hiện tại: {max(1, int(bundle_size or 1))}",
        ]
        if thread_name:
            meta_rows.append(f"Tên thread: {thread_name}")
        if participant_hint:
            meta_rows.append(f"Gợi ý participant: {participant_hint}")
        prompt_parts.append("Metadata cuộc trò chuyện:\n" + "\n".join(meta_rows))

        prompt_parts.append(
            "Tin nhắn mới nhất từ Zalo cần xử lý:\n"
            + str(bundle_text or "").strip()
        )
        prompt_parts.append(
            "Yêu cầu trả lời:\n"
            "- Ưu tiên tiếng Việt tự nhiên, rõ ràng.\n"
            "- Nếu người dùng vừa gửi nhiều tin liên tiếp, hãy trả lời gộp theo đúng mạch ý.\n"
            "- Không mở đầu bằng tiêu đề kiểu 'Trả lời', 'Trợ lý...', không dùng markdown đậm, không tự đặt heading.\n"
            "- Trả lời như một người đang nhắn Zalo thật: gọn, mạch lạc, tối đa 1-2 đoạn ngắn hoặc vài câu liền nhau.\n"
            "- Không nhắc đến database, summary, retention hay cơ chế nội bộ.\n"
            "- Nếu chưa đủ chắc chắn, hỏi lại ngắn gọn thay vì đoán."
        )

        return "\n\n".join([part for part in prompt_parts if str(part or "").strip()]).strip(), {
            "context_char_used": int(context.get("context_char_used", 0) or 0),
            "summary_count": len(summaries or []),
            "fact_count": len(facts or []),
            "turn_count": len(recent_turns or []),
            "bundle_size": max(1, int(bundle_size or 1)),
        }
