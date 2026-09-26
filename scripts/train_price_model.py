#!/usr/bin/env python3
"""Train price prediction models on scraped Paris apartment listings.

One HistGradientBoostingRegressor per transaction type (rent / buy), since
the price scales differ by two orders of magnitude. Features: surface, rooms,
bedrooms, postal_code, district, DPE energy + climate classes, furnished,
and regex keyword features from title/description.

Enriches data/apartments.json with predicted_price and deal_score.
"""
import json
import math
import re
from pathlib import Path

import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.model_selection import KFold
from sklearn.preprocessing import OrdinalEncoder
from sklearn.inspection import permutation_importance

DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "apartments.json"

DPE_ORDER = ["A", "B", "C", "D", "E", "F", "G"]
GES_ORDER = ["A", "B", "C", "D", "E", "F", "G"]
TRANSACTIONS = ("rent", "buy")
PRICE_RANGE = {"rent": (100, 15000), "buy": (20000, 5000000)}

KEYWORD_PATTERNS = [
    (r"balcon|terrasse|jardin|cour", "outdoor"),
    (r"ascenseur", "elevator"),
    (r"gardien|concierge|digicode", "security"),
    (r"m[éèe]tro|rer|gare|bus", "transport"),
    (r"r[éèe]nov|neuf|refait|modernis", "renovated"),
    (r"lumineux|vue|etage|dernier", "bright_view"),
    (r"cave|parking|garage|box", "storage_parking"),
    (r"calme|silencieux", "quiet"),
]


def extract_text_features(title, desc):
    text = ((title or "") + " " + (desc or "")).lower()
    return [1 if re.search(p, text, re.IGNORECASE) else 0 for p, _ in KEYWORD_PATTERNS]


def load_data():
    raw = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    listings = raw.get("listings", [])
    print(f"Loaded {len(listings)} listings from {DATA_PATH.name}")
    return raw, listings


def is_valid_for_training(l, ttype):
    price = l.get("price")
    surface = l.get("surface_m2")
    rooms = l.get("rooms")
    postal = l.get("postal_code", "")
    if not all([price, surface, rooms, postal]):
        return False
    lo, hi = PRICE_RANGE[ttype]
    if not (lo <= price <= hi):
        return False
    if not (8 <= surface <= 200):
        return False
    if not (1 <= rooms <= 8):
        return False
    return True


def build_features(listings, ttype):
    valid = [l for l in listings if is_valid_for_training(l, ttype)]
    print(f"  {len(valid)} listings have complete data for training "
          f"({len(listings) - len(valid)} skipped)")

    X_num = np.array([
        [l["surface_m2"],
         l["rooms"],
         l.get("bedrooms") or 0,
         1 if l.get("furnished") else 0]
        for l in valid
    ], dtype=np.float32)

    price_per_room = np.array([
        l["surface_m2"] / max(l["rooms"], 1) for l in valid
    ], dtype=np.float32).reshape(-1, 1)

    postals = np.array([[l["postal_code"]] for l in valid])
    postal_enc = OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1)
    postal_X = postal_enc.fit_transform(postals).astype(np.float32)

    districts = np.array([[l.get("district") or ""] for l in valid])
    district_enc = OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1)
    district_X = district_enc.fit_transform(districts).astype(np.float32)

    dpe_values = np.array([[l.get("energy_class") or ""] for l in valid])
    dpe_enc = OrdinalEncoder(categories=[[""] + DPE_ORDER],
                              handle_unknown="use_encoded_value", unknown_value=-1)
    dpe_X = dpe_enc.fit_transform(dpe_values).astype(np.float32)

    ges_values = np.array([[l.get("climate_class") or ""] for l in valid])
    ges_enc = OrdinalEncoder(categories=[[""] + GES_ORDER],
                              handle_unknown="use_encoded_value", unknown_value=-1)
    ges_X = ges_enc.fit_transform(ges_values).astype(np.float32)

    text_feats = np.array([
        extract_text_features(l.get("title", ""), l.get("description", ""))
        for l in valid
    ], dtype=np.float32)

    X = np.hstack([X_num, price_per_room, postal_X, district_X, dpe_X, ges_X, text_feats])
    y = np.log(np.array([l["price"] for l in valid], dtype=np.float32))

    feature_names = [
        "surface_m2", "rooms", "bedrooms", "furnished", "surface_per_room",
        "postal_code", "district", "energy_class", "climate_class"
    ] + [name for _, name in KEYWORD_PATTERNS]

    return X, y, valid, feature_names, postal_enc, district_enc, dpe_enc, ges_enc


