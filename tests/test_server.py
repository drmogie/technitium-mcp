"""End-to-end test: start a mock Technitium, run the MCP tool over stdio, call every tool."""
import asyncio, json, os, subprocess, sys, tempfile, time
from pathlib import Path
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[1]
PORT = 5391
TOKEN = "test-token-123"
dl = tempfile.mkdtemp()

async def call(session, name, args=None):
    r = await session.call_tool(name, args or {})
    return "\n".join(c.text for c in r.content if hasattr(c, "text"))

def check(label, cond, detail=""):
    print(("PASS " if cond else "FAIL ") + label + ("" if cond else f"  -> {detail[:300]}"))
    return cond

async def main():
    mock = subprocess.Popen([sys.executable, str(ROOT / "tests" / "mock_technitium.py"), str(PORT)])
    time.sleep(0.8)
    ok = True
    try:
        env = {**os.environ, "TECHNITIUM_URL": f"http://127.0.0.1:{PORT}", "TECHNITIUM_TOKEN": TOKEN,
               "TECHNITIUM_DOWNLOAD_DIR": dl, "PYTHONPATH": str(ROOT)}
        params = StdioServerParameters(command=sys.executable, args=["-m", "technitium_mcp"], env=env)
        async with stdio_client(params) as (r, w):
            async with ClientSession(r, w) as s:
                await s.initialize()
                tools = {t.name for t in (await s.list_tools()).tools}
                ok &= check("tools listed", {"technitium_call", "technitium_endpoints", "technitium_stats",
                            "technitium_settings_set", "technitium_blocking", "technitium_flush_cache"} <= tools, str(tools))

                out = await call(s, "technitium_stats")
                ok &= check("stats read", "42" in out and "ERROR" not in out, out)
                out = await call(s, "technitium_settings_get")
                ok &= check("settings read", "enableBlocking" in out, out)
                out = await call(s, "technitium_zones")
                ok &= check("zones list", "home.arpa" in out, out)

                out = await call(s, "technitium_endpoints", {"query": "blocking"})
                ok &= check("endpoint search", "temporaryDisableBlocking" in out, out)
                out = await call(s, "technitium_endpoint_help", {"path": "/api/settings/set"})
                ok &= check("endpoint help", "enableBlocking" in out and '"safety": "change"' in out, out)

                # change gate
                out = await call(s, "technitium_settings_set", {"settings": {"enableBlocking": False}})
                ok &= check("change blocked until confirm", out.startswith("NOT RUN") and "applied" not in out, out)
                out = await call(s, "technitium_settings_set", {"settings": {"enableBlocking": False}, "confirm": True})
                ok &= check("change runs with confirm", "applied" in out and '"enableBlocking": "false"' in out, out)

                # risky setting needs phrase
                out = await call(s, "technitium_settings_set", {"settings": {"webServiceHttpPort": 8080}, "confirm": True})
                ok &= check("risky setting needs phrase", out.startswith("NOT RUN") and "confirm_phrase" in out, out)
                out = await call(s, "technitium_settings_set", {"settings": {"webServiceHttpPort": 8080}, "confirm": True, "confirm_phrase": "/api/settings/set"})
                ok &= check("risky setting runs with phrase", "applied" in out, out)

                out = await call(s, "technitium_blocking", {"minutes": 10})
                ok &= check("blocking pause gated", out.startswith("NOT RUN"), out)
                out = await call(s, "technitium_blocking", {"minutes": 10, "confirm": True})
                ok &= check("blocking pause runs", "temporaryDisableBlockingTill" in out, out)
                out = await call(s, "technitium_blocking", {})
                ok &= check("blocking needs one option", out.startswith("ERROR"), out)
                out = await call(s, "technitium_flush_cache")
                ok &= check("flush gated", out.startswith("NOT RUN"), out)
                out = await call(s, "technitium_flush_cache", {"confirm": True})
                ok &= check("flush runs", "ERROR" not in out and "NOT RUN" not in out, out)

                # destructive via generic call
                out = await call(s, "technitium_call", {"endpoint": "/api/zones/delete", "params": {"zone": "home.arpa"}, "confirm": True})
                ok &= check("delete needs phrase", out.startswith("NOT RUN"), out)
                out = await call(s, "technitium_call", {"endpoint": "/api/zones/delete", "params": {"zone": "home.arpa"}, "confirm": True, "confirm_phrase": "/api/zones/delete"})
                ok &= check("delete runs with phrase", "NOT RUN" not in out and "ERROR" not in out, out)
                out = await call(s, "technitium_call", {"endpoint": "/api/admin/users/set", "params": {"user": "x", "disabled": True}, "confirm": True})
                ok &= check("disabling a user is risky", out.startswith("NOT RUN") and "lock" in out, out)

                # guards
                out = await call(s, "technitium_call", {"endpoint": "/api/user/login", "params": {"user": "a", "pass": "b"}})
                ok &= check("login blocked", out.startswith("ERROR") and "password" in out, out)
                out = await call(s, "technitium_call", {"endpoint": "/api/stats/get", "params": {"token": "x"}})
                ok &= check("token param refused", out.startswith("ERROR"), out)
                out = await call(s, "technitium_call", {"endpoint": "/other/path"})
                ok &= check("non-api path refused", out.startswith("ERROR"), out)
                out = await call(s, "technitium_call", {"endpoint": "/api/../etc/passwd"})
                ok &= check("path trick refused", out.startswith("ERROR"), out)

                # errors and secrets
                out = await call(s, "technitium_call", {"endpoint": "/api/zones/create", "params": {"zone": "x"}, "confirm": True})
                ok &= check("api error shown", "Zone already exists" in out, out)
                ok &= check("token scrubbed from errors", TOKEN not in out, out)

                # files and size limits
                out = await call(s, "technitium_call", {"endpoint": "/api/settings/backup"})
                saved = json.loads(out).get("saved_file", "") if out.startswith("{") else ""
                ok &= check("file download saved", saved.endswith("backup.zip") and Path(saved).read_bytes().startswith(b"PK"), out)
                out = await call(s, "technitium_call", {"endpoint": "/api/test/getBig", "max_chars": 1000})
                ok &= check("long output cut", "cut at 1000" in out and len(out) < 1300, out[-200:])

        # bad token
        env2 = {**env, "TECHNITIUM_TOKEN": "wrong"}
        async with stdio_client(StdioServerParameters(command=sys.executable, args=["-m", "technitium_mcp"], env=env2)) as (r, w):
            async with ClientSession(r, w) as s:
                await s.initialize()
                out = await call(s, "technitium_stats")
                ok &= check("bad token message", "not valid" in out, out)
        # missing settings
        env3 = {k: v for k, v in env.items() if not k.startswith("TECHNITIUM_URL") and k != "TECHNITIUM_TOKEN"}
        async with stdio_client(StdioServerParameters(command=sys.executable, args=["-m", "technitium_mcp"], env=env3)) as (r, w):
            async with ClientSession(r, w) as s:
                await s.initialize()
                out = await call(s, "technitium_stats")
                ok &= check("missing settings message", "TECHNITIUM_URL" in out or "Set TECHNITIUM" in out, out)
        # unreachable
        env4 = {**env, "TECHNITIUM_URL": "http://127.0.0.1:9"}
        async with stdio_client(StdioServerParameters(command=sys.executable, args=["-m", "technitium_mcp"], env=env4)) as (r, w):
            async with ClientSession(r, w) as s:
                await s.initialize()
                out = await call(s, "technitium_stats")
                ok &= check("unreachable message", "Could not reach" in out, out)
    finally:
        mock.terminate()
    print("\nALL PASSED" if ok else "\nSOME FAILED")
    sys.exit(0 if ok else 1)

asyncio.run(main())
