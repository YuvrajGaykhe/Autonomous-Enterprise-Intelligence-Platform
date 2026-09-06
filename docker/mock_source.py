"""
Minimal mock-source HTTP server for A2 container verification.

This is a deliberately minimal service scaffold that proves the
mock-source Docker container starts and is reachable on the network.

The actual mock data endpoints (/odoo/..., /rest/...) belong to
Task C3 and will replace this scaffold.

Implementation choice (A2): uses Python's built-in http.server to
avoid introducing additional dependencies. Task C3 may replace
this with a different framework if appropriate.
"""

import json
import os
from http.server import HTTPServer, BaseHTTPRequestHandler


class MockSourceHandler(BaseHTTPRequestHandler):
    """Handles HTTP requests for the mock-source service."""

    def do_GET(self) -> None:
        """Handle GET requests. Only /health is implemented for A2."""
        if self.path == "/health":
            self._send_json(200, {
                "status": "healthy",
                "service": "mock-source",
                "message": "Mock source service is running. "
                           "Odoo and REST endpoints will be added in Task C3.",
            })
        elif self.path == "/":
            self._send_json(200, {
                "service": "mock-source",
                "paths": {
                    "/health": "Service health check",
                    "/odoo/...": "Odoo mock endpoints (Task C3)",
                    "/rest/...": "REST mock endpoints (Task C3)",
                },
            })
        else:
            self._send_json(404, {
                "error": "not_found",
                "message": f"Path {self.path} is not implemented yet. "
                           f"See Task C3 for Odoo/REST mock endpoints.",
            })

    def _send_json(self, status_code: int, body: dict) -> None:
        """Send a JSON response."""
        payload = json.dumps(body, indent=2).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format: str, *args) -> None:
        """Override to use a cleaner log format."""
        print(f"[mock-source] {self.address_string()} - {format % args}")


def main() -> None:
    """Start the mock-source HTTP server."""
    host = os.environ.get("MOCK_SOURCE_HOST", "0.0.0.0")
    port = int(os.environ.get("MOCK_SOURCE_PORT", "8080"))

    server = HTTPServer((host, port), MockSourceHandler)
    print(f"[mock-source] Starting on {host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("[mock-source] Shutting down.")
        server.server_close()


if __name__ == "__main__":
    main()
