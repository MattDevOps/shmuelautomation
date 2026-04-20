import pytest
from fastapi.testclient import TestClient

from shmuel_backend.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)
