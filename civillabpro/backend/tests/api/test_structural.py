import io

import ezdxf
import openpyxl
import pytest

from tests.conftest import register

BEAM = {"element_type": "beam", "name": "B1", "inputs": {}}


@pytest.fixture()
def design(client, team, project):
    r = client.post(f"/api/v1/projects/{project['id']}/designs", headers=team["engineer"], json=BEAM)
    assert r.status_code == 201, r.text
    return r.json()


def test_elements_registry_describes_the_beam(client, owner):
    elements = {e["type"]: e for e in client.get("/api/v1/structural/elements", headers=owner).json()}
    assert list(elements) == ["beam", "continuous_beam", "column", "slab", "footing", "combined_footing"]
    beam = elements["beam"]
    assert beam["type"] == "beam" and beam["code_basis"][0] == "IS 456:2000" and beam["limitations"]
    assert beam["defaults"]["clear_span_mm"] == 4000
    props = beam["input_schema"]["properties"]
    assert props["clear_span_mm"]["title"] == "Clear span" and props["clear_span_mm"]["unit"] == "mm" and props["clear_span_mm"]["group"] == "Geometry"
    assert props["dead_load_kn_m"]["show_if"] == {"mode": "loads"} and props["fck"]["labels"]["25"] == "M25"


def test_calculate_runs_the_engine_without_saving(client, owner):
    r = client.post("/api/v1/structural/beam/calculate", headers=owner, json={})
    assert r.status_code == 200
    res = r.json()
    assert res["status"] == "ok" and res["data"]["mu"] == pytest.approx(75.78, abs=0.01) and res["reinforcement"]["bottom"]["label"] == "3-T16"
    assert res["sheet"]["sections"][0]["title"].startswith("1.") and res["drawing"]["views"][0]["id"] == "section"
    assert client.get("/api/v1/dashboard/summary", headers=owner).json()["designs"]["total"] == 0


def test_calculate_reports_input_errors_by_field(client, owner):
    r = client.post("/api/v1/structural/beam/calculate", headers=owner, json={"width_mm": 50, "fck": 15})
    assert r.status_code == 422
    fields = {d["field"] for d in r.json()["error"]["details"]}
    assert fields == {"width_mm", "fck"}
    r = client.post("/api/v1/structural/beam/calculate", headers=owner, json={"mode": "forces"})
    assert r.status_code == 422 and "Enter the factored moment and shear" in r.json()["error"]["message"]
    assert client.post("/api/v1/structural/spaceframe/calculate", headers=owner, json={}).status_code == 404
    assert client.post("/api/v1/structural/beam/calculate", json={}).status_code == 401


def test_saved_design_is_stored_with_inputs_and_result(client, team, project, design):
    assert design["status"] == "ok" and design["revision"] == 0 and design["review_status"] == "draft"
    assert design["designed_by_name"] == "Engineer User" and design["inputs"]["depth_mm"] == 450
    got = client.get(f"/api/v1/designs/{design['id']}", headers=team["viewer"]).json()
    assert got["result"]["key_results"] == design["result"]["key_results"]
    listed = client.get(f"/api/v1/projects/{project['id']}/designs", headers=team["viewer"]).json()
    assert [d["name"] for d in listed] == ["B1"] and "result" not in listed[0]
    assert client.get(f"/api/v1/projects/{project['id']}", headers=team["viewer"]).json()["design_count"] == 1
    assert client.post(f"/api/v1/projects/{project['id']}/designs", headers=team["viewer"], json=BEAM).status_code == 403
    assert client.post(f"/api/v1/projects/{project['id']}/designs", headers=team["engineer"], json={**BEAM, "inputs": {"depth_mm": 1}}).status_code == 422


