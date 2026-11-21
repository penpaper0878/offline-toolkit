from tests.conftest import PASSWORD, register

PROJECT = {"code": "P-1", "name": "Test project"}


def test_roles_map_to_permissions(client, team):
    roles = {r["role"]: set(r["permissions"]) for r in client.get("/api/v1/users/roles", headers=team["viewer"]).json()}
    assert roles["viewer"] == {"project:read", "design:read", "estimate:read"}
    assert "design:approve" in roles["reviewer"] and "design:write" not in roles["reviewer"]
    assert "design:write" in roles["engineer"] and "design:approve" not in roles["engineer"]
    # estimates follow designs: engineers prepare them and keep the rates, reviewers issue them
    assert {"estimate:write", "rates:manage"} <= roles["engineer"] and "estimate:issue" not in roles["engineer"]
    assert "estimate:issue" in roles["reviewer"] and "estimate:write" not in roles["reviewer"]
    assert "org:manage" in roles["owner"] and "org:manage" not in roles["admin"]


def test_project_permissions_by_role(client, team):
    assert client.post("/api/v1/projects", headers=team["viewer"], json=PROJECT).status_code == 403
    assert client.post("/api/v1/projects", headers=team["reviewer"], json=PROJECT).status_code == 403
    r = client.post("/api/v1/projects", headers=team["engineer"], json=PROJECT)
    assert r.status_code == 201
    pid = r.json()["id"]
    assert client.get(f"/api/v1/projects/{pid}", headers=team["viewer"]).status_code == 200
    r = client.delete(f"/api/v1/projects/{pid}", headers=team["engineer"])
    assert r.status_code == 403 and "project:delete" in r.json()["error"]["message"]
    assert client.delete(f"/api/v1/projects/{pid}", headers=team["admin"]).status_code == 204


def test_only_administrators_manage_users(client, team):
    body = {"full_name": "New Person", "email": "new@sahyadri.example", "role": "viewer", "password": PASSWORD}
    assert client.post("/api/v1/users", headers=team["engineer"], json=body).status_code == 403
    assert client.get("/api/v1/users", headers=team["viewer"]).status_code == 403
    assert client.post("/api/v1/users", headers=team["admin"], json=body).status_code == 201
    # an administrator cannot mint or alter an owner
    assert client.post("/api/v1/users", headers=team["admin"], json={**body, "email": "o2@sahyadri.example", "role": "owner"}).status_code == 403
    owner_id = next(u["id"] for u in client.get("/api/v1/users", headers=team["admin"]).json() if u["role"] == "owner")
    assert client.patch(f"/api/v1/users/{owner_id}", headers=team["admin"], json={"role": "viewer"}).status_code == 403


def test_the_last_owner_cannot_be_removed(client, team):
    owner_id = next(u["id"] for u in client.get("/api/v1/users", headers=team["owner"]).json() if u["role"] == "owner")
    r = client.patch(f"/api/v1/users/{owner_id}", headers=team["owner"], json={"role": "admin"})
    assert r.status_code == 409 and "at least one active owner" in r.json()["error"]["message"]
    assert client.patch(f"/api/v1/users/{owner_id}", headers=team["owner"], json={"is_active": False}).status_code == 409


def test_organisations_are_isolated(client, owner, project):
    other = register(client, email="owner@other.example", org="Other Org", name="Other Owner")
    assert client.get("/api/v1/projects", headers=other).json() == {"items": [], "total": 0}
    assert client.get(f"/api/v1/projects/{project['id']}", headers=other).status_code == 404
    assert client.patch(f"/api/v1/projects/{project['id']}", headers=other, json={"name": "Hijacked"}).status_code == 404
    d = client.post(f"/api/v1/projects/{project['id']}/designs", headers=owner, json={"element_type": "beam", "name": "B1", "inputs": {}}).json()
    assert client.post(f"/api/v1/projects/{project['id']}/designs", headers=other, json={"element_type": "beam", "name": "X", "inputs": {}}).status_code == 404
    for path in ("", "/report.pdf", "/bbs.xlsx", "/drawing.dxf", "/revisions"):
        assert client.get(f"/api/v1/designs/{d['id']}{path}", headers=other).status_code == 404
    assert client.delete(f"/api/v1/designs/{d['id']}", headers=other).status_code == 404
    assert client.get("/api/v1/search", headers=other, params={"q": "ward"}).json() == []
    assert client.get("/api/v1/dashboard/summary", headers=other).json()["designs"]["total"] == 0
    # users of another organisation cannot be edited either
    target = client.get("/api/v1/users", headers=owner).json()[0]["id"]
    assert client.patch(f"/api/v1/users/{target}", headers=other, json={"full_name": "Renamed"}).status_code == 404


def test_audit_trail_records_who_did_what(client, team, project):
    log = client.get("/api/v1/users/audit", headers=team["reviewer"]).json()
    actions = [e["action"] for e in log]
    assert "project.created" in actions and "user.created" in actions and "organization.created" in actions
    assert log[0]["user_name"] == "Asha Owner"
    assert client.get("/api/v1/users/audit", headers=team["engineer"]).status_code == 403
