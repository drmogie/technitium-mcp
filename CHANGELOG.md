# Changelog

## 2026.09.28.02

- Fix: the tool closed right after starting. The install rule allowed the
  new mcp version 2, which renamed FastMCP. Now pinned to mcp below version 2.

## 2026.09.28.01

- First release.
- Tools: technitium_endpoints, technitium_endpoint_help, technitium_call,
  technitium_stats, technitium_settings_get, technitium_settings_set,
  technitium_blocking, technitium_flush_cache, technitium_zones.
- Catalog of 137 API endpoints built from the official Technitium API docs.
- Safety levels: read runs at once. Changes need confirm. Risky changes
  also need the endpoint path typed back.
- Token comes from the environment only. It is scrubbed from errors.
- File downloads (backups, logs) are saved to a folder, not sent to chat.
- Tested against a fake Technitium server. Not yet tested on a real one.