def test_revising_a_design_archives_the_previous_state(client, team, design):
    r = client.put(f"/api/v1/designs/{design['id']}", headers=team["engineer"], json={"inputs": {**design["inputs"], "depth_mm": 500}})
    assert r.status_code == 200
    revised = r.json()
    assert revised["revision"] == 1 and revised["inputs"]["depth_mm"] == 500 and revised["result"]["data"]["d"] > design["result"]["data"]["d"]
    revs = client.get(f"/api/v1/designs/{design['id']}/revisions", headers=team["viewer"]).json()
    assert [(v["revision"], v["status"]) for v in revs] == [(0, "ok")]
    r = client.put(f"/api/v1/designs/{design['id']}", headers=team["engineer"], json={"name": "B1a"})
    assert r.json()["name"] == "B1a" and r.json()["revision"] == 1  # renaming is not a revision


def test_approval_needs_a_second_person_and_lapses_on_revision(client, team, design):
    url = f"/api/v1/designs/{design['id']}"
    assert client.post(f"{url}/approve", headers=team["engineer"]).status_code == 403  # no permission
    r = client.post(f"{url}/approve", headers=team["reviewer"])
    assert r.status_code == 200 and r.json()["review_status"] == "approved" and r.json()["approved_by_name"] == "Reviewer User"
    r = client.put(url, headers=team["engineer"], json={"inputs": {**design["inputs"], "live_load_kn_m": 10}})
    assert r.json()["review_status"] == "draft" and r.json()["approved_by_name"] == ""
    assert client.get(f"{url}/revisions", headers=team["viewer"]).json()[0]["review_status"] == "approved"


def test_designer_cannot_approve_own_work_and_failed_designs_cannot_be_approved(client, team, project):
    own = client.post(f"/api/v1/projects/{project['id']}/designs", headers=team["owner"], json=BEAM).json()
    r = client.post(f"/api/v1/designs/{own['id']}/approve", headers=team["owner"])
    assert r.status_code == 409 and "other than its designer" in r.json()["error"]["message"]
    bad = client.post(f"/api/v1/projects/{project['id']}/designs", headers=team["engineer"],
                      json={"element_type": "beam", "name": "B9", "inputs": {"fck": 20, "exposure": "severe"}}).json()
    assert bad["status"] == "not_ok"
    r = client.post(f"/api/v1/designs/{bad['id']}/approve", headers=team["reviewer"])
    assert r.status_code == 409 and "every check OK" in r.json()["error"]["message"]


def test_exports_are_real_documents(client, team, design):
    url = f"/api/v1/designs/{design['id']}"
    pdf = client.get(f"{url}/report.pdf", headers=team["viewer"])
    assert pdf.status_code == 200 and pdf.headers["content-type"] == "application/pdf" and pdf.content.startswith(b"%PDF-")
    assert 'filename="beam_B1_R0_report.pdf"' in pdf.headers["content-disposition"] and len(pdf.content) > 20_000

    xlsx = client.get(f"{url}/bbs.xlsx", headers=team["viewer"])
    wb = openpyxl.load_workbook(io.BytesIO(xlsx.content))
    ws = wb["BBS"]
    assert ws["A1"].value == "Bar bending schedule" and ws["B8"].value.startswith("Bottom bars (tension), 2-T16 continuing") and ws["B9"].value.startswith("Bottom bars (tension, curtailed), 1-T16")
    assert ws["I8"].value == 4630 and ws["J8"].value == "=ROUND(E8*I8/1000,3)" and wb["Summary"]["A2"].value == 8

    dxf = client.get(f"{url}/drawing.dxf", headers=team["viewer"])
    doc = ezdxf.read(io.StringIO(dxf.content.decode()))
    kinds = {e.dxftype() for e in doc.modelspace()}
    assert {"LINE", "LWPOLYLINE", "CIRCLE", "TEXT", "DIMENSION"} <= kinds and not doc.audit().errors
    assert {"CLP-CONCRETE", "CLP-REBAR", "CLP-STIRRUP"} <= {layer.dxf.name for layer in doc.layers}
    assert client.get(f"{url}/report.pdf").status_code == 401


