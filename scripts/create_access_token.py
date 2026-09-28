"""Create a signed SureDesk access token for local development."""

from __future__ import annotations

import argparse

from newcode.api.auth import create_access_token, validate_auth_configuration
from newcode.models.domain import UserRole


def parse_args() -> argparse.Namespace:
    """Parse the token subject and application role."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("user_id", help="Authenticated SureDesk user ID")
    parser.add_argument(
        "--role",
        choices=[role.value for role in UserRole],
        default=UserRole.BUYER.value,
        help="Application role embedded in the token",
    )
    return parser.parse_args()


def main() -> None:
    """Validate configuration and print a signed access token."""
    args = parse_args()
    validate_auth_configuration()
    print(create_access_token(args.user_id, args.role))


if __name__ == "__main__":
    main()
