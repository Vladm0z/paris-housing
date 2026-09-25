#!/usr/bin/env python3
"""Price prediction model on scraped Paris apartment listings"""

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

# Both DPE Energy and GES Climate use the A-G scale
DPE_ORDER = ["A", "B", "C", "D", "E", "F", "G"]
GES_ORDER = ["A", "B", "C", "D", "E", "F", "G"]

# High-value keywords in French real estate descriptions
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
    """Scan text for high-value real estate keywords"""
    text = ((title or "") + " " + (desc or "")).lower()
    feats = []
    for pattern, _ in KEYWORD_PATTERNS:
        feats.append(1 if re.search(pattern, text, re.IGNORECASE) else 0)
    return feats

def load_data():
    raw = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    listings = raw.get("listings", [])
    print(f"Loaded {len(listings)} listings from {DATA_PATH.name}")
    return raw, listings

def is_valid_for_training(l):
    """Only train on listings with complete data"""
    price = l.get("price")
    surface = l.get("surface_m2")
    rooms = l.get("rooms")
    postal = l.get("postal_code", "")
    if not all([price, surface, rooms, postal]):
        return False
    if not (100 <= price <= 15000):
        return False
    if not (8 <= surface <= 200):
        return False
    if not (1 <= rooms <= 8):
        return False
    return True

def build_features(listings):
    """Convert raw listings to a numpy feature matrix + target vector"""
    valid = [l for l in listings if is_valid_for_training(l)]
    print(f"  {len(valid)} listings have complete data for training "
          f"({len(listings) - len(valid)} skipped)")

    # Numeric features
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

    # postal code (arrondissement)
    postals = np.array([[l["postal_code"]] for l in valid])
    postal_enc = OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1)
    postal_X = postal_enc.fit_transform(postals).astype(np.float32)

    # district (neighborhood)
    districts = np.array([[l.get("district") or ""] for l in valid])
    district_enc = OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1)
    district_X = district_enc.fit_transform(districts).astype(np.float32)

    # DPE energy class
    dpe_values = np.array([[l.get("energy_class") or ""] for l in valid])
    dpe_enc = OrdinalEncoder(categories=[[""] + DPE_ORDER],
                              handle_unknown="use_encoded_value", unknown_value=-1)
    dpe_X = dpe_enc.fit_transform(dpe_values).astype(np.float32)

    # GES climate class
    ges_values = np.array([[l.get("climate_class") or ""] for l in valid])
    ges_enc = OrdinalEncoder(categories=[[""] + GES_ORDER],
                              handle_unknown="use_encoded_value", unknown_value=-1)
    ges_X = ges_enc.fit_transform(ges_values).astype(np.float32)

    # Text features (Regex keyword extraction)
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

def train_and_evaluate(X, y, feature_names):
    """Train with K-fold CV"""
    model = HistGradientBoostingRegressor(
        max_iter=400,
        max_depth=6,
        learning_rate=0.05,
        min_samples_leaf=20,
        l2_regularization=0.1,
        random_state=42,
    )

    kf = KFold(n_splits=5, shuffle=True, random_state=42)
    maes, rmses = [], []

    print("\nCross-validation (5-fold):")
    for fold, (train_idx, val_idx) in enumerate(kf.split(X), 1):
        model.fit(X[train_idx], y[train_idx])
        pred_log = model.predict(X[val_idx])
        pred = np.exp(pred_log)
        actual = np.exp(y[val_idx])
        mae = np.mean(np.abs(pred - actual))
        rmse = np.sqrt(np.mean((pred - actual) ** 2))
        maes.append(mae)
        rmses.append(rmse)
        print(f"  fold {fold}: MAE={mae:.0f} EUR, RMSE={rmse:.0f} EUR")

    model.fit(X, y)
    train_r2 = model.score(X, y)
    print(f"\nFinal model R² on training set: {train_r2:.3f}")
    print(f"Mean CV MAE: {np.mean(maes):.0f} EUR")
    print(f"Mean CV RMSE: {np.mean(rmses):.0f} EUR")

    print("\nFeature importance (permutation, higher = more predictive):")
    perm = permutation_importance(model, X, y, n_repeats=10, random_state=42)
    for name, imp in sorted(zip(feature_names, perm.importances_mean),
                             key=lambda x: -x[1]):
        print(f"  {name:20s} {imp:.3f}")

    return model

def predict_for_all(model, listings, postal_enc, district_enc, dpe_enc, ges_enc):
    """Predict price for every listing"""
    predictions = []
    
    for l in listings:
        surface = l.get("surface_m2") or 30
        rooms = l.get("rooms") or 1
        bedrooms = l.get("bedrooms") or 0
        furnished = 1 if l.get("furnished") else 0
        surface_per_room = surface / max(rooms, 1)
        
        # Text features
        text_feats = extract_text_features(l.get("title", ""), l.get("description", ""))
        
        postal = l.get("postal_code", "")
        district = l.get("district", "")
        dpe = l.get("energy_class", "")
        ges = l.get("climate_class", "")
        
        # Encode categoricals (fallback to -1 if unknown)
        try: p_ord = float(postal_enc.transform([[postal]])[0, 0])
        except: p_ord = -1
        try: d_ord = float(district_enc.transform([[district]])[0, 0])
        except: d_ord = -1
        try: dpe_ord = float(dpe_enc.transform([[dpe]])[0, 0])
        except: dpe_ord = -1
        try: ges_ord = float(ges_enc.transform([[ges]])[0, 0])
        except: ges_ord = -1

        x = np.array([[surface, rooms, bedrooms, furnished, surface_per_room,
                       p_ord, d_ord, dpe_ord, ges_ord] + text_feats], dtype=np.float32)
        
        pred_price = math.exp(float(model.predict(x)[0]))
        actual = l.get("price")

        deal_score = round(actual / pred_price, 2) if actual and pred_price > 0 else None

        predictions.append({
            "predicted_price": round(pred_price),
            "deal_score": deal_score,
        })

    return predictions

def main():
    print("=== Training Paris rental price model ===\n")

    raw, listings = load_data()
    X, y, valid_listings, feature_names, postal_enc, district_enc, dpe_enc, ges_enc = build_features(listings)

    if len(valid_listings) < 50:
        print("\nNot enough training data (< 50 listings). Skipping model.")
        return

    model = train_and_evaluate(X, y, feature_names)
    predictions = predict_for_all(model, listings, postal_enc, district_enc, dpe_enc, ges_enc)

    enriched = 0
    good_deals = 0
    overvalued = 0
    for l, p in zip(listings, predictions):
        l["predicted_price"] = p["predicted_price"]
        if p["deal_score"] is not None:
            l["deal_score"] = p["deal_score"]
            enriched += 1
            if p["deal_score"] <= 0.9:
                good_deals += 1
            elif p["deal_score"] >= 1.1:
                overvalued += 1

    raw["listings"] = listings
    raw["price_model"] = {
        "trained_at": raw.get("generated_at"),
        "training_samples": len(valid_listings),
        "features": feature_names,
        "stats": {
            "enriched_listings": enriched,
            "good_deals_below_90pct": good_deals,
            "overvalued_above_110pct": overvalued,
        },
    }

    DATA_PATH.write_text(json.dumps(raw, ensure_ascii=False, separators=(",", ":")),
                          encoding="utf-8")
    print(f"\nEnriched {enriched} listings with predicted_price")
    print(f"  Good deals (<=90% of predicted):  {good_deals}")
    print(f"  Overvalued (>=110% of predicted): {overvalued}")
    print(f"\nWrote updated {DATA_PATH.name}")

if __name__ == "__main__":
    main()