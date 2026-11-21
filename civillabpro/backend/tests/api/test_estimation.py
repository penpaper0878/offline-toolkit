"""Quantity estimation (EST-001 to EST-003): schedules of rates, rate analyses, estimates with design-linked quantities."""

import base64
import copy
import io

import openpyxl
import pytest

from tests.conftest import register

# an excerpt in the shape of a published schedule: a chapter row, a heading with sub-items, a bad row; the rates are illustrative
CSV = """Code,Description,Unit,Rate
,Chapter 5: Concrete work,,
5.1,"Providing and laying in position cement concrete of specified grade excluding the cost of centering and shuttering, all work up to plinth level",,
5.1.1,1:1.5:3 (1 cement : 1.5 coarse sand : 3 graded stone aggregate 20 mm nominal size),cum,"7,105.40"
5.1.2,1:2:4 (1 cement : 2 coarse sand : 4 graded stone aggregate 20 mm nominal size),cum,6544.15
5.3,Centering and shuttering including strutting and removal of form for foundations and footings,sqm,312.80
5.22,"Steel reinforcement for R.C.C. work including straightening, cutting, bending, placing in position and binding all complete",kg,98.35
5.99,Item with no rate,cum,
"""


def _import(client, headers, title="Illustrative schedule 2026", **kw):
    body = {"title": title, "authority": "Illustrative", "state": "Gujarat", "year": 2026, "filename": "dsr.csv", "content": CSV, **kw}
    return client.post("/api/v1/sor-books/import", headers=headers, json=body)


def test_import_and_search_a_schedule(client, team):
    r = _import(client, team["engineer"])
    assert r.status_code == 201, r.text
    out = r.json()
    assert out["imported"] == 4 and out["headings"] == 1 and out["skipped"] == ["row 8: no rate"]  # the file's eighth line
    book = out["book"]
    assert book["item_count"] == 4 and book["source_name"] == "dsr.csv"
    items = client.get(f"/api/v1/sor-books/{book['id']}/items", headers=team["viewer"], params={"q": "1:2:4"}).json()
    assert items["total"] == 1
    it = items["items"][0]
    assert it["item_code"] == "5.1.2" and it["rate"] == 6544.15 and it["unit"] == "cum" and it["chapter"] == "Chapter 5: Concrete work"
    assert it["description"].startswith("Providing and laying in position cement concrete") and it["description"].endswith("20 mm nominal size)")
    assert client.get(f"/api/v1/sor-books/{book['id']}/items", headers=team["viewer"], params={"q": "steel reinforcement"}).json()["items"][0]["rate"] == 98.35
    assert client.get(f"/api/v1/sor-books/{book['id']}/items", headers=team["viewer"], params={"q": "5.1.1"}).json()["items"][0]["rate"] == 7105.40
    assert _import(client, team["engineer"]).status_code == 409  # the same title twice
    assert _import(client, team["viewer"], title="Another").status_code == 403
    bad = _import(client, team["engineer"], title="No header", content="a,b\n1,2\n")
    assert bad.status_code == 422 and "header row" in bad.json()["error"]["message"]
    # another organisation sees nothing of it
    other = register(client, "o@other.example", "Other", "Other Owner")
    assert client.get(f"/api/v1/sor-books/{book['id']}/items", headers=other).status_code == 404
    assert client.get("/api/v1/sor-books", headers=other).json() == []
    assert client.delete(f"/api/v1/sor-books/{book['id']}", headers=other).status_code == 404
    assert client.delete(f"/api/v1/sor-books/{book['id']}", headers=team["engineer"]).status_code == 204


def test_import_an_excel_schedule(client, team):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Schedule of rates (illustrative)"])
    ws.append([])
    ws.append(["Item No.", "Description of item", "Unit", "Rate (Rs.)", "Chapter"])
    ws.append(["2.8", "Earth work in excavation by mechanical means in foundation trenches", "cum", 186.0, "Earth work"])
    ws.append(["2.25", "Filling available excavated earth in trenches, plinth, sides of foundations", "cum", 155.5, "Earth work"])
    buf = io.BytesIO()
    wb.save(buf)
    r = client.post("/api/v1/sor-books/import", headers=team["engineer"], json={
        "title": "Earth work", "filename": "earth.xlsx", "content_base64": base64.b64encode(buf.getvalue()).decode()})
    assert r.status_code == 201, r.text
    assert r.json()["imported"] == 2
    items = client.get(f"/api/v1/sor-books/{r.json()['book']['id']}/items", headers=team["viewer"]).json()["items"]
    assert [(i["item_code"], i["rate"], i["chapter"]) for i in items] == [("2.8", 186.0, "Earth work"), ("2.25", 155.5, "Earth work")]
    assert client.post("/api/v1/sor-books/import", headers=team["engineer"], json={"title": "x", "filename": "a.pdf", "content": "x"}).status_code == 422


