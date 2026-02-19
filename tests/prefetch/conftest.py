"""
Pytest configuration for prefetch engine tests.
"""

import pytest


@pytest.fixture(scope="session")
def anyio_backend():
    """Configure anyio to use only asyncio backend."""
    return "asyncio"
