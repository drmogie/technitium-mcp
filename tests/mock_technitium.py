"""A tiny fake Technitium server for testing. Not part of the tool."""
import json, sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs

GOOD = "test-token-123"
calls = []

class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _send(self, code, body, ctype="application/json", extra=None):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        for k, v in (extra or {}).items(): self.send_header(k, v)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers(); self.wfile.write(data)
    def do_GET(self):
        u = urlparse(self.path); q = {k: v[0] for k, v in parse_qs(u.query).items()}
        auth = self.headers.get("Authorization", "")
        calls.append((u.path, q, auth))
        if auth != f"Bearer {GOOD}":
            return self._send(200, {"status": "invalid-token", "errorMessage": "Invalid token or session expired."})
        if u.path == "/api/dashboard/stats/get":
            return self._send(200, {"status": "ok", "response": {"stats": {"totalQueries": 42, "totalBlocked": 7}}})
        if u.path == "/api/settings/get":
            return self._send(200, {"status": "ok", "response": {"version": "15.0", "enableBlocking": True, "dnsServerDomain": "technitium-dns"}})
        if u.path == "/api/settings/set":
            return self._send(200, {"status": "ok", "response": {"applied": q}})
        if u.path == "/api/settings/temporaryDisableBlocking":
            return self._send(200, {"status": "ok", "response": {"temporaryDisableBlockingTill": "soon"}})
        if u.path == "/api/cache/flush":
            return self._send(200, {"status": "ok"})
        if u.path == "/api/zones/list":
            return self._send(200, {"status": "ok", "response": {"zones": [{"name": "home.arpa"}]}})
        if u.path == "/api/zones/delete":
            return self._send(200, {"status": "ok"})
        if u.path == "/api/zones/create":
            return self._send(200, {"status": "error", "errorMessage": "Zone already exists: " + q.get("zone", "") + " token=" + GOOD})
        if u.path == "/api/settings/backup":
            return self._send(200, b"PK\x03\x04fakezip", "application/zip", {"Content-Disposition": 'attachment; filename="backup.zip"'})
        if u.path == "/api/test/getBig":
            return self._send(200, {"status": "ok", "response": {"x": "a" * 50000}})
        return self._send(404, {"status": "error", "errorMessage": "nope"})

if __name__ == "__main__":
    HTTPServer(("127.0.0.1", int(sys.argv[1])), H).serve_forever()
