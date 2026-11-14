---
title: Offer format
summary: Every field of an entry in a search result, the diagnostic codes and the tool failure format.
order: 20
icon: file
audience: users
status: draft
---

`search_offers`, `search_by_image` and `latest_deals` return a list of entries with one shape. `kind` says what an entry is: `offer`, `comp` or `diagnostic`.

```json title="An offer from ebay_au (example values)"
{
  "offer_id": "ebay_au:v1|1234|0",
  "marketplace": "ebay_au",
  "title": "USB-C Hub 7 in 1",
  "url": "https://www.ebay.com.au/itm/1234",
  "price_aud": 39.95,
  "currency": "AUD",
  "shipping": {
    "eta_days": [3, 7],
    "delivery": "direct",
    "delivery_basis": "eBay lists a shipping option for the buyer's postcode",
    "cost_aud": 8.5
  },
  "seller": { "shop_name": "example-seller" },
  "source_reliability": "authoritative",
  "kind": "offer",
  "landed_aud": 48.45,
  "landed_basis": "exact",
  "landed_breakdown": { "goods": 39.95, "shipping": 8.5 }
}
```

## Fields

| Field | Type | Meaning |
| --- | --- | --- |
| `offer_id` | string | `<marketplace>:<item id>`. Pass it to `get_offer_detail`. |
| `marketplace` | string | The marketplace the entry belongs to. |
| `kind` | `offer`, `comp`, `diagnostic` | Default `offer`. |
| `title`, `title_en` | string | The listing title, and its English form when the source gives one. |
| `url`, `image` | string | Links to the listing and its picture. |
| `price_aud` | number | The price of one item in AUD. For an auction, the current bid. |
| `price_cny` | number | The price in CNY, on Chinese marketplaces. |
| `price_native`, `currency` | number, string | The price in `currency` when the source gave no AUD price. `price_aud` is then null. |
| `moq` | integer | Minimum order quantity. |
| `stock` | integer | Units in stock, when the source states it. |
| `unit_price_aud`, `unit` | number, string | Grocery: the price per unit, such as per 100 g or per litre. |
| `regular_price_aud` | number | Grocery: the price before a special. `price_aud` holds the special price. |
| `shipping` | object | See [Shipping](#shipping). |
| `seller` | object | `shop_name`, `shop_id`, `rating`, `verified`. |
| `seller_country` | string | Country code of the item or seller, from eBay. |
| `community` | object | Deal sites: `votes_pos`, `votes_neg`, `comment_count`, `click_count`, `expiry`, `brand`, `tags`. |
| `auction` | object | eBay auctions: `current_bid_aud`, `bid_count`, `end_time`, `time_left`, `reserve_met`. |
| `price_history` | object | Amazon offers: the Keepa summary, when Keepa is configured. |
| `landed_aud` | number | Total in AUD for `qty` delivered to the destination. |
| `landed_basis` | `exact`, `estimated`, `item_only` | How firm `landed_aud` is. |
| `landed_breakdown` | object | The parts that sum to `landed_aud`. |
| `source_reliability` | `authoritative`, `aggregator`, `best_effort` | How direct the source is. Default `aggregator`. |
| `diagnostic_code` | string | Set when `kind` is `diagnostic`. |
| `raw` | object | The source's payload. Set when `PROCUREMENT_INCLUDE_RAW=1`. |

A field with no value is null.

## Shipping

| Field | Type | Meaning |
| --- | --- | --- |
| `delivery` | `direct`, `pickup`, `via_forwarder`, `no`, `unknown` | Whether and how the offer reaches the destination. Default `unknown`. |
| `delivery_basis` | string | What the delivery status rests on. |
| `cost_aud` | number | The shipping cost the source stated. Null means the source stated none. It does not mean free. |
| `eta_days` | `[min, max]` | Delivery window in days. Fixed per marketplace. |
| `method` | string | A label for the shipping method. |
| `domestic_cny` | number | The delivery leg inside China, in CNY. |
| `intl_estimate_aud` | number | The forwarder freight estimate in AUD. |

[[concepts/landed-cost]] explains each `delivery` value and each `landed_basis`.

## Diagnostic codes

A requested marketplace with no offers returns one diagnostic. Its `title` is `[<marketplace>] <detail>`.

| `diagnostic_code` | `offer_id` | Meaning |
| --- | --- | --- |
| `missing_key` | `<marketplace>:missing_key` | The key is not set. The title names the variable. |
| `timeout` | `<marketplace>:timeout` | No reply before the deadline. The upstream call was cancelled. |
| `upstream_error` | `<marketplace>:error` | The source replied with an error, or its reply could not be read. |
| `quota` | `<marketplace>:error` | An Apify actor reported its free runs or credit as used up. |
| `unsubscribed` | `<marketplace>:unsubscribed` | TMAPI answered 401: the API is not subscribed in the TMAPI console. |
| `degraded` | `<marketplace>:degraded` | The source needs extra setup. Gumtree needs `GUMTREE_COOKIES`. |
| `unsupported` | `<marketplace>:unsupported` | No source exists for this marketplace, or the name is unknown. |
| `no_results` | `<marketplace>:no_results` | The source ran and matched nothing. |
| `not_deliverable` | `<marketplace>:not_deliverable` | Offers were found and left out because they do not reach the destination. |

```json title="A diagnostic"
{
  "offer_id": "ebay_au:missing_key",
  "marketplace": "ebay_au",
  "title": "[ebay_au] not configured: set EBAY_APP_ID and EBAY_CERT_ID",
  "kind": "diagnostic",
  "diagnostic_code": "missing_key"
}
```

## Tool failure

`get_offer_detail`, `get_price_history` and `search_history` return this object when they cannot produce a result.

| Field | Type | Meaning |
| --- | --- | --- |
| `error` | string | What went wrong, in a sentence. |
| `code` | string | `bad_id`, `diagnostic_id`, `not_found`, `db_disabled`, or a diagnostic code. |
| `offer_id` | string | The id the call was about, when there is one. |

```json title="A tool failure"
{ "error": "KEEPA_API_KEY is not set", "code": "missing_key", "offer_id": null }
```

:::see-also
- [[reference/tools]]
- [[concepts/landed-cost]]
:::