def test_stopped_design_has_a_report_but_no_schedule_or_drawing(client, team, project):
    d = client.post(f"/api/v1/projects/{project['id']}/designs", headers=team["engineer"],
                    json={"element_type": "beam", "name": "DB", "inputs": {"clear_span_mm": 1500, "depth_mm": 1000, "width_mm": 300}}).json()
    assert d["status"] == "stopped" and "deep beam" in d["result"]["stop_message"]
    assert client.get(f"/api/v1/designs/{d['id']}/report.pdf", headers=team["engineer"]).content.startswith(b"%PDF-")
    assert client.get(f"/api/v1/designs/{d['id']}/bbs.xlsx", headers=team["engineer"]).status_code == 409
    assert client.get(f"/api/v1/designs/{d['id']}/drawing.dxf", headers=team["engineer"]).status_code == 409


def test_delete_design_and_cascade_from_project(client, team, project, design):
    assert client.delete(f"/api/v1/designs/{design['id']}", headers=team["viewer"]).status_code == 403
    assert client.delete(f"/api/v1/designs/{design['id']}", headers=team["engineer"]).status_code == 204
    assert client.get(f"/api/v1/designs/{design['id']}", headers=team["engineer"]).status_code == 404
    d2 = client.post(f"/api/v1/projects/{project['id']}/designs", headers=team["engineer"], json=BEAM).json()
    client.put(f"/api/v1/designs/{d2['id']}", headers=team["engineer"], json={"inputs": {**d2["inputs"], "depth_mm": 500}})
    assert client.delete(f"/api/v1/projects/{project['id']}", headers=team["owner"]).status_code == 204
    assert client.get(f"/api/v1/designs/{d2['id']}", headers=team["engineer"]).status_code == 404


def test_dashboard_and_search_reflect_saved_work(client, team, project, design):
    client.post(f"/api/v1/projects/{project['id']}/designs", headers=team["engineer"],
                json={"element_type": "beam", "name": "Lintel L2", "inputs": {"fck": 20, "exposure": "severe"}})
    s = client.get("/api/v1/dashboard/summary", headers=team["viewer"]).json()
    assert s["projects"] == {"total": 1, "by_status": {"active": 1}}
    assert s["designs"]["total"] == 2 and s["designs"]["by_status"] == {"ok": 1, "not_ok": 1} and s["designs"]["awaiting_approval"] == 1
    assert s["designs"]["by_type"] == {"beam": 2} and len(s["recent_designs"]) == 2 and s["recent_designs"][0]["project_code"] == "SC-2026-014"
    assert len(s["design_activity"]) == 14 and s["design_activity"][-1]["count"] == 2 and s["activity"][0]["action"] == "design.created"
    hits = client.get("/api/v1/search", headers=team["viewer"], params={"q": "lintel"}).json()
    assert [(h["kind"], h["title"]) for h in hits] == [("design", "RCC beam Lintel L2")]
    hits = client.get("/api/v1/search", headers=team["viewer"], params={"q": "ward"}).json()
    assert hits[0]["kind"] == "project" and hits[0]["title"].startswith("SC-2026-014")
    other = register(client, email="o@other.example", org="Other", name="Other Owner")
    assert client.get("/api/v1/search", headers=other, params={"q": "lintel"}).json() == []


COLUMN = {"element_type": "column", "name": "C1", "inputs": {}}


def test_column_goes_through_the_same_life_cycle(client, team, project):
    elements = {e["type"]: e for e in client.get("/api/v1/structural/elements", headers=team["viewer"]).json()}
    col = elements["column"]
    assert col["title"] == "RCC column" and col["defaults"]["pu_kn"] == 1200
    props = col["input_schema"]["properties"]
    assert props["end_x"]["labels"]["c"].startswith("1.00 l") and props["k_x"]["show_if"] == {"end_x": "custom"}

    calc = client.post("/api/v1/structural/column/calculate", headers=team["viewer"], json={}).json()
    assert calc["status"] == "ok" and calc["reinforcement"]["main"]["label"] == "12-T12"
    assert [c["id"] for c in calc["charts"]] == ["interaction_x", "interaction_y"]

    r = client.post(f"/api/v1/projects/{project['id']}/designs", headers=team["engineer"], json=COLUMN)
    assert r.status_code == 201
    d = r.json()
    assert d["element_type"] == "column" and d["result"]["charts"][0]["series"][0]["kind"] == "line"
    url = f"/api/v1/designs/{d['id']}"
    r = client.put(url, headers=team["engineer"], json={"inputs": {**d["inputs"], "pu_kn": 1400}})
    assert r.json()["revision"] == 1 and r.json()["result"]["data"]["case1_mx"] == 90
    assert client.post(f"{url}/approve", headers=team["reviewer"]).json()["review_status"] == "approved"

    pdf = client.get(f"{url}/report.pdf", headers=team["viewer"])
    assert pdf.content.startswith(b"%PDF-") and 'filename="column_C1_R1_report.pdf"' in pdf.headers["content-disposition"]
    wb = openpyxl.load_workbook(io.BytesIO(client.get(f"{url}/bbs.xlsx", headers=team["viewer"]).content))
    assert wb["BBS"]["B8"].value.startswith("Main bars")
    doc = ezdxf.read(io.StringIO(client.get(f"{url}/drawing.dxf", headers=team["viewer"]).content.decode()))
    assert "CLP-CENTER" in {layer.dxf.name for layer in doc.layers} and not doc.audit().errors

    s = client.get("/api/v1/dashboard/summary", headers=team["viewer"]).json()
    assert s["designs"]["by_type"] == {"column": 1}


