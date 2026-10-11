# Écoute – French listening practice

Hear a French word, type the English. Built-in topics plus your own saved word lists.

## Deploy on Railway
1. Push this folder to a new GitHub repo.
2. In Railway: New Project → Deploy from GitHub repo → pick the repo.
3. Settings → Networking → Generate Domain.

Railway picks up `requirements.txt` and starts it with the command in `railway.json`.

## Install on iPhone / iPad
Open the Railway URL in **Safari** → Share → **Add to Home Screen**.

## Updating
After changing `static/index.html`, bump `CACHE` in `static/sw.js` (e.g. `ecoute-v2`)
so installed copies fetch the new version.

## Run locally
    pip install -r requirements.txt
    python app.py
