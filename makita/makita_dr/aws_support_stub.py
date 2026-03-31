"""AWS Support stub server that intercepts Boto3 Support API calls.

Intercepts Boto3 Support API calls using endpoint URL override.
Logs and displays all received API calls for demonstration and verification.

Validates: Requirements 6.1, 6.6
"""

import json
import logging
import threading
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

from flask import Flask, Response, request

logger = logging.getLogger(__name__)

# The Boto3 Support client uses the AWS JSON 1.1 protocol.
# All requests are POST to "/" with an X-Amz-Target header indicating the operation.
_TARGET_PREFIX = "AWSSupport_20130415"


class AWSSupportStub:
    """Intercepts Boto3 Support API calls using endpoint URL override.

    Logs and displays all received API calls for demonstration.
    """

    def __init__(self, host: str = "0.0.0.0", port: int = 8081):
        self.host = host
        self.port = port
        self._request_log: List[dict] = []
        self._cases: Dict[str, dict] = {}
        self._communications: Dict[str, List[dict]] = {}  # caseId -> list of comms
        self.app = self._create_app()
        self._server_thread: Optional[threading.Thread] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the stub server in a background thread."""
        self._server_thread = threading.Thread(
            target=self.app.run,
            kwargs={"host": self.host, "port": self.port, "use_reloader": False},
            daemon=True,
        )
        self._server_thread.start()
        logger.info("AWS Support stub server started on %s:%s", self.host, self.port)

    def get_request_log(self) -> list:
        """Return all received API calls for verification."""
        return list(self._request_log)

    # ------------------------------------------------------------------
    # Flask app factory
    # ------------------------------------------------------------------

    def _create_app(self) -> Flask:
        app = Flask(__name__)
        app.config["TESTING"] = True

        @app.route("/", methods=["POST"])
        def handle_request():
            return self._dispatch()

        return app

    # ------------------------------------------------------------------
    # Request dispatcher
    # ------------------------------------------------------------------

    def _dispatch(self) -> Response:
        """Route the request to the correct handler based on X-Amz-Target."""
        target = request.headers.get("X-Amz-Target", "")
        # Boto3 sends application/x-amz-json-1.1 which Flask doesn't auto-parse
        body = request.get_json(silent=True, force=True) or {}

        operation = target.replace(f"{_TARGET_PREFIX}.", "") if target.startswith(_TARGET_PREFIX) else target

        self._log_request(operation, body)

        handlers = {
            "CreateCase": self._handle_create_case,
            "AddCommunicationToCase": self._handle_add_communication,
            "DescribeCases": self._handle_describe_cases,
        }

        handler = handlers.get(operation)
        if handler is None:
            return self._json_response(
                {"__type": "UnknownOperationException", "message": f"Unknown operation: {operation}"},
                status=400,
            )

        return handler(body)

    # ------------------------------------------------------------------
    # Operation handlers
    # ------------------------------------------------------------------

    def _handle_create_case(self, body: dict) -> Response:
        case_id = f"case-{uuid.uuid4().hex[:12]}"
        display_id = f"DR-{uuid.uuid4().hex[:8].upper()}"
        now_ts = datetime.now(timezone.utc).isoformat()

        case_record = {
            "caseId": case_id,
            "displayId": display_id,
            "subject": body.get("subject", ""),
            "serviceCode": body.get("serviceCode", ""),
            "categoryCode": body.get("categoryCode", ""),
            "severityCode": body.get("severityCode", ""),
            "communicationBody": body.get("communicationBody", ""),
            "language": body.get("language", "en"),
            "ccEmailAddresses": body.get("ccEmailAddresses", []),
            "status": "opened",
            "timeCreated": now_ts,
        }
        self._cases[case_id] = case_record
        self._communications[case_id] = []

        logger.info("Created stub Support case %s (display=%s)", case_id, display_id)
        return self._json_response({"caseId": case_id})

    def _handle_add_communication(self, body: dict) -> Response:
        case_id = body.get("caseId", "")

        if case_id and case_id not in self._cases:
            return self._json_response(
                {"__type": "CaseIdNotFound", "message": f"Case {case_id} not found"},
                status=400,
            )

        comm = {
            "caseId": case_id,
            "body": body.get("communicationBody", ""),
            "submittedBy": "stub-agent",
            "timeCreated": datetime.now(timezone.utc).isoformat(),
        }
        if case_id:
            self._communications[case_id].append(comm)

        logger.info("Added communication to case %s", case_id)
        return self._json_response({"result": True})

    def _handle_describe_cases(self, body: dict) -> Response:
        case_ids = body.get("caseIdList", [])
        # AWS API defaults includeCommunications to True
        include_comms = body.get("includeCommunications", True)

        if case_ids:
            cases = [self._cases[cid] for cid in case_ids if cid in self._cases]
        else:
            cases = list(self._cases.values())

        result_cases = []
        for case in cases:
            entry = dict(case)
            if include_comms:
                comms = self._communications.get(case["caseId"], [])
                entry["recentCommunications"] = {"communications": comms}
            result_cases.append(entry)

        return self._json_response({"cases": result_cases})

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _log_request(self, operation: str, body: dict) -> None:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "operation": operation,
            "body": body,
        }
        self._request_log.append(entry)
        logger.info("Logged AWS Support API call: %s", operation)

    @staticmethod
    def _json_response(data: dict, status: int = 200) -> Response:
        return Response(
            json.dumps(data),
            status=status,
            content_type="application/x-amz-json-1.1",
        )
