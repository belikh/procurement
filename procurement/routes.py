"""eBay marketplace account deletion notification routes."""

from __future__ import annotations

import hashlib
import json
import logging

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from procurement.config import settings
from procurement.instance import mcp

log = logging.getLogger("procurement.ebay")

# ---------------------------------------------------------------------------
# eBay marketplace account deletion/closure notifications — compliance routes
# ---------------------------------------------------------------------------
# Contract (developer.ebay.com/develop/guides/sell/marketplace-user-account-deletion):
#   GET  <endpoint>?challenge_code=<code> → 200 OK, application/json,
#        {"challengeResponse": "<sha256_hex(challengeCode + token + endpoint)>"}
#        Hash order is EXACT: challengeCode + verificationToken + endpoint.
#   POST <endpoint> — deletion notification payload → any 2xx ACK
#        (200/201/202/204). We log it and 204.
# Plain Starlette routes mounted on the FastMCP streamable-HTTP app — served
# whenever MCP_HTTP_PORT is set (the callisto systemd unit / tunnel path).


@mcp.custom_route("/ebay/notifications", methods=["GET"])
async def ebay_deletion_challenge(request: Request) -> JSONResponse:
    """eBay subscription verification: hash challenge + token + endpoint."""
    challenge = request.query_params.get("challenge_code")
    if not settings.ebay_deletion_token:
        return JSONResponse({"error": "EBAY_DELETION_TOKEN not configured"}, status_code=500)
    if not challenge:
        return JSONResponse({"error": "challenge_code query param required"}, status_code=400)
    # EXACT hash order per eBay's contract: challengeCode + verificationToken + endpoint
    digest = hashlib.sha256(
        (challenge + settings.ebay_deletion_token + settings.ebay_deletion_endpoint).encode("utf-8")
    ).hexdigest()
    return JSONResponse({"challengeResponse": digest})


@mcp.custom_route("/ebay/notifications", methods=["POST"])
async def ebay_deletion_notify(request: Request) -> Response:
    """eBay deletion/closure notification: acknowledge with 2xx."""
    try:
        body = await request.json()
    except Exception:
        body = None
    # Log-only audit trail — this app holds no marketplace user data to
    # delete (search-only, no user tokens persisted), so ACK is the whole
    # obligation. Keep the payload in the journal for the audit trail.
    log.info(
        "ebay deletion notification received: %s", json.dumps(body)[:500] if body else "(empty)"
    )
    return Response(status_code=204)
