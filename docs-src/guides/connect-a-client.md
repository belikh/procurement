---
title: Connect an MCP client
summary: Register the server with an MCP client over stdio or streamable HTTP.
order: 10
icon: link
audience: users
status: draft
---

An MCP client starts the server as a child process over stdio, or connects to a running server over HTTP. Replace `/path/to/procurement` with the path of your checkout.

## Stdio

Most clients read a JSON entry with a command and its arguments. `uv run --directory` starts the server from the checkout, so the server finds its `.env` file.

```json title="MCP server entry"
{
  "mcpServers": {
    "procurement": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/procurement", "python", "server.py"]
    }
  }
}
```

In Claude Code, one command adds the same entry:

```sh title="Claude Code, stdio"
claude mcp add procurement -- uv run --directory /path/to/procurement python server.py
```

## Streamable HTTP

1. Start the server with a port. It listens on `127.0.0.1` only.

   ```sh title="Serve HTTP"
   MCP_HTTP_PORT=8765 uv run python server.py
   ```

2. Point the client at `http://127.0.0.1:8765/mcp`.

   ```sh title="Claude Code, HTTP"
   claude mcp add --transport http procurement http://127.0.0.1:8765/mcp
   ```

To reach the server from another machine, put a reverse proxy or a tunnel in front of the port. The server has no authentication of its own.

## Tool call time limit

A search runs for up to `PROCUREMENT_DEADLINE_S` seconds, 55 by default. Many clients cut a tool call at 60 seconds. If your client allows longer calls, raise the deadline so that the Apify lanes, which take 30 to 90 seconds, can finish.

```sh title=".env"
PROCUREMENT_DEADLINE_S=110
```

## eBay notification endpoint

Over HTTP the server also answers eBay's account-deletion notifications at `/ebay/notifications`. eBay keeps a new production keyset disabled until this endpoint answers its challenge.

| Setting | Meaning |
| --- | --- |
| `EBAY_DELETION_TOKEN` | The verification token you entered in the eBay developer portal. |
| `EBAY_DELETION_ENDPOINT` | The public URL registered in the portal. The challenge hash covers this string, so it must match exactly. |

A `GET` with `challenge_code` returns `{"challengeResponse": "<sha256 hex>"}`. A `POST` is logged and answered with 204. The server stores no eBay user data.

:::see-also
- [[guides/search]]
- [[reference/settings]]
:::