def test_column_input_errors_come_back_by_field(client, owner):
    r = client.post("/api/v1/structural/column/calculate", headers=owner, json={"width_mm": 200, "depth_mm": 900})
    assert r.status_code == 422 and "wall" in r.json()["error"]["message"]
    r = client.post("/api/v1/structural/column/calculate", headers=owner, json={"pu_kn": 0, "fck": 15})
    assert {d["field"] for d in r.json()["error"]["details"]} == {"pu_kn", "fck"}


def _life_cycle(client, team, project, element_type, name, change):
    """Calculate, save, revise, approve and export one element through the shared endpoints."""
    r = client.post(f"/api/v1/projects/{project['id']}/designs", headers=team["engineer"], json={"element_type": element_type, "name": name, "inputs": {}})
    assert r.status_code == 201, r.text
    d = r.json()
    assert d["element_type"] == element_type and d["status"] == "ok"
    url = f"/api/v1/designs/{d['id']}"
    revised = client.put(url, headers=team["engineer"], json={"inputs": {**d["inputs"], **change}}).json()
    assert revised["revision"] == 1
    assert client.post(f"{url}/approve", headers=team["reviewer"]).json()["review_status"] == "approved"
    pdf = client.get(f"{url}/report.pdf", headers=team["viewer"])
    assert pdf.content.startswith(b"%PDF-") and f'filename="{element_type}_{name}_R1_report.pdf"' in pdf.headers["content-disposition"]
    wb = openpyxl.load_workbook(io.BytesIO(client.get(f"{url}/bbs.xlsx", headers=team["viewer"]).content))
    doc = ezdxf.read(io.StringIO(client.get(f"{url}/drawing.dxf", headers=team["viewer"]).content.decode()))
    assert not doc.audit().errors
    return d, revised, wb, doc


def test_slab_goes_through_the_same_life_cycle(client, team, project):
    elements = {e["type"]: e for e in client.get("/api/v1/structural/elements", headers=team["viewer"]).json()}
    slab = elements["slab"]
    assert slab["title"] == "RCC slab" and slab["defaults"]["span_x_mm"] == 3300 and any("Table 26" in x for x in slab["limitations"])
    props = slab["input_schema"]["properties"]
    assert props["long_edge_1"]["group"] and props["span_y_mm"]["unit"] == "mm"

    calc = client.post("/api/v1/structural/slab/calculate", headers=team["viewer"], json={}).json()
    assert calc["key_results"][0]["value"] == "Two-way, Table 26 case 4" and calc["data"]["case"] == 4
    assert [v["id"] for v in calc["drawing"]["views"]] == ["plan", "elevation"]
    one_way = client.post("/api/v1/structural/slab/calculate", headers=team["viewer"], json={"span_y_mm": 7000}).json()
    assert one_way["data"]["one_way"] and one_way["key_results"][0]["value"] == "One-way"
    bad = client.post("/api/v1/structural/slab/calculate", headers=team["viewer"], json={"span_x_mm": 5000, "span_y_mm": 4000})
    assert bad.status_code == 422

    d, revised, wb, doc = _life_cycle(client, team, project, "slab", "S1", {"live_load_kn_m2": 4.0})
    assert revised["result"]["data"]["wu"] > d["result"]["data"]["wu"]
    assert wb["BBS"]["B8"].value.startswith("Short span bottom, middle strip")
    assert {"CLP-REBAR", "CLP-SUPPORT"} <= {layer.dxf.name for layer in doc.layers}


