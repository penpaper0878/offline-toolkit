"""Project archives between installations and the backup of a single-organisation database (PLAT-018)."""

import json
import sqlite3

from app.core.database import get_engine
from tests.conftest import register


def _design(client, headers, project, element_type, name, inputs=None):
    r = client.post(f"/api/v1/projects/{project['id']}/designs", headers=headers,
                    json={"element_type": element_type, "name": name, "inputs": inputs or {}})
    assert r.status_code == 201, r.text
    return r.json()


def test_a_project_travels_whole_and_unchanged(client, team, project):
    beam = _design(client, team["engineer"], project, "beam", "B1")
    cb = _design(client, team["engineer"], project, "continuous_beam", "CB2", {"analysis": "elastic"})
    url = f"/api/v1/designs/{beam['id']}"
    client.put(url, headers=team["engineer"], json={"inputs": {**beam["inputs"], "live_load_kn_m": 20}})  # revision 1, the first kept
    assert client.post(f"{url}/approve", headers=team["reviewer"]).json()["review_status"] == "approved"

    r = client.get(f"/api/v1/projects/{project['id']}/export", headers=team["viewer"])
    assert r.status_code == 200 and r.headers["content-disposition"].endswith('.clp.json"')
    archive = r.json()
    assert archive["format"] == "civillabpro.project" and archive["format_version"] == 1
    assert {d["name"] for d in archive["designs"]} == {"B1", "CB2"}
    b1 = next(d for d in archive["designs"] if d["name"] == "B1")
    assert b1["revision"] == 1 and b1["review_status"] == "approved" and b1["approved_by_name"] == "Reviewer User" and len(b1["revisions"]) == 1

    # into another organisation (another installation, say): the same job number is free there
    other = register(client, "owner@other.example", "Other Consultants", "Ravi Other")
    assert client.get(f"/api/v1/projects/{project['id']}/export", headers=other).status_code == 404  # not theirs to export
    r = client.post("/api/v1/projects/import", headers=other, json=archive)
    assert r.status_code == 201, r.text
    out = r.json()
    assert out["designs"] == 2 and out["revisions"] == 1 and not out["code_changed"] and out["project"]["code"] == project["code"]
    pid = out["project"]["id"]
    designs = client.get(f"/api/v1/projects/{pid}/designs", headers=other).json()
    got = {d["name"]: client.get(f"/api/v1/designs/{d['id']}", headers=other).json() for d in designs}
    assert got["B1"]["result"] == client.get(url, headers=team["viewer"]).json()["result"]  # not recalculated
    assert got["B1"]["review_status"] == "approved" and got["B1"]["revision"] == 1
    assert len(client.get(f"/api/v1/designs/{got['B1']['id']}/revisions", headers=other).json()) == 1
    assert got["CB2"]["result"]["data"]["method"] == "elastic" and got["CB2"]["engine_version"] == cb["engine_version"]
    # the imported designs are this organisation's own: reports, revision and approval work as for any design
    assert client.get(f"/api/v1/designs/{got['B1']['id']}/report.pdf", headers=other).content.startswith(b"%PDF-")
    log = client.get("/api/v1/users/audit", headers=other).json()
    assert any(e["action"] == "project.imported" for e in log)
    # the first organisation still cannot see it
    assert client.get(f"/api/v1/projects/{pid}", headers=team["owner"]).status_code == 404


def test_import_into_the_same_organisation_takes_a_free_job_number(client, team, project):
    _design(client, team["engineer"], project, "slab", "S1")
    archive = client.get(f"/api/v1/projects/{project['id']}/export", headers=team["owner"]).json()
    first = client.post("/api/v1/projects/import", headers=team["engineer"], json=archive).json()
    second = client.post("/api/v1/projects/import", headers=team["engineer"], json=archive).json()
    assert first["code_changed"] and first["project"]["code"] == f"{project['code']}-2" and "already in use" in first["note"]
    assert second["project"]["code"] == f"{project['code']}-3"


def test_import_refuses_what_it_cannot_trust(client, team, project):
    _design(client, team["engineer"], project, "beam", "B1")
    archive = client.get(f"/api/v1/projects/{project['id']}/export", headers=team["owner"]).json()
    bad = json.loads(json.dumps(archive))
    bad["format_version"] = 2
    assert client.post("/api/v1/projects/import", headers=team["owner"], json=bad).status_code == 422
    bad = json.loads(json.dumps(archive))
    bad["designs"][0]["element_type"] = "pile_cap"
    r = client.post("/api/v1/projects/import", headers=team["owner"], json=bad)
    assert r.status_code == 422 and "no designer for pile_cap" in r.json()["error"]["message"]
    bad = json.loads(json.dumps(archive))
    bad["designs"][0]["result"]["status"] = "ok" if bad["designs"][0]["status"] != "ok" else "not_ok"
    assert "altered or damaged" in client.post("/api/v1/projects/import", headers=team["owner"], json=bad).json()["error"]["message"]
    # a viewer may export but not import; nothing was created by the refusals
    assert client.post("/api/v1/projects/import", headers=team["viewer"], json=archive).status_code == 403
    assert client.get("/api/v1/projects", headers=team["owner"]).json()["total"] == 1


def test_backup_of_a_single_organisation_database(client, team, project, tmp_path):
    _design(client, team["engineer"], project, "beam", "B1")
    assert client.get("/api/v1/admin/backup", headers=team["admin"]).status_code == 403  # the owner only
    if get_engine().dialect.name != "sqlite":
        r = client.get("/api/v1/admin/backup", headers=team["owner"])
        assert r.status_code == 409 and "pg_dump" in r.json()["error"]["message"]
        return
    r = client.get("/api/v1/admin/backup", headers=team["owner"])
    assert r.status_code == 200 and r.headers["content-disposition"].startswith("attachment; filename=\"civillabpro-backup-")
    assert r.content.startswith(b"SQLite format 3\x00")
    f = tmp_path / "b.db"
    f.write_bytes(r.content)
    con = sqlite3.connect(f)
    assert con.execute("select count(*) from structural_designs").fetchone()[0] == 1
    assert con.execute("select code from projects").fetchone()[0] == project["code"]
    con.close()
    # a database that holds another organisation is not handed to one of them
    register(client, "owner@other.example", "Other Consultants", "Ravi Other")
    r = client.get("/api/v1/admin/backup", headers=team["owner"])
    assert r.status_code == 409 and "other organisations" in r.json()["error"]["message"]
