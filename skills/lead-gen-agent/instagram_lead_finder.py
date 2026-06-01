"""
Instagram Lead Finder — discovers potential Pinterest service leads via hashtags.
Uses Apify's Instagram Hashtag Scraper actor to pull recent posts,
then filters profiles by follower count and bio keywords.

Apify actor: apify/instagram-hashtag-scraper
Docs: https://apify.com/apify/instagram-hashtag-scraper
"""

import os
import sys
import time
import requests
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
except ImportError:
    pass

sys.path.insert(0, str(Path(__file__).parent))
from lead_tracker import append_leads

APIFY_API_KEY = os.getenv("APIFY_API_KEY")
APIFY_BASE = "https://api.apify.com/v2"

# ── Hashtags to mine ──────────────────────────────────────────────────────────

HASHTAGS = [
    # Physical product sellers
    "etsyjewelry",
    "handmadejewelry",
    "jewelrymaker",
    "etsycandles",
    "candlemaker",
    "etsyceramics",
    "potterymaker",
    "etsyhomedecor",
    "handmadehomedecor",
    "etsyseller",
    "shopsmall",
    "handmadewithlove",
    # Service / experience businesses
    "weddingphotographer",
    "weddingphotographerusa",
    "interiorstylist",
    "interiordesigner",
    "weddingflorist",
    "florist",
    "eventplanner",
    "weddingplanner",
    "giftshop",
    "travelagent",
    "boutiquetravel",
]

# Profiles with any of these in their bio are excluded (digital product sellers)
EXCLUSION_KEYWORDS = [
    "digital products",
    "digital downloads",
    "printables",
    "canva templates",
    "design files",
    "svg files",
    "digital files",
    "templates shop",
]

FOLLOWER_MIN = 50
FOLLOWER_MAX = 5000


# ── Apify helpers ─────────────────────────────────────────────────────────────

# Actor ID from the account's saved actors
INSTAGRAM_ACTOR = "shu8hvrXbJbY3Eb9W"


def _run_actor(actor_id: str, input_data: dict, timeout_secs: int = 300) -> list:
    """Start an Apify actor using token auth, wait for completion, return dataset items."""
    if not APIFY_API_KEY:
        print("[warn] APIFY_API_KEY not set — skipping Instagram scrape", file=sys.stderr)
        return []

    token_params = {"token": APIFY_API_KEY}

    resp = requests.post(
        f"{APIFY_BASE}/acts/{actor_id}/runs",
        params=token_params,
        json=input_data,
        timeout=30,
    )
    if resp.status_code not in (200, 201):
        print(f"  [error] Actor start failed: {resp.status_code} {resp.text[:300]}", file=sys.stderr)
        return []

    run_data = resp.json().get("data", {})
    run_id = run_data.get("id")
    print(f"  Actor run started: {run_id}", file=sys.stderr)

    deadline = time.time() + timeout_secs
    dataset_id = None
    while time.time() < deadline:
        s = requests.get(
            f"{APIFY_BASE}/actor-runs/{run_id}",
            params=token_params, timeout=15,
        )
        data = s.json().get("data", {})
        status = data.get("status", "")
        if status == "SUCCEEDED":
            dataset_id = data.get("defaultDatasetId")
            break
        if status in ("FAILED", "ABORTED", "TIMED-OUT"):
            print(f"  [error] Actor run {status}", file=sys.stderr)
            return []
        time.sleep(10)
    else:
        print(f"  [warn] Actor timed out after {timeout_secs}s", file=sys.stderr)
        return []

    if not dataset_id:
        return []

    items_resp = requests.get(
        f"{APIFY_BASE}/datasets/{dataset_id}/items",
        params={**token_params, "format": "json", "clean": "true"},
        timeout=30,
    )
    return items_resp.json() if items_resp.status_code == 200 else []


# ── Profile filtering ─────────────────────────────────────────────────────────

def _is_excluded(bio: str) -> bool:
    bio_lower = (bio or "").lower()
    return any(kw in bio_lower for kw in EXCLUSION_KEYWORDS)


