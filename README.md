# Ubuntu Disaster Viewer

Visualiseur avant/après pour l'évaluation des dégâts post-catastrophe — **Geo Wakanda**.
*« Je suis parce que nous sommes » — évaluer la situation, ensemble.*

Ce dépôt unique (monorepo) contient **deux services** déployés séparément sur Railway
depuis le même code :

```
ubuntu-disaster-viewer/
├── backend/     API FastAPI + TiTiler + détection V2 + résolveur Vantor + veille GDACS/ReliefWeb
└── frontend/    Interface MapLibre (curseur avant/après, BD OSM, évaluation, export)
```

- **backend/** — sert les tuiles COG, résout automatiquement les COG avant/après d'un
  événement Vantor, détecte/calibre les dégâts (V2), et surveille les événements (GDACS + ReliefWeb).
- **frontend/** — l'interface web ; consomme l'API du backend.

## Déploiement sur Railway (un dépôt, deux services)

Railway déploie deux services depuis ce même dépôt grâce au réglage **Root Directory**.

### 1. Pousser le dépôt sur GitHub
Crée **un** dépôt (ex. `ubuntu-disaster-viewer`) et pousse tout le contenu (les dossiers
`backend/` et `frontend/` à la racine).

### 2. Service backend
1. Railway → **New Project → Deploy from GitHub repo** → choisis ce dépôt.
2. Le service créé → **Settings → Source → Root Directory** = `backend`
   (Railway build alors le `Dockerfile` de `backend/`).
3. **Settings → Networking → Generate Domain** → note l'URL, ex. `https://udv-backend-xxxx.up.railway.app`.
4. Vérifie : ouvre `…/api/health` et `…/docs`.

### 3. Service frontend (dans le même projet)
1. Dans le projet → **New → GitHub Repo** → **le même dépôt**.
2. Ce second service → **Settings → Source → Root Directory** = `frontend`.
3. **Generate Domain** → ouvre l'URL.
4. Dans l'appli : champ **Backend** → colle l'URL du backend (étape 2.3) → **Connecter**.

### 4. Test de bout en bout
- **🔔 Veille** → événements Cameroun / Afrique centrale (valide GDACS + ReliefWeb en réel).
- Événement Vantor → **Charger l'imagerie** → **Charger la BD OSM** → **Calibrer V2** → **Auto-détection V2** → **Exporter GeoJSON**.

## Variables d'environnement (optionnelles, sur le service backend)
`WATCH_COUNTRY` (défaut Cameroon) · `WATCH_REGION` (true = Afrique centrale) ·
`WATCH_INTERVAL_MIN` (défaut 30) · `WATCH_WEBHOOK` (Slack/Discord) · `WATCH_ENABLED` (false pour couper la veille).

## Notes
- Le **backend doit être déployé (domaine généré) avant** de connecter le frontend.
- Premier build backend un peu long (dépendances géospatiales `titiler`/`rasterio`).
- Détails techniques : voir `backend/README.md` et `frontend/README.md`.
- Imagerie Vantor : licence **CC BY-NC 4.0** (non commercial).
