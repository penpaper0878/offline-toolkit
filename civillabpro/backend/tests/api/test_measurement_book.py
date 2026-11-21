"""The measurement book (EST-004): entries against an issued estimate, checked by a second person, and progress per item."""

from datetime import date, timedelta

import pytest

from tests.conftest import register

DOC = {"items": [
    {"id": "a", "description": "Cement concrete M20 in footings", "unit": "cum", "rate": 6544.15, "quantity_mode": "direct", "quantity": 10.0},
    {"id": "b", "description": "Brick masonry in foundations", "unit": "cum", "rate": 5210.4, "quantity_mode": "direct", "quantity": 4.5},
]}
TODAY = date.today().isoformat()


def _issued(client, team, project):
    est = client.post(f"/api/v1/projects/{project['id']}/estimates", headers=team["engineer"], json={"title": "Foundations"}).json()
    assert client.put(f"/api/v1/estimates/{est['id']}", headers=team["engineer"], json={"title": "Foundations", "doc": DOC}).status_code == 200
    return est


def _entry(item_id="a", lines=None, on=TODAY, location="Footings F1 to F4"):
    return {"item_id": item_id, "measured_on": on, "location": location,
            "lines": lines or [{"description": "F1 to F4", "nos": 4, "length": 1.8, "breadth": 1.8, "depth": 0.45}]}