def train_and_evaluate(X, y, feature_names, ttype):
    model = HistGradientBoostingRegressor(
        max_iter=400, max_depth=6, learning_rate=0.05,
        min_samples_leaf=20, l2_regularization=0.1, random_state=42,
    )
    kf = KFold(n_splits=5, shuffle=True, random_state=42)
    maes, rmses = [], []

    print(f"\n[{ttype}] Cross-validation (5-fold):")
    for fold, (tr, va) in enumerate(kf.split(X), 1):
        model.fit(X[tr], y[tr])
        pred = np.exp(model.predict(X[va]))
        actual = np.exp(y[va])
        maes.append(np.mean(np.abs(pred - actual)))
        rmses.append(np.sqrt(np.mean((pred - actual) ** 2)))
        print(f"  fold {fold}: MAE={maes[-1]:.0f} EUR, RMSE={rmses[-1]:.0f} EUR")

    model.fit(X, y)
    print(f"[{ttype}] Mean CV MAE: {np.mean(maes):.0f} EUR, RMSE: {np.mean(rmses):.0f} EUR")

    perm = permutation_importance(model, X, y, n_repeats=10, random_state=42)
    top = sorted(zip(feature_names, perm.importances_mean), key=lambda x: -x[1])[:6]
    print(f"[{ttype}] Top features: " + ", ".join(f"{n}({i:.2f})" for n, i in top))
    return model


def predict_for_all(model, listings, postal_enc, district_enc, dpe_enc, ges_enc):
    predictions = []
    for l in listings:
        surface = l.get("surface_m2") or 30
        rooms = l.get("rooms") or 1
        bedrooms = l.get("bedrooms") or 0
        furnished = 1 if l.get("furnished") else 0
        surface_per_room = surface / max(rooms, 1)
        text_feats = extract_text_features(l.get("title", ""), l.get("description", ""))

        def enc(encoder, value):
            try:
                return float(encoder.transform([[value]])[0, 0])
            except Exception:
                return -1.0

        x = np.array([[surface, rooms, bedrooms, furnished, surface_per_room,
                       enc(postal_enc, l.get("postal_code", "")),
                       enc(district_enc, l.get("district", "")),
                       enc(dpe_enc, l.get("energy_class", "")),
                       enc(ges_enc, l.get("climate_class", ""))]
                      + text_feats], dtype=np.float32)
        pred_price = math.exp(float(model.predict(x)[0]))
        actual = l.get("price")
        deal_score = round(actual / pred_price, 2) if actual and pred_price > 0 else None
        predictions.append({"predicted_price": round(pred_price), "deal_score": deal_score})
    return predictions


def main():
    print("=== Training Paris price models (rent + buy) ===\n")
    raw, listings = load_data()

    models_meta = {}
    for ttype in TRANSACTIONS:
        subset = [l for l in listings if (l.get("transaction") or "rent") == ttype]
        print(f"\n--- {ttype}: {len(subset)} listings ---")
        if not subset:
            continue
        X, y, valid, feature_names, p_enc, d_enc, e_enc, g_enc = build_features(subset, ttype)
        if len(valid) < 50:
            print("  skipping (not enough training data)")
            continue

        model = train_and_evaluate(X, y, feature_names, ttype)
        preds = predict_for_all(model, subset, p_enc, d_enc, e_enc, g_enc)

        good = over = 0
        for l, p in zip(subset, preds):
            l["predicted_price"] = p["predicted_price"]
            if p["deal_score"] is not None:
                l["deal_score"] = p["deal_score"]
                if p["deal_score"] <= 0.9:
                    good += 1
                elif p["deal_score"] >= 1.1:
                    over += 1
        models_meta[ttype] = {
            "training_samples": len(valid),
            "features": feature_names,
            "stats": {"good_deals_below_90pct": good, "overvalued_above_110pct": over},
        }
        print(f"  enriched {len(subset)}; good deals {good}, overvalued {over}")

    raw["listings"] = listings
    raw["price_model"] = models_meta
    DATA_PATH.write_text(json.dumps(raw, ensure_ascii=False, separators=(",", ":")),
                         encoding="utf-8")
    print(f"\nWrote updated {DATA_PATH.name}")


if __name__ == "__main__":
    main()