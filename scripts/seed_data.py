"""Database initialization and mock seed data script."""

import asyncio
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from newcode.core.database import async_session_factory, engine, init_db
from newcode.models.domain import (
    Logistics,
    LogisticsStatus,
    Order,
    OrderStatus,
    User,
    UserRole,
)

USERS_DATA = [
    {
        "id": "user_buyer_1",
        "username": "买家小明",
        "role": UserRole.BUYER.value,
        "created_at": datetime(2026, 9, 1, 0, 0, 0, tzinfo=UTC),
    },
    {
        "id": "user_buyer_2",
        "username": "买家小红",
        "role": UserRole.BUYER.value,
        "created_at": datetime(2026, 9, 2, 0, 0, 0, tzinfo=UTC),
    },
    {
        "id": "user_operator_1",
        "username": "运营人员",
        "role": UserRole.OPERATOR.value,
        "created_at": datetime(2026, 9, 1, 0, 0, 0, tzinfo=UTC),
    },
]

ORDERS_DATA = [
    # user_buyer_1 orders
    {
        "id": "order_1001",
        "user_id": "user_buyer_1",
        "status": OrderStatus.PAID_UNSHIPPED.value,
        "amount": 299.00,
        "product_name": "人体工学静音办公椅",
        "paid_at": datetime(2026, 9, 24, 10, 0, 0, tzinfo=UTC),
        "created_at": datetime(2026, 9, 24, 9, 55, 0, tzinfo=UTC),
    },
    {
        "id": "order_1002",
        "user_id": "user_buyer_1",
        "status": OrderStatus.SHIPPED.value,
        "amount": 89.90,
        "product_name": "无线降噪蓝牙耳机",
        "paid_at": datetime(2026, 9, 23, 14, 30, 0, tzinfo=UTC),
        "created_at": datetime(2026, 9, 23, 14, 20, 0, tzinfo=UTC),
    },
    {
        "id": "order_1003",
        "user_id": "user_buyer_1",
        "status": OrderStatus.DELIVERED_OVER_7D.value,
        "amount": 1999.00,
        "product_name": "智能扫地机器人 Pro",
        "paid_at": datetime(2026, 9, 1, 9, 15, 0, tzinfo=UTC),
        "created_at": datetime(2026, 9, 1, 9, 0, 0, tzinfo=UTC),
    },
    # user_buyer_2 orders
    {
        "id": "order_2001",
        "user_id": "user_buyer_2",
        "status": OrderStatus.SHIPPED.value,
        "amount": 499.00,
        "product_name": "客制化机械键盘 (青轴)",
        "paid_at": datetime(2026, 9, 23, 16, 20, 0, tzinfo=UTC),
        "created_at": datetime(2026, 9, 23, 16, 10, 0, tzinfo=UTC),
    },
    {
        "id": "order_2002",
        "user_id": "user_buyer_2",
        "status": OrderStatus.REFUNDED.value,
        "amount": 59.00,
        "product_name": "Type-C 编织快充数据线",
        "paid_at": datetime(2026, 9, 20, 11, 0, 0, tzinfo=UTC),
        "created_at": datetime(2026, 9, 20, 10, 50, 0, tzinfo=UTC),
    },
]

LOGISTICS_DATA = [
    # logistics for order_1002 (user_buyer_1)
    {
        "id": "log_1002",
        "order_id": "order_1002",
        "user_id": "user_buyer_1",
        "tracking_number": "SF100288889999",
        "carrier": "顺丰速运",
        "status": LogisticsStatus.IN_TRANSIT.value,
        "traces": [
            {"timestamp": "2026-09-23 18:00:00", "event": "顺丰速运 已收取快件"},
            {"timestamp": "2026-09-24 02:30:00", "event": "快件到达 杭州萧山转运中心"},
            {"timestamp": "2026-09-24 10:15:00", "event": "快件正在发往 北京顺义集散中心"},
        ],
        "updated_at": datetime(2026, 9, 24, 10, 15, 0, tzinfo=UTC),
    },
    # logistics for order_1003 (user_buyer_1)
    {
        "id": "log_1003",
        "order_id": "order_1003",
        "user_id": "user_buyer_1",
        "tracking_number": "JD100377778888",
        "carrier": "京东物流",
        "status": LogisticsStatus.DELIVERED.value,
        "traces": [
            {"timestamp": "2026-09-02 09:00:00", "event": "京东快递 已揽收"},
            {"timestamp": "2026-09-03 08:30:00", "event": "包裹正在派送中，派件员：张师傅"},
            {"timestamp": "2026-09-03 12:00:00", "event": "已签收，签收人：本人签收"},
        ],
        "updated_at": datetime(2026, 9, 3, 12, 0, 0, tzinfo=UTC),
    },
    # logistics for order_2001 (user_buyer_2)
    {
        "id": "log_2001",
        "order_id": "order_2001",
        "user_id": "user_buyer_2",
        "tracking_number": "ZT200166667777",
        "carrier": "中通快递",
        "status": LogisticsStatus.IN_TRANSIT.value,
        "traces": [
            {"timestamp": "2026-09-23 20:00:00", "event": "中通快递 深圳南山分部已收件"},
            {"timestamp": "2026-09-24 06:00:00", "event": "快件到达 上海分拨中心"},
            {"timestamp": "2026-09-24 14:00:00", "event": "快件正在发往 上海浦东新区三林营业部"},
        ],
        "updated_at": datetime(2026, 9, 24, 14, 0, 0, tzinfo=UTC),
    },
]


async def seed_data(session: AsyncSession) -> None:
    """Seed users, orders, and logistics into the provided session."""
    # 1. Seed Users
    for user_data in USERS_DATA:
        stmt = select(User).where(User.id == user_data["id"])
        existing = (await session.execute(stmt)).scalar_one_or_none()
        if not existing:
            user = User(**user_data)
            session.add(user)

    await session.flush()

    # 2. Seed Orders
    for order_data in ORDERS_DATA:
        stmt = select(Order).where(Order.id == order_data["id"])
        existing = (await session.execute(stmt)).scalar_one_or_none()
        if not existing:
            order = Order(**order_data)
            session.add(order)

    await session.flush()

    # 3. Seed Logistics
    for log_data in LOGISTICS_DATA:
        stmt = select(Logistics).where(Logistics.id == log_data["id"])
        existing = (await session.execute(stmt)).scalar_one_or_none()
        if not existing:
            logistics = Logistics(**log_data)
            session.add(logistics)

    await session.commit()


async def seed_all(custom_engine: AsyncEngine | None = None) -> None:
    """Create database schema and populate initial seed data."""
    target_engine = custom_engine or engine
    await init_db(target_engine)

    if custom_engine is not None:
        from sqlalchemy.ext.asyncio import async_sessionmaker
        factory = async_sessionmaker(bind=custom_engine, class_=AsyncSession, expire_on_commit=False)
    else:
        factory = async_session_factory

    async with factory() as session:
        await seed_data(session)


if __name__ == "__main__":
    asyncio.run(seed_all())
    print("Database successfully initialized and seeded with mock data.")
