"""
Etsy API v3 client for Switzertemplates.
Fetches shop info and active listings using the API key from .env.
Listing-level stats (orders per listing) require OAuth and are not available
with an API key alone - views and favorites are fetched from the listing object.
"""

import os
import time
import requests
from dotenv import load_dotenv

load_dotenv()

ETSY_API_BASE = "https://openapi.etsy.com/v3/application"
SHOP_NAME = "switzertemplates"


class EtsyClient:
    def __init__(self):
        self.api_key = os.getenv("ETSY_API_KEY")
        if not self.api_key:
            raise ValueError("ETSY_API_KEY not found in .env")
        self.headers = {"x-api-key": self.api_key}
        self.shop_id = None

    def _get(self, path, params=None):
        url = f"{ETSY_API_BASE}{path}"
        resp = requests.get(url, headers=self.headers, params=params, timeout=15)
        if resp.status_code == 401:
            raise PermissionError(
                "Etsy API key unauthorised. Check ETSY_API_KEY in .env."
            )
        if resp.status_code == 403:
            body = ""
            try:
                body = resp.json().get("error", "")
            except Exception:
                pass
            if "not found" in body.lower() or "not active" in body.lower():
                raise PermissionError(
                    "Etsy API key is not active or not found. "
                    "Go to https://www.etsy.com/developers/your-apps to check your app and regenerate the key, "
                    "then update ETSY_API_KEY in .env."
                )
            raise PermissionError(
                "Etsy API returned 403. This endpoint may require OAuth."
            )
        if resp.status_code == 429:
            print("  Rate limited by Etsy API - waiting 10s...")
            time.sleep(10)
            return self._get(path, params)
        resp.raise_for_status()
        return resp.json()

    def get_shop(self):
        """Fetch shop details by name, cache the shop_id."""
        data = self._get("/shops", params={"shop_name": SHOP_NAME})
        results = data.get("results", [])
        if not results:
            raise ValueError(f"No Etsy shop found with name '{SHOP_NAME}'")
        shop = results[0]
        self.shop_id = shop["shop_id"]
        return {
            "shop_id": shop["shop_id"],
            "shop_name": shop["shop_name"],
            "title": shop.get("title", ""),
            "listing_active_count": shop.get("listing_active_count", 0),
            "num_favorers": shop.get("num_favorers", 0),
            "review_count": shop.get("review_count", 0),
            "review_average": shop.get("review_average", 0),
            "url": shop.get("url", ""),
        }

    def get_active_listings(self, limit=100):
        """
        Fetch all active listings for the shop.
        Returns a list of dicts with key fields useful for trend analysis.
        Paginates automatically up to 1000 listings.
        """
        if not self.shop_id:
            self.get_shop()

        listings = []
        offset = 0
        page_size = min(limit, 100)

        while True:
            data = self._get(
                f"/shops/{self.shop_id}/listings/active",
                params={
                    "limit": page_size,
                    "offset": offset,
                    "includes": "tags,images",
                    "sort_on": "views",
                    "sort_order": "desc",
                },
            )
            results = data.get("results", [])
            if not results:
                break

            for l in results:
                price_val = None
                if l.get("price"):
                    try:
                        price_val = float(l["price"]["amount"]) / float(
                            l["price"]["divisor"]
                        )
                    except (KeyError, TypeError, ZeroDivisionError):
                        pass

                created_ts = l.get("creation_timestamp", 0)
                days_listed = 0
                if created_ts:
                    days_listed = max(
                        1, int((time.time() - created_ts) / 86400)
                    )

                views = l.get("views", 0)
                views_per_day = round(views / days_listed, 2) if days_listed else 0

                listings.append(
                    {
                        "listing_id": l["listing_id"],
                        "title": l.get("title", ""),
                        "tags": l.get("tags", []),
                        "price_usd": price_val,
                        "views": views,
                        "num_favorers": l.get("num_favorers", 0),
                        "days_listed": days_listed,
                        "views_per_day": views_per_day,
                        "quantity": l.get("quantity", 0),
                        "state": l.get("state", ""),
                        "url": f"https://www.etsy.com/listing/{l['listing_id']}",
                    }
                )

            offset += len(results)
            if offset >= data.get("count", 0) or len(results) < page_size:
                break

            time.sleep(0.3)

        return listings
