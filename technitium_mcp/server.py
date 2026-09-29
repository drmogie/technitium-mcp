"""Technitium DNS Server MCP tool.

Lets Claude read and change a Technitium DNS Server through its HTTP API.

Settings come from environment variables only. The token is never written
to disk, never printed, and never sent anywhere except the Technitium server.

  TECHNITIUM_URL            Example: http://172.16.90.10:5380   (required)
  TECHNITIUM_TOKEN          API token from the Technitium web page  (required)
  TECHNITIUM_VERIFY_TLS     "false" to skip TLS checks for a self-signed https URL
  TECHNITIUM_TOKEN_IN_QUERY "true" for old servers that ignore the Bearer header
  TECHNITIUM_DOWNLOAD_DIR   Where file downloads are saved
"""

from __future__ import annotations

import json
import os
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

__version__ = "2026.09.28.01"

mcp = FastMCP("technitium-dns")

CATALOG_PATH = Path(__file__).with_name("endpoints.json")
try:
    CATALOG: list[dict[str, Any]] = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
except (OSError, ValueError):
    CATALOG = []
CATALOG_BY_PATH = {e["path"]: e for e in CATALOG}

# ---------------------------------------------------------------------------
# Safety tiers
# ---------------------------------------------------------------------------
# read        runs right away
# change      needs confirm=true (Claude must ask the user first)
# destructive needs confirm=true AND confirm_phrase equal to the endpoint path

READ_PREFIXES = (
    "get", "list", "view", "check", "status", "state", "resolve",
    "health", "export", "backup", "query", "download",
)
DESTRUCTIVE_PREFIXES = (
    "delete", "remove", "uninstall", "restore", "import", "changepassword",
    "logout", "init", "join", "leave", "sign", "unsign",
)
# Never sent through this tool. These carry passwords through the chat.
BLOCKED_PATHS = {"/api/user/login", "/api/user/createToken"}
# Settings that can lock you out or stop DNS.
RISKY_SETTINGS = {
    "webServiceLocalAddresses", "webServiceHttpPort", "webServiceEnableTls",
    "webServiceHttpToTlsRedirect", "webServiceTlsPort", "webServiceUseSelfSignedTlsCertificate",
    "webServiceTlsCertificatePath", "webServiceTlsCertificatePassword",
    "dnsServerLocalEndPoints", "enableDnsOverHttp", "enableDnsOverTls",
    "enableDnsOverHttps", "enableDnsOverQuic", "recursion", "recursionNetworkACL",
    "forwarders", "forwarderProtocol", "proxy",
}


def _verb(path: str) -> str:
    return path.rstrip("/").rsplit("/", 1)[-1]


def classify(path: str, params: dict[str, Any]) -> str:
    verb = _verb(path).lower()
    if path == "/api/admin/users/set":
        if str(params.get("disabled", "")).lower() == "true" or "newPass" in params:
            return "destructive"
    if path == "/api/settings/set" and RISKY_SETTINGS.intersection(params):
        return "destructive"
    if verb.startswith(DESTRUCTIVE_PREFIXES):
        return "destructive"
    if verb.startswith(READ_PREFIXES):
        return "read"
    return "change"


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

def _config() -> tuple[str, str]:
    url = os.environ.get("TECHNITIUM_URL", "").strip().rstrip("/")
    token = os.environ.get("TECHNITIUM_TOKEN", "").strip()
    if not url or not token:
        raise RuntimeError(
            "Set TECHNITIUM_URL and TECHNITIUM_TOKEN in this tool's environment "
            "(see the README). The token is not stored anywhere else."
        )
    return url, token


def _scrub(text: str, token: str) -> str:
    return text.replace(token, "***") if token else text


def _to_param(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, tuple)):
        return ",".join(str(v) for v in value)
    return str(value)


