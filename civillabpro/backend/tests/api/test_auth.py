from tests.conftest import PASSWORD, login, register


def test_register_creates_organisation_and_owner(client):
    headers = register(client)
    me = client.get("/api/v1/auth/me", headers=headers).json()
    assert me["role"] == "owner" and me["organization"]["name"] == "Sahyadri Consultants"
    assert "org:manage" in me["permissions"] and "design:approve" in me["permissions"]
    assert "password" not in str(me).lower()


def test_health_reports_the_database(client):
    r = client.get("/api/v1/health")
    assert r.status_code == 200 and r.json()["status"] == "ok" and r.json()["database"] in ("sqlite", "postgresql")


def test_duplicate_email_and_weak_passwords_are_rejected(client, owner):
    body = {"organization_name": "Other", "full_name": "Other Person", "email": "OWNER@sahyadri.example", "password": PASSWORD}
    r = client.post("/api/v1/auth/register", json=body)
    assert r.status_code == 409 and r.json()["error"]["code"] == "conflict"
    for bad in ("short1", "onlyletterslong", "1234567890123"):
        r = client.post("/api/v1/auth/register", json={**body, "email": "new@x.example", "password": bad})
        assert r.status_code == 422 and r.json()["error"]["details"][0]["field"] == "password"


def test_requests_without_a_valid_token_are_refused(client, owner):
    assert client.get("/api/v1/projects").status_code == 401
    r = client.get("/api/v1/projects", headers={"Authorization": "Bearer not-a-token"})
    assert r.status_code == 401 and r.json()["error"]["code"] == "unauthorized"
    assert r.headers["www-authenticate"] == "Bearer"


def test_login_and_wrong_password(client, owner):
    assert client.post("/api/v1/auth/login", data={"username": "owner@sahyadri.example", "password": "Wrong-password1"}).status_code == 401
    assert client.post("/api/v1/auth/login", data={"username": "nobody@x.example", "password": PASSWORD}).status_code == 401
    r = client.post("/api/v1/auth/login", data={"username": "Owner@Sahyadri.example ", "password": PASSWORD})
    assert r.status_code == 200 and r.json()["token_type"] == "bearer" and r.json()["expires_in"] == 1800


def test_account_locks_after_repeated_failures(client, owner):
    for _ in range(5):
        assert client.post("/api/v1/auth/login", data={"username": "owner@sahyadri.example", "password": "Wrong-password1"}).status_code == 401
    r = client.post("/api/v1/auth/login", data={"username": "owner@sahyadri.example", "password": PASSWORD})
    assert r.status_code == 423 and "Try again" in r.json()["error"]["message"]


def test_refresh_rotates_and_reuse_ends_every_session(client):
    r = client.post("/api/v1/auth/register", json={"organization_name": "Org", "full_name": "Asha Owner", "email": "a@x.example", "password": PASSWORD})
    first = r.json()["refresh_token"]
    r2 = client.post("/api/v1/auth/refresh", json={"refresh_token": first})
    assert r2.status_code == 200
    second = r2.json()["refresh_token"]
    assert second != first
    # the rotated token is presented again: treated as stolen
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": first}).status_code == 401
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": second}).status_code == 401


def test_logout_revokes_the_refresh_token(client):
    r = client.post("/api/v1/auth/register", json={"organization_name": "Org", "full_name": "Asha Owner", "email": "a@x.example", "password": PASSWORD})
    token = r.json()["refresh_token"]
    assert client.post("/api/v1/auth/logout", json={"refresh_token": token}).status_code == 204
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": token}).status_code == 401


def test_change_password(client, owner):
    r = client.post("/api/v1/auth/change-password", headers=owner, json={"current_password": "Wrong-password1", "new_password": "Foundation2027"})
    assert r.status_code == 401
    r = client.post("/api/v1/auth/change-password", headers=owner, json={"current_password": PASSWORD, "new_password": "Foundation2027"})
    assert r.status_code == 204
    assert client.post("/api/v1/auth/login", data={"username": "owner@sahyadri.example", "password": PASSWORD}).status_code == 401
    login(client, "owner@sahyadri.example", "Foundation2027")


def test_deactivated_user_cannot_sign_in_or_use_old_tokens(client, team):
    users = client.get("/api/v1/users", headers=team["owner"]).json()
    engineer = next(u for u in users if u["role"] == "engineer")
    assert client.patch(f"/api/v1/users/{engineer['id']}", headers=team["owner"], json={"is_active": False}).status_code == 200
    assert client.get("/api/v1/auth/me", headers=team["engineer"]).status_code == 401
    assert client.post("/api/v1/auth/login", data={"username": "engineer@sahyadri.example", "password": PASSWORD}).status_code == 403
