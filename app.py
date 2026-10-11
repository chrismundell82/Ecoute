import json
import logging
import os
import threading

from flask import Flask, abort, jsonify, request, send_from_directory

app = Flask(__name__, static_folder="static", static_url_path="")
log = logging.getLogger("ecoute")

DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
DATA_DIR = os.environ.get("DATA_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "data"))
LISTS_FILE = os.path.join(DATA_DIR, "lists.json")
MAX_NAME = 100
MAX_TEXT = 200_000
_file_lock = threading.Lock()


# ---------- Saved word lists ----------
# Stored in Postgres when DATABASE_URL is set (survives redeploys), otherwise in a
# JSON file under DATA_DIR, which only survives redeploys if DATA_DIR is on a volume.

def _db():
    import psycopg
    return psycopg.connect(DATABASE_URL, connect_timeout=10)


def init_db():
    if not DATABASE_URL:
        return
    with _db() as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS word_lists (
                   name TEXT PRIMARY KEY,
                   body TEXT NOT NULL,
                   updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
               )"""
        )


def _read_file():
    try:
        with open(LISTS_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        return {}


def _write_file(data):
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = LISTS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, LISTS_FILE)


def get_lists():
    if DATABASE_URL:
        with _db() as conn:
            return {name: body for name, body in conn.execute("SELECT name, body FROM word_lists")}
    with _file_lock:
        return _read_file()


def save_list(name, body):
    if DATABASE_URL:
        with _db() as conn:
            conn.execute(
                """INSERT INTO word_lists (name, body) VALUES (%s, %s)
                   ON CONFLICT (name) DO UPDATE SET body = EXCLUDED.body, updated_at = now()""",
                (name, body),
            )
        return
    with _file_lock:
        data = _read_file()
        data[name] = body
        _write_file(data)


def delete_list(name):
    if DATABASE_URL:
        with _db() as conn:
            conn.execute("DELETE FROM word_lists WHERE name = %s", (name,))
        return
    with _file_lock:
        data = _read_file()
        if data.pop(name, None) is not None:
            _write_file(data)


def _list_name(name):
    name = (name or "").strip()
    if not name or len(name) > MAX_NAME:
        abort(400, "Bad list name")
    return name


@app.get("/api/lists")
def api_lists():
    return jsonify(lists=get_lists(), persistent=bool(DATABASE_URL))


@app.put("/api/lists/<path:name>")
def api_save_list(name):
    name = _list_name(name)
    body = (request.get_json(silent=True) or {}).get("text")
    if not isinstance(body, str) or not body.strip() or len(body) > MAX_TEXT:
        abort(400, "Bad list text")
    save_list(name, body)
    return jsonify(ok=True)


@app.delete("/api/lists/<path:name>")
def api_delete_list(name):
    delete_list(_list_name(name))
    return jsonify(ok=True)


# ---------- Alternative answers ----------
# Asks Claude for other English answers that should also count as correct
# (synonyms, US/UK spellings, contractions). Needs ANTHROPIC_API_KEY; without it
# the page falls back to its built-in contraction rules.

ALT_MODEL = os.environ.get("ALT_MODEL", "claude-opus-5-5")
ALT_BATCH = 80
ALT_PROMPT = """You help a French vocabulary listening app. A learner hears the French and types the English meaning.
For each numbered French = English pair below, list OTHER English answers that should also be marked correct:
true synonyms for this meaning, British/American spelling variants, contractions and their expanded forms
(e.g. "it's" -> "it is", "its"), and common everyday alternatives.
Only include answers a teacher would accept for this French word. Do not repeat answers already given,
do not add loose associations, and leave the list empty when there is nothing good to add.
Each answer should be short plain text with no slashes, commas or semicolons.

{pairs}"""
ALT_SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "n": {"type": "integer"},
                    "alternatives": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["n", "alternatives"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["items"],
    "additionalProperties": False,
}


def _alternatives_batch(client, pairs):
    numbered = "\n".join(f"{i}. {fr} = {en}" for i, (fr, en) in enumerate(pairs))
    response = client.beta.messages.create(
        model=ALT_MODEL,
        max_tokens=16000,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        output_config={"effort": "low", "format": {"type": "json_schema", "schema": ALT_SCHEMA}},
        messages=[{"role": "user", "content": ALT_PROMPT.format(pairs=numbered)}],
    )
    if response.stop_reason != "end_turn":
        log.warning("alternatives request stopped early: %s", response.stop_reason)
        return {}
    text = next((b.text for b in response.content if b.type == "text"), "")
    out = {}
    for item in json.loads(text).get("items", []):
        n = item.get("n")
        if isinstance(n, int) and 0 <= n < len(pairs):
            out[n] = [a for a in item.get("alternatives", []) if isinstance(a, str)]
    return out


@app.post("/api/alternatives")
def api_alternatives():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return jsonify(available=False, alternatives=[])
    words = (request.get_json(silent=True) or {}).get("words")
    if not isinstance(words, list) or len(words) > 1000:
        abort(400, "Bad word list")
    pairs = [(str(w[0])[:200], str(w[1])[:500]) for w in words if isinstance(w, list) and len(w) == 2]

    import anthropic
    client = anthropic.Anthropic()
    result = [[] for _ in pairs]
    try:
        for start in range(0, len(pairs), ALT_BATCH):
            for i, alts in _alternatives_batch(client, pairs[start:start + ALT_BATCH]).items():
                result[start + i] = alts
    except (anthropic.APIError, ValueError) as e:
        log.warning("alternatives lookup failed: %s", e)
        return jsonify(available=False, alternatives=[])
    return jsonify(available=True, alternatives=result)


# ---------- Pages ----------

@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.route("/sw.js")
def service_worker():
    resp = send_from_directory(app.static_folder, "sw.js")
    resp.headers["Cache-Control"] = "no-cache"
    resp.headers["Service-Worker-Allowed"] = "/"
    return resp


@app.route("/health")
def health():
    return {"status": "ok"}


try:
    init_db()
except Exception as e:  # keep the app up; list requests will report the error
    log.error("could not initialise the database: %s", e)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
