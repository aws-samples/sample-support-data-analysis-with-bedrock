"""Unit tests for the AWS Support stub server."""

import json

import pytest

from makita_dr.aws_support_stub import AWSSupportStub


@pytest.fixture
def stub():
    server = AWSSupportStub()
    return server


@pytest.fixture
def client(stub):
    stub.app.config["TESTING"] = True
    return stub.app.test_client()


def _post(client, operation, body=None):
    """Helper: send a Boto3-style JSON request to the stub."""
    return client.post(
        "/",
        data=json.dumps(body or {}),
        content_type="application/x-amz-json-1.1",
        headers={"X-Amz-Target": f"AWSSupport_20130415.{operation}"},
    )


# ------------------------------------------------------------------
# CreateCase
# ------------------------------------------------------------------

class TestCreateCase:
    def test_returns_case_id(self, client):
        resp = _post(client, "CreateCase", {
            "subject": "DR failover initiated",
            "serviceCode": "amazon-rds",
            "severityCode": "high",
            "communicationBody": "Initiating DR failover from us-east-1 to us-east-2",
        })
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert "caseId" in data
        assert data["caseId"].startswith("case-")

    def test_generates_unique_case_ids(self, client):
        ids = set()
        for _ in range(5):
            resp = _post(client, "CreateCase", {"subject": "test"})
            ids.add(json.loads(resp.data)["caseId"])
        assert len(ids) == 5

    def test_stores_case_fields(self, stub, client):
        _post(client, "CreateCase", {
            "subject": "DR event",
            "serviceCode": "amazon-rds",
            "categoryCode": "database-failover",
            "severityCode": "urgent",
            "communicationBody": "body text",
            "language": "en",
        })
        # Verify via DescribeCases
        resp = _post(client, "DescribeCases", {})
        cases = json.loads(resp.data)["cases"]
        assert len(cases) == 1
        case = cases[0]
        assert case["subject"] == "DR event"
        assert case["serviceCode"] == "amazon-rds"
        assert case["categoryCode"] == "database-failover"
        assert case["severityCode"] == "urgent"
        assert case["status"] == "opened"

    def test_empty_body(self, client):
        resp = _post(client, "CreateCase", {})
        assert resp.status_code == 200
        assert "caseId" in json.loads(resp.data)


# ------------------------------------------------------------------
# AddCommunicationToCase
# ------------------------------------------------------------------

class TestAddCommunication:
    def test_adds_communication_to_existing_case(self, client):
        create_resp = _post(client, "CreateCase", {"subject": "test"})
        case_id = json.loads(create_resp.data)["caseId"]

        resp = _post(client, "AddCommunicationToCase", {
            "caseId": case_id,
            "communicationBody": "Failover completed successfully",
        })
        assert resp.status_code == 200
        assert json.loads(resp.data)["result"] is True

    def test_communication_appears_in_describe(self, client):
        create_resp = _post(client, "CreateCase", {"subject": "test"})
        case_id = json.loads(create_resp.data)["caseId"]

        _post(client, "AddCommunicationToCase", {
            "caseId": case_id,
            "communicationBody": "Update: replica promoted",
        })

        resp = _post(client, "DescribeCases", {"caseIdList": [case_id]})
        case = json.loads(resp.data)["cases"][0]
        comms = case["recentCommunications"]["communications"]
        assert len(comms) == 1
        assert comms[0]["body"] == "Update: replica promoted"

    def test_returns_error_for_unknown_case(self, client):
        resp = _post(client, "AddCommunicationToCase", {
            "caseId": "case-nonexistent",
            "communicationBody": "test",
        })
        assert resp.status_code == 400
        data = json.loads(resp.data)
        assert "CaseIdNotFound" in data["__type"]


# ------------------------------------------------------------------
# DescribeCases
# ------------------------------------------------------------------

