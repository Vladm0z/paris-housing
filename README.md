# Student Paris Map

A static web map for students in Paris combining three data layers: live CROUS cafeteria status, rental apartment listings with price predictions, and daily amenities (supermarkets, pharmacies, bakeries). 

Status and pricing are computed client-side from data scraped from official open-data portals and public real estate APIs.

## Data sources

- **Cafeterias:** `fr_crous_restauration_france_entiere` (MESR Opendatasoft) for locations/hours, and the CROUStillant API for daily menus.
- **Apartments:** Bien'ici public JSON search API.
- **Amenities:** OpenStreetMap Overpass API.

## Repository layout

```text
.
├── .github/workflows/refresh-data.yml  # scheduled re-scrape (1st & 15th of month) + ML training
├── data/
│   ├── paris.json                      # CROUS venues and menus
│   ├── apartments.json                 # listings enriched with ML predictions
│   └── amenities.json                  # OSM shops and pharmacies
├── scripts/
│   ├── scrape.py                       # CROUS + CROUStillant scraper
│   ├── scrape_apartments.py            # Bien'ici scraper
│   ├── scrape_amenities.py             # OSM Overpass grid scraper
│   └── train_price_model.py            # scikit-learn price prediction pipeline
├── index.html                          # map page (Leaflet)
├── app.js                              # layers, viewport rendering, popups
├── style.css                           # layout, markers, mobile adjustments
└── README.md
```

## How it works

### Scrapers (`scripts/`)
1. **Cafeterias:** Fetches MESR records, parses French free-text opening hours into weekly minute-interval schedules, and matches them with CROUStillant menu data via fuzzy name matching.
2. **Apartments:** Paginates the Bien'ici JSON API.
3. **Amenities:** Splits the Paris bounding box into a 3x3 grid and queries Overpass sequentially with delays to avoid 504/429 timeouts on endpoints.

### ML Price Model (`scripts/train_price_model.py`)
Trains a `HistGradientBoostingRegressor` on `log(price)` to estimate market value.
- **Features:** Surface, rooms, bedrooms, furnished, postal code, district, DPE Energy class, DPE Climate (GES) class, and binary regex text features (e.g., `balcon`, `ascenseur`, `parking`, `rénové`).
- **Output:** Enriches `apartments.json` with `predicted_price` and a `deal_score` (actual / predicted).

### Map client (`app.js`)
- **Cafeterias:** Grouped by coordinate proximity. Pie-chart markers show open/closed status for multiple venues at the same spot.
- **Apartments:** Hidden below zoom level 13 to reduce clutter. Markers are colored on a green-yellow-red gradient based on the `deal_score`.
- **Amenities:** Minor categories (butchers, laundromats) are automatically hidden below zoom level 14.

## Configuration

Key constants can be adjusted directly in the source files:
- `app.js` -> `CONFIG`: Time thresholds, refresh interval, map center/zoom, and coordinate grouping precision.
- `app.js` -> `KEYWORD_PATTERNS` (inside `train_price_model.py`): Regex patterns for extracting real estate features from descriptions.
- `scripts/scrape_amenities.py` -> `GRID`: Adjust the grid size (e.g., 5x5) if Overpass timeouts occur.

## Attribution
- **Cafeterias:** MESR (Licence Ouverte / Etalab) & CROUStillant.
- **Apartments:** Bien'ici (public data).
- **Amenities:** OpenStreetMap contributors (ODbL).
- **Basemap:** OpenStreetMap contributors.