def test_entries_are_measured_checked_and_summed_against_the_estimate(client, team, project):
    est = _issued(client, team, project)
    url = f"/api/v1/estimates/{est['id']}/measurement-book"
    # not before the estimate is issued
    assert client.get(url, headers=team["viewer"]).json()["open"] is False
    assert client.post(url, headers=team["engineer"], json=_entry()).status_code == 409
    assert client.post(f"/api/v1/estimates/{est['id']}/issue", headers=team["reviewer"]).status_code == 200

    # the lines are worked out by the server, also before saving
    calc = client.post("/api/v1/measurement-book/calculate", headers=team["viewer"], json={"lines": _entry()["lines"]}).json()
    assert calc == {"lines": [5.83], "quantity": 5.83}  # 4 x 1.8 x 1.8 x 0.45 = 5.832

    e1 = client.post(url, headers=team["engineer"], json=_entry())
    assert e1.status_code == 201, e1.text
    e1 = e1.json()
    assert (e1["entry_no"], e1["quantity"], e1["status"], e1["measured_by_name"]) == (1, 5.83, "recorded", "Engineer User")
    lines2 = [{"description": "F5 to F8", "nos": 4, "length": 1.8, "breadth": 1.8, "depth": 0.45},
              {"description": "F9", "nos": 1, "length": 2.4, "breadth": 2.4, "depth": 0.6},
              {"description": "Pipe sleeve", "nos": 1, "length": 0.5, "breadth": 0.5, "depth": 0.6, "deduct": True}]
    e2 = client.post(url, headers=team["engineer"], json=_entry(lines=lines2, location="Footings F5 to F9")).json()
    # 5.83 + 3.46 (2.4 x 2.4 x 0.6 = 3.456) - 0.15 = 9.14
    assert e2["entry_no"] == 2 and e2["line_quantities"] == [5.83, 3.46, -0.15] and e2["quantity"] == 9.14
    e3 = client.post(url, headers=team["engineer"], json=_entry("b", [{"description": "Walls", "nos": 1, "length": 12.0, "breadth": 0.23, "depth": 0.9}])).json()
    assert e3["quantity"] == 2.48  # 12 x 0.23 x 0.9 = 2.484

    # wrong item, a date to come, an empty entry, a viewer
    assert client.post(url, headers=team["engineer"], json=_entry("zz")).status_code == 422
    assert client.post(url, headers=team["engineer"], json=_entry(on=(date.today() + timedelta(days=3)).isoformat())).status_code == 422
    assert client.post(url, headers=team["engineer"], json={**_entry(), "lines": []}).status_code == 422
    assert client.post(url, headers=team["viewer"], json=_entry()).status_code == 403

    # checked by someone other than the one who measured; a checked entry is kept as it is
    assert client.post(f"/api/v1/mb-entries/{e1['id']}/check", headers=team["engineer"]).status_code == 403  # engineers do not check
    assert client.post(f"/api/v1/mb-entries/{e1['id']}/check", headers=team["owner"]).status_code == 200
    assert client.post(f"/api/v1/mb-entries/{e2['id']}/check", headers=team["reviewer"]).json()["checked_by_name"] == "Reviewer User"
    assert client.post(f"/api/v1/mb-entries/{e2['id']}/check", headers=team["reviewer"]).status_code == 409
    assert client.put(f"/api/v1/mb-entries/{e1['id']}", headers=team["engineer"], json=_entry()).status_code == 409
    assert client.delete(f"/api/v1/mb-entries/{e1['id']}", headers=team["engineer"]).status_code == 409
    assert client.post(url, headers=team["reviewer"], json=_entry()).status_code == 403  # reviewers check, they do not record
    own = client.post(url, headers=team["owner"], json=_entry(lines=[{"description": "x", "nos": 1, "length": 1.0}])).json()
    assert client.post(f"/api/v1/mb-entries/{own['id']}/check", headers=team["owner"]).status_code == 409  # self-check
    assert client.delete(f"/api/v1/mb-entries/{own['id']}", headers=team["engineer"]).status_code == 204
    # a recorded entry may be corrected
    fixed = client.put(f"/api/v1/mb-entries/{e3['id']}", headers=team["engineer"],
                       json=_entry("b", [{"description": "Walls", "nos": 1, "length": 24.0, "breadth": 0.23, "depth": 0.9}])).json()
    assert fixed["quantity"] == 4.97 and fixed["entry_no"] == 3  # 24 x 0.23 x 0.9 = 4.968

    book = client.get(url, headers=team["viewer"]).json()
    assert book["open"] is True and [m["entry_no"] for m in book["entries"]] == [1, 2, 3]
    a, b = book["items"]
    # item a: 5.83 + 9.14 = 14.97 against 10: excess 4.97, valued at 6544.15 = 32524.43; measured 14.97 x 6544.15 = 97965.93
    assert (a["estimated"], a["measured"], a["checked"], a["balance"], a["excess"], a["percent"]) == (10.0, 14.97, 14.97, 0.0, 4.97, 149.7)
    assert (a["value_measured"], a["value_excess"], a["entries"]) == (97965.93, 32524.43, 2)
    # item b: 4.97 of 4.5, not checked
    assert (b["measured"], b["checked"], b["excess"], b["value_measured"], b["value_checked"]) == (4.97, 0.0, 0.47, 25895.69, 0.0)
    assert book["value_measured"] == pytest.approx(97965.93 + 25895.69) and book["value_checked"] == 97965.93

    # a revision keeps the book; an item taken out of the estimate is still shown, flagged
    client.post(f"/api/v1/estimates/{est['id']}/revise", headers=team["engineer"])
    client.put(f"/api/v1/estimates/{est['id']}", headers=team["engineer"], json={"title": "Foundations", "doc": {"items": DOC["items"][:1]}})
    book = client.get(url, headers=team["viewer"]).json()
    assert book["open"] is True and [(i["item_id"], i["in_estimate"]) for i in book["items"]] == [("a", True), ("b", False)]
    assert client.post(url, headers=team["engineer"], json=_entry("b")).status_code == 422  # not in the current revision
    assert client.delete(f"/api/v1/estimates/{est['id']}", headers=team["engineer"]).status_code == 409  # the book keeps it

    pdf = client.get(f"/api/v1/estimates/{est['id']}/measurement-book.pdf", headers=team["viewer"])
    assert pdf.content.startswith(b"%PDF-") and 'filename="measurement_book_Foundations.pdf"' in pdf.headers["content-disposition"]
    log = [x["action"] for x in client.get("/api/v1/users/audit", headers=team["owner"]).json()]
    assert {"mb.recorded", "mb.checked", "mb.changed", "mb.deleted"} <= set(log)

    other = register(client, "o@other.example", "Other", "Other Owner")
    assert client.get(url, headers=other).status_code == 404
    assert client.post(f"/api/v1/mb-entries/{e3['id']}/check", headers=other).status_code == 404
    assert client.delete(f"/api/v1/mb-entries/{e3['id']}", headers=other).status_code == 404
