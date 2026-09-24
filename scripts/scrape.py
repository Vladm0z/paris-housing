#!/usr/bin/env python3
"""Scrape CROUS Paris restaurants/cafeterias from the official open-data API,
   and enrich with daily menus from the CROUStillant API."""
import json, re, time, urllib.parse, urllib.request, unicodedata
from datetime import datetime, timezone, date, timedelta
from pathlib import Path

API = ("https://mesr.opendatasoft.com/api/explore/v2.1/catalog/datasets/"
       "fr_crous_restauration_france_entiere/records")
WHERE = 'zone like "Paris*"'
OUT = Path(__file__).resolve().parents[1] / "data" / "paris.json"

DAYS = {"lundi": 0, "mardi": 1, "mercredi": 2, "jeudi": 3,
        "vendredi": 4, "samedi": 5, "dimanche": 6}
DA = "|".join(DAYS)

RANGE_RE   = re.compile(rf"\b(?:du\s+|des\s+)?(?P<a>{DA})s?\s+au(?:x)?\s+(?P<b>{DA})s?\b", re.I)
SINGLE_RE  = re.compile(rf"\b(?:le\s+|les\s+)?(?P<d>{DA})s?\b", re.I)
ALLDAYS_RE = re.compile(r"\b(?:tous\s+les\s+jours|chaque\s+jour|7\s*j/7|7\s+jours\s+sur\s+7)\b", re.I)
TIME_RE = re.compile(r"\b(\d{1,2})\s*(?:[hH:](\d{2})|h)?\s*(?:à|-|–|—)\s*(\d{1,2})\s*(?:[hH:](\d{2})|h)?\b")
SEP_RE  = re.compile(r"\s*(?:,\s*)?(?:et|&)\s*")
COND_RE = re.compile(r"selon\s+le\s+calendrier|susceptibles?\s+d['’][ée]tre\s+ouverts?", re.I)

def fetch_records():
    recs, offset = [], 0
    while True:
        q = urllib.parse.urlencode({"where": WHERE, "limit": 100, "offset": offset})
        req = urllib.request.Request(f"{API}?{q}", headers={"User-Agent": "resto-u-map/1.0"})
        with urllib.request.urlopen(req, timeout=60) as r:
            payload = json.load(r)
        batch = payload.get("results", [])
        recs.extend(batch)
        total = payload.get("total_count", 0)
        offset += len(batch)
        if not batch or offset >= total:
            if not recs:
                raise SystemExit(f"ERROR: 0 records for where={WHERE!r} - dataset renamed?")
            return recs

def normalize(name):
    return re.sub(r"[^a-z0-9]", "", name.lower())

def slugify(name):
    """Generate CROUStillant-compatible slug from restaurant name."""
    if not name: return ""
    n = ''.join(c for c in unicodedata.normalize('NFD', name.lower()) if unicodedata.category(c) != 'Mn')
    n = re.sub(r"[^a-z0-9\s]", "", n)
    n = re.sub(r"\s+", "-", n.strip())
    return n

def core_name(name):
    """Strips generic prefixes/suffixes to improve fuzzy matching"""
    if not name: return ""
    n = re.sub(r"[^a-z0-9\s]", " ", name.lower())
    n = re.sub(r"\b(ru|cafeteria|restaurant|libre service|administratif|brasserie|self|sandwicherie|de|la|le|les|l|du|d)\b", " ", n)
    return re.sub(r"\s+", " ", n).strip()

def get_type_kw(name, type_str=""):
    """Extracts a type keyword to disambiguate e.g. RU Nation vs Admin Nation"""
    n = (name + " " + type_str).lower()
    if "administratif" in n: return "admin"
    if "libre" in n: return "libre"
    if "cafet" in n or "cafétéria" in n: return "cafet"
    if "brasserie" in n: return "brasserie"
    if "restaurant" in n or "ru " in n or n.startswith("ru"): return "resto"
    return "other"

