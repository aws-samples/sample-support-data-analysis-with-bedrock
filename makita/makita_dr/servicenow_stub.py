"""ServiceNow stub server that mimics the ServiceNow REST Table API.

Accepts and displays incoming API requests for demonstration and verification.
Validates: Requirements 4.1, 4.6
"""

import logging
import threading
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

from flask import Flask, jsonify, request

logger = logging.getLogger(__name__)


class ServiceNowStubServer:
    """A lightweight HTTP server that mimics the ServiceNow REST API.

    Logs and displays all incoming requests for demonstration.
    """

    def __init__(self, host: str = "0.0.0.0", port: int = 8080):
        self.host = host
        self.port = port
        self._request_log: List[dict] = []
        self._incidents: Dict[str, dict] = {}
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
        logger.info("ServiceNow stub server started on %s:%s", self.host, self.port)

    def get_request_log(self) -> list:
        """Return all received requests for verification."""
        return list(self._request_log)

    # ------------------------------------------------------------------
    # Flask app factory
    # ------------------------------------------------------------------

    def _create_app(self) -> Flask:
        app = Flask(__name__)
        app.config["TESTING"] = True

        @app.route("/api/now/table/incident", methods=["POST"])
        def create_incident():
            return self._handle_create_incident()

        @app.route("/api/now/table/incident/<sys_id>", methods=["PATCH", "PUT"])
        def update_incident(sys_id: str):
            return self._handle_update_incident(sys_id)

        @app.route("/api/now/table/incident/<sys_id>", methods=["GET"])
        def get_incident(sys_id: str):
            return self._handle_get_incident(sys_id)

        @app.route("/api/now/table/incident", methods=["GET"])
        def list_incidents():
            return self._handle_list_incidents()

        return app

    # ------------------------------------------------------------------
    # Route handlers
    # ------------------------------------------------------------------

    def _handle_create_incident(self):
        payload = request.get_json(silent=True) or {}
        sys_id = str(uuid.uuid4())
        now_ts = datetime.now(timezone.utc).isoformat()

        record = {
            "sys_id": sys_id,
            "number": f"INC{uuid.uuid4().hex[:8].upper()}",
            "sys_created_on": now_ts,
            "sys_updated_on": now_ts,
            **payload,
        }
        self._incidents[sys_id] = record

        self._log_request("POST", "/api/now/table/incident", payload, sys_id)
        logger.info("Created stub incident %s (sys_id=%s)", record["number"], sys_id)

        return jsonify({"result": record}), 201

    def _handle_update_incident(self, sys_id: str):
        payload = request.get_json(silent=True) or {}

        if sys_id not in self._incidents:
            self._log_request(request.method, f"/api/now/table/incident/{sys_id}", payload, sys_id)
            return jsonify({"error": {"message": "Record not found"}}), 404

        self._incidents[sys_id].update(payload)
        self._incidents[sys_id]["sys_updated_on"] = datetime.now(timezone.utc).isoformat()

        self._log_request(request.method, f"/api/now/table/incident/{sys_id}", payload, sys_id)
        logger.info("Updated stub incident sys_id=%s", sys_id)

        return jsonify({"result": self._incidents[sys_id]}), 200

    def _handle_get_incident(self, sys_id: str):
        self._log_request("GET", f"/api/now/table/incident/{sys_id}", None, sys_id)

        if sys_id not in self._incidents:
            return jsonify({"error": {"message": "Record not found"}}), 404

        return jsonify({"result": self._incidents[sys_id]}), 200

    def _handle_list_incidents(self):
        self._log_request("GET", "/api/now/table/incident", None, None)
        return jsonify({"result": list(self._incidents.values())}), 200

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _log_request(self, method: str, path: str, body: Optional[dict], sys_id: Optional[str]) -> None:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "method": method,
            "path": path,
            "body": body,
            "sys_id": sys_id,
        }
        self._request_log.append(entry)
        logger.info("Logged request: %s %s", method, path)
