---
title: Add marketplace keys
summary: Set the API keys that turn each marketplace on, and confirm them with the health tool.
order: 20
icon: key
audience: users
status: draft
---

Each [[term:Marketplace]] runs when its key is set in `.env` or in the environment. The server reads `.env` from the repository root at start, so restart it after a change.

## Steps

1. Open `.env` and set the keys you hold.

   | Key | Turns on | Where to get it |
   | --- | --- | --- |
   | `APIFY_TOKEN` | `taobao`, `tmall`, `jd`, `1688`, `amazon_au`, `ebay_sold`, `woolworths`, `coles`, `aldi`, `gumtree`, and `search_by_image` | [Apify console, Integrations](https://console.apify.com/settings/integrations) |
   | `EBAY_APP_ID` and `EBAY_CERT_ID` | `ebay_au`, and live `ebay_au` detail | [eBay developer program](https://developer.ebay.com) |
   | `TMAPI_TOKEN` | `1688` through TMAPI, and detail for `taobao`, `tmall`, `1688`, `jd`, `pdd` | [TMAPI console](https://console.tmapi.io/account/center) |
   | `SOCIAVAULT_API_KEY` | `facebook` | [SociaVault](https://sociavault.com) |
   | `KEEPA_API_KEY` and `KEEPA_DOMAIN` | `get_price_history` | [Keepa](https://keepa.com) |
   | `GUMTREE_COOKIES` | `gumtree`, with `APIFY_TOKEN` | Cookies exported from a browser session on gumtree.com.au |

2. Restart the server.

3. Call `health`. A marketplace with its key set reports `"missing": null`.

   ```json title="health, one marketplace"
   {
     "ebay_au": {
       "ready": true,
       "missing": null,
       "source": "eBay Browse API",
       "status": "unverified"
     }
   }
   ```

4. Run one live search for the marketplaces you turned on. Each Apify lane starts one actor run, which spends Apify credits.

   ```sh title="Live check"
   uv run python scripts/live_smoke.py ebay_au jd
   ```

## Key notes

- `EBAY_CLIENT_ID`, `EBAY_CLIENT_SECRET` and `TMAPI_API_TOKEN` are accepted as other names for the eBay and TMAPI keys.
- `EBAY_OAUTH_TOKEN` holds a bearer token you fetched yourself. With it set, the server skips the client-credentials call.
- `1688` uses TMAPI when `TMAPI_TOKEN` is set, and the Apify actor otherwise.
- `KEEPA_DOMAIN` has no default. Keepa's official clients list domain ids 1 to 12 and none is Australia. Set the id that your Keepa account documents for amazon.com.au.
- `gumtree` stays `degraded` in `health` and is never counted in `ready_count`. Without `GUMTREE_COOKIES` it returns a `degraded` diagnostic, because Gumtree blocks the actor.
- `health` shows key names only. It prints no key values.

## Errors

| Diagnostic | Cause | Fix |
| --- | --- | --- |
| `[ebay_au] not configured: set EBAY_APP_ID and EBAY_CERT_ID` | The key is unset or empty. | Set the named variable and restart. |
| `TMAPI error 4013: API not subscribed; subscribe at console.tmapi.io, APIs List` | TMAPI answered 401. | Subscribe to the API in the TMAPI console. |
| `actor <name>: ...` with code `quota` | The Apify actor reported its free runs or credit as used up. | Add credit in Apify, or set another actor in the `*_APIFY_ACTOR` setting. |

:::see-also
- [[reference/marketplaces]]
- [[reference/settings]]
- [[develop/verify-a-lane]]
:::
