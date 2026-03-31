"""Unit tests for the ServiceNow stub server."""

import json

import pytest

from makita_dr.servicenow_stub import ServiceNowStubServer


@pytest.fixture
def stub():
    """Create a ServiceNowStubServer and return its Flask test client."""
    server = ServiceNowStubServer()
    return server


@pytest.fixture
def client(stub):
    """Flask test client for the stub server."""
    stub.app.config["TESTING"] = True
    return stub.app.test_client()


class TestCreateIncident:
    def test_returns_201_with_result(self, client):
        resp = client.post(
            "/api/now/table/incident",
            json={"short_description": "DR failover initiated", "urgency": "1"},
        )
        assert resp.status_code == 201
        data = resp.get_json()
        assert "result" in data
        result = data["result"]
        assert "sys_id" in result
        assert "number" in result
        assert result["number"].startswith("INC")
        assert result["short_description"] == "DR failover initiated"
        assert result["urgency"] == "1"

    def test_generates_unique_sys_ids(self, client):
        ids = set()
        for _ in range(5):
            resp = client.post("/api/now/table/incident", json={"short_description": "test"})
            ids.add(resp.get_json()["result"]["sys_id"])
        assert len(ids) == 5

    def test_includes_timestamps(self, client):
        resp = client.post("/api/now/table/incident", json={})
        result = resp.get_json()["result"]
        assert "sys_created_on" in result
        assert "sys_updated_on" in result

    def test_empty_payload(self, client):
        resp = client.post(
            "/api/now/table/incident",
            data="",
            content_type="application/json",
        )
        assert resp.status_code == 201


class TestUpdateIncident:
    def test_updates_existing_incident(self, client):
        create_resp = client.post(
            "/api/now/table/incident",
            json={"short_description": "original", "state": "1"},
        )
        sys_id = create_resp.get_json()["result"]["sys_id"]

        update_resp = client.patch(
            f"/api/now/table/incident/{sys_id}",
            json={"state": "6", "close_notes": "Resolved"},
        )
        assert update_resp.status_code == 200
        result = update_resp.get_json()["result"]
        assert result["state"] == "6"
        assert result["close_notes"] == "Resolved"
        # Original fields preserved
        assert result["short_description"] == "original"

    def test_returns_404_for_unknown_sys_id(self, client):
        resp = client.patch(
            "/api/now/table/incident/nonexistent",
            json={"state": "6"},
        )
        assert resp.status_code == 404


class TestGetIncident:
    def test_retrieves_existing_incident(self, client):
        create_resp = client.post(
            "/api/now/table/incident",
            json={"short_description": "get test"},
        )
        sys_id = create_resp.get_json()["result"]["sys_id"]

        get_resp = client.get(f"/api/now/table/incident/{sys_id}")
        assert get_resp.status_code == 200
        assert get_resp.get_json()["result"]["short_description"] == "get test"

    def test_returns_404_for_unknown_sys_id(self, client):
        resp = client.get("/api/now/table/incident/nonexistent")
        assert resp.status_code == 404


class TestListIncidents:
    def test_returns_empty_list_initially(self, client):
        resp = client.get("/api/now/table/incident")
        assert resp.status_code == 200
        assert resp.get_json()["result"] == []

    def test_returns_all_created_incidents(self, client):
        for i in range(3):
            client.post("/api/now/table/incident", json={"short_description": f"inc-{i}"})

        resp = client.get("/api/now/table/incident")
        assert len(resp.get_json()["result"]) == 3


class TestRequestLogging:
    def test_log_starts_empty(self, stub):
        assert stub.get_request_log() == []

    def test_create_is_logged(self, stub, client):
        client.post("/api/now/table/incident", json={"short_description": "logged"})
        log = stub.get_request_log()
        assert len(log) == 1
        entry = log[0]
        assert entry["method"] == "POST"
        assert entry["path"] == "/api/now/table/incident"
        assert entry["body"]["short_description"] == "logged"
        assert entry["sys_id"] is not None
        assert "timestamp" in entry

    def test_update_is_logged(self, stub, client):
        resp = client.post("/api/now/table/incident", json={})
        sys_id = resp.get_json()["result"]["sys_id"]
        client.patch(f"/api/now/table/incident/{sys_id}", json={"state": "2"})

        log = stub.get_request_log()
        assert len(log) == 2
        assert log[1]["method"] == "PATCH"
        assert sys_id in log[1]["path"]

    def test_get_is_logged(self, stub, client):
        resp = client.post("/api/now/table/incident", json={})
        sys_id = resp.get_json()["result"]["sys_id"]
        client.get(f"/api/now/table/incident/{sys_id}")

        log = stub.get_request_log()
        assert len(log) == 2
        assert log[1]["method"] == "GET"

    def test_list_is_logged(self, stub, client):
        client.get("/api/now/table/incident")
        log = stub.get_request_log()
        assert len(log) == 1
        assert log[0]["method"] == "GET"
        assert log[0]["path"] == "/api/now/table/incident"

    def test_all_requests_logged_in_order(self, stub, client):
        # Create, update, get — 3 requests total
        resp = client.post("/api/now/table/incident", json={"short_description": "a"})
        sys_id = resp.get_json()["result"]["sys_id"]
        client.patch(f"/api/now/table/incident/{sys_id}", json={"state": "2"})
        client.get(f"/api/now/table/incident/{sys_id}")

        log = stub.get_request_log()
        assert len(log) == 3
        assert [e["method"] for e in log] == ["POST", "PATCH", "GET"]

    def test_log_returns_copy(self, stub, client):
        client.post("/api/now/table/incident", json={})
        log1 = stub.get_request_log()
        log1.clear()
        # Internal log should be unaffected
        assert len(stub.get_request_log()) == 1
