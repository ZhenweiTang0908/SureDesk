"""Domain ORM models for NewCode ecommerce customer service system."""

import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from newcode.models.base import Base, TimestampMixin


def generate_uuid() -> str:
    """Generate standard uuid4 hex string."""
    return str(uuid.uuid4())


# --- Enums ---

class UserRole(str, Enum):
    """User system roles."""
    BUYER = "BUYER"
    OPERATOR = "OPERATOR"
    ADMIN = "ADMIN"


class OrderStatus(str, Enum):
    """Order lifecycle status."""
    PAID_UNSHIPPED = "PAID_UNSHIPPED"
    SHIPPED = "SHIPPED"
    DELIVERED = "DELIVERED"
    DELIVERED_OVER_7D = "DELIVERED_OVER_7D"
    REFUNDING = "REFUNDING"
    REFUNDED = "REFUNDED"
    CANCELLED = "CANCELLED"


class LogisticsStatus(str, Enum):
    """Logistics transit status."""
    PENDING = "PENDING"
    IN_TRANSIT = "IN_TRANSIT"
    DELIVERED = "DELIVERED"
    EXCEPTION = "EXCEPTION"


class TriggerType(str, Enum):
    """Triggers for entering the low-confidence problem pool."""
    CONFIDENCE_GATE = "CONFIDENCE_GATE"
    SELF_EVAL_FAIL = "SELF_EVAL_FAIL"
    USER_THUMBS_DOWN = "USER_THUMBS_DOWN"


class OperatorStatus(str, Enum):
    """Review status in the operator problem workbench."""
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    IGNORED = "IGNORED"


class AuditStatus(str, Enum):
    """Access control audit outcome status."""
    ALLOWED = "ALLOWED"
    BLOCKED = "BLOCKED"


# --- Domain Entities ---

class User(Base):
    """User entity representing buyers, operators, and administrators."""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    username: Mapped[str] = mapped_column(String(128), nullable=False)
    role: Mapped[str] = mapped_column(String(32), default=UserRole.BUYER.value, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=func.now(),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    orders: Mapped[list["Order"]] = relationship(
        "Order",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    logistics_records: Mapped[list["Logistics"]] = relationship(
        "Logistics",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    sessions: Mapped[list["ChatSession"]] = relationship(
        "ChatSession",
        back_populates="user",
        cascade="all, delete-orphan",
    )


class Order(Base):
    """Order entity with strict user ownership for IDOR defense."""

    __tablename__ = "orders"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # order_id
    user_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    amount: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    product_name: Mapped[str] = mapped_column(String(256), nullable=False)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=func.now(),
        server_default=func.now(),
        nullable=False,
    )

    # Composite index for fast scoped queries and IDOR filtering
    __table_args__ = (
        Index("ix_orders_user_id_id", "user_id", "id"),
        Index("ix_orders_user_id_status", "user_id", "status"),
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="orders")
    logistics: Mapped["Logistics | None"] = relationship(
        "Logistics",
        back_populates="order",
        uselist=False,
        cascade="all, delete-orphan",
    )


class Logistics(Base):
    """Logistics and shipment tracking entity with dual foreign keys for IDOR checks."""

    __tablename__ = "logistics"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    order_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("orders.id", ondelete="CASCADE"),
        unique=True,
        index=True,
        nullable=False,
    )
    user_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    tracking_number: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    status: Mapped[str] = mapped_column(
        String(64),
        default=LogisticsStatus.IN_TRANSIT.value,
        nullable=False,
    )
    carrier: Mapped[str] = mapped_column(String(128), nullable=False)
    traces: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSON,
        default=list,
        nullable=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=func.now(),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Composite index for user-scoped logistics queries
    __table_args__ = (
        Index("ix_logistics_user_id_order_id", "user_id", "order_id"),
    )

    # Relationships
    order: Mapped["Order"] = relationship("Order", back_populates="logistics")
    user: Mapped["User"] = relationship("User", back_populates="logistics_records")


class ChatSession(Base, TimestampMixin):
    """Customer conversation session entity."""

    __tablename__ = "chat_sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=generate_uuid)
    user_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(256), default="新会话", nullable=False)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="sessions")
    messages: Mapped[list["ChatMessage"]] = relationship(
        "ChatMessage",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="ChatMessage.created_at",
    )


class ChatMessage(Base):
    """Individual message in a conversation session."""

    __tablename__ = "chat_messages"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=generate_uuid)
    session_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    role: Mapped[str] = mapped_column(String(32), nullable=False)  # user, assistant, system, tool
    content: Mapped[str] = mapped_column(Text, nullable=False)
    thoughts: Mapped[str | None] = mapped_column(Text, nullable=True)
    tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=func.now(),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    session: Mapped["ChatSession"] = relationship("ChatSession", back_populates="messages")


class ProblemPool(Base, TimestampMixin):
    """Low-confidence and negative feedback question pool for data flywheel."""

    __tablename__ = "problem_pool"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=generate_uuid)
    session_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    trigger_type: Mapped[str] = mapped_column(
        String(64),
        index=True,
        nullable=False,
    )  # CONFIDENCE_GATE, SELF_EVAL_FAIL, USER_THUMBS_DOWN
    query: Mapped[str] = mapped_column(Text, nullable=False)
    rewritten_query: Mapped[str | None] = mapped_column(Text, nullable=True)
    retrieved_chunks: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSON,
        nullable=True,
    )
    answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    operator_status: Mapped[str] = mapped_column(
        String(32),
        default=OperatorStatus.PENDING.value,
        index=True,
        nullable=False,
    )  # PENDING, ACCEPTED, IGNORED
    standard_answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    frequency: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    sessions: Mapped[list[str] | None] = mapped_column(JSON, default=list, nullable=True)


class AuditLog(Base):
    """Security and compliance audit trail recording all tool actions and authorization outcomes."""

    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=generate_uuid)
    user_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    action: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(
        String(32),
        default=AuditStatus.ALLOWED.value,
        index=True,
        nullable=False,
    )  # ALLOWED, BLOCKED
    details: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=func.now(),
        server_default=func.now(),
        nullable=False,
    )