ANALYSIS = {"title": "RCC M25 in footings, illustrative", "unit": "cum", "output_qty": 1.0, "water_pct": 1.0, "overheads_profit_pct": 15.0,
            "lines": [{"kind": "material", "description": "Cement", "unit": "t", "quantity": 0.384, "rate": 7100.0},
                      {"kind": "material", "description": "Coarse sand", "unit": "cum", "quantity": 0.445, "rate": 2150.0},
                      {"kind": "labour", "description": "Beldar", "unit": "day", "quantity": 2.0, "rate": 707.0},
                      {"kind": "plant", "description": "Mixer", "unit": "day", "quantity": 0.07, "rate": 1350.0}]}


def test_rate_analyses(client, team):
    r = client.post("/api/v1/rate-analyses", headers=team["engineer"], json=ANALYSIS)
    assert r.status_code == 201, r.text
    a = r.json()
    # 2726.40 + 956.75 + 1414.00 + 94.50 = 5191.65; water 51.92; 15 % of 5243.57 = 786.54; rate 6030.11
    assert a["result"]["material"] == 3683.15 and a["result"]["cost"] == 5191.65 and a["result"]["water"] == 51.92
    assert a["result"]["overheads_profit"] == 786.54 and a["rate"] == 6030.11
    calc = client.post("/api/v1/rate-analyses/calculate", headers=team["viewer"], json={**ANALYSIS, "output_qty": 2.0}).json()
    assert calc["rate"] == 3015.06  # 6030.11 / 2, from the unrounded total 6030.11
    upd = client.put(f"/api/v1/rate-analyses/{a['id']}", headers=team["engineer"], json={**ANALYSIS, "overheads_profit_pct": 10.0}).json()
    assert upd["result"]["overheads_profit"] == 524.36 and upd["rate"] == 5767.93
    assert client.post("/api/v1/rate-analyses", headers=team["viewer"], json=ANALYSIS).status_code == 403
    assert client.post("/api/v1/rate-analyses", headers=team["engineer"], json={**ANALYSIS, "output_qty": 0}).status_code == 422
    assert [x["title"] for x in client.get("/api/v1/rate-analyses", headers=team["viewer"]).json()] == [ANALYSIS["title"]]
    assert client.delete(f"/api/v1/rate-analyses/{a['id']}", headers=team["engineer"]).status_code == 204


def _design(client, headers, project, element_type, name, inputs=None):
    r = client.post(f"/api/v1/projects/{project['id']}/designs", headers=headers, json={"element_type": element_type, "name": name, "inputs": inputs or {}})
    assert r.status_code == 201, r.text
    return r.json()


