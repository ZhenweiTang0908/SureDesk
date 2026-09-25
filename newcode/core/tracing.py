"""
End-to-End Tracing and Observability recorder.
Tracks trace ID, stage latency, tokens, tool I/O, and evidence snapshots.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any
from newcode.core.database import AsyncSessionLocal
from newcode.models.domain import AuditLog, AuditStatus


@dataclass
class StageSpan:
    name: str
    start_time: float
    end_time: float = 0.0
    duration_ms: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def finish(self, **meta):
        self.end_time = time.perf_counter()
        self.duration_ms = (self.end_time - self.start_time) * 1000.0
        self.metadata.update(meta)


class RequestTracer:
    def __init__(self, trace_id: str | None = None, user_id: str = "anon", session_id: str = "default"):
        self.trace_id = trace_id or f"trace_{uuid.uuid4().hex[:12]}"
        self.user_id = user_id
        self.session_id = session_id
        self.start_time = time.perf_counter()
        self.spans: list[StageSpan] = []
        self.tokens_prompt: int = 0
        self.tokens_completion: int = 0
        self.evidence_snapshot: list[dict[str, Any]] = []

    def start_span(self, name: str) -> StageSpan:
        span = StageSpan(name=name, start_time=time.perf_counter())
        self.spans.append(span)
        return span

    def set_tokens(self, prompt: int, completion: int):
        self.tokens_prompt += prompt
        self.tokens_completion += completion

    def record_evidence(self, chunks: list[dict[str, Any]]):
        self.evidence_snapshot = chunks

    def to_dict(self) -> dict[str, Any]:
        total_duration_ms = (time.perf_counter() - self.start_time) * 1000.0
        return {
            "trace_id": self.trace_id,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "total_duration_ms": total_duration_ms,
            "total_tokens": self.tokens_prompt + self.tokens_completion,
            "tokens_prompt": self.tokens_prompt,
            "tokens_completion": self.tokens_completion,
            "evidence_count": len(self.evidence_snapshot),
            "spans": [
                {
                    "name": s.name,
                    "duration_ms": s.duration_ms,
                    "meta": s.metadata,
                }
                for s in self.spans
            ],
        }

    async def persist_audit(self):
        async with AsyncSessionLocal() as session:
            audit = AuditLog(
                user_id=self.user_id,
                action="REQUEST_TRACE",
                resource_type="trace",
                resource_id=self.trace_id,
                status=AuditStatus.ALLOWED,
                details=self.to_dict(),
            )
            session.add(audit)
            await session.commit()