def _score_lead(profile: dict) -> int:
    score = 0
    if profile.get("website"):
        score += 3
    bio = (profile.get("biography") or "").lower()
    # Etsy mention in bio → likely physical product seller
    if "etsy" in bio:
        score += 3
    # Has a business category
    if profile.get("businessCategoryName"):
        score += 2
    # Follower sweet spot
    followers = int(profile.get("followersCount") or 0)
    if 500 <= followers <= 3000:
        score += 5
    elif 100 <= followers < 500:
        score += 3
    elif 3000 < followers <= 5000:
        score += 2
    return score


def _extract_niche(profile: dict, hashtag: str) -> str:
    """Best-guess product/niche from profile category + hashtag."""
    category = profile.get("businessCategoryName") or ""
    if category:
        return category
    # Map hashtag to readable niche
    niche_map = {
        "etsyjewelry": "handmade jewelry",
        "handmadejewelry": "handmade jewelry",
        "jewelrymaker": "handmade jewelry",
        "etsycandles": "handmade candles",
        "candlemaker": "handmade candles",
        "etsyceramics": "ceramic pottery",
        "potterymaker": "ceramic pottery",
        "etsyhomedecor": "home decor",
        "handmadehomedecor": "home decor",
        "etsyseller": "handmade products",
        "shopsmall": "small business",
        "handmadewithlove": "handmade products",
        "weddingphotographer": "wedding photography",
        "weddingphotographerusa": "wedding photography",
        "interiorstylist": "interior design",
        "interiordesigner": "interior design",
        "weddingflorist": "wedding florals",
        "florist": "floristry",
        "eventplanner": "event planning",
        "weddingplanner": "wedding planning",
        "giftshop": "gift shop",
        "travelagent": "travel agency",
        "boutiquetravel": "boutique travel",
    }
    return niche_map.get(hashtag, hashtag.replace("_", " "))


def run(hashtags=None, results_per_hashtag=50):
    tags = hashtags or HASHTAGS
    leads = []
    seen_handles = set()

    for hashtag in tags:
        print(f"\n[Instagram] Scraping #{hashtag}...", file=sys.stderr)

        items = _run_actor(
            INSTAGRAM_ACTOR,
            {
                "directUrls": [f"https://www.instagram.com/explore/tags/{hashtag}/"],
                "resultsType": "posts",
                "resultsLimit": results_per_hashtag,
                "addParentData": True,
            },
            timeout_secs=300,
        )

        print(f"  Got {len(items)} posts", file=sys.stderr)

        for item in items:
            # Post-level owner data
            owner = item.get("ownerUsername") or item.get("owner", {}).get("username", "")
            if not owner or owner in seen_handles:
                continue

            followers = int(
                item.get("ownerFollowersCount") or
                item.get("owner", {}).get("followersCount") or 0
            )
            bio = (
                item.get("ownerBiography") or
                item.get("owner", {}).get("biography") or ""
            )
            full_name = (
                item.get("ownerFullName") or
                item.get("owner", {}).get("fullName") or ""
            )
            website = (
                item.get("ownerExternalUrl") or
                item.get("owner", {}).get("externalUrl") or ""
            )

            # Apply filters
            if not (FOLLOWER_MIN <= followers <= FOLLOWER_MAX):
                continue
            if _is_excluded(bio):
                continue

            seen_handles.add(owner)

            profile = {
                "followersCount": followers,
                "biography": bio,
                "website": website,
                "businessCategoryName": item.get("owner", {}).get("businessCategoryName", ""),
            }
            score = _score_lead(profile)
            niche = _extract_niche(profile, hashtag)

            lead = {
                "source": "instagram",
                "owner_name": full_name,
                "shop_or_business_name": full_name or owner,
                "instagram_handle": f"@{owner}",
                "website": website,
                "product_type": niche,
                "follower_count": followers,
                "priority_score": score,
                "status": "found",
                "notes": f"Found via #{hashtag}",
            }
            leads.append(lead)
            print(f"    + @{owner} ({followers} followers, score {score})", file=sys.stderr)

    added = append_leads(leads)
    print(f"\n[Instagram] {added} new leads added to tracker.", file=sys.stderr)
    return added


if __name__ == "__main__":
    run()
