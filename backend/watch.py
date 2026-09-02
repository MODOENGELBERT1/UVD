"""
Ubuntu Disaster Viewer — couche de veille (monitoring des evenements)

Agrege des sources d'alerte publiques pour lister TOUS les evenements
(pas seulement ceux que Vantor active) :
  - GDACS  : flux mondial automatique (seismes, inondations, cyclones...), sans cle.
  - ReliefWeb (OCHA) : rapports d'evenements, filtrables par pays.

Schema normalise : {source, id, type, title, level, country, date, lat, lon, bbox, url}
Les fonctions parse_* sont pures (testables sans reseau). URLs/champs configurables par env.
"""
import os
import httpx

GDACS_URL = os.getenv("GDACS_URL", "https://www.gdacs.org/gdacsapi/api/events/geteventlist/EVENTS4APP")
RELIEFWEB_URL = os.getenv("RELIEFWEB_URL", "https://api.reliefweb.int/v1/disasters")
RELIEFWEB_APPNAME = os.getenv("RELIEFWEB_APPNAME", "ubuntu-disaster-viewer")

TYPE_FR = {"EQ": "Séisme", "FL": "Inondation", "TC": "Cyclone", "DR": "Sécheresse",
           "VO": "Volcan", "WF": "Incendie", "TS": "Tsunami", "LS": "Glissement de terrain"}

REGION_CENTRAL_AFRICA = ["Cameroon", "Chad", "Central African Republic", "Gabon",
                         "Congo", "Democratic Republic of the Congo",
                         "Equatorial Guinea", "Nigeria"]


def _bbox_from_point(lon, lat, pad=0.15):
    if lon is None or lat is None:
        return None
    return [round(lon - pad, 4), round(lat - pad, 4), round(lon + pad, 4), round(lat + pad, 4)]


def parse_gdacs(data, country=None):
    feats = data.get("features", data if isinstance(data, list) else [])
    out = []
    for f in feats:
        p = f.get("properties", f) or {}
        geom = f.get("geometry") or {}
        coords = geom.get("coordinates")
        if isinstance(coords, list) and len(coords) >= 2:
            lon, lat = coords[0], coords[1]
        else:
            lon, lat = p.get("longitude"), p.get("latitude")
        url = p.get("url")
        if isinstance(url, dict):
            url = url.get("report") or url.get("details")
        out.append({
            "source": "GDACS",
            "id": f"gdacs-{p.get('eventid', p.get('eventname', ''))}",
            "type": TYPE_FR.get(p.get("eventtype"), p.get("eventtype")),
            "title": p.get("name") or p.get("eventname") or (p.get("description") or "")[:90],
            "level": p.get("alertlevel"),
            "country": p.get("country") or "",
            "date": (p.get("fromdate") or p.get("todate") or "")[:10],
            "lat": lat, "lon": lon,
            "bbox": p.get("bbox") or _bbox_from_point(lon, lat),
            "url": url,
        })
    if country:
        out = [e for e in out if country.lower() in (e["country"] or "").lower()]
    return out


def fetch_gdacs(country=None, timeout=30):
    with httpx.Client(timeout=timeout, follow_redirects=True) as c:
        r = c.get(GDACS_URL)
    r.raise_for_status()
    return parse_gdacs(r.json(), country=country)


def parse_reliefweb(data):
    out = []
    for d in data.get("data", []):
        fld = d.get("fields", {}) or {}
        pc = fld.get("primary_country") or {}
        country = pc.get("name") or (fld.get("country", [{}])[0].get("name") if fld.get("country") else "")
        types = fld.get("type", [])
        date = (fld.get("date", {}) or {}).get("created") or (fld.get("date", {}) or {}).get("event") or ""
        loc = pc.get("location", {}) or {}
        out.append({
            "source": "ReliefWeb",
            "id": f"rw-{d.get('id')}",
            "type": (types[0].get("name") if types else None),
            "title": fld.get("name"),
            "level": fld.get("status"),
            "country": country,
            "date": date[:10],
            "lat": loc.get("lat"), "lon": loc.get("lon"),
            "bbox": _bbox_from_point(loc.get("lon"), loc.get("lat")),
            "url": fld.get("url_alias") or d.get("href"),
        })
    return out


