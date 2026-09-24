#!/usr/bin/env python3
"""Fetch Paris daily-life amenities from OpenStreetMap Overpass API.

Uses a 3x3 grid with separate lightweight queries per category.
Sequential execution with smart retry for 429s and timeouts.

Output: data/amenities.json
"""

import json, time, urllib.parse, urllib.request, urllib.error, sys
from datetime import datetime, timezone
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "data" / "amenities.json"

OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.osm.ch/api/interpreter",
]

# Paris bounds
S, W, N, E = 48.8155, 2.2241, 48.9021, 2.4699

def make_grid(rows=3, cols=3):
    cells = []
    dlat = (N - S) / rows
    dlon = (E - W) / cols
    for r in range(rows):
        for c in range(cols):
            s = S + r * dlat
            n = s + dlat
            w = W + c * dlon
            e = w + dlon
            cells.append(f"{s:.4f},{w:.4f},{n:.4f},{e:.4f}")
    return cells

GRID = make_grid(3, 3)

# Separate lightweight queries per category (proven to work)
QUERY_TEMPLATES = {
    "grocery":        '[out:json][timeout:45];(node["shop"~"supermarket|convenience|grocery"]({bbox}););out body;',
    "bakery":         '[out:json][timeout:45];(node["shop"="bakery"]({bbox}););out body;',
    "food_other":     '[out:json][timeout:45];(node["shop"~"butcher|cheese|greengrocer|seafood"]({bbox}););out body;',
    "organic":        '[out:json][timeout:45];(node["shop"~"organic|health_food"]({bbox});node["diet:vegan"="yes"]["shop"]({bbox}););out body;',
    "pharmacy":       '[out:json][timeout:45];(node["amenity"="pharmacy"]({bbox}););out body;',
    "laundry":        '[out:json][timeout:30];(node["shop"="laundry"]({bbox}););out body;',
    "grocery_ways":   '[out:json][timeout:60];(way["shop"~"supermarket|convenience"]({bbox}););out center body;',
    "pharmacy_ways":  '[out:json][timeout:60];(way["amenity"="pharmacy"]({bbox}););out center body;',
    "bakery_ways":    '[out:json][timeout:60];(way["shop"="bakery"]({bbox}););out center body;',
}

BRAND_SIZE = {
    "auchan": "hypermarket", "geant": "hypermarket",
    "carrefour": "supermarket", "monoprix": "supermarket",
    "casino": "supermarket", "intermarche": "supermarket",
    "u express": "supermarket", "super u": "supermarket",
    "lidl": "discount", "aldi": "discount", "netto": "discount",
    "carrefour city": "convenience", "carrefour express": "convenience",
    "carrefour contact": "convenience", "franprix": "convenience",
    "g20": "convenience", "coccinelle": "convenience",
    "monop'": "convenience", "petit casino": "convenience",
    "spar": "convenience", "vival": "convenience", "proxi": "convenience",
    "biocoop": "organic", "naturalia": "organic",
    "bio c' bon": "organic", "la vie claire": "organic",
    "day by day": "zero_waste",
}

CATEGORY_LABELS = {
    "hypermarket": "Hypermarket", "supermarket": "Supermarket",
    "convenience": "Convenience store", "discount": "Discount supermarket",
    "organic": "Organic store", "zero_waste": "Zero-waste store",
    "bakery": "Bakery", "butcher": "Butcher", "cheese": "Cheese shop",
    "greengrocer": "Greengrocer", "seafood": "Fish shop",
    "health_food": "Health food", "pharmacy": "Pharmacy",
    "laundry": "Laundromat",
}

SKIP_SHOPS = {"vacant", "hairdresser", "books", "wine", "alcohol",
              "tobacco", "florist", "clothes", "shoes", "jewelry",
              "furniture", "electronics", "hardware", "doityourself",
              "beauty", "optician", "pet", "gift", "stationery",
              "travel_agency", "mobile_phone", "car", "car_repair"}


def overpass_request(query: str):
    """Send one Overpass query. Handles 429 with backoff, skips dead endpoints."""
    data = urllib.parse.urlencode({"data": query}).encode()

    for endpoint in OVERPASS_ENDPOINTS:
        ep_name = endpoint.split('/')[2]

        for attempt in range(3):
            try:
                req = urllib.request.Request(endpoint, data=data, headers={
                    "User-Agent": "StudentParisMap/1.0 (educational; OSM ODbL)",
                    "Content-Type": "application/x-www-form-urlencoded",
                })
                with urllib.request.urlopen(req, timeout=70) as r:
                    payload = json.loads(r.read().decode())

                if "remark" in payload:
                    wait = 20 + attempt * 15
                    print(f"\n    [!] Remark on {ep_name}: {payload['remark'][:60]}... waiting {wait}s")
                    time.sleep(wait)
                    continue

                if "elements" in payload:
                    return payload["elements"], None, endpoint

            except urllib.error.HTTPError as e:
                if e.code == 429:
                    wait = 30 + attempt * 20
                    print(f"\n    [x] 429 on {ep_name} (attempt {attempt+1}). Waiting {wait}s...")
                    time.sleep(wait)
                    continue
                else:
                    break  # try next endpoint

            except Exception as e:
                err_msg = str(e)
                if "10060" in err_msg or "timed out" in err_msg.lower():
                    break  # dead endpoint, try next
                else:
                    break

    return [], "All endpoints failed", None


