"""The MCPServer instance and its lifespan (database pool open and close)."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from mcp.server.mcpserver import MCPServer

from procurement.db import close_db, init_db


@asynccontextmanager
async def lifespan(_server: MCPServer) -> AsyncGenerator[None]:
    await init_db()
    try:
        yield
    finally:
        await close_db()


mcp = MCPServer(
    "procurement-search",
    instructions=(
        "Price search across Australian sources (eBay AU, Amazon AU, Woolworths, Coles, Aldi, "
        "Gumtree, Facebook Marketplace, OzBargain, Cheapies) and Chinese sources (1688, Taobao, "
        "Tmall, JD). Every source is a hosted API. "
        "Tools: search_offers ranks offers for a product; get_offer_detail refreshes one offer; "
        "search_by_image finds suppliers from a photo; latest_deals lists current deals; "
        "get_price_history gives Amazon price history; search_history reads past searches; "
        "health lists which sources are configured. "
        "A source that returns nothing adds one entry with kind='diagnostic' that says why."
    ),
    lifespan=lifespan,
)