def fetch_croustillant_data():
    """Fetches Paris restaurants and the next 7 days of menus from CROUStillant API."""
    region_code = 22 
    url = f"https://api.croustillant.menu/v1/regions/{region_code}/restaurants"
    req = urllib.request.Request(url, headers={"User-Agent": "RestoU-Paris-Map/1.0 (university project)"})

    restaurants = []
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            payload = json.loads(r.read().decode('utf-8'))
            if payload.get("success"):
                restaurants = payload.get("data", [])
    except Exception as e:
        print(f"Warning: Could not fetch CROUStillant restaurants: {e}")
        return {}

    today = date.today()
    max_date = today + timedelta(days=6)
    result = {}

    for rest in restaurants:
        code = rest.get("code")
        nom = rest.get("nom") or ""
        norm_name = normalize(nom)
        

        menus = []
        if code:
            menu_url = f"https://api.croustillant.menu/v1/restaurants/{code}/menu"
            try:
                mreq = urllib.request.Request(menu_url, headers={"User-Agent": "RestoU-Paris-Map/1.0 (university project)"})
                with urllib.request.urlopen(mreq, timeout=10) as mr:
                    data = json.loads(mr.read().decode('utf-8'))
                    if data.get("success") and data.get("data"):
                        for entry in data["data"]:
                            try:
                                entry_date = datetime.strptime(entry.get("date", ""), "%d-%m-%Y").date()
                            except (ValueError, TypeError):
                                continue
                            if entry_date < today or entry_date > max_date:
                                continue

                            repas_clean = []
                            for repas in entry.get("repas", []):
                                cats_clean = []
                                for cat in repas.get("categories", []):
                                    plats_clean = [
                                        p["libelle"] for p in cat.get("plats", [])
                                        if p.get("libelle") and not re.search(r"menu non communiqu", p["libelle"], re.I)
                                    ]
                                    if plats_clean:
                                        cats_clean.append({"libelle": cat["libelle"], "plats": plats_clean})
                                if cats_clean:
                                    repas_clean.append({"type": repas.get("type", "midi"), "categories": cats_clean})
                            if repas_clean:
                                menus.append({"date": entry.get("date"), "repas": repas_clean})
            except Exception:
                pass
            time.sleep(0.15)

        result[norm_name] = {"code": code, "menus": menus, "original_name": nom, "slug": slugify(nom)}
    return result

def hours_section(infos: str) -> str:
    if not infos: return ""
    m = re.search(r"Horaires?\s*(.*?)(?=Moyen\s+d'acc[eè]s|\bPratique\b|\bPaiements\b|\bContact\b|\bTarifs\b|$)", infos, re.I | re.S)
    txt = m.group(1) if m else infos
    txt = re.sub(r"Attention[,.][^.\n]*évoluer\.?", "", txt, flags=re.I)
    return re.sub(r"\s+", " ", txt).strip()

def day_clauses(text):
    spans = []
    for m in ALLDAYS_RE.finditer(text): spans.append((m.start(), m.end(), list(range(7))))
    for m in RANGE_RE.finditer(text):
        a, b = DAYS[m.group("a").lower()], DAYS[m.group("b").lower()]
        days, d = [], a
        while True:
            days.append(d)
            if d == b: break
            d = (d + 1) % 7
        spans.append((m.start(), m.end(), days))
    taken = [(s, e) for s, e, _ in spans]
    for m in SINGLE_RE.finditer(text):
        if any(s <= m.start() < e for s, e in taken): continue
        spans.append((m.start(), m.end(), [DAYS[m.group("d").lower()]]))
    spans.sort(key=lambda t: t[0])
    merged = []
    for s, e, days in spans:
        if merged and (SEP_RE.fullmatch(text[merged[-1][1]:s]) or text[merged[-1][1]:s].strip() == ","):
            ps, _, pdays = merged[-1]
            merged[-1] = (ps, e, pdays + days)
        else: merged.append((s, e, days))
    return [(days, text[e:(merged[i + 1][0] if i + 1 < len(merged) else len(text))]) for i, (s, e, days) in enumerate(merged)]

def _merge(iv):
    out = []
    for o, c in iv:
        if out and o <= out[-1][1]: out[-1][1] = max(out[-1][1], c)
        else: out.append([o, c])
    return out

def parse_schedule(text):
    schedule = {d: [] for d in range(7)}
    found, had_days = False, False
    def add(chunk, days):
        nonlocal found
        for h1, m1, h2, m2 in TIME_RE.findall(chunk):
            o = int(h1) * 60 + int(m1 or 0)
            c = int(h2) * 60 + int(m2 or 0)
            if 0 <= o < 1440 and 0 < c <= 1440 and c > o:
                found = True
                for d in days: schedule[d].append([o, c])
    clauses = day_clauses(text)
    if clauses:
        had_days = True
        for days, chunk in clauses: add(chunk, days)
    else: add(text, list(range(5)))
    for d in schedule: schedule[d] = _merge(sorted(schedule[d]))
    conf = "parsed" if (had_days and found) else ("defaulted_days" if found else "unparsed")
    return {str(d): v for d, v in schedule.items() if v}, conf

