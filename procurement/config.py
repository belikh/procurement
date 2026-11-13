"""Settings read from the environment and from .env in the repo root.

Every key is optional. A lane without its key reports that it is unconfigured.
Empty values count as unset.
"""

from __future__ import annotations

import re
from pathlib import Path

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_FILE, env_ignore_empty=True, extra="ignore", populate_by_name=True
    )

    # China marketplaces and aggregators
    tmapi_token: str | None = Field(
        default=None, validation_alias=AliasChoices("TMAPI_TOKEN", "TMAPI_API_TOKEN")
    )

    # Australian sources
    ebay_app_id: str | None = Field(
        default=None, validation_alias=AliasChoices("EBAY_APP_ID", "EBAY_CLIENT_ID")
    )
    ebay_cert_id: str | None = Field(
        default=None, validation_alias=AliasChoices("EBAY_CERT_ID", "EBAY_CLIENT_SECRET")
    )
    ebay_oauth_token: str | None = None  # optional pre-fetched bearer token
    sociavault_api_key: str | None = None
    keepa_api_key: str | None = None

    # Apify: one token, one actor per lane
    apify_token: str | None = None
    gumtree_apify_actor: str = "crawlerbros/gumtree-scraper"
    gumtree_cookies: str | None = None
    ebay_sold_apify_actor: str = "caffein.dev/ebay-sold-listings"
    amazon_apify_actor: str = "junglee/free-amazon-product-scraper"
    image_search_apify_actor: str = "dev00/alibaba-1688-aliexpress-reverse-image-search-api"
    # zen-studio actors require maxItems >= 10.
    taobao_apify_actor: str = "zen-studio/taobao-search-scraper"
    jd_apify_actor: str = "zen-studio/jd-com-search-scraper"
    ali1688_apify_actor: str = "zen-studio/1688-wholesale-scraper"
    # Costco is left out: every Costco actor on the Apify store targets costco.com (US, USD).
    woolworths_apify_actor: str = "dromb/woolworths-au-product-search-catalog-unofficial"
    coles_apify_actor: str = "dromb/coles-au-product-search-specials-stores-unofficial"
    aldi_apify_actor: str = "dromb/aldi-au-product-search-catalog-unofficial"

    # Deal feeds: the sites' own RSS, no key
    ozbargain_feed_url: str = "https://www.ozbargain.com.au/deals/feed"
    cheapies_feed_url: str = "https://www.cheapies.nz/deals/feed"

    # eBay account deletion notifications. A new production keyset stays disabled until
    # the endpoint answers eBay's GET challenge. The challenge hash covers the endpoint
    # string, so it must match the URL registered in the developer portal exactly.
    ebay_deletion_token: str | None = None
    ebay_deletion_endpoint: str = "https://procurement.jupiter.au/ebay/notifications"

    # Postgres cache and search log
    database_url: str | None = None
    pg_schema: str = Field(default="procurement", validation_alias="PROCUREMENT_PG_SCHEMA")

    # Where offers must be delivered. Brisbane CBD by default.
    ship_to_country: str = "AU"
    ship_to_postcode: str = "4000"
    ship_to_lat: float = -27.4698
    ship_to_lng: float = 153.0251
    pickup_radius_km: float = 50

    # Freight forwarder estimate for China-domestic marketplaces. These defaults are
    # placeholders; set them from your forwarder's rate card.
    forwarder_rate_aud_per_kg: float = 12.0
    forwarder_default_weight_kg: float = 0.5
    forwarder_min_charge_aud: float = 15.0
    forwarder_fee_pct: float = 0.0
    gst_rate: float = 0.10
    nzd_to_aud: float = 0.92

    # Behaviour
    cny_to_aud: float = 0.215
    default_timeout_s: float = Field(default=8, validation_alias="PROCUREMENT_TIMEOUT_S")
    cache_ttl_s: int = Field(default=3600, validation_alias="PROCUREMENT_CACHE_TTL_S")
    include_raw: bool = Field(default=False, validation_alias="PROCUREMENT_INCLUDE_RAW")
    mcp_http_port: int | None = None
    # One wall-clock limit for a whole search. MCP clients commonly cut a tool call at 60 s.
    deadline_s: float = Field(default=55, validation_alias="PROCUREMENT_DEADLINE_S")
    # Keepa domain id for amazon.com.au. Keepa's official clients list ids 1 to 12
    # (12 is Brazil) and no Australian id, so price history stays off until this is set.
    keepa_domain: int | None = None

    @field_validator("pg_schema")
    @classmethod
    def _schema_is_identifier(cls, v: str) -> str:
        # The schema name is interpolated into SQL, so it must be a plain identifier.
        if not re.fullmatch(r"[a-z_][a-z0-9_]*", v):
            raise ValueError("PROCUREMENT_PG_SCHEMA must match [a-z_][a-z0-9_]*")
        return v


settings = Settings()
