"""Integration tests for signed identities, RBAC, and CORS boundaries."""

import pytest
from httpx import ASGITransport, AsyncClient

from newcode.core.database import init_db
from newcode.main import app
from newcode.models.domain import UserRole
from tests.auth_helpers import auth_headers


@pytest.fixture(autouse=True)
async def initialize_database():
    await init_db()


@pytest.mark.asyncio
async def test_chat_requires_authentication_and_matching_identity():
    payload = {"user_id": "buyer_auth", "session_id": "session_auth", "query": "你好"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        unauthenticated = await client.post("/api/chat/sync", json=payload)
        assert unauthenticated.status_code == 401

        mismatched = await client.post(
            "/api/chat/sync",
            json=payload,
            headers=auth_headers("different_buyer"),
        )
        assert mismatched.status_code == 403

        mismatched_stream = await client.post(
            "/api/chat/stream",
            json=payload,
            headers=auth_headers("different_buyer"),
        )
        assert mismatched_stream.status_code == 403


@pytest.mark.asyncio
async def test_workbench_requires_operator_role():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        buyer_response = await client.get(
            "/api/workbench/problems",
            headers=auth_headers("buyer_auth", UserRole.BUYER),
        )
        assert buyer_response.status_code == 403

        operator_response = await client.get(
            "/api/workbench/problems",
            headers=auth_headers("operator_auth", UserRole.OPERATOR),
        )
        assert operator_response.status_code == 200


@pytest.mark.asyncio
async def test_untrusted_origin_is_not_allowed_credentials():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/health",
            headers={"Origin": "https://attacker.example"},
        )
        assert response.headers.get("access-control-allow-origin") is None