def conditional_days(text: str):
    if not text or not COND_RE.search(text): return []
    days = set()
    for m in COND_RE.finditer(text):
        window = text[max(0, m.start() - 50):m.end() + 70].lower()
        for name, idx in DAYS.items():
            if re.search(rf"\b{name}s?\b", window): days.add(idx)
    return sorted(days) or [5]

ACCESS_RE = re.compile(r"(?:accessible|ouvert[e]?s?|r[ée]serv[ée]e?s?)\s+(?:[àa]\s+|au(?:x)?\s+)([^.\n]{3,150})", re.I)
ACCESS_SKIP_RE = re.compile(r"mobilit[ée]\s+r[ée]duite|handicap|pmr", re.I)
SPECIFIC_UNI_RE = re.compile(r"universit|campus|[ée]cole|institut|ensa|\bens\b|sorbonne|dauphine|assas|sciences\s*po|inalco|psl|condorcet", re.I)

def parse_access(infos, place_type="", place_name=""):
    phrases = []
    for m in ACCESS_RE.finditer(infos or ""):
        ph = m.group(1).strip()
        if ph and not ACCESS_SKIP_RE.search(ph): phrases.append(ph)
    phrases.sort(key=lambda p: (bool(re.search(r"[ée]tudiant|personnel", p, re.I)), len(p)), reverse=True)
    phrase = phrases[0] if phrases else ""
    if not phrase:
        if re.search(r"administratif", f"{place_type} {place_name}", re.I):
            return {"level": "staff", "note": "Restaurant administratif (staff restaurant)"}
        return {"level": "unknown", "note": ""}
    pl = phrase.lower()
    has_students      = bool(re.search(r"[ée]tudiant", pl))
    has_all_higher_ed = bool(re.search(r"tout[e]?s?\s+[ée]tudiant|enseignement\s+sup[ée]rieur", pl))
    has_specific_uni  = bool(SPECIFIC_UNI_RE.search(pl))
    has_only_staff    = bool(re.search(r"personnel", pl)) and not has_students
    if has_only_staff: return {"level": "staff", "note": phrase}
    if has_students and has_all_higher_ed and not has_specific_uni: return {"level": "all", "note": phrase}
    if has_students and has_specific_uni: return {"level": "restricted", "note": phrase}
    if has_students: return {"level": "restricted", "note": phrase + " (implied campus restriction)"}
    return {"level": "restricted", "note": phrase}

CLOSURE_OK_RE  = re.compile(r"\bferm[ée]e?\b|\bfermeture\b|travaux|r[ée]novation", re.I)
CLOSURE_SKIP_RE = re.compile(rf"ferm[ée]e?\s+(?:le\s+|les\s+)?(?:{DA}|jours?\s+f[ée]ri[ée]s)", re.I)

def closure_notice(*texts):
    for t in texts:
        if not t: continue
        for sent in re.split(r"(?<=[.!?])\s+", t):
            if CLOSURE_OK_RE.search(sent) and not CLOSURE_SKIP_RE.search(sent) \
               and not re.search(r"r[ée]ouvert", sent, re.I):
                return re.sub(r"\s+", " ", sent).strip()
    return None

def clean_address(rec):
    c = rec.get("contact") or ""
    c = re.sub(r"(T[eé]l[eé]phone|T[eé]l\.?|E-?mail).*$", "", c, flags=re.I | re.S)
    name = rec.get("title") or ""
    if c.lower().startswith(name.lower()): c = c[len(name):]
    addr = re.sub(r"\s+", " ", c).strip(" ,")
    if len(addr) < 8: addr = f"{rec.get('zone') or 'Paris'} - adresse non renseignée"
    return addr

