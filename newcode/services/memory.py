"""
Dual-layer conversation memory manager.
- Near-term window: preserves exact raw messages (e.g. recent 3~5 turns).
- Far-term window: compresses older turns into structured entity & topic summary.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ConversationContext:
    near_messages: list[dict[str, str]]
    summary: str
    entities: dict[str, Any] = field(default_factory=dict)


class DualLayerMemoryManager:
    def __init__(self, near_window_turns: int = 4):
        self.near_window_turns = near_window_turns
        self.near_window_messages = near_window_turns * 2

    def process_messages(
        self, messages: list[dict[str, str]], existing_summary: str = ""
    ) -> ConversationContext:
        if len(messages) <= self.near_window_messages:
            return ConversationContext(
                near_messages=messages,
                summary=existing_summary,
                entities=self._extract_entities(messages),
            )

        far_messages = messages[:-self.near_window_messages]
        near_messages = messages[-self.near_window_messages:]

        entities = self._extract_entities(messages)

        compressed_topics: list[str] = []
        for msg in far_messages:
            role = "用户" if msg.get("role") == "user" else "客服"
            content = msg.get("content", "")
            snippet = content[:40].replace("\n", " ")
            compressed_topics.append(f"{role}: {snippet}")

        far_summary_str = " | ".join(compressed_topics)
        combined_summary = (
            f"{existing_summary} [历史压缩摘要]: {far_summary_str}"
            if existing_summary
            else f"[历史压缩摘要]: {far_summary_str}"
        )

        return ConversationContext(
            near_messages=near_messages,
            summary=combined_summary,
            entities=entities,
        )

    def _extract_entities(self, messages: list[dict[str, str]]) -> dict[str, Any]:
        orders: set[str] = set()
        products: set[str] = set()

        for msg in messages:
            content = msg.get("content", "")
            found_orders = re.findall(r"ord_[a-zA-Z0-9_]+", content)
            orders.update(found_orders)

            raw_products = re.findall(
                r"([A-Za-z0-9\u4e00-\u9fff]{2,8}(?:耳机|手机|音箱|机器人|手环|电脑|手表))",
                content,
            )
            for p in raw_products:
                clean_p = re.sub(r"^(?:购买了|买了|看中了|查到了|查询|已查到您的)", "", p)
                if clean_p:
                    products.add(clean_p)

        return {
            "order_ids": list(orders),
            "products": list(products),
        }

