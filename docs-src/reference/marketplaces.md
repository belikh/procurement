---
title: Marketplaces
summary: The 16 marketplace names, the hosted API behind each, the key it needs and its verification status.
order: 30
icon: globe
audience: users
status: draft
---

Pass these names in `marketplaces` of `search_offers`. With no list, the server searches all 16.

| Marketplace | Source | Key | Status | Budget |
| --- | --- | --- | --- | --- |
| `ebay_au` | eBay Browse API, `EBAY_AU` marketplace | `EBAY_APP_ID`, `EBAY_CERT_ID` | unverified | 15 s |
| `ebay_sold` | Apify `caffein.dev/ebay-sold-listings`. Returns comps. | `APIFY_TOKEN` | unverified | 65 s |
| `amazon_au` | Apify `junglee/free-amazon-product-scraper` | `APIFY_TOKEN` | unverified | 75 s |
| `woolworths` | Apify `dromb/woolworths-au-product-search-catalog-unofficial` | `APIFY_TOKEN` | unverified | 45 s |
| `coles` | Apify `dromb/coles-au-product-search-specials-stores-unofficial` | `APIFY_TOKEN` | unverified | 45 s |
| `aldi` | Apify `dromb/aldi-au-product-search-catalog-unofficial` | `APIFY_TOKEN` | unverified | 45 s |
| `facebook` | SociaVault Facebook Marketplace search | `SOCIAVAULT_API_KEY` | unverified | 15 s |
| `gumtree` | Apify `crawlerbros/gumtree-scraper` | `APIFY_TOKEN`, `GUMTREE_COOKIES` | degraded | 60 s |
| `ozbargain` | OzBargain RSS feed | none | verified | 12 s |
| `cheapies` | Cheapies RSS feed (New Zealand) | none | verified | 12 s |
| `taobao` | Apify `zen-studio/taobao-search-scraper` | `APIFY_TOKEN` | unverified | 95 s |
| `tmall` | The same actor run as `taobao` | `APIFY_TOKEN` | unverified | 95 s |
| `jd` | Apify `zen-studio/jd-com-search-scraper` | `APIFY_TOKEN` | unverified | 95 s |
| `1688` | TMAPI `/1688/search/items`, else Apify `zen-studio/1688-wholesale-scraper` | `TMAPI_TOKEN` or `APIFY_TOKEN` | unverified | 95 s |
| `pdd` | No search source. TMAPI item detail works through `get_offer_detail`. | `TMAPI_TOKEN` | unsupported | |
| `aliexpress` | No source yet | | unsupported | |

Budget is the longest one lane may run. The search deadline (55 seconds by default) also applies, and the shorter of the two wins.

## Status

`health` reports one of four values for each marketplace.

| Status | Meaning |
| --- | --- |
| `verified` | A live run returned offers and the parser matched them. |
| `unverified` | The lane is written from the source's documentation or from notes of an earlier run. No live run has confirmed it since the rewrite of 2026-11. |
| `degraded` | The lane returns nothing without extra setup. |
| `unsupported` | No source exists yet. |

[[develop/verify-a-lane]] shows how to run a live check for the keys you hold.

## Delivery and ETA

Each lane sets a fixed ETA window. The windows are constants in the code. No source supplies them.

| Marketplace | `eta_days` | Default `delivery` |
| --- | --- | --- |
| `ebay_au` | 3 to 7 | `direct` when eBay lists a shipping option to the postcode, else `unknown` |
| `amazon_au` | 2 to 7 | `direct` |
| `woolworths`, `coles` | 1 to 5 | `direct` |
| `aldi` | 1 to 5 | `pickup` |
| `gumtree` | 2 to 5 | `pickup` |
| `facebook` | 1 to 4 | `pickup`, or `direct` when the listing offers shipping |
| `ozbargain` | 0 to 0 | `direct` when the title says "Delivered", else `unknown` |
| `cheapies` | 0 to 0 | `no` |
| `taobao`, `tmall`, `1688`, `jd` | 10 to 25 | `via_forwarder` |

## Source notes

### Deal feeds

`ozbargain` and `cheapies` read the sites' RSS feeds, which hold about the latest 100 deals. A search keeps deals whose title, brand or tags contain every query word. The price is the first dollar amount in the title. Cheapies prices are in NZD and convert with `NZD_TO_AUD`.

### Grocery

`woolworths`, `coles` and `aldi` offers carry `unit_price_aud`, `unit` and `regular_price_aud`. `price_aud` holds the special price when there is one. Results pass a relevance filter: every query word must appear in the name, brand or category.

### eBay

`price_aud` is set only when eBay reports the amount in AUD. Other currencies go to `price_native` with `currency`. `shipping.cost_aud` is set only when eBay states a cost for the destination postcode.

### TMAPI

The 1688 endpoints are `/1688/search/items` and `/1688/item_detail`. The `/alibaba/...` paths belong to Alibaba.com, which this server does not use. The server sends the key as an `apikey` header and as an `apiToken` query parameter.

### Tmall

Taobao actor items flagged `isTmall` are labelled `tmall`. If the actor's items carry no such flag, `tmall` returns a diagnostic and the listings stay under `taobao`.

### Keepa

`get_price_history` needs `KEEPA_API_KEY` and `KEEPA_DOMAIN`. Prices are read as integer cents, and `-1` means no offer. The Keepa code has not been run against the live API.

### Sources left out

- Amazon Product Advertising API 5.0 is deprecated in favour of the Creators API, which requires 10 qualifying sales in the past 30 days. The server uses the Apify actor.
- Every Costco actor on the Apify store targets costco.com (US, USD), so Costco has no lane.

:::see-also
- [[guides/add-keys]]
- [[reference/settings]]
:::