class TestDescribeCases:
    def test_returns_empty_list_initially(self, client):
        resp = _post(client, "DescribeCases", {})
        assert resp.status_code == 200
        assert json.loads(resp.data)["cases"] == []

    def test_returns_all_cases(self, client):
        for i in range(3):
            _post(client, "CreateCase", {"subject": f"case-{i}"})

        resp = _post(client, "DescribeCases", {})
        cases = json.loads(resp.data)["cases"]
        assert len(cases) == 3

    def test_filters_by_case_id_list(self, client):
        ids = []
        for i in range(3):
            r = _post(client, "CreateCase", {"subject": f"case-{i}"})
            ids.append(json.loads(r.data)["caseId"])

        resp = _post(client, "DescribeCases", {"caseIdList": [ids[0], ids[2]]})
        cases = json.loads(resp.data)["cases"]
        assert len(cases) == 2
        returned_ids = {c["caseId"] for c in cases}
        assert returned_ids == {ids[0], ids[2]}

    def test_excludes_communications_when_requested(self, client):
        create_resp = _post(client, "CreateCase", {"subject": "test"})
        case_id = json.loads(create_resp.data)["caseId"]
        _post(client, "AddCommunicationToCase", {
            "caseId": case_id,
            "communicationBody": "hello",
        })

        resp = _post(client, "DescribeCases", {
            "caseIdList": [case_id],
            "includeCommunications": False,
        })
        case = json.loads(resp.data)["cases"][0]
        assert "recentCommunications" not in case


# ------------------------------------------------------------------
# Unknown operation
# ------------------------------------------------------------------

class TestUnknownOperation:
    def test_returns_400_for_unknown_operation(self, client):
        resp = _post(client, "FakeOperation", {})
        assert resp.status_code == 400
        data = json.loads(resp.data)
        assert "UnknownOperationException" in data["__type"]


# ------------------------------------------------------------------
# Request logging
# ------------------------------------------------------------------

class TestRequestLogging:
    def test_log_starts_empty(self, stub):
        assert stub.get_request_log() == []

    def test_create_case_is_logged(self, stub, client):
        _post(client, "CreateCase", {"subject": "logged"})
        log = stub.get_request_log()
        assert len(log) == 1
        entry = log[0]
        assert entry["operation"] == "CreateCase"
        assert entry["body"]["subject"] == "logged"
        assert "timestamp" in entry

    def test_add_communication_is_logged(self, stub, client):
        r = _post(client, "CreateCase", {"subject": "test"})
        case_id = json.loads(r.data)["caseId"]
        _post(client, "AddCommunicationToCase", {
            "caseId": case_id,
            "communicationBody": "update",
        })
        log = stub.get_request_log()
        assert len(log) == 2
        assert log[1]["operation"] == "AddCommunicationToCase"

    def test_describe_cases_is_logged(self, stub, client):
        _post(client, "DescribeCases", {})
        log = stub.get_request_log()
        assert len(log) == 1
        assert log[0]["operation"] == "DescribeCases"

    def test_all_requests_logged_in_order(self, stub, client):
        r = _post(client, "CreateCase", {"subject": "a"})
        case_id = json.loads(r.data)["caseId"]
        _post(client, "AddCommunicationToCase", {
            "caseId": case_id,
            "communicationBody": "b",
        })
        _post(client, "DescribeCases", {})

        log = stub.get_request_log()
        assert len(log) == 3
        assert [e["operation"] for e in log] == [
            "CreateCase",
            "AddCommunicationToCase",
            "DescribeCases",
        ]

    def test_log_returns_copy(self, stub, client):
        _post(client, "CreateCase", {"subject": "test"})
        log1 = stub.get_request_log()
        log1.clear()
        # Internal log should be unaffected
        assert len(stub.get_request_log()) == 1

    def test_unknown_operation_is_logged(self, stub, client):
        _post(client, "FakeOp", {"foo": "bar"})
        log = stub.get_request_log()
        assert len(log) == 1
        assert log[0]["operation"] == "FakeOp"
