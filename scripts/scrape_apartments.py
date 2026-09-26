#!/usr/bin/env python3
"""Scrape Paris apartment listings (rent + sale) from Bien'ici.

The same public JSON API serves both markets: filterType=rent / filterType=buy.
Each listing carries a "transaction" field so the frontend and the price model
can treat them separately.

Output: data/apartments.json
"""
import json, time, hashlib, urllib.parse, urllib.request
from datetime import datetime, timezone
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "data" / "apartments.json"

HEADERS = {
    "accept": "*/*",
    "accept-language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
    "user-agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/125.0.0.0 Safari/537.36"),
    "x-requested-with": "XMLHttpRequest",
}

BIENICI_API = "https://www.bienici.com/realEstateAds.json"
BIENICI_SUGGEST = "https://res.bienici.com/suggest.json"

# Sanity price ranges per transaction type (EUR)
PRICE_RANGE = {"rent": (100, 15000), "buy": (20000, 5000000)}


def get_bienici_zone_id(location_slug: str) -> list:
    url = f"{BIENICI_SUGGEST}?q={urllib.parse.quote(location_slug)}"
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=15) as r:
        data = json.loads(r.read().decode())
    if not data:
        raise SystemExit(f"Bien'ici: no zone found for {location_slug!r}")
    return data[0].get("zoneIds", [])


def fetch_bienici_listings(location="paris-75", transaction="rent",
                           max_pages=55, max_items=1500):
    """Fetch listings for one transaction type ('rent' or 'buy')."""
    zone_ids = get_bienici_zone_id(location)
    print(f"  Bien'ici zone IDs for {location}: {zone_ids}")

    listings = []
    page = 1
    while page <= max_pages and len(listings) < max_items:
        filters = {
            "size": 24,
            "from": (page - 1) * 24,
            "page": page,
            "filterType": transaction,
            "propertyType": ["flat"],
            "zoneIdsByTypes": {"zoneIds": zone_ids},
            "sortBy": "publicationDate",
            "sortOrder": "desc",
            "onTheMarket": [True],
        }
        params = urllib.parse.urlencode({
            "filters": json.dumps(filters),
            "extensionType": "extendedIfNoResult",
            "leadingCount": "2",
        })
        url = f"{BIENICI_API}?{params}"
        req = urllib.request.Request(url, headers={
            **HEADERS, "referer": "https://www.bienici.com/"
        })
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                payload = json.loads(r.read().decode())
        except Exception as e:
            print(f"  Bien'ici page {page} error: {e}")
            break

        ads = payload.get("realEstateAds", [])
        total = payload.get("total", 0)
        if page == 1:
            print(f"  Bien'ici total results ({transaction}): {total}")

        for ad in ads:
            listings.append(parse_bienici_ad(ad, transaction))

        print(f"  page {page}: +{len(ads)} (cumulative {len(listings)})")
        if not ads or len(listings) >= total:
            break
        page += 1
        time.sleep(1)

    return listings[:max_items]


def parse_bienici_ad(ad: dict, transaction: str) -> dict:
    photos = [p.get("url_photo", p.get("url", "")) for p in ad.get("photos", [])]
    blur = ad.get("blurInfo", {})
    pos = blur.get("position") or blur.get("centroid") or {}
    return {
        "source": "bienici",
        "source_id": ad.get("id", ""),
        "transaction": transaction,
        "title": ad.get("title", ""),
        "price": ad.get("price"),
        "price_unit": "EUR/month" if transaction == "rent" else "EUR",
        "surface_m2": ad.get("surfaceArea"),
        "rooms": ad.get("roomsQuantity"),
        "bedrooms": ad.get("bedroomsQuantity"),
        "property_type": ad.get("propertyType", "flat"),
        "city": ad.get("city", ""),
        "postal_code": ad.get("postalCode", ""),
        "district": (ad.get("district") or {}).get("libelle", ""),
        "lat": pos.get("lat"),
        "lon": pos.get("lon"),
        "blur_radius": blur.get("radius"),
        "description": ad.get("description", ""),
        "energy_class": ad.get("energyClassification"),
        "climate_class": ad.get("climateClassification") or ad.get("greenhouseGasClassification") or ad.get("gesClassification"),
        "furnished": ad.get("isFurnished"),
        "publication_date": ad.get("publicationDate"),
        "photos": photos[:5],
        "url": f"https://www.bienici.com/annonce/location/{ad.get('id', '')}" if transaction == "rent"
               else f"https://www.bienici.com/annonce/vente/{ad.get('id', '')}",
        "agency": (ad.get("contact") or {}).get("contactName", ""),
    }


