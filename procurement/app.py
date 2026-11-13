"""Assemble the server: importing tools and routes registers them on the instance."""

from __future__ import annotations

from procurement import routes, tools
from procurement.config import settings
from procurement.instance import mcp

REGISTERED = (routes, tools)


def main() -> None:
    """Serve over stdio, or over streamable HTTP on loopback when MCP_HTTP_PORT is set."""
    if settings.mcp_http_port:
        mcp.run(transport="streamable-http", host="127.0.0.1", port=settings.mcp_http_port)
    else:
        mcp.run()


__all__ = ["main", "mcp"]