def fetch_reliefweb(country="Cameroon", limit=25, timeout=30):
    body = {
        "filter": {"field": "country", "value": country},
        "fields": {"include": ["name", "date", "status", "type", "primary_country", "country", "url_alias"]},
        "sort": ["date:desc"],
        "limit": limit,
    }
    with httpx.Client(timeout=timeout, follow_redirects=True) as c:
        r = c.post(f"{RELIEFWEB_URL}?appname={RELIEFWEB_APPNAME}", json=body)
    r.raise_for_status()
    return parse_reliefweb(r.json())


def _key(e):
    return ((e.get("country") or "").lower().strip(),
            (e.get("type") or "").lower().strip(),
            (e.get("date") or "")[:7])


def merge_events(gdacs_list, reliefweb_list):
    merged = {}
    for e in gdacs_list + reliefweb_list:
        k = _key(e)
        if k not in merged:
            e = dict(e); e["sources"] = [e["source"]]
            merged[k] = e
        else:
            m = merged[k]
            if e["source"] not in m["sources"]:
                m["sources"].append(e["source"])
            if not m.get("bbox") and e.get("bbox"):
                m["bbox"] = e["bbox"]
            if not m.get("url") and e.get("url"):
                m["url"] = e["url"]
    events = list(merged.values())
    events.sort(key=lambda e: e.get("date") or "", reverse=True)
    return events


def watch(country="Cameroon", region=False):
    countries = REGION_CENTRAL_AFRICA if region else [country]
    g, rw, errors = [], [], {}
    try:
        allg = fetch_gdacs()
        g = [e for e in allg if any(c.lower() in (e["country"] or "").lower() for c in countries)]
    except Exception as ex:
        errors["gdacs"] = str(ex)
    for c in countries:
        try:
            rw += fetch_reliefweb(country=c)
        except Exception as ex:
            errors["reliefweb"] = str(ex)
            break
    return {"events": merge_events(g, rw), "errors": errors,
            "scope": countries, "counts": {"gdacs": len(g), "reliefweb": len(rw)}}


# ---------- persistance & polling (pour le loop de veille en tache de fond) ----------
import json
import threading


class Store:
    """Cache persistant simple (fichier JSON) des evenements detectes."""
    def __init__(self, path="watch_store.json"):
        self.path = path
        self._lock = threading.Lock()
        self.events = {}
        try:
            if os.path.exists(path):
                with open(path) as f:
                    for e in json.load(f):
                        self.events[e["id"]] = e
        except Exception:
            pass

    def _save(self):
        try:
            with open(self.path, "w") as f:
                json.dump(list(self.events.values()), f)
        except Exception:
            pass

    def add(self, evs):
        new = []
        with self._lock:
            for e in evs:
                if e.get("id") and e["id"] not in self.events:
                    self.events[e["id"]] = e
                    new.append(e)
            if new:
                self._save()
        return new

    def all(self, country=None, limit=200):
        evs = list(self.events.values())
        if country:
            evs = [e for e in evs if country.lower() in (e.get("country") or "").lower()]
        evs.sort(key=lambda e: e.get("date") or "", reverse=True)
        return evs[:limit]


def poll(store, country=None, region=None):
    """Interroge les flux et ajoute les nouveaux evenements au store. Retourne les nouveaux."""
    country = country or os.getenv("WATCH_COUNTRY", "Cameroon")
    if region is None:
        region = os.getenv("WATCH_REGION", "true").lower() == "true"
    res = watch(country=country, region=region)
    return store.add(res.get("events", []))
