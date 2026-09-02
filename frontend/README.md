# Ubuntu Disaster Viewer — Frontend

Interface MapLibre du visualiseur avant/après de Geo Wakanda. **Service Railway indépendant**
(site statique). Il consomme l'API du backend.

## Ce qu'il fait
- Curseur **avant/après** entre deux imageries.
- Charge **toute la BD OSM exploitable de la zone** (via Overpass) : bâtiments, routes, eau, rail,
  réseau électrique, POI critiques (hôpitaux, écoles, points d'eau…), en couches activables.
- Évaluation multi-couches : bâtiments (intact / endommagé / détruit), routes (ouverte ↔ coupée),
  points d'infrastructure (ok ↔ affecté).
- **Auto-détection V2** : appelle `/api/detect` du backend pour pré-classer les bâtiments ; l'utilisateur valide.
- Rapport en direct (bâtiments détruits/endommagés, **routes coupées en km**, infrastructures affectées,
  population estimée, zone prioritaire) + export **GeoJSON** de toute la situation.

## Lancer en local
```bash
python -m http.server 8080     # http://localhost:8080
```

## Déployer sur Railway
1. Pousse **ce dossier** dans un dépôt GitHub (frontend seul).
2. Railway → **New Project → Deploy from GitHub repo**.
3. Railway détecte le `Dockerfile` (sert la page via `http.server` sur `$PORT`).
4. **Settings → Networking → Generate Domain** → ouvre l'URL.

## Connexion au backend
Au premier lancement, colle l'URL de ton **backend** Railway (`https://xxx.up.railway.app`)
dans le champ **Backend** puis « Connecter ». Elle est mémorisée dans le navigateur (localStorage).

## Utilisation
1. Zoome sur un quartier (niveau ≥ 14) → **Charger toute la BD OSM (zone)**.
2. Renseigne un **COG avant** et un **COG après** (assets Vantor `*-visual.tif`) → **Imagerie**.
3. **Auto-détection V2** pré-classe les bâtiments → clique bâtiments / routes / points pour valider et compléter.
4. Active/désactive les **couches** (bâtiments, routes, eau, rail, électricité, POI) selon le besoin.
5. **Exporter GeoJSON** de toute la situation évaluée (pour le rapport / QGIS).

> Sans backend ni COG, l'appli fonctionne en mode démo avec le fond satellite Esri (curseur + tagging manuel).
> Imagerie Vantor : licence CC BY-NC 4.0 (non commercial).

## Fichiers
`index.html` · `Dockerfile` · `railway.toml`