def test_footing_goes_through_the_same_life_cycle(client, team, project):
    elements = {e["type"]: e for e in client.get("/api/v1/structural/elements", headers=team["viewer"]).json()}
    ft = elements["footing"]
    assert ft["title"] == "RCC isolated footing" and ft["defaults"]["p_service_kn"] == 800 and ft["defaults"]["length_mm"] is None

    calc = client.post("/api/v1/structural/footing/calculate", headers=team["viewer"], json={}).json()
    assert calc["key_results"][0]["value"] == "2200 x 2050 x 450" and calc["reinforcement"]["along_l"]["label"] == "8-T20 @ 270"
    r = client.post("/api/v1/structural/footing/calculate", headers=team["viewer"], json={"length_mm": 2000})
    assert r.status_code == 422 and "both" in r.json()["error"]["message"].lower()

    d, revised, wb, doc = _life_cycle(client, team, project, "footing", "F1", {"p_service_kn": 1000})
    assert revised["result"]["data"]["L"] > d["result"]["data"]["L"]
    assert wb["BBS"]["B8"].value.startswith("Bars along L, bottom, T20")
    assert "CLP-CONCRETE" in {layer.dxf.name for layer in doc.layers}

    s = client.get("/api/v1/dashboard/summary", headers=team["viewer"]).json()
    assert s["designs"]["by_type"] == {"footing": 1}


def test_combined_footing_goes_through_the_same_life_cycle(client, team, project):
    cf = {e["type"]: e for e in client.get("/api/v1/structural/elements", headers=team["viewer"]).json()}["combined_footing"]
    assert cf["title"] == "RCC combined footing" and cf["defaults"]["p2_service_kn"] == 1200 and cf["defaults"]["left_end_mm"] is None
    assert cf["input_schema"]["properties"]["column1_width_mm"]["group"] == "Column 1 (left)"

    calc = client.post("/api/v1/structural/combined_footing/calculate", headers=team["viewer"], json={}).json()
    assert calc["status"] == "ok" and calc["key_results"][0]["value"] == "6100 x 1950 x 900"
    assert [v["id"] for v in calc["drawing"]["views"]] == ["plan", "elevation", "section"] and [c["id"] for c in calc["charts"]] == ["moments", "shear"]
    r = client.post("/api/v1/structural/combined_footing/calculate", headers=team["viewer"], json={"left_end_mm": 300, "p1_service_kn": 2000})
    assert r.status_code == 422 and "strap" in r.json()["error"]["message"]

    d, revised, wb, doc = _life_cycle(client, team, project, "combined_footing", "CF1", {"left_end_mm": 200})
    assert revised["result"]["data"]["a"] == 200 and revised["result"]["data"]["L"] < d["result"]["data"]["L"]
    assert wb["BBS"]["B8"].value.startswith("Bars along, bottom")
    assert {"CLP-REBAR", "CLP-SUPPORT", "CLP-CONCRETE"} <= {layer.dxf.name for layer in doc.layers}


def test_flanged_beam_through_the_same_endpoint(client, owner):
    props = {e["type"]: e for e in client.get("/api/v1/structural/elements", headers=owner).json()}["beam"]["input_schema"]["properties"]
    assert props["flange_width_mm"]["show_if"] == {"section": ["t_beam", "l_beam"]}
    r = client.post("/api/v1/structural/beam/calculate", headers=owner,
                    json={"section": "t_beam", "width_mm": 300, "depth_mm": 550, "flange_thickness_mm": 120, "flange_width_mm": 3000,
                          "clear_span_mm": 6000, "support_width_mm": 300, "dead_load_kn_m": 30, "live_load_kn_m": 15})
    res = r.json()
    assert r.status_code == 200 and res["status"] == "ok" and res["data"]["bf"] == 2070 and res["data"]["na_in_flange"]
    r = client.post("/api/v1/structural/beam/calculate", headers=owner, json={"section": "l_beam", "flange_width_mm": 200})
    assert r.status_code == 422 and "more than the web width" in r.json()["error"]["message"]


