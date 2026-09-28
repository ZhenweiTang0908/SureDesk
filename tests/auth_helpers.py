"""Authentication helpers shared by API integration tests."""

from newcode.api.auth import create_access_token
from newcode.models.domain import UserRole


def auth_headers(user_id: str, role: UserRole = UserRole.BUYER) -> dict[str, str]:
    """Return a signed bearer header for an integration-test identity."""
    return {"Authorization": f"Bearer {create_access_token(user_id, role)}"}
