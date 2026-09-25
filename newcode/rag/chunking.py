"""
Hierarchical Markdown and Table Chunker for MewHelp / NewCode.
"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Chunk:
    chunk_id: str
    content: str
    title_path: str
    is_table: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


class HierarchicalMarkdownChunker:
    """
    Parses Markdown documents, keeps track of header hierarchies (#, ##, ###),
    ensures tables are kept intact, and produces hierarchical chunks.
    """

    def __init__(self, target_chunk_size: int = 500, overlap: int = 100):
        self.target_chunk_size = target_chunk_size
        self.overlap = overlap

    def chunk_document(self, text: str, source_doc: str = "default") -> list[Chunk]:
        lines = text.splitlines()
        chunks: list[Chunk] = []

        header_stack: list[tuple[int, str]] = []  # (level, title)
        current_text_lines: list[str] = []
        in_table = False
        table_lines: list[str] = []

        def get_current_title_path() -> str:
            if not header_stack:
                return source_doc
            return " > ".join([h[1] for h in header_stack])

        def flush_text():
            nonlocal current_text_lines
            if not current_text_lines:
                return
            block = "\n".join(current_text_lines).strip()
            current_text_lines = []
            if not block:
                return

            # If block fits in target size, output single chunk
            if len(block) <= self.target_chunk_size:
                chunks.append(
                    Chunk(
                        chunk_id=str(uuid.uuid4())[:8],
                        content=block,
                        title_path=get_current_title_path(),
                        is_table=False,
                        metadata={"source": source_doc},
                    )
                )
            else:
                # Split large block by paragraphs or sentences
                paragraphs = block.split("\n\n")
                current_sub: list[str] = []
                current_len = 0
                for p in paragraphs:
                    p = p.strip()
                    if not p:
                        continue
                    if current_len + len(p) > self.target_chunk_size and current_sub:
                        sub_text = "\n\n".join(current_sub).strip()
                        chunks.append(
                            Chunk(
                                chunk_id=str(uuid.uuid4())[:8],
                                content=sub_text,
                                title_path=get_current_title_path(),
                                is_table=False,
                                metadata={"source": source_doc},
                            )
                        )
                        current_sub = [p]
                        current_len = len(p)
                    else:
                        current_sub.append(p)
                        current_len += len(p)
                if current_sub:
                    sub_text = "\n\n".join(current_sub).strip()
                    chunks.append(
                        Chunk(
                            chunk_id=str(uuid.uuid4())[:8],
                            content=sub_text,
                            title_path=get_current_title_path(),
                            is_table=False,
                            metadata={"source": source_doc},
                        )
                    )

        def flush_table():
            nonlocal table_lines, in_table
            if not table_lines:
                in_table = False
                return
            table_content = "\n".join(table_lines).strip()
            table_lines = []
            in_table = False
            if table_content:
                chunks.append(
                    Chunk(
                        chunk_id=str(uuid.uuid4())[:8],
                        content=table_content,
                        title_path=get_current_title_path(),
                        is_table=True,
                        metadata={"source": source_doc, "type": "table"},
                    )
                )

        header_pattern = re.compile(r"^(#{1,6})\s+(.+)$")
        table_pattern = re.compile(r"^\s*\|.*\|\s*$")

        for line in lines:
            h_match = header_pattern.match(line)
            if h_match:
                if in_table:
                    flush_table()
                flush_text()

                level = len(h_match.group(1))
                title = h_match.group(2).strip()

                # Pop headers with >= current level
                while header_stack and header_stack[-1][0] >= level:
                    header_stack.pop()
                header_stack.append((level, title))
                continue

            if table_pattern.match(line):
                if not in_table:
                    flush_text()
                    in_table = True
                table_lines.append(line)
                continue
            else:
                if in_table:
                    flush_table()
                current_text_lines.append(line)

        if in_table:
            flush_table()
        flush_text()

        return chunks

