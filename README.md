<p align="right">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/belikh/design/main/packages/graphics/logo/jupiter-logo-dark.svg">
    <img alt="jupiter.au" src="https://raw.githubusercontent.com/belikh/design/main/packages/graphics/logo/jupiter-logo-light.svg" width="260">
  </picture>
</p>

# Procurement MCP

An MCP server that searches Chinese and Australian marketplaces in one call. Ask for the cheapest, fastest or best-value item and it returns normalised offers ranked by landed cost, delivery time and seller trust.

Every source is a hosted API that you call with a key. The server contains no scrapers. Chinese sources go through aggregators (TMAPI), Australian sources go through official APIs where they exist (eBay AU), and Gumtree and Facebook Marketplace go through hosted scraper APIs.

<p>
  <a href="#install">Install</a> ·
  <a href="#tools">Tools</a> ·
  <a href="#configuration">Configuration</a> ·
  <a href="#ranking">Ranking</a> ·
  <a href="#database">Database</a> ·
  <a href="#develop">Develop</a>
</p>

<br>

---

<br>

## Install

```sh
uv sync
cp .env.example .env              # add keys
uv run mcp dev server.py          # MCP Inspector at http://localhost:5173
uv run python server.py           # stdio, for Claude Desktop
uv run mcp install server.py      # install into Claude Desktop
```

With no keys set, `search_offers` returns synthetic offers and `health` reports `mock_fallback: true`, so the server can be tried without signing up for anything.

<br>

## Tools

| Tool | Purpose |
|---|---|
| `search_offers(query, marketplaces?, sort=best_value, qty=1, ship_to=AU, max_results=10)` | Parallel search across marketplaces. Returns offers ranked by the chosen sort. |
| `search_by_image(image_url, destination, max_results)` | Reverse image search. Takes a photo and returns matching supplier listings from 1688, Alibaba, AliExpress and global retail sites, with price, MOQ and supplier. Costs $0.10 per search. |
| `get_offer_detail(offer_id)` | Detail for `marketplace:item_id` (TMAPI) or `ebay_au:itemId` (eBay Browse `getItem`). |
| `health()` | Which integrations are configured. Shows no secrets. |
| Prompt `procurement_brief` | System prompt for procurement reasoning. |

`marketplaces` takes any subset of: `taobao`, `tmall`, `1688`, `jd`, `pdd`, `aliexpress`, `ebay_au`, `ebay_sold`, `amazon_au`, `gumtree`, `facebook`, `woolworths`, `coles`, `aldi`, `ozbargain`, `cheapies`, `ozbargain_search`.

Searches run concurrently with a per-marketplace timeout (`PROCUREMENT_TIMEOUT_S`, default 8 seconds). If one marketplace fails, the others still return.

<details>
<summary><b>Deal-signal sources</b></summary>

- **`ozbargain` and `cheapies`** read the sites' official RSS feeds (`/deals/feed`) with the standard library `xml.etree`. They need no key. Each offer carries community data (votes, comments, clicks, expiry, brand, tags) taken from the `ozb:meta` extension and the `<category>` taxonomy, the price parsed from the title, and the affiliate `goto` link. The `best_value` trust term uses net community votes, so a deal with +5 votes outranks a seller with a 4.8 rating.
- **`ozbargain_search`** does keyword search over OzBargain through the Apify actor `parseforge/ozbargain-australia-scraper`. It reuses `APIFY_TOKEN` and costs Apify credits.
- **`ebay_sold`** returns eBay AU sold prices, meaning what items sold for rather than asking prices, through `caffein.dev/ebay-sold-listings` with `ebaySite: ebay.com.au`. Sold prices go into `price_history`.
- **Keepa price history.** When `KEEPA_API_KEY` is set, `amazon_au` offers get a `price_history` block with the 90-day average and minimum from Keepa's official API (domain 12, amazon.com.au).

</details>

<details>
<summary><b>Grocery sources</b></summary>

`woolworths`, `coles` and `aldi` use the dromb Apify actors ($0.30 per 1,000 results) with `operation: search`, which returns unit prices, specials and barcodes. Grocery offers carry `unit_price_aud`, `unit` and `regular_price_aud`. `price_aud` holds the effective price, which is the special price when there is one.

The `cheapest` sort uses unit price when it exists. A $4.50 2L bottle of milk beats a $3.10 1L bottle, and item price cannot show that.