def main():
    print("Fetching CROUStillant data (restaurants + upcoming menus)...")
    croustillant_data = fetch_croustillant_data()
    if croustillant_data:
        print(f"Found {len(croustillant_data)} Paris venues in CROUStillant API.")

    places, stale = [], []
    for r in fetch_records():
        geo = r.get("geolocalisation") or {}
        lat, lon = geo.get("lat") or r.get("lat"), geo.get("lon")
        if lat is None or lon is None: continue
        infos = r.get("infos") or ""
        desc  = r.get("short_desc") or ""
        hrs = hours_section(infos)
        sched, conf = parse_schedule(hrs)
        notice = closure_notice(desc, infos)
        flag = bool(r.get("closing"))
        if flag and notice: closure_status = "confirmed"
        elif notice: closure_status = "notice_only"
        else:
            if flag: stale.append(r.get("title"))
            closure_status = None
            
        venue_name = r.get("title", "")
        venue_type = r.get("type", "")
        norm_venue = normalize(venue_name)
        venue_core = core_name(venue_name)
        venue_tkw = get_type_kw(venue_name, venue_type)
        
        matched_crous = None
        best_score = -1
        
        # Score-based matching to prevent e.g. RU Nation matching Admin Nation
        for crous_norm, crous_data in croustillant_data.items():
            crous_orig = crous_data["original_name"]
            crous_core = core_name(crous_orig)
            crous_tkw = get_type_kw(crous_orig)
            
            score = -1
            if norm_venue and norm_venue == crous_norm:
                score = 100
            elif venue_core and crous_core and (venue_core == crous_core or venue_core in crous_core or crous_core in venue_core):
                score = 50
                if venue_tkw == crous_tkw: score += 20
                score += 10 * (min(len(venue_core), len(crous_core)) / max(len(venue_core), len(crous_core)))
            elif crous_norm in norm_venue or norm_venue in crous_norm:
                score = 10
                
            if score > best_score:
                best_score = score
                matched_crous = crous_data

        menus = matched_crous["menus"] if matched_crous else []
        croustillant_code = matched_crous["code"] if matched_crous else None
        croustillant_slug = matched_crous["slug"] if matched_crous else None # Add this line

        places.append({
            "id": r.get("id"), "name": venue_name, "type": venue_type,
            "zone": r.get("zone"), "address": clean_address(r),
            "lat": lat, "lon": lon,
            "description": desc or None,
            "hours_raw": hrs,
            "schedule": sched, "schedule_confidence": conf,
            "conditional_days": conditional_days(hrs),
            "access": parse_access(infos, venue_type, venue_name),
            "closure_status": closure_status,
            "closure_notice": notice,
            "closing_flag_raw": flag,
            "photo": r.get("photo"),
            "menus": menus,
            "croustillant_code": croustillant_code,
            "croustillant_slug": croustillant_slug,
        })
        
    # Deduplicate menus
    unique_menus = []
    menu_index = {}
    for p in places:
        refs = []
        for menu in p.get("menus", []):
            canonical = json.dumps(menu["repas"], ensure_ascii=False, sort_keys=True)
            idx = menu_index.get(canonical)
            if idx is None:
                idx = len(unique_menus)
                menu_index[canonical] = idx
                unique_menus.append(menu["repas"])
            refs.append({"date": menu["date"], "m": idx})
        p["menu_refs"] = refs
        p.pop("menus", None)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": API, "license": "Licence Ouverte / Etalab",
        "count": len(places),
        "menus": unique_menus,
        "places": places,
    }, ensure_ascii=False, separators=(',', ':')), encoding="utf-8")
    
    unp = sum(1 for p in places if p["schedule_confidence"] == "unparsed")
    cond = sum(1 for p in places if p["conditional_days"])
    confirmed = sum(1 for p in places if p["closure_status"] == "confirmed")
    with_menus = sum(1 for p in places if p.get("menu_refs"))
    
    print(f"\nwrote {OUT}: {len(places)} places ({len(places) - unp} parsed, {unp} unparsed, "
          f"{cond} conditional, {with_menus} with menus, {len(unique_menus)} unique menus)")
    print(f"closures: {confirmed} confirmed, {len(stale)} stale flags ignored: {stale}")

    # Diagnostic for unmatched venues
    unmatched = [p["name"] for p in places if not p.get("croustillant_code")]
    if unmatched:
        print(f"\n  Note: {len(unmatched)} venues have no CROUStillant match (likely closed or no daily menu):")
        for n in unmatched[:15]:
            print(f"    - {n}")

if __name__ == "__main__":
    main()