---
title: Tools
summary: The 7 tools and the prompt, with every argument, its default and what each tool returns.
order: 10
icon: code
audience: users
status: draft
---

The server registers as `procurement-search` with 7 tools and 1 prompt.

| Tool | Purpose | Needs |
| --- | --- | --- |
| `search_offers` | Search marketplaces and rank the offers. | A key per marketplace |
| `get_offer_detail` | Refresh one offer. | `TMAPI_TOKEN` or eBay keys for a live fetch |
| `search_by_image` | Find listings that match a photo. | `APIFY_TOKEN` |
| `latest_deals` | List the newest deals, most upvoted first. | Nothing |
| `get_price_history` | Amazon price history from Keepa. | `KEEPA_API_KEY`, `KEEPA_DOMAIN` |
| `search_history` | Read past searches. | `DATABASE_URL` |
| `health` | Report which marketplaces can run. | Nothing |

## search_offers

Searches the requested marketplaces at once under one deadline. Returns a list of entries: offers ranked by `sort`, then comps, then diagnostics. [[reference/offer]] lists the fields.

| Argument | Type | Default | Meaning |
| --- | --- | --- | --- |
| `query` | string | required | Product keyword. Sent as written to every source. |
| `marketplaces` | list of strings | all 16 | The marketplaces to search. An unknown name returns an `unsupported` diagnostic. |
| `sort` | `cheapest`, `fastest`, `best_value` | `best_value` | How offers are ranked. |
| `qty` | integer, 1 or more | `1` | Quantity. Offers with a larger minimum order rank last. |
| `ship_to` | string | `SHIP_TO_COUNTRY` | Destination country code. |
| `postcode` | string | `SHIP_TO_POSTCODE` | Destination postcode. |
| `max_results` | integer, 1 to 50 | `10` | Cap per marketplace. |
| `query_zh` | string | none | The query in Chinese, for `taobao`, `tmall`, `1688` and `jd`. |
| `est_weight_kg` | number above 0 | `FORWARDER_DEFAULT_WEIGHT_KG` | Weight of one item, for the forwarder estimate. |
| `include_pickup` | boolean | `true` | Keep listings that must be collected in person. |
| `deadline_s` | number, 5 to 300 | `PROCUREMENT_DEADLINE_S` | Seconds allowed for the whole search. |
| `ebay_auctions` | boolean | `false` | eBay: auction listings only. |
| `ebay_seller_scope` | `domestic`, `global`, `auto` | `domestic` | eBay: items located in AU, sellers worldwide, or eBay's default. |

The result holds at most `max_results * 2` offers. Comps and diagnostics are added after that cut.

## get_offer_detail

Returns one offer, or a tool failure.

| Argument | Type | Default | Meaning |
| --- | --- | --- | --- |
| `offer_id` | string | required | An id from `search_offers`, in the form `<marketplace>:<item id>`. |

| Marketplace of the id | Source of the answer |
| --- | --- |
| `taobao`, `tmall`, `1688`, `jd`, `pdd` | TMAPI item detail, fetched live. |
| `ebay_au` | eBay Browse API, fetched live. |
| any other | The offer as the most recent search held it. |

When a live fetch fails, the tool falls back to the stored offer, then to the failure. The server remembers the last 2000 offers in memory. With a database it also looks in unexpired cached searches.

| Failure `code` | `error` | Cause |
| --- | --- | --- |
| `bad_id` | `offer id must look like <marketplace>:<item id>` | The id has no colon. |
| `diagnostic_id` | `this id names a diagnostic entry, which has no detail` | The id is a diagnostic's, such as `jd:timeout`. |
| `not_found` | `<marketplace> has no detail endpoint and no recent search holds this offer; run search_offers again` | The offer is in neither the memory nor the cache. |
| `missing_key` | `TMAPI_TOKEN is not set` | A live fetch needs a key that is unset. |
| `unsubscribed` | `TMAPI error 4013: API not subscribed; subscribe at console.tmapi.io, APIs List` | TMAPI answered 401. |
| `upstream_error` | The source's error | The source replied with an error. |

## search_by_image

Runs a reverse image search through an Apify actor and returns matching listings as offers. One search costs about 0.10 USD in Apify credit.

| Argument | Type | Default | Meaning |
| --- | --- | --- | --- |
| `image_url` | string | required | Public URL of a product photo, JPG or PNG. |
| `destination` | `1688`, `alibaba`, `aliexpress`, `global` | `1688` | Where to search. `global` covers Amazon, Walmart, eBay and other retail sites. |
| `max_results` | integer, 1 to 50 | `10` | Cap on matches. |

