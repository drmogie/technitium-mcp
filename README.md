# Technitium MCP

![Version](https://img.shields.io/badge/version-2026.09.28.02-blue)
![License](https://img.shields.io/badge/license-MIT-green)

A small tool that lets Claude read and change a
[Technitium DNS Server](https://technitium.com/dns/) through its API.

It runs on your own computer. Your token stays on your computer.

## What Claude can do with it

- Look at stats, settings, zones, logs, and users.
- Turn ad blocking on, off, or pause it.
- Flush the cache and refresh block lists.
- Change settings and zones.
- Anything else in the Technitium API. 137 endpoints are in the catalog.

## Safety

Every call has a safety level.

- **read**: runs right away.
- **change**: does not run until Claude asks you and sets `confirm`.
- **destructive**: deleting, restoring, importing, password changes,
  disabling users, and changing ports or listeners.
  It also needs the exact endpoint path typed back.

Other protections:

- Login and create-token calls are blocked. They would put a password in the chat.
- The token is never printed. It is removed from error messages.
- File downloads (backups, logs) are saved to a folder. They are not sent to chat.
  Default folder: `technitium-downloads` in your home folder.

## Set up

### 1. Make an API token

1. Open the Technitium web page.
2. Go to the Administration part, then Sessions, then create an API token.
   Menu names can differ a little by version.
3. Best: make a separate user just for this, and make the token from that user.
   Then you can delete it on its own later.
4. Give the token a name, like `Claude`.

**Do not paste the token in a chat.** Put it only in the config file below.
If it ever lands in a chat, delete that token and make a new one.

### 2. Add the tool to Claude

Open the Claude desktop app settings and find the MCP servers config file.
Add the block from `claude_desktop_config.example.json`.
Change the address and token.

- `TECHNITIUM_URL`: your server, like `http://172.16.90.10:5380`
- `TECHNITIUM_TOKEN`: your token

That file now holds a secret. Do not share it. Do not put it on GitHub.

The example uses `uvx`. If you do not have it, use Python instead:

```
pip install D:\GitHub-Projects\technitium-mcp
```

Then use `"command": "technitium-mcp"` and no args.

Restart the Claude desktop app.

### 3. Try it

Ask Claude: "Show my Technitium stats for the last day."

## Other settings

- `TECHNITIUM_VERIFY_TLS=false`: for an https address with a self-signed certificate.
- `TECHNITIUM_TOKEN_IN_QUERY=true`: for an old Technitium version that ignores the
  Bearer header. This puts the token in the URL, so avoid it if you can.
- `TECHNITIUM_DOWNLOAD_DIR`: where downloads are saved.

## Test it

```
pip install mcp
python tests/test_server.py
```

The test starts a fake Technitium and checks every tool and every safety rule.

## Limits

- File uploads are not supported yet: zone import, settings restore, and
  app install from a file. Installing an app from a URL works.
- Cluster options are in the catalog but not tested.
- Tested against a fake server only. Not yet tested on a real one.

## Credits

Endpoint list built from the official
[Technitium API docs](https://github.com/TechnitiumSoftware/DnsServer/blob/master/APIDOCS.md).
Technitium is made by Technitium. This project is not made by Technitium.

## License

MIT. See [LICENSE](LICENSE).
