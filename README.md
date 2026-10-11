# Écoute – French listening practice

Hear a French word, type the English. Built-in topics plus your own saved word lists.

## Deploy on Railway
1. Push this folder to a new GitHub repo.
2. In Railway: New Project → Deploy from GitHub repo → pick the repo.
3. Settings → Networking → Generate Domain.

Railway picks up `requirements.txt` and starts it with the command in `railway.json`.

### Sharing saved lists between devices
Saved word lists are stored on the server, so every device that opens the app sees them
(each device also keeps an offline copy and uploads changes made offline when it's back online).

- **Recommended:** in the Railway project add a **PostgreSQL** database, then in the app
  service's Variables add `DATABASE_URL` = `${{Postgres.DATABASE_URL}}`.
- Without `DATABASE_URL` the lists go in `data/lists.json` on the server, which is wiped on every
  redeploy unless you attach a Railway volume and set `DATA_DIR` to its mount path.

Anyone with the app's URL can see and edit the saved lists.

### Alternative answers
When a list is loaded from a file or pasted in, the app adds other answers that should also
count after the slashes, e.g. `c'est = it's / its / it is`. Contractions are always handled
(and "it's", "its" and "it is" are accepted for each other when answering). For synonyms and
spelling variants (`car / automobile`, `colour / color`), add an `ANTHROPIC_API_KEY` variable
on Railway; the app then asks Claude for them. `ALT_MODEL` overrides the model used.

## Install on iPhone / iPad
Open the Railway URL in **Safari** → Share → **Add to Home Screen**.

## Updating
After changing `static/index.html`, bump `CACHE` in `static/sw.js` (e.g. `ecoute-v2`)
so installed copies fetch the new version.

## Run locally
    pip install -r requirements.txt
    python app.py
