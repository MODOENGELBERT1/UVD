"""
Ubuntu Disaster Viewer — API (backend)
Geo Wakanda · visualiseur avant/apres + evaluation des degats

Endpoints :
  GET  /cog/tiles/{z}/{x}/{y}?url=<COG>   tuiles d'imagerie (TiTiler)
  GET  /api/events                        evenements du catalogue STAC Vantor
  POST /api/detect                        detection de changement (V2)
  GET  /api/health                        statut

Deploiement : service Railway independant (API seule). CORS ouvert pour le frontend.
"""
import os
import asyncio
import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from titiler.core.factory import TilerFactory
from titiler.core.errors import DEFAULT_STATUS_CODES, add_exception_handlers

from change_detect import detect, calibrate
from vantor import event_assets
import watch as watch

watch_store = watch.Store(os.getenv("WATCH_STORE", "watch_store.json"))

app = FastAPI(title="Ubuntu Disaster Viewer API", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Tuilage COG (TiTiler) ---
cog = TilerFactory(router_prefix="/cog")
app.include_router(cog.router, prefix="/cog", tags=["COG"])
add_exception_handlers(app, DEFAULT_STATUS_CODES)

STAC_EVENTS = os.getenv(
    "STAC_EVENTS",
    "https://maxar-opendata.s3.amazonaws.com/events/catalog.json",
)


class DetectBody(BaseModel):
    before_cog: str
    after_cog: str
    buildings: dict
    t1: float = 0.15
    t2: float = 0.35
    max_buildings: int = 300


class CalibrateBody(BaseModel):
    before_cog: str
    after_cog: str
    buildings: dict          # empreintes taguees a la main (properties.damage = verite terrain)
    max_buildings: int = 300


@app.get("/api/events", tags=["STAC"])
async def events():
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(STAC_EVENTS)
    if r.status_code != 200:
        raise HTTPException(status_code=502, detail="Catalogue STAC indisponible")
    catalog = r.json()
    return [
        {
            "id": link.get("href", "").rstrip("/").split("/")[-2] if "/" in link.get("href", "") else link.get("href"),
            "title": link.get("title", link.get("href")),
            "href": link.get("href"),
        }
        for link in catalog.get("links", [])
        if link.get("rel") == "child"
    ]


@app.post("/api/detect", tags=["Detection V2"])
def detect_damage(body: DetectBody):
    """Pre-classe les batiments (intact / endommage / detruit) par image differencing."""
    try:
        return detect(
            body.before_cog, body.after_cog, body.buildings,
            t1=body.t1, t2=body.t2, max_buildings=body.max_buildings,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur de detection : {e}")


@app.get("/api/event/assets", tags=["STAC"])
def event_assets_endpoint(event: str, bbox: str = None, event_date: str = None):
    """Retrouve les COG avant/apres d'un evenement Vantor pour une zone (bbox=minx,miny,maxx,maxy)."""
    bb = None
    if bbox:
        try:
            bb = tuple(float(x) for x in bbox.split(","))
            assert len(bb) == 4
        except Exception:
            raise HTTPException(status_code=400, detail="bbox invalide (attendu: minx,miny,maxx,maxy)")
    try:
        return event_assets(event, bbox=bb, event_date=event_date)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Resolveur indisponible : {e}")


@app.get("/api/watch", tags=["Veille"])
def watch_endpoint(country: str = "Cameroon", region: bool = False):
    """Veille : agrege GDACS + ReliefWeb pour lister les evenements (pays ou region)."""
    try:
        return watch.watch(country=country, region=region)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Veille indisponible : {e}")


@app.post("/api/calibrate", tags=["Detection V2"])
def calibrate_thresholds(body: CalibrateBody):
    """Calage : ajuste t1/t2 a partir de batiments tagues a la main sur l'evenement reel."""
    try:
        return calibrate(body.before_cog, body.after_cog, body.buildings,
                         max_buildings=body.max_buildings)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur de calibration : {e}")


@app.get("/api/watch/events", tags=["Veille"])
def watch_events(country: str = None, limit: int = 200):
    """Liste des evenements detectes (GDACS + ReliefWeb), filtres sur la region."""
    return watch_store.all(country=country, limit=limit)


@app.post("/api/watch/refresh", tags=["Veille"])
async def watch_refresh():
    """Declenche une interrogation immediate des flux d'alerte."""
    new = await asyncio.to_thread(watch.poll, watch_store)
    return {"new": len(new), "events": new}


@app.on_event("startup")
async def _start_watch():
    # Desactive par defaut : evite tout appel reseau au demarrage.
    # Passe WATCH_ENABLED=true pour activer la veille de fond une fois l'app stable.
    if os.getenv("WATCH_ENABLED", "false").lower() != "true":
        return
    interval = int(os.getenv("WATCH_INTERVAL_MIN", "30")) * 60

    async def loop():
        while True:
            try:
                await asyncio.to_thread(watch.poll, watch_store)
            except Exception as e:
                print("watch poll error:", e)
            await asyncio.sleep(interval)

    asyncio.create_task(loop())


@app.get("/", tags=["Systeme"])
def root():
    return {"service": "ubuntu-disaster-viewer", "status": "ok", "docs": "/docs"}


@app.get("/api/health", tags=["Systeme"])
def health():
    return {"status": "ok", "service": "ubuntu-disaster-viewer", "version": "0.2.0"}