def test_continuous_beam_goes_through_the_same_life_cycle(client, team, project):
    cb = {e["type"]: e for e in client.get("/api/v1/structural/elements", headers=team["viewer"]).json()}["continuous_beam"]
    assert cb["title"] == "RCC continuous beam" and cb["defaults"]["spans"] == 4 and any("Cl. 22.5.1" in x for x in cb["limitations"])
    calc = client.post("/api/v1/structural/continuous_beam/calculate", headers=team["viewer"], json={}).json()
    assert calc["status"] == "ok" and calc["key_results"][2]["value"] == "5-T16"
    assert [v["id"] for v in calc["drawing"]["views"]] == ["elevation", "sections"]
    r = client.post("/api/v1/structural/continuous_beam/calculate", headers=team["viewer"], json={"spans": 2})
    assert r.status_code == 422 and r.json()["error"]["details"][0]["field"] == "spans"

    d, revised, wb, doc = _life_cycle(client, team, project, "continuous_beam", "CB1", {"live_load_kn_m": 20})
    assert revised["result"]["data"]["m_b"] > d["result"]["data"]["m_b"]
    assert wb["BBS"]["B8"].value.startswith("Bottom bars, end spans")
    assert "CLP-REBAR" in {layer.dxf.name for layer in doc.layers}


def test_continuous_beam_by_elastic_analysis_through_the_same_endpoints(client, team, project):
    cb = {e["type"]: e for e in client.get("/api/v1/structural/elements", headers=team["viewer"]).json()}["continuous_beam"]
    props = cb["input_schema"]["properties"]
    # list inputs reach the client with their rows' schema inlined
    assert props["span_table"]["type"] == "array" and props["span_table"]["items"]["properties"]["clear_span_mm"]["unit"] == "mm"
    assert props["point_loads"]["items"]["properties"]["span"]["type"] == "integer" and "$defs" not in cb["input_schema"]
    assert props["span_table"]["show_if"] == {"analysis": "elastic"} and props["spans"]["show_if"] == {"analysis": "coefficients"}
    calc = client.post("/api/v1/structural/continuous_beam/calculate", headers=team["viewer"], json={"analysis": "elastic"}).json()
    assert calc["status"] == "ok" and calc["data"]["method"] == "elastic" and len(calc["charts"]) == 2
    bad = client.post("/api/v1/structural/continuous_beam/calculate", headers=team["viewer"],
                      json={"analysis": "elastic", "span_table": [{"clear_span_mm": 5000}, {"clear_span_mm": 500}]})
    assert bad.status_code == 422 and bad.json()["error"]["details"][0]["field"] == "span_table.1.clear_span_mm"

    r = client.post(f"/api/v1/projects/{project['id']}/designs", headers=team["engineer"],
                    json={"element_type": "continuous_beam", "name": "CB2", "inputs": {"analysis": "elastic"}})
    assert r.status_code == 201, r.text
    d = r.json()
    url = f"/api/v1/designs/{d['id']}"
    revised = client.put(url, headers=team["engineer"], json={"inputs": {**d["inputs"], "redistribution_pct": 30}}).json()
    assert revised["result"]["data"]["m_sup"][1] < d["result"]["data"]["m_sup"][1]  # more redistribution, less hogging to design for
    pdf = client.get(f"{url}/report.pdf", headers=team["viewer"])
    assert pdf.content.startswith(b"%PDF-")
    wb = openpyxl.load_workbook(io.BytesIO(client.get(f"{url}/bbs.xlsx", headers=team["viewer"]).content))
    assert wb["BBS"]["B8"].value.startswith("Bottom bars")
    doc = ezdxf.read(io.StringIO(client.get(f"{url}/drawing.dxf", headers=team["viewer"]).content.decode()))
    assert not doc.audit().errors