def _download_dir() -> Path:
    base = os.environ.get("TECHNITIUM_DOWNLOAD_DIR")
    path = Path(base) if base else Path.home() / "technitium-downloads"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _request(path: str, params: dict[str, Any]) -> dict[str, Any]:
    """Call the API. Returns a dict with ok, and either data or error."""
    base, token = _config()
    query = {k: v for k, v in ((k, _to_param(v)) for k, v in params.items()) if v is not None}
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    if os.environ.get("TECHNITIUM_TOKEN_IN_QUERY", "").lower() == "true":
        query["token"] = token
    url = f"{base}{path}"
    if query:
        url += "?" + urllib.parse.urlencode(query)

    ctx = None
    if os.environ.get("TECHNITIUM_VERIFY_TLS", "true").lower() == "false":
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=30, context=ctx) as resp:
            ctype = resp.headers.get("Content-Type", "")
            raw = resp.read()
            disp = resp.headers.get("Content-Disposition", "")
    except urllib.error.HTTPError as exc:
        body = _scrub(exc.read().decode("utf-8", "replace")[:500], token)
        return {"ok": False, "error": f"HTTP {exc.code} from Technitium: {body}"}
    except urllib.error.URLError as exc:
        return {"ok": False, "error": _scrub(f"Could not reach Technitium: {exc.reason}", token)}
    except TimeoutError:
        return {"ok": False, "error": "Technitium did not answer within 30 seconds."}

    if "json" in ctype.lower() or raw[:1] in (b"{", b"["):
        try:
            doc = json.loads(raw.decode("utf-8"))
        except ValueError:
            return {"ok": False, "error": "Technitium sent JSON that could not be read."}
        status = doc.get("status") if isinstance(doc, dict) else None
        if status == "ok" or status is None:
            return {"ok": True, "data": doc.get("response", doc) if isinstance(doc, dict) else doc}
        if status == "invalid-token":
            return {"ok": False, "error": "Technitium says the token is not valid. Make a new API token and update TECHNITIUM_TOKEN."}
        if status == "2fa-required":
            return {"ok": False, "error": "This account needs a 2FA code. Use an API token from an account without 2FA."}
        return {"ok": False, "error": _scrub(str(doc.get("errorMessage", doc))[:500], token)}

    # A file (backup, log download, export).
    name = "download"
    if "filename=" in disp:
        name = disp.split("filename=", 1)[1].strip().strip('"').split(";")[0]
        name = Path(name).name or "download"
    target = _download_dir() / f"{int(time.time())}-{name}"
    target.write_bytes(raw)
    return {"ok": True, "file": str(target), "bytes": len(raw), "content_type": ctype}


def _render(result: dict[str, Any], max_chars: int) -> str:
    if not result.get("ok"):
        return "ERROR: " + result.get("error", "unknown error")
    if "file" in result:
        return json.dumps({"saved_file": result["file"], "bytes": result["bytes"]}, indent=1)
    text = json.dumps(result.get("data"), indent=1, ensure_ascii=False)
    if len(text) > max_chars:
        return text[:max_chars] + f"\n... cut at {max_chars} characters. Ask for fewer fields or use max_chars."
    return text


def _gate(path: str, params: dict[str, Any], confirm: bool, phrase: str) -> str | None:
    """Return a message if the call must not run yet, else None."""
    tier = classify(path, params)
    if tier == "read":
        return None
    shown = {k: ("***" if "pass" in k.lower() else v) for k, v in params.items()}
    if not confirm:
        return (
            f"NOT RUN. This call makes a change ({tier}).\n"
            f"Endpoint: {path}\nParameters: {json.dumps(shown)}\n"
            "Tell the user exactly what will change and ask for a clear yes. "
            "Then call again with confirm=true"
            + (f" and confirm_phrase=\"{path}\"." if tier == "destructive" else ".")
        )
    if tier == "destructive" and phrase != path:
        return (
            f"NOT RUN. This call can delete data or lock someone out.\n"
            f"Endpoint: {path}\nParameters: {json.dumps(shown)}\n"
            f"Ask the user again. To run it, set confirm=true and confirm_phrase=\"{path}\"."
        )
    return None


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@mcp.tool()
def technitium_endpoints(query: str = "", group: str = "") -> str:
    """Find Technitium API endpoints and see their parameters and safety level.

    query: words to look for in the path or title (for example "blocking" or "zone").
    group: part of a group name (for example "Settings" or "DHCP").
    Safety level: read runs at once. change and destructive need the user's yes.
    """
    q = query.lower().split()
    g = group.lower()
    rows = []
    for e in CATALOG:
        hay = f"{e['path']} {e['title']} {e['group']}".lower()
        if g and g not in e["group"].lower():
            continue
        if q and not all(w in hay for w in q):
            continue
        rows.append({
            "path": e["path"],
            "title": e["title"],
            "safety": classify(e["path"], {}),
            "params": [p["name"] + ("" if p["optional"] else " (required)") for p in e["params"]],
        })
    if not rows:
        return "No match. Try fewer words, or leave query empty and set a group."
    return json.dumps(rows[:60], indent=1) + (f"\n... {len(rows) - 60} more" if len(rows) > 60 else "")


