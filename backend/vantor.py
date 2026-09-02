"""
Ubuntu Disaster Viewer — resolveur d'evenements Vantor (ex-Maxar) Open Data

A partir d'un evenement + une zone (bbox), retrouve automatiquement les COG
"avant" et "apres" disponibles (URLs S3 pretes pour TiTiler), tries par
couverture nuageuse, en separant les prises pre- et post-evenement.

Source : miroir GeoJSON du catalogue (chaque tuile expose son URL 'visual' S3,
sa 'datetime' et son % de nuages). En production on peut aussi pointer sur le
STAC S3 ; le miroir donne les memes URLs S3 pour l'asset visual.
"""
import os
from datetime import datetime
import httpx

MIRROR = os.getenv(
    "VANTOR_MIRROR",
    "https://github.com/opengeos/maxar-open-data/raw/master/datasets",
)


def _parse_dt(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def _feat_bbox(f):
    xs, ys = [], []
    def walk(c):
        if isinstance(c[0], (int, float)):
            xs.append(c[0]); ys.append(c[1])
        else:
            for x in c:
                walk(x)
    walk(f["geometry"]["coordinates"])
    return min(xs), min(ys), max(xs), max(ys)


def _overlap(a, b):
    return not (a[2] < b[0] or a[0] > b[2] or a[3] < b[1] or a[1] > b[3])


def event_assets(event, bbox=None, event_date=None, limit=6, timeout=45):
    """Retourne les COG avant/apres d'un evenement Vantor pour la zone donnee."""
    url = f"{MIRROR}/{event}.geojson"
    with httpx.Client(timeout=timeout, follow_redirects=True) as c:
        r = c.get(url)
    if r.status_code != 200:
        return {"error": f"Evenement introuvable dans le catalogue : {event}", "status": r.status_code}
    feats = r.json().get("features", [])

    if bbox:
        feats = [f for f in feats if _overlap(_feat_bbox(f), bbox)]
    if not feats:
        return {"event": event, "before": [], "after": [], "counts": {"before": 0, "after": 0}}

    feats.sort(key=lambda f: f["properties"]["datetime"])

    # separation avant/apres
    if event_date:
        split = _parse_dt(event_date)
    else:
        # coupe au plus grand ecart temporel entre dates d'acquisition
        dates = sorted({f["properties"]["datetime"][:10] for f in feats})
        if len(dates) >= 2:
            gaps = [(( _parse_dt(dates[i + 1]) - _parse_dt(dates[i])).days, dates[i + 1])
                    for i in range(len(dates) - 1)]
            split = _parse_dt(max(gaps, key=lambda g: g[0])[1] + "T00:00:00Z")
        else:
            split = _parse_dt(dates[-1] + "T00:00:00Z")

    before = [f for f in feats if _parse_dt(f["properties"]["datetime"]) < split]
    after = [f for f in feats if _parse_dt(f["properties"]["datetime"]) >= split]

    def pack(lst):
        lst = sorted(lst, key=lambda f: f["properties"].get("tile:clouds_percent", 100))
        return [{
            "url": f["properties"]["visual"],
            "datetime": f["properties"]["datetime"],
            "clouds": f["properties"].get("tile:clouds_percent"),
            "gsd": f["properties"].get("gsd"),
            "quadkey": f["properties"].get("quadkey"),
        } for f in lst[:limit]]

    return {
        "event": event,
        "split_date": split.isoformat(),
        "before": pack(before),
        "after": pack(after),
        "counts": {"before": len(before), "after": len(after)},
    }
