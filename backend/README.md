# Ubuntu Disaster Viewer — Backend (API)

API du visualiseur avant/après de Geo Wakanda. **Service Railway indépendant** (aucun frontend ici).

## Rôle
- Sert les tuiles d'imagerie COG (Vantor / drone) via **TiTiler**.
- **V2** : détecte automatiquement les dégâts par *image differencing* sur les empreintes OSM.
- Liste les événements du catalogue STAC Vantor.

## Endpoints
| Méthode | Route | Rôle |
|---|---|---|
| GET | `/cog/tiles/WebMercatorQuad/{z}/{x}/{y}.png?url=<COG>` | tuiles d'un COG |
| GET | `/cog/info?url=<COG>` | métadonnées d'un COG |
| GET | `/api/events` | liste des événements STAC Vantor (id + titre) |
| GET | `/api/event/assets?event=&bbox=` | **résout automatiquement les COG avant/après** d'un événement sur une zone |
| POST | `/api/detect` | détection de changement (V2) |
| GET | `/api/health` | statut |
| GET | `/api/watch/events?country=&limit=` | événements détectés (veille GDACS + ReliefWeb) |
| POST | `/api/watch/refresh` | interroge les flux d'alerte immédiatement |

### POST /api/detect
```json
{
  "before_cog": "https://…/pre-visual.tif",
  "after_cog":  "https://…/post-visual.tif",
  "buildings":  { "type":"FeatureCollection", "features":[ … ] },
  "t1": 0.10, "t2": 0.22
}
```
Retourne la FeatureCollection enrichie : `properties.change_score` (0..1) et `properties.damage`
(`intact` / `damaged` / `destroyed`). Seuils `t1`/`t2` ajustables.

## Lancer en local
```bash
pip install -r requirements.txt
uvicorn main:app --reload      # http://localhost:8000/docs
```

## Déployer sur Railway
1. Pousse **ce dossier** dans un dépôt GitHub (backend seul).
2. Railway → **New Project → Deploy from GitHub repo**.
3. Railway détecte le `Dockerfile` — aucune variable requise.
4. **Settings → Networking → Generate Domain** → note l'URL `https://xxx.up.railway.app`.
   C'est cette URL que tu renseignes dans le frontend.

Variables d'env (optionnelles) : `STAC_EVENTS` (catalogue STAC, défaut Vantor/Maxar).

## Notes
- La détection V2 lit chaque empreinte dans les deux COG → fournis **un COG avant ET un COG après**
  (Vantor publie l'imagerie pré- et post-événement).
- Approche explicable (différence de luminance) ; la validation humaine reste dans la boucle.
  Un modèle type xView2 / fAIr pourra remplacer `building_score()` sans changer l'API.
- Imagerie Vantor : licence **CC BY-NC 4.0** (non commercial).

## Fichiers
`main.py` (API) · `change_detect.py` (moteur V2) · `requirements.txt` · `Dockerfile` · `railway.toml`

## Veille automatique (worker)

Le backend interroge en tâche de fond des flux publics d'alerte catastrophe, filtre sur la région,
dédoublonne et stocke les événements — pour que l'appli liste **tous** les événements, pas seulement
ceux que Vantor a activés.

- **Sources** : GDACS (sans clé) + ReliefWeb (OCHA). Défensif : si une source échoue, l'autre continue.
- **Boucle** : au démarrage, un poll tourne toutes les `WATCH_INTERVAL_MIN` minutes.
- **Manuel** : `POST /api/watch/refresh` déclenche un poll immédiat.

### Variables d'environnement
| Variable | Défaut | Rôle |
|---|---|---|
| `WATCH_ENABLED` | `true` | active la boucle de veille |
| `WATCH_INTERVAL_MIN` | `30` | fréquence du poll (min) |
| `WATCH_COUNTRIES` | Cameroun + voisins | pays/région ciblés (sous-chaînes, séparées par des virgules) |
| `WATCH_STORE` | `watch_store.json` | fichier de stockage des événements |
| `GDACS_URL`, `RELIEFWEB_URL` | flux publics | surchargeables |

### Persistance sur Railway
Le stockage est un fichier JSON. Pour qu'il **survive aux redéploiements**, attache un **Volume Railway**
(ex. monté sur `/data`) et mets `WATCH_STORE=/data/watch_store.json`. Sinon, la liste se reconstruit au
prochain poll (les flux ne gardent que les événements récents).

### Alternative cron
Au lieu de la boucle intégrée (`WATCH_ENABLED=false`), tu peux créer un **service cron Railway** qui
appelle `POST /api/watch/refresh` selon un planning — même résultat, séparation web/worker.

### Limite honnête
Savoir qu'un événement existe (facile) ≠ avoir une image VHR pour l'évaluer. Pour les petits événements
locaux non couverts par Vantor, tu auras l'événement + l'exposition OSM + (au mieux) l'étendue Sentinel,
mais pas toujours le détail bâtiment — sauf imagerie drone/autre fournie manuellement.

## Fichiers
`main.py` · `change_detect.py` (V2) · `vantor.py` (résolveur) · `watch.py` (veille) · `requirements.txt` · `Dockerfile` · `railway.toml`

## Veille automatique (GDACS + ReliefWeb)
Le backend interroge périodiquement GDACS (flux mondial sans clé) et ReliefWeb (OCHA, par pays)
pour lister **tous** les événements — pas seulement ceux activés par Vantor.

- En tâche de fond : un loop au démarrage (variables `WATCH_ENABLED`, `WATCH_INTERVAL_MIN`, `WATCH_COUNTRY`, `WATCH_REGION`).
- En cron Railway (alternative) : service dédié, `startCommand = "python worker.py"`, schedule `*/15 * * * *`.
  Variables : `WATCH_COUNTRY`, `WATCH_REGION` ("true" = Afrique centrale), `WATCH_WEBHOOK` (Slack/Discord, optionnel).

> Sources configurables via `GDACS_URL`, `RELIEFWEB_URL`. Chaque événement porte un `bbox` :
> savoir qu'un événement existe ≠ disposer d'une image VHR. Pour les petits événements, l'imagerie
> Vantor peut manquer — on retombe alors sur Sentinel (étendue) ou une image manuelle (drone/autre).
