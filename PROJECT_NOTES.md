# Technitium MCP - project notes

## 2026-09-28: first build (2026.09.28.01)

- Ask: "build something that works with an API token to help with settings
  and other configurations." Mogie chose: local MCP tool, full control.
- Full control is enforced in the tool: read / change / destructive tiers.
  Kept "asks before risky steps" from the answer text.
- Catalog: `technitium_mcp/endpoints.json`, made from the official
  APIDOCS.md (raw.githubusercontent.com works from the cloud shell).
  137 endpoints, 730 params. First parse missed params written as
  "(optional, cluster parameter)"; fixed. Re-run the parse if Technitium
  ships new API docs.
- Blocked on purpose: /api/user/login and /api/user/createToken.
- Auth: Bearer header. Fallback env TECHNITIUM_TOKEN_IN_QUERY.
- Token only from env. The config file with the token lives on Mogie's PC
  (Claude desktop MCP config). Never in this repo.
- Tested with a fake server over stdio (tests/test_server.py, 30 checks).
  NOT tested against real Technitium or on Windows.
- Unknown verbs default to "change" (safe default).
- Not built: file uploads (import, restore, install from file).
- GitHub repo: NOT created yet. Waiting on Mogie for the repo name
  (suggested: technitium-mcp).
