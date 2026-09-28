"""Deterministic test configuration loaded before application modules."""

import os

os.environ.setdefault("AUTH_SECRET", "local_test_signing_secret_not_for_production")
