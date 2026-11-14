---
title: Install
summary: Install the server with uv, start it and run a first search without any keys.
order: 10
icon: terminal
audience: users
status: draft
---

## Requirements

| Requirement | Version |
| --- | --- |
| Python | 3.12, pinned in `.python-version` |
| [uv](https://docs.astral.sh/uv/) | any current release |
| `mcp` | 2.3 or later, installed by `uv sync` |

## Install

1. Clone the repository and install the dependencies.

   ```sh title="Install"
   git clone https://github.com/belikh/procurement
   cd procurement
   uv sync
   ```

2. Copy the settings template. Every key in it is optional, and an empty value counts as unset.

   ```sh title="Create .env"
   cp .env.example .env
   ```

## Run

The server speaks MCP over stdio by default. Set `MCP_HTTP_PORT` to serve streamable HTTP on `127.0.0.1`.

| Command | Result |
| --- | --- |
| `uv run python server.py` | MCP over stdio |
| `MCP_HTTP_PORT=8765 uv run python server.py` | Streamable HTTP at `http://127.0.0.1:8765/mcp` |
| `uv run mcp dev server.py` | The MCP Inspector, to call tools from a browser |
| `uv run procurement-mcp` | The same as `server.py`, through the installed script |

## First search

With no keys set, the `ozbargain` and `cheapies` deal feeds work. In the MCP Inspector, call `search_offers` with these arguments:

```json title="Arguments"
{ "query": "ssd", "marketplaces": ["ozbargain", "ebay_au"], "sort": "cheapest", "max_results": 2 }
```

The result lists the OzBargain deals whose title, brand or tags contain "ssd", then one [[term:Diagnostic]] for `ebay_au`:

```json title="Result (shortened)"
[
  {
    "offer_id": "ozbargain:983075",
    "marketplace": "ozbargain",
    "title": "Lenovo Legion 5i ... 1TB SSD $2186 (RRP $2999) Delivered @ Amazon AU",
    "price_aud": 2186.0,
    "shipping": { "delivery": "direct", "delivery_basis": "the deal title says Delivered" },
    "kind": "offer",
    "landed_aud": 2186.0,
    "landed_basis": "item_only"
  },
  {
    "offer_id": "ebay_au:missing_key",
    "marketplace": "ebay_au",
    "title": "[ebay_au] not configured: set EBAY_APP_ID and EBAY_CERT_ID",
    "kind": "diagnostic",
    "diagnostic_code": "missing_key"
  }
]
```

The deal feeds hold about the latest 100 deals, so the titles you get differ. A query that matches no current deal returns a `no_results` diagnostic.

## Check the setup

Call `health` to see which marketplaces can run. It lists each [[term:Marketplace]] with `ready`, the `missing` key, its `source` and its `status`. With no keys, `ready_count` is 2.

:::see-also
- [[guides/add-keys]]
- [[guides/connect-a-client]]
- [[guides/search]]
:::
