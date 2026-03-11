from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ZaloInboundEvent:
    thread_id: str
    sender_id: str
    chat_type: str
    content: str
    mentions: list[str] = field(default_factory=list)
    timestamp: str = ""
    message_id: str = ""
    raw_payload: dict = field(default_factory=dict)

    @property
    def is_group(self) -> bool:
        return self.chat_type == "group"

    @property
    def is_direct(self) -> bool:
        return self.chat_type == "dm"

    def mentions_user(self, user_id: str) -> bool:
        target = str(user_id or "").strip()
        return bool(target and target in {str(x).strip() for x in self.mentions})

    @classmethod
    def from_raw_payload(cls, payload: dict) -> "ZaloInboundEvent | None":
        if not isinstance(payload, dict):
            return None

        thread_id = _find_first_value(payload, ("threadId", "thread_id", "groupId", "conversationId", "chatId"))
        sender_id = _find_first_value(payload, ("senderId", "sender_id", "fromId", "userId", "uid", "actorId"))
        content = _find_text_value(payload)
        message_id = _find_first_value(payload, ("msgId", "messageId", "message_id", "cliMsgId"))
        timestamp = _find_first_value(payload, ("timestamp", "ts", "msgTime", "clientTimestamp", "time"))
        mentions = _extract_mentions(payload)
        chat_type = _detect_chat_type(payload)

        if not thread_id or not sender_id or not content:
            return None

        return cls(
            thread_id=str(thread_id),
            sender_id=str(sender_id),
            chat_type=chat_type,
            content=str(content).strip(),
            mentions=[str(x).strip() for x in mentions if str(x).strip()],
            timestamp=str(timestamp or "").strip(),
            message_id=str(message_id or "").strip(),
            raw_payload=payload,
        )


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


def _detect_chat_type(payload: dict) -> str:
    if _find_first_value(payload, ("groupId", "group_id")):
        return "group"
    raw = " ".join(
        [
            str(payload.get("chatType") or ""),
            str(payload.get("type") or ""),
            str(payload.get("threadType") or ""),
        ]
    ).lower()
    if "group" in raw:
        return "group"
    return "dm"