def test_an_estimate_priced_from_a_schedule_with_quantities_measured_and_from_designs(client, team, project):
    book = _import(client, team["engineer"]).json()["book"]
    conc = client.get(f"/api/v1/sor-books/{book['id']}/items", headers=team["engineer"], params={"q": "5.1.2"}).json()["items"][0]
    steel = client.get(f"/api/v1/sor-books/{book['id']}/items", headers=team["engineer"], params={"q": "5.22"}).json()["items"][0]
    footing = _design(client, team["engineer"], project, "footing", "F1")
    q = client.get(f"/api/v1/projects/{project['id']}/design-quantities", headers=team["viewer"]).json()
    assert [(x["name"], x["title"]) for x in q] == [("F1", "RCC isolated footing")] and set(q[0]["quantities"]) == {"concrete_m3", "formwork_m2", "steel_kg"}
    steel_kg = q[0]["quantities"]["steel_kg"]

    est = client.post(f"/api/v1/projects/{project['id']}/estimates", headers=team["engineer"], json={"title": "Footings"}).json()
    assert est["status"] == "draft" and est["result"]["abstract"]["rounded"] == 0
    doc = {"items": [
        {"id": "a", "description": conc["description"], "unit": "cum", "rate": conc["rate"],
         "rate_source": {"kind": "sor", "sor_item_id": conc["id"], "book_title": book["title"], "item_code": conc["item_code"]},
         "quantity_mode": "measured", "measurements": [
             {"description": "Footings F1", "nos": 4, "length": 2.2, "breadth": 2.05, "depth": 0.45},
             {"description": "Pipe sleeve", "nos": 2, "length": 0.5, "breadth": 0.5, "depth": 0.45, "deduct": True}]},
        {"id": "b", "description": steel["description"], "unit": "t", "rate": 98350.0, "quantity_mode": "design",
         "design": {"design_id": footing["id"], "key": "steel_kg"}},
        {"id": "c", "item_no": "NS-1", "description": "Anti-termite treatment (non-scheduled)", "unit": "sqm", "rate": 45.5, "quantity_mode": "direct",
         "quantity": 18.04}],
        "additions": [{"label": "Cost index", "pct": 12.5}, {"label": "Contingencies", "pct": 3.0}]}
    r = client.put(f"/api/v1/estimates/{est['id']}", headers=team["engineer"], json={"title": "Footings", "notes": "Rates illustrative.", "doc": doc})
    assert r.status_code == 200, r.text
    e = r.json()
    items = {i["id"]: i for i in e["result"]["items"]}
    # 4 x 2.2 x 2.05 x 0.45 = 8.118 -> 8.12; less 2 x 0.5 x 0.5 x 0.45 = 0.225 -> 0.23; 7.89 cum at 6544.15 = 51633.34
    assert items["a"]["lines"] == [8.12, -0.23] and items["a"]["quantity"] == 7.89 and items["a"]["amount"] == 51633.34
    t = round(steel_kg / 1000, 3)
    assert items["b"]["quantity"] == pytest.approx(t) and items["b"]["amount"] == pytest.approx(round(t * 98350, 2)) and not items["b"]["stale"]
    assert e["doc"]["items"][1]["design"]["revision"] == 0 and e["doc"]["items"][1]["design"]["label"] == "RCC isolated footing F1"
    assert items["c"]["no"] == "NS-1" and items["c"]["amount"] == 820.82 and items["a"]["no"] == "1"
    ab = e["result"]["abstract"]
    sub = round(51633.34 + items["b"]["amount"] + 820.82, 2)
    assert ab["subtotal"] == pytest.approx(sub)
    assert ab["additions"][0]["amount"] == pytest.approx(round(sub * 0.125, 2)) and ab["additions"][1]["amount"] == pytest.approx(round(sub * 0.03, 2))
    assert ab["rounded"] == round(ab["total"]) and e["total"] == ab["rounded"]

    # a preview works out an unsaved document and keeps nothing
    pv = client.post(f"/api/v1/estimates/{est['id']}/preview", headers=team["viewer"], json={**doc, "additions": []}).json()
    assert pv["abstract"]["subtotal"] == ab["subtotal"] and pv["abstract"]["additions"] == []
    assert client.get(f"/api/v1/estimates/{est['id']}", headers=team["viewer"]).json()["doc"]["additions"] == doc["additions"]

    # the design is revised: the item shows it, until the estimate is refreshed
    url = f"/api/v1/designs/{footing['id']}"
    client.put(url, headers=team["engineer"], json={"inputs": {**footing["inputs"], "p_service_kn": 1200}})
    stale = client.get(f"/api/v1/estimates/{est['id']}", headers=team["viewer"]).json()
    assert stale["result"]["stale"] == 1 and stale["result"]["items"][1]["design_now"]["revision"] == 1
    assert client.post(f"/api/v1/estimates/{est['id']}/issue", headers=team["reviewer"]).status_code == 409  # stale quantities
    fresh = client.post(f"/api/v1/estimates/{est['id']}/refresh", headers=team["engineer"]).json()
    assert fresh["result"]["stale"] == 0 and fresh["doc"]["items"][1]["design"]["revision"] == 1
    assert fresh["result"]["items"][1]["quantity"] > items["b"]["quantity"]
    # an unchanged link keeps what it took, whatever the client sends
    tampered = copy.deepcopy(fresh["doc"])
    tampered["items"][1]["design"]["value"] = 1.0
    kept = client.put(f"/api/v1/estimates/{est['id']}", headers=team["engineer"], json={"title": "Footings", "doc": tampered}).json()
    assert kept["doc"]["items"][1]["design"]["value"] == fresh["doc"]["items"][1]["design"]["value"]

    # issue: by someone other than the one who prepared it
    assert client.post(f"/api/v1/estimates/{est['id']}/issue", headers=team["engineer"]).status_code == 403  # engineers do not issue
    issued = client.post(f"/api/v1/estimates/{est['id']}/issue", headers=team["reviewer"]).json()
    assert issued["status"] == "issued" and issued["issued_by_name"] == "Reviewer User"
    assert client.put(f"/api/v1/estimates/{est['id']}", headers=team["engineer"], json={"title": "x", "doc": doc}).status_code == 409
    assert client.delete(f"/api/v1/estimates/{est['id']}", headers=team["engineer"]).status_code == 409

    # exports
    wb = openpyxl.load_workbook(io.BytesIO(client.get(f"/api/v1/estimates/{est['id']}/estimate.xlsx", headers=team["viewer"]).content))
    abs_ = wb["Abstract"]
    assert abs_["F7"].value == "=ROUND(C7*E7,2)" and abs_["C7"].value == 7.89 and abs_["B7"].value.startswith("Providing and laying")
    assert wb["Measurements"]["B5"].value == "Footings F1"
    pdf = client.get(f"/api/v1/estimates/{est['id']}/estimate.pdf", headers=team["viewer"])
    assert pdf.content.startswith(b"%PDF-") and 'filename="estimate_Footings_R0.pdf"' in pdf.headers["content-disposition"]

    revised = client.post(f"/api/v1/estimates/{est['id']}/revise", headers=team["engineer"]).json()
    assert revised["status"] == "draft" and revised["revision"] == 1
    listed = client.get(f"/api/v1/projects/{project['id']}/estimates", headers=team["viewer"]).json()
    assert [(x["title"], x["item_count"], x["revision"]) for x in listed] == [("Footings", 3, 1)]
    assert client.get("/api/v1/estimates", headers=team["viewer"]).json()[0]["id"] == est["id"]
    log = [x["action"] for x in client.get("/api/v1/users/audit", headers=team["owner"]).json()]
    assert {"estimate.created", "estimate.saved", "estimate.issued", "estimate.revised", "sor_book.imported"} <= set(log)

    # another organisation sees nothing
    other = register(client, "o@other.example", "Other", "Other Owner")
    assert client.get(f"/api/v1/estimates/{est['id']}", headers=other).status_code == 404
    assert client.get(f"/api/v1/projects/{project['id']}/estimates", headers=other).status_code == 404


