---
title: Search for a product
summary: Call search_offers, choose marketplaces and a sort, and read the three kinds of entry it returns.
order: 30
icon: search
audience: users
status: draft
---

`search_offers` takes a product keyword and returns one list: ranked offers, then comps, then diagnostics. Only `query` is required.

## Run a search

1. Call `search_offers` with a query and a sort.

   ```json title="Cheapest delivered price for 2 units"
   { "query": "usb-c hub", "sort": "cheapest", "qty": 2 }
   ```

2. To search fewer marketplaces, list them. The search then ends when the slowest listed lane ends.

   ```json title="Two marketplaces"
   { "query": "usb-c hub", "marketplaces": ["ebay_au", "amazon_au"] }
   ```

3. Read `kind` on each entry.

   | `kind` | Meaning | Order |
   | --- | --- | --- |
   | `offer` | A listing you can buy, ranked by `sort`. | First |
   | `comp` | A past sale price from `ebay_sold`. | Second |
   | `diagnostic` | A marketplace that returned no offers. `diagnostic_code` gives the reason. | Last |

4. Compare offers on `landed_aud` and check `landed_basis` beside it. `exact` includes shipping, `item_only` leaves shipping out, and `estimated` holds a forwarder estimate.

## Choose a sort

| `sort` | Orders by |
| --- | --- |
| `best_value` (default) | A score of price, speed and trust. |
| `cheapest` | `landed_aud`. Grocery offers sort by `unit_price_aud`. |
| `fastest` | The later bound of `shipping.eta_days`, then price. |

[[concepts/ranking]] has the formulas.

## Search Chinese marketplaces

`taobao`, `tmall`, `1688` and `jd` match Chinese text far better than English. The server does not translate. Pass the query in Chinese as `query_zh`, and give the item weight so that the forwarder estimate uses it.

```json title="Chinese marketplaces"
{
  "query": "silicone kitchen utensils",
  "query_zh": "硅胶厨具",
  "marketplaces": ["1688", "taobao", "jd"],
  "qty": 50,
  "est_weight_kg": 0.3
}
```

An offer whose `moq` is larger than `qty` goes to the end of the list in every sort.

## Change the destination

The [[term:Destination]] is `SHIP_TO_COUNTRY` and `SHIP_TO_POSTCODE`, AU 4000 by default. To change it for one call, pass `postcode`, and `ship_to` for another country.

```json title="Deliver to Melbourne"
{ "query": "usb-c hub", "postcode": "3000" }
```

`ebay_au` sends the postcode to eBay and gets the shipping options and costs for it. Pickup searches on `facebook` stay centred on `SHIP_TO_LAT` and `SHIP_TO_LNG`, which a call cannot change.

To drop listings that must be collected in person, pass `"include_pickup": false`.

## Search eBay auctions and overseas sellers

| Argument | Value | Result |
| --- | --- | --- |
| `ebay_auctions` | `true` | Auction listings only. `price_aud` is the current bid and `auction` holds the bid count and end time. |
| `ebay_seller_scope` | `domestic` (default) | Items located in Australia. |
| `ebay_seller_scope` | `global` | Sellers worldwide on the AU marketplace. |
| `ebay_seller_scope` | `auto` | eBay's default ranking. |

## Refresh one offer

Call `get_offer_detail` with an `offer_id` from the search. `taobao`, `tmall`, `1688`, `jd` and `pdd` ids are fetched from TMAPI, and `ebay_au` ids from eBay. For every other marketplace the tool returns the offer as the most recent search held it.

```json title="Arguments"
{ "offer_id": "ebay_au:v1|1234|0" }
```

## Timeouts

All lanes run at once under one deadline of 55 seconds. A lane that has not replied by then is cancelled and returns a `timeout` diagnostic. Apify lanes take 30 to 90 seconds.

To give one search more time, pass `deadline_s` (5 to 300):

```json title="A longer search"
{ "query": "usb-c hub", "marketplaces": ["taobao", "jd"], "deadline_s": 120 }
```

A search with a `timeout`, `upstream_error` or `quota` diagnostic is not cached, so the next call tries the source again.

:::see-also
- [[reference/tools]]
- [[reference/offer]]
- [[concepts/landed-cost]]
:::
