# Egg Predictor

This service stores snapshots supplied by an authorized Roblox-side collector and exposes historical, probabilistic estimates. It cannot discover Roblox remotes or predict a server schedule without data being sent to `/ingest`.

## Run

```powershell
cd egg_predictor
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
uvicorn api:app --reload
```

Run the Discord client in another terminal with the same environment:

```powershell
python bot.py
```

## Collector contract

Send `POST /ingest` with header `X-Collector-Key` and JSON such as:

```json
{
  "server_time": 1730000000,
  "next_reset_at": 1730000300,
  "cycle_seconds": 300,
  "eggs": [{"uid": "abc", "egg_type": "Legendary", "area": "Field"}]
}
```

The `/next` probabilities are historical observations, not guaranteed future spawns. Keep the collector key private and put the API behind HTTPS when deployed.