def test_design_links_are_checked(client, team, project):
    beam = _design(client, team["engineer"], project, "beam", "B1")
    other_project = client.post("/api/v1/projects", headers=team["owner"], json={"code": "P2", "name": "Other", "project_type": "building"}).json()
    elsewhere = _design(client, team["engineer"], other_project, "beam", "B9")
    est = client.post(f"/api/v1/projects/{project['id']}/estimates", headers=team["engineer"], json={"title": "Beams"}).json()

    def save(item):
        return client.put(f"/api/v1/estimates/{est['id']}", headers=team["engineer"], json={"title": "Beams", "doc": {"items": [item]}})
    base = {"id": "x", "description": "Concrete", "unit": "cum", "rate": 6000.0, "quantity_mode": "design"}
    assert "choose the design" in save(base).json()["error"]["message"]
    r = save({**base, "unit": "kg", "design": {"design_id": beam["id"], "key": "concrete_m3"}})  # 'cum' converts from m3, kg does not
    assert r.status_code == 422 and "does not convert" in r.json()["error"]["message"]
    r = save({**base, "design": {"design_id": elsewhere["id"], "key": "concrete_m3"}})
    assert r.status_code == 422 and "not in this project" in r.json()["error"]["message"]
    ok = save({**base, "design": {"design_id": beam["id"], "key": "concrete_m3"}})
    assert ok.status_code == 200 and ok.json()["result"]["items"][0]["quantity"] == pytest.approx(beam["result"]["quantities"]["concrete_m3"], abs=5e-4)
    # deleting the design leaves the item standing, marked
    client.delete(f"/api/v1/designs/{beam['id']}", headers=team["owner"])
    gone = client.get(f"/api/v1/estimates/{est['id']}", headers=team["viewer"]).json()
    assert gone["result"]["stale"] == 1 and gone["result"]["items"][0]["design_now"] is None
    dup = client.put(f"/api/v1/estimates/{est['id']}", headers=team["engineer"], json={"title": "Beams", "doc": {"items": [
        {**base, "quantity_mode": "direct", "quantity": 1}, {**base, "quantity_mode": "direct", "quantity": 2}]}})
    assert dup.status_code == 422 and "share an identifier" in dup.json()["error"]["message"]
