import pytest
from fastapi.testclient import TestClient

from console.app import app
from console.deps import get_db
from core import security

PASSWORD = "password-di-prova-123"


@pytest.fixture()
def client(db):
    security.create_user(db, "anna", PASSWORD, name="Anna Analista")
    security.create_user(db, "capo", PASSWORD, role="amministratore")
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app, follow_redirects=False) as test_client:
        yield test_client
    app.dependency_overrides.clear()
