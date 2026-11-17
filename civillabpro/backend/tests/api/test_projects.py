def test_project_crud_and_search(client, owner):
    for i, name in enumerate(["Rajkot water supply scheme", "Surat STP augmentation", "NH-48 widening"]):
        r = client.post("/api/v1/projects", headers=owner, json={"code": f"J-{i + 1}", "name": name, "client": "GWSSB" if i == 0 else "SMC",
                                                                 "project_type": ["water_supply", "sewerage", "highway"][i]})
        assert r.status_code == 201, r.text
    page = client.get("/api/v1/projects", headers=owner).json()
    assert page["total"] == 3 and len(page["items"]) == 3 and page["items"][0]["design_count"] == 0
    assert client.get("/api/v1/projects", headers=owner, params={"q": "gwssb"}).json()["total"] == 1
    assert client.get("/api/v1/projects", headers=owner, params={"q": "j-2"}).json()["items"][0]["name"] == "Surat STP augmentation"
    assert len(client.get("/api/v1/projects", headers=owner, params={"limit": 2, "offset": 2}).json()["items"]) == 1

    pid = page["items"][0]["id"]
    r = client.patch(f"/api/v1/projects/{pid}", headers=owner, json={"status": "completed", "location": "Gujarat"})
    assert r.status_code == 200 and r.json()["status"] == "completed"
    assert client.get("/api/v1/projects", headers=owner, params={"status": "completed"}).json()["total"] == 1
    assert client.delete(f"/api/v1/projects/{pid}", headers=owner).status_code == 204
    assert client.get(f"/api/v1/projects/{pid}", headers=owner).status_code == 404


def test_job_number_is_unique_within_the_organisation(client, owner, project):
    r = client.post("/api/v1/projects", headers=owner, json={"code": "sc-2026-014", "name": "Duplicate"})
    assert r.status_code == 409 and "already in use" in r.json()["error"]["message"]


def test_project_validation(client, owner, project):
    r = client.post("/api/v1/projects", headers=owner, json={"code": "", "name": "x"})
    assert r.status_code == 422 and {d["field"] for d in r.json()["error"]["details"]} == {"code", "name"}
    r = client.post("/api/v1/projects", headers=owner, json={"code": "D-1", "name": "Dates", "start_date": "2026-05-01", "end_date": "2026-04-01"})
    assert r.status_code == 422 and "before the start date" in r.json()["error"]["message"]
    r = client.patch(f"/api/v1/projects/{project['id']}", headers=owner, json={"start_date": "2026-05-01", "end_date": "2026-01-01"})
    assert r.status_code == 422
    assert client.post("/api/v1/projects", headers=owner, json={"code": "T-1", "name": "Type", "project_type": "spaceport"}).status_code == 422
    assert client.get("/api/v1/projects/not-a-uuid", headers=owner).status_code == 422
