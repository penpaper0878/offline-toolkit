"""Shared fixtures: an isolated in-memory database and API clients for each role."""

from __future__ import annotations

import os

os.environ.setdefault("CLP_ENV", "test")
os.environ.setdefault("CLP_JWT_SECRET", "test-secret-test-secret-test-secret-0123456789")
os.environ.setdefault("CLP_DATABASE_URL", "sqlite://")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.core import database  # noqa: E402
from app.main import app  # noqa: E402
from app.modules import models_registry  # noqa: E402,F401

PASSWORD = "Structure2026"


@pytest.fixture()
def client():
    """A fresh database for every test, on PostgreSQL when CLP_TEST_DATABASE_URL is set, else in-memory SQLite."""
    engine = database.init_engine(os.environ.get("CLP_TEST_DATABASE_URL", "sqlite://"))
    database.Base.metadata.drop_all(engine)
    database.Base.metadata.create_all(engine)
    with TestClient(app) as c:
        yield c
    database.Base.metadata.drop_all(engine)
    engine.dispose()


def register(client: TestClient, email: str = "owner@sahyadri.example", org: str = "Sahyadri Consultants", name: str = "Asha Owner") -> dict[str, str]:
    r = client.post("/api/v1/auth/register", json={"organization_name": org, "full_name": name, "email": email, "password": PASSWORD})
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def login(client: TestClient, email: str, password: str = PASSWORD) -> dict[str, str]:
    r = client.post("/api/v1/auth/login", data={"username": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture()
def owner(client):
    return register(client)


@pytest.fixture()
def team(client, owner):
    """Headers for one user of each role in the owner's organisation."""
    out = {"owner": owner}
    for role in ("admin", "engineer", "reviewer", "viewer"):
        email = f"{role}@sahyadri.example"
        r = client.post("/api/v1/users", headers=owner, json={"full_name": f"{role.capitalize()} User", "email": email, "role": role, "password": PASSWORD})
        assert r.status_code == 201, r.text
        out[role] = login(client, email)
    return out


@pytest.fixture()
def project(client, owner):
    r = client.post("/api/v1/projects", headers=owner, json={"code": "SC-2026-014", "name": "Ward 12 Community Hall", "client": "Municipal Corporation",
                                                             "state": "Gujarat", "project_type": "building"})
    assert r.status_code == 201, r.text
    return r.json()