The offers carry a price, a minimum order and a supplier name. They have no delivery status and no landed cost. A failed or empty search returns one diagnostic.

## latest_deals

Reads the deal sites' RSS feeds, which hold about the latest 100 deals each. Returns deals sorted by net votes, highest first, then one diagnostic for each feed that failed.

| Argument | Type | Default | Meaning |
| --- | --- | --- | --- |
| `sources` | list of `ozbargain`, `cheapies` | `["ozbargain"]` | The deal sites to read. `cheapies` is a New Zealand site priced in NZD. |
| `query` | string | none | Keep deals whose title, brand or tags contain every word. |
| `min_votes` | integer, 0 or more | `0` | Keep deals with at least this many net votes. |
| `max_results` | integer, 1 to 100 | `20` | Cap on deals. |

Each deal has a `community` block with votes, comments, clicks and expiry. `price_aud` is the first dollar amount in the deal's title.

## get_price_history

Returns the Amazon price history of one product from Keepa, for the price sold by Amazon itself.

| Argument | Type | Default | Meaning |
| --- | --- | --- | --- |
| `offer_id_or_asin` | string | required | `amazon_au:B0XXXXXXXX` or a bare 10-character ASIN. |
| `days` | integer, 1 to 365 | `90` | Window for the price series. |
| `include_series` | boolean | `false` | Also return every price change in the window. |

| Result field | Meaning |
| --- | --- |
| `asin` | The product id. |
| `current_aud` | The current price. |
| `avg_30d_aud`, `avg_90d_aud` | The 30-day and 90-day average. |
| `min_aud`, `max_aud` | The lowest and highest price Keepa has recorded. |
| `series` | With `include_series`: a list of `{ t, price_aud }`, oldest first. `t` is an ISO datetime in UTC. |

| Failure `code` | `error` | Cause |
| --- | --- | --- |
| `bad_id` | `expected a 10-character ASIN or amazon_au:<ASIN>` | The argument is no ASIN. |
| `missing_key` | `KEEPA_API_KEY is not set` or `KEEPA_DOMAIN is not set` | A Keepa setting is unset. |
| `not_found` | `Keepa has no price data for <ASIN>` | Keepa does not track the product. |

## search_history

Reads the Postgres search log or the cache, newest first.

| Argument | Type | Default | Meaning |
| --- | --- | --- | --- |
| `source` | `log`, `cache` | `log` | `log`: every past search. `cache`: unexpired cached results. |
| `query_contains` | string | none | Keep searches whose query contains this text. Case is ignored. |
| `since_hours` | integer, 1 to 2160 | `168` | How far back to look. |
| `limit` | integer, 1 to 200 | `20` | Cap on rows. |
| `include_offers` | boolean | `false` | `cache` only: include the cached offers in each row. |

| `source` | Row fields |
| --- | --- |
| `log` | `id`, `created_at`, `query`, `marketplaces`, `sort`, `qty`, `ship_to`, `result_count`, `elapsed_ms` |
| `cache` | `cache_key`, `created_at`, `query`, `marketplaces`, `sort`, `expires_in_s`, `offer_count`, and `offers` on request |

Without a database the tool returns a failure with code `db_disabled`.

## health

Takes no arguments and shows no key values.

| Field | Meaning |
| --- | --- |
| `status` | `ok` when the server answers. |
| `marketplaces` | For each marketplace: `ready`, `missing` (the unset key), `source` and `status`. |
| `ready_count` | The number of marketplaces with `ready: true`. |
| `image_search` | `ready` and `missing` for `search_by_image`. |
| `price_history` | `ready` and the list of `missing` Keepa settings. |
| `ship_to` | The default destination: `country`, `postcode`, `lat`, `lng`, `radius_km`. |
| `forwarder_estimate` | The freight rate, default weight, minimum charge, fee and GST rate in use. |
| `deadline_s`, `cny_to_aud` | The search deadline and the CNY rate in use. |
| `database` | `configured`, `schema`, `enabled`, `error`, `cache_ttl_s`. |

`ready` is `true` when the key is set and the status is `verified` or `unverified`. [[reference/marketplaces#status|Status]] lists the four values.

## Prompt procurement_brief

Takes `query` and returns a system prompt. The prompt tells the model to call `search_offers` with `sort: best_value`, compare `landed_aud` with its `landed_basis`, and report diagnostics separately.

:::see-also
- [[reference/offer]]
- [[reference/marketplaces]]
- [[guides/search]]
:::