Grocery and Amazon results pass a relevance filter: every query term must appear in the title, brand or category. Without it, ALDI's catalogue search matches "milk" to oil and lollipops.

Costco is left out. Every Costco actor targets costco.com (US, USD). It can be added if an Australian actor appears.

</details>

<br>

## Configuration

Copy `.env.example` to `.env` and fill in the keys you have. The sign-up identity for the keys below is `io+agent@jupiter.au`.

| Source | Where to get it | Variables |
|---|---|---|
| TMAPI (Taobao, Tmall, 1688, PDD, JD; recommended first key) | [console.tmapi.io](https://console.tmapi.io/user/signup), then Account Center, `apiToken`. Free tier of 200 requests per month; paid from about $8 per month. | `TMAPI_TOKEN` |
| AliExpress Affiliate (official) | [openservice.aliexpress.com](https://openservice.aliexpress.com). Create a UAC account, join the Affiliate Program and create an app. Approval takes 1 to 2 days. | `ALIEXPRESS_APP_KEY`, `ALIEXPRESS_APP_SECRET` |
| eBay AU | [developer.ebay.com](https://developer.ebay.com). Create an app and take the App ID and Cert ID. The server uses the client-credentials flow and calls `buy/browse/v1/item_summary/search` with `X-EBAY-C-MARKETPLACE-ID: EBAY_AU`. | `EBAY_APP_ID`, `EBAY_CERT_ID` |
| Amazon AU | Seller Central Professional with the [SP-API](https://developer.amazonservices.com) Far East endpoint, or the Product Advertising API 5.0. | `AMAZON_PAAPI_ACCESS_KEY`, `AMAZON_PAAPI_SECRET_KEY`, `AMAZON_PAAPI_PARTNER_TAG` (example: `jupiter-22`) |
| Facebook Marketplace | [sociavault.com](https://sociavault.com). Supports AU latitude and longitude. Pay per request. | `SOCIAVAULT_API_KEY` |
| Gumtree AU and other Apify actors | [console.apify.com](https://console.apify.com/settings/integrations), actor `crawlerbros/gumtree-scraper`. Apify handles the residential proxy and Akamai bypass. | `APIFY_TOKEN` |
| JD fallback (optional) | [elim.asia](https://elim.asia) and RapidAPI | `ELIM_API_TOKEN`, `RAPIDAPI_KEY` |

<br>

## Ranking

- **Price.** `price_cny` is converted to `price_aud` with `CNY_TO_AUD` (default 0.215). Landed cost is `price_aud * qty + shipping.intl_estimate_aud`.
- **MOQ.** For 1688, offers with `qty < moq` go to the end of the list and are flagged.
- **Delivery.** `shipping.eta_days` is a `[min, max]` range.
- **Trust.** Taken from `seller.rating` and `source_reliability` (`authoritative`, then `aggregator`, then `best_effort`).
- **Sorts.** `cheapest` sorts by landed cost (unit price for grocery). `fastest` sorts by delivery time. `best_value` is `0.5 price + 0.25 speed + 0.25 trust`.

<br>

## Database

When `DATABASE_URL` is set, the server caches federated results and logs searches in the fleet Postgres (`10.1.1.3:5432`, database `jupiter`, schema `procurement`). Without it, the server keeps no state.

```sh
# in .env
DATABASE_URL=postgresql://procurement:__SET_ME__@10.1.1.3:5432/jupiter
PROCUREMENT_PG_SCHEMA=procurement

# apply once
psql "$DATABASE_URL" -f migrations/001_procurement_cache.sql
```

The tables are `procurement.search_cache` (keyed by query, marketplaces, sort, qty and ship_to) and `procurement.search_log`. The cache lifetime is `PROCUREMENT_CACHE_TTL_S` (default 3600 seconds). `health()` reports `database.enabled` and `database.error` without exposing secrets.

<br>

## Develop

```sh
uv sync --extra dev
uv run ruff check server.py
uv run python -m py_compile server.py
uv run python -c "from server import health; print(health())"
```

```text
server.py          FastMCP server and all integrations
migrations/        Postgres schema for the cache and search log
.env.example       environment variable template
pyproject.toml
```

<br>

## Licence

`pyproject.toml` declares MIT.

<br>

<p align="right"><sub>jupiter.au</sub></p>
