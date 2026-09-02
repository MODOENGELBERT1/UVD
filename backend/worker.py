"""
Ubuntu Disaster Viewer — worker de veille (a lancer en cron Railway)

Interroge GDACS + ReliefWeb, agrege les evenements du pays/region, et
(optionnel) envoie une notification a un webhook (Slack/Discord/...).

Variables d'environnement :
  WATCH_COUNTRY   pays cible (defaut: Cameroon)
  WATCH_REGION    "true" pour elargir a l'Afrique centrale (defaut: false)
  WATCH_WEBHOOK   URL de webhook pour notifier les nouveaux evenements (optionnel)

Cron Railway (ex. toutes les 15 min) :
  service dedie, memes fichiers, startCommand = "python worker.py",
  schedule = "*/15 * * * *"
"""
import os
import httpx
from watch import watch


def main():
    country = os.getenv("WATCH_COUNTRY", "Cameroon")
    region = os.getenv("WATCH_REGION", "false").lower() == "true"
    res = watch(country=country, region=region)
    events = res.get("events", [])
    print(f"[veille] {len(events)} evenement(s) | sources {res.get('counts')} | scope {res.get('scope')}")
    if res.get("errors"):
        print("[veille] erreurs:", res["errors"])
    for e in events[:10]:
        print(f"  - {e.get('date','?')} | {e.get('type','?')} | {e.get('title','?')} "
              f"[{e.get('level','?')}] ({'/'.join(e.get('sources', []))})")

    hook = os.getenv("WATCH_WEBHOOK")
    if hook and events:
        try:
            httpx.post(hook, json={
                "text": f"🔔 Ubuntu Disaster Viewer — {len(events)} événement(s) suivi(s) ({country})",
                "events": events[:10],
            }, timeout=20)
            print("[veille] notification webhook envoyee")
        except Exception as ex:
            print("[veille] echec webhook:", ex)


if __name__ == "__main__":
    main()