@mcp.tool()
def technitium_endpoint_help(path: str) -> str:
    """Show every parameter for one endpoint, for example /api/settings/set."""
    e = CATALOG_BY_PATH.get(path)
    if not e:
        return "Unknown endpoint. Use technitium_endpoints to search."
    return json.dumps({**e, "safety": classify(path, {})}, indent=1)


@mcp.tool()
def technitium_call(
    endpoint: str,
    params: dict[str, Any] | None = None,
    confirm: bool = False,
    confirm_phrase: str = "",
    max_chars: int = 20000,
) -> str:
    """Call any Technitium API endpoint, for example /api/dashboard/stats/get.

    Reads run at once. Anything that changes things is NOT run until you set
    confirm=true, and you must first tell the user what will change and get a
    clear yes. Risky calls (deleting, restoring, importing, changing ports or
    listeners, disabling users, password changes) also need confirm_phrase set
    to the exact endpoint path. Never guess parameters: use technitium_endpoint_help.
    The token is added automatically. Do not pass a token or a password unless
    the user asked for a password change.
    """
    params = dict(params or {})
    if not endpoint.startswith("/api/") or ".." in endpoint or "?" in endpoint:
        return "ERROR: endpoint must look like /api/zones/list (no query string)."
    if endpoint in BLOCKED_PATHS:
        return ("ERROR: login and createToken are not allowed here. They would put a "
                "password in the chat. Make the API token in the Technitium web page.")
    if "token" in params:
        return "ERROR: do not pass a token. The tool adds it from its own settings."
    blocked = _gate(endpoint, params, confirm, confirm_phrase)
    if blocked:
        return blocked
    return _render(_request(endpoint, params), max_chars)


@mcp.tool()
def technitium_stats(period: str = "LastDay") -> str:
    """Dashboard numbers: queries, blocked, cached, top charts.

    period: LastHour, LastDay, LastWeek, LastMonth, LastYear.
    """
    return _render(_request("/api/dashboard/stats/get", {"type": period}), 12000)


@mcp.tool()
def technitium_settings_get() -> str:
    """Read all server settings."""
    return _render(_request("/api/settings/get", {}), 30000)


@mcp.tool()
def technitium_settings_set(
    settings: dict[str, Any], confirm: bool = False, confirm_phrase: str = ""
) -> str:
    """Change server settings. Send only the settings that should change.

    Example: {"enableBlocking": true}. Check names with technitium_endpoint_help
    on /api/settings/set. Read the settings first and tell the user what will
    change. Needs confirm=true after the user says yes. Port, listener, DNS
    over HTTPS/TLS, recursion and forwarder changes need confirm_phrase
    "/api/settings/set".
    """
    blocked = _gate("/api/settings/set", settings, confirm, confirm_phrase)
    if blocked:
        return blocked
    return _render(_request("/api/settings/set", settings), 30000)


@mcp.tool()
def technitium_blocking(
    minutes: int | None = None, enable: bool | None = None,
    confirm: bool = False,
) -> str:
    """Turn ad blocking off for some minutes, or turn it on or off for good.

    minutes: pause blocking for this many minutes.
    enable: true or false to switch blocking for good.
    Ask the user first, then set confirm=true.
    """
    if (minutes is None) == (enable is None):
        return "ERROR: set exactly one of minutes or enable."
    if minutes is not None:
        path, params = "/api/settings/temporaryDisableBlocking", {"minutes": minutes}
    else:
        path, params = "/api/settings/set", {"enableBlocking": enable}
    blocked = _gate(path, params, confirm, "")
    if blocked:
        return blocked
    return _render(_request(path, params), 5000)


@mcp.tool()
def technitium_flush_cache(confirm: bool = False) -> str:
    """Clear the whole DNS cache. Ask the user first, then set confirm=true."""
    blocked = _gate("/api/cache/flush", {}, confirm, "")
    if blocked:
        return blocked
    return _render(_request("/api/cache/flush", {}), 2000)


@mcp.tool()
def technitium_zones(zone: str = "") -> str:
    """List DNS zones. Give a zone name to list its records instead."""
    if zone:
        return _render(_request("/api/zones/records/get", {"domain": zone, "zone": zone, "listZone": "true"}), 30000)
    return _render(_request("/api/zones/list", {}), 30000)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
