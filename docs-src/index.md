---
title: Procurement MCP
summary: An MCP server that searches Australian and Chinese marketplaces in one call and ranks offers by landed cost, delivery time and seller trust.
icon: cart
audience: users
status: draft
---

Procurement MCP is a Model Context Protocol server with 7 tools. `search_offers` searches up to 16 marketplaces at once and returns one ranked list. Each [[term:Offer]] carries a delivery status and a [[term:Landed cost]] in AUD for the [[term:Destination]], which is Brisbane 4000 by default.

Every source is a hosted API that the server calls with a key. With no keys set, the `ozbargain` and `cheapies` deal feeds work. Every other [[term:Marketplace]] returns a [[term:Diagnostic]] that names the variable to set.

```sh title="Run it"
git clone https://github.com/belikh/procurement
cd procurement
uv sync
uv run python server.py
```

[[start/install]]

[[guides/search]]

[[reference/tools]]

[[concepts/landed-cost]]

::graphic rule/end

:::see-also
- [[guides/connect-a-client]]
- [[reference/marketplaces]]
- [[reference/settings]]
:::