def listing_fingerprint(l: dict) -> str:
    """Fuzzy fingerprint; includes transaction so rent/buy never merge."""
    price_bucket = round((l.get("price") or 0) / 50) * 50
    surface_bucket = round((l.get("surface_m2") or 0) / 3) * 3
    key = (f"{l.get('transaction', 'rent')}|{l.get('postal_code', '')}|"
           f"{price_bucket}|{surface_bucket}|{l.get('rooms', '')}")
    return hashlib.md5(key.encode()).hexdigest()


def deduplicate(listings: list) -> list:
    groups = {}
    for l in listings:
        fp = listing_fingerprint(l)
        groups.setdefault(fp, []).append(l)

    merged = []
    for fp, group in groups.items():
        if len(group) == 1:
            merged.append(group[0])
        else:
            primary = group[0].copy()
            primary["sources"] = [{"source": g["source"], "url": g["url"],
                                   "source_id": g["source_id"]} for g in group]
            for g in group[1:]:
                if g.get("lat") and not primary.get("lat"):
                    primary["lat"], primary["lon"] = g["lat"], g["lon"]
                if g.get("surface_m2") and not primary.get("surface_m2"):
                    primary["surface_m2"] = g["surface_m2"]
                if g.get("bedrooms") and not primary.get("bedrooms"):
                    primary["bedrooms"] = g["bedrooms"]
            merged.append(primary)
    return merged


def main():
    print("=== Scraping Paris apartments (rent + buy) ===\n")

    all_listings = []
    for ttype in ("rent", "buy"):
        print(f"[{ttype}] Bien'ici...")
        lst = fetch_bienici_listings(transaction=ttype)
        print(f"  -> {len(lst)} listings\n")
        all_listings.extend(lst)
        time.sleep(2)

    print("Deduplicating...")
    merged = deduplicate(all_listings)
    print(f"  -> {len(merged)} unique ({len(all_listings) - len(merged)} duplicates merged)")

    kept = []
    for l in merged:
        lo, hi = PRICE_RANGE.get(l.get("transaction", "rent"), (0, 10**12))
        if l.get("price") and lo <= l["price"] <= hi:
            kept.append(l)
    print(f"  -> price filter: dropped {len(merged) - len(kept)} outliers")

    with_coords = sum(1 for l in kept if l.get("lat"))
    per_type = {}
    for ttype in ("rent", "buy"):
        prices = [l["price"] for l in kept if l.get("transaction") == ttype and l.get("price")]
        per_type[ttype] = {
            "count": len(prices),
            "avg_price": round(sum(prices) / len(prices)) if prices else 0,
            "min_price": min(prices) if prices else None,
            "max_price": max(prices) if prices else None,
        }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sources": ["bienici.com"],
        "note": ("SeLoger changed URL structure and blocks scrapers; dropped. "
                 "Jinka has no public API; skipped."),
        "count": len(kept),
        "stats": {"with_coordinates": with_coords, "per_transaction": per_type},
        "listings": kept,
    }, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    print(f"\nWrote {OUT}: {len(kept)} listings, {with_coords} with coords")
    for ttype, s in per_type.items():
        print(f"  {ttype}: {s['count']} listings, "
              f"price {s['min_price']} - {s['max_price']} (avg {s['avg_price']})")


if __name__ == "__main__":
    main()