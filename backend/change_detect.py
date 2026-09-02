"""
Ubuntu Disaster Viewer — moteur de detection de changement (V2.1, robuste)

Concu pour de VRAIES images satellite (Vantor), ou deux prises different par :
  - la luminosite / le contraste (heure, atmosphere)  -> normalisation radiometrique
  - un leger decalage geometrique (co-registration)   -> difference tolerante au shift
  - la vegetation (changement saisonnier)              -> masque de vegetation (ExG)

Score de changement 0..1 combinant : difference structurelle, chute de correlation,
variation de densite de contours (un toit detruit perd sa structure).

`calibrate()` ajuste automatiquement les seuils t1/t2 a partir de quelques batiments
tagues a la main (verite terrain) sur l'evenement reel : c'est le "calage".
La validation humaine reste dans la boucle.
"""
from typing import Optional
import numpy as np
from rio_tiler.io import Reader


# ---------- lecture & indices ----------
def _read(cog: str, feature: dict, max_size: int):
    with Reader(cog) as r:
        img = r.feature(feature, shape_crs="epsg:4326", max_size=max_size)
    return img.data.astype("float32"), np.asarray(img.mask).astype(bool)


def _gray(d):
    return 0.299 * d[0] + 0.587 * d[1] + 0.114 * d[2] if d.shape[0] >= 3 else d[0]


def _exg(d):  # excess green (vegetation)
    if d.shape[0] < 3:
        return np.zeros(d.shape[1:], dtype="float32")
    r, g, b = d[0], d[1], d[2]
    s = r + g + b + 1e-6
    return (2 * g - r - b) / s


def _grad(g):  # densite de contours locale
    gx = np.zeros_like(g); gy = np.zeros_like(g)
    gx[:, 1:] = np.abs(g[:, 1:] - g[:, :-1])
    gy[1:, :] = np.abs(g[1:, :] - g[:-1, :])
    return gx + gy


def _match(src, ref, mask):  # normalisation radiometrique (mean/std) de src vers ref
    s, r = src[mask], ref[mask]
    ss = s.std()
    if ss < 1e-6:
        return src - s.mean() + r.mean()
    return (src - s.mean()) / ss * r.std() + r.mean()


def _best_align(a, b, valid, maxshift=3):  # co-registration : meilleur decalage entier
    H, W = a.shape
    best = None
    for dy in range(-maxshift, maxshift + 1):
        for dx in range(-maxshift, maxshift + 1):
            h, w = H - abs(dy), W - abs(dx)
            if h < 3 or w < 3:
                continue
            ay, by = (dy if dy > 0 else 0), (-dy if dy < 0 else 0)
            ax, bx = (dx if dx > 0 else 0), (-dx if dx < 0 else 0)
            A = a[ay:ay + h, ax:ax + w]; B = b[by:by + h, bx:bx + w]
            V = valid[ay:ay + h, ax:ax + w] & valid[by:by + h, bx:bx + w]
            if V.sum() < 9:
                continue
            d = np.abs(A[V] - B[V]).mean()
            if best is None or d < best[0]:
                best = (d, A, B, V)
    return None if best is None else (best[1], best[2], best[3])


# ---------- score par batiment ----------
def building_score(before_cog, after_cog, feature, max_size=96,
                   veg_thresh=0.15, maxshift=2) -> Optional[float]:
    db, mb = _read(before_cog, feature, max_size)
    da, ma = _read(after_cog, feature, max_size)
    H = min(db.shape[1], da.shape[1]); W = min(db.shape[2], da.shape[2])
    if H < 3 or W < 3:
        return None
    db, da = db[:, :H, :W], da[:, :H, :W]
    mb, ma = mb[:H, :W], ma[:H, :W]

    gb, ga = _gray(db), _gray(da)
    veg = (_exg(db) > veg_thresh) | (_exg(da) > veg_thresh)
    valid = mb & ma & (~veg)
    if valid.sum() < 9:
        return None

    ga_n = _match(ga, gb, valid)                      # normalisation radiometrique
    aligned = _best_align(ga_n, gb, valid, maxshift)  # co-registration
    if aligned is None:
        return None
    A, B, V = aligned                                 # A=apres, B=avant, alignes

    struct = np.abs(A[V] - B[V]).mean() / 255.0

    x, y = B[V], A[V]
    corr = 1.0 if (x.std() < 1e-6 or y.std() < 1e-6) else float(np.corrcoef(x, y)[0, 1])
    corr_drop = (1.0 - max(min(corr, 1.0), -1.0)) / 2.0

    eb, ea = _grad(B)[V].mean(), _grad(A)[V].mean()
    edge = abs(ea - eb) / (eb + ea + 1e-6)

    score = 0.45 * struct + 0.45 * corr_drop + 0.10 * min(edge, 1.0)
    return float(max(0.0, min(1.0, score)))


def classify(score, t1=0.15, t2=0.35):
    if score is None:
        return "intact"
    if score >= t2:
        return "destroyed"
    if score >= t1:
        return "damaged"
    return "intact"


def _scores(before_cog, after_cog, buildings, max_size, veg_thresh, maxshift, cap):
    out = []
    for i, f in enumerate(buildings.get("features", [])[:cap]):
        try:
            s = building_score(before_cog, after_cog, f, max_size, veg_thresh, maxshift)
        except Exception:
            s = None
        out.append((i, f, s))
    return out


# ---------- API haut niveau ----------
def detect(before_cog, after_cog, buildings, t1=0.15, t2=0.35,
           max_buildings=300, max_size=96):
    feats = []
    for i, f, s in _scores(before_cog, after_cog, buildings, max_size, 0.15, 2, max_buildings):
        props = dict(f.get("properties", {}))
        props["change_score"] = round(s, 4) if s is not None else None
        props["damage"] = classify(s, t1, t2)
        feats.append({"type": "Feature", "id": f.get("id", i + 1),
                      "geometry": f["geometry"], "properties": props})
    return {"type": "FeatureCollection", "features": feats}


def calibrate(before_cog, after_cog, labeled_buildings, max_buildings=300, max_size=96):
    """Ajuste t1/t2 a partir de batiments tagues a la main (properties.damage).
    Recherche sur grille les seuils qui maximisent l'accord avec la verite terrain."""
    data = []
    for i, f, s in _scores(before_cog, after_cog, labeled_buildings, max_size, 0.15, 2, max_buildings):
        truth = (f.get("properties", {}) or {}).get("damage")
        if s is not None and truth in ("intact", "damaged", "destroyed"):
            data.append((s, truth))
    if len(data) < 3:
        return {"error": "Pas assez de batiments tagues (min 3).", "n": len(data)}

    # seuils candidats = points milieux entre scores tries (+ bornes)
    vals = sorted(set(s for s, _ in data))
    cands = [0.0] + [round((vals[i] + vals[i + 1]) / 2, 4) for i in range(len(vals) - 1)] + [1.0]
    best = None
    for t1 in cands:
        for t2 in cands:
            if t2 <= t1:
                continue
            acc = sum(1 for s, tr in data if classify(s, t1, t2) == tr) / len(data)
            if best is None or acc > best[2]:
                best = (round(t1, 4), round(t2, 4), acc)
    t1, t2, acc = best
    return {"t1": t1, "t2": t2, "accuracy": round(acc, 3), "n": len(data)}