def classify_shop(tags: dict):
    shop = tags.get("shop", "")
    amenity = tags.get("amenity", "")

    if ";" in shop:
        shop = shop.split(";")[0]

    name = (tags.get("name") or tags.get("brand") or "").lower()

    if shop in SKIP_SHOPS:
        return None

    if amenity == "pharmacy":
        cat = "pharmacy"
    elif shop == "laundry":
        cat = "laundry"
    elif shop == "bakery":
        cat = "bakery"
    elif shop == "butcher":
        cat = "butcher"
    elif shop == "cheese":
        cat = "cheese"
    elif shop == "greengrocer":
        cat = "greengrocer"
    elif shop == "seafood":
        cat = "seafood"
    elif shop in ("organic", "health_food"):
        cat = "organic"
    elif shop in ("supermarket", "convenience", "grocery"):
        cat = "convenience"
        for brand, size in BRAND_SIZE.items():
            if brand in name:
                cat = size
                break
        if shop == "supermarket" and cat == "convenience":
            cat = "supermarket"
    else:
        cat = shop or "other"

    return {
        "category": cat,
        "category_label": CATEGORY_LABELS.get(cat, cat.title()),
        "vegan_friendly": tags.get("diet:vegan") == "yes",
        "vegetarian_friendly": tags.get("diet:vegetarian") == "yes",
        "organic": tags.get("organic") in ("yes", "only") or shop == "organic",
    }


def parse_element(el: dict):
    tags = el.get("tags", {})
    if not tags:
        return None
    lat = el.get("lat") or (el.get("center") or {}).get("lat")
    lon = el.get("lon") or (el.get("center") or {}).get("lon")
    if lat is None or lon is None:
        return None

    info = classify_shop(tags)
    if info is None:
        return None

    name = tags.get("name") or tags.get("brand") or info["category_label"]

    return {
        "id": f"osm-{el['type']}/{el['id']}",
        "name": name,
        "brand": tags.get("brand", ""),
        "lat": lat, "lon": lon,
        "category": info["category"],
        "category_label": info["category_label"],
        "vegan_friendly": info["vegan_friendly"],
        "vegetarian_friendly": info["vegetarian_friendly"],
        "organic": info["organic"],
        "address": ", ".join(filter(None, [
            tags.get("addr:housenumber", ""), tags.get("addr:street", "")])),
        "opening_hours": tags.get("opening_hours", ""),
        "phone": tags.get("phone", tags.get("contact:phone", "")),
        "website": tags.get("website", tags.get("contact:website", "")),
        "wheelchair": tags.get("wheelchair", ""),
    }


def main():
    total_queries = len(GRID) * len(QUERY_TEMPLATES)
    print("=== Fetching Paris amenities from OpenStreetMap ===\n")
    print(f"Grid: {len(GRID)} cells x {len(QUERY_TEMPLATES)} query types = {total_queries} queries")
    print("Sequential execution with smart retry...\n")

    all_elements = []
    errors = 0
    done = 0

    results_by_query = {q: [] for q in QUERY_TEMPLATES}

    for qname, template in QUERY_TEMPLATES.items():
        row = ""
        for ci, bbox in enumerate(GRID):
            done += 1
            query = template.replace("{bbox}", bbox)
            elements, err, _ = overpass_request(query)

            results_by_query[qname].append((ci, len(elements), err))

            if err:
                errors += 1
                row += " E"
            elif not elements:
                row += " ."
            else:
                all_elements.extend(elements)
                row += f" +{len(elements)}"

            sys.stdout.write(f"\r  [{done}/{total_queries}] {qname}: {row}   ")
            sys.stdout.flush()

            time.sleep(1.0)  # 1s between requests

        print()  # newline after each query type

    print(f"\n  Done: {len(all_elements)} raw elements, {errors} errors")

    # Print results grid
    print("\nResults by category (. = empty, E = error, +N = found):")
    for qname, results in results_by_query.items():
        results.sort(key=lambda x: x[0])
        line = f"  {qname:16s}"
        for ci, count, err in results:
            if err:
                line += " E"
            elif count == 0:
                line += " ."
            else:
                line += f" +{count}"
        print(line)

    # Deduplicate by OSM id
    seen = set()
    amenities = []
    for el in all_elements:
        parsed = parse_element(el)
        if parsed and parsed["id"] not in seen:
            seen.add(parsed["id"])
            amenities.append(parsed)

    cats = {}
    for a in amenities:
        cats[a["category"]] = cats.get(a["category"], 0) + 1

    print(f"\nTotal: {len(amenities)} unique amenities (after filtering)")
    print("\nBy category:")
    for c, n in sorted(cats.items(), key=lambda x: -x[1]):
        print(f"  {CATEGORY_LABELS.get(c, c):25s} {n:5d}")

    vegan_count = sum(1 for a in amenities if a["vegan_friendly"])
    organic_count = sum(1 for a in amenities if a["organic"])
    print(f"\n  Vegan-friendly: {vegan_count}, Organic: {organic_count}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": "OpenStreetMap contributors (ODbL)",
        "count": len(amenities),
        "category_counts": cats,
        "amenities": amenities,
    }, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    print(f"\nWrote {OUT}: {len(amenities)} amenities")


if __name__ == "__main__":
    main